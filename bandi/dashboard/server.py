"""
FastAPI Server and REST API for BANDI Dashboard.
Provides high-performance, low-memory HTTP endpoints, serves static UI assets,
and coordinates EA telemetry, order queues, decisions, and risk management.
"""

from __future__ import annotations
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from bandi.config import settings
from bandi.database.db import db
from bandi.calendar.client import calendar_client
from bandi.telegram.bot import telegram_notifier
from bandi.research.fundamental_engine import fundamental_calculator
from bandi.research.macro import fundamental_engine
from bandi.research.currency_strength import calculate_currency_strength
from bandi.research.watchlist import WATCHLIST_SYMBOLS, get_standard_symbol_info
from bandi.mt5.bridge import mt5_bridge
from bandi.mt5.risk import risk_manager
from bandi.mt5.compiler import mql5_compiler
from bandi.engine.decision import decision_engine

logger = logging.getLogger("bandi.dashboard")

app = FastAPI(
    title="BANDI - Trading Intelligence Platform",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url=None
)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -----------------------------------------------------------------------------
# Request Schemas
# -----------------------------------------------------------------------------
class TelemetryPayload(BaseModel):
    symbol: Optional[str] = "EURUSD"
    bid: Optional[float] = 0.0
    ask: Optional[float] = 0.0
    spread: Optional[float] = 0.0
    balance: Optional[float] = 0.0
    equity: Optional[float] = 0.0
    account: Optional[int] = 0
    broker: Optional[str] = "MetaTrader 5"
    trade_mode: Optional[str] = "DEMO"
    positions: Optional[List[Dict[str, Any]]] = None


class OrderResultPayload(BaseModel):
    order_id: str
    success: bool
    ticket: Optional[int] = 0
    message: Optional[str] = ""
    symbol: Optional[str] = ""


class KillSwitchPayload(BaseModel):
    active: bool


class TradingModePayload(BaseModel):
    mode: str  # OFF | SIGNALS_ONLY | APPROVAL | AUTO
    confirmed: Optional[bool] = False


class CandleItem(BaseModel):
    symbol: str
    timeframe: str
    candle_ts: int
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0.0


class CandleBatchPayload(BaseModel):
    candles: List[CandleItem]


# -----------------------------------------------------------------------------
# Root UI Route
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h2>BANDI Dashboard UI initializing...</h2>", status_code=200)
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


# -----------------------------------------------------------------------------
# Core System & Status Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/status")
async def get_system_status():
    """Retrieve full system health, trading mode, lock state, kill switch, and component statuses."""
    now_utc = settings.now_utc()
    now_sast = settings.now_sast()
    tg_check = telegram_notifier.test_connection()
    mt5_stat = mt5_bridge.get_status()

    return {
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "time_utc": now_utc.isoformat(),
        "time_sast": now_sast.strftime("%Y-%m-%d %H:%M:%S SAST"),
        "timezone": settings.DISPLAY_TIMEZONE_NAME,
        "trading_mode": settings.TRADING_MODE,
        "trading_locked": settings.RISK_TRADING_LOCKED,
        "kill_switch_active": settings.is_kill_switch_active(),
        "live_trading_confirmed": settings.LIVE_TRADING_CONFIRMED,
        "telegram": {
            "enabled": settings.TELEGRAM_ENABLED,
            "connected": tg_check.get("ok", False),
            "username": tg_check.get("username", "Unconfigured"),
            "chat_id": settings.TELEGRAM_CHAT_ID[:4] + "***" if settings.TELEGRAM_CHAT_ID else "None"
        },
        "mt5": mt5_stat,
        "risk": risk_manager.get_status()
    }


@app.post("/api/kill-switch")
async def toggle_kill_switch(payload: KillSwitchPayload):
    """Emergency kill switch toggle."""
    settings.set_kill_switch(payload.active)
    action_str = "ACTIVATED" if payload.active else "DEACTIVATED"
    db.log("WARNING" if payload.active else "INFO", "KILL_SWITCH", f"Emergency kill switch {action_str} via dashboard.")
    return {"status": "ok", "kill_switch_active": settings.is_kill_switch_active()}


@app.post("/api/trading-mode")
async def set_trading_mode(payload: TradingModePayload):
    """Update execution mode (OFF, SIGNALS_ONLY, APPROVAL, AUTO)."""
    mode = payload.mode.upper().strip()
    if mode not in ("OFF", "SIGNALS_ONLY", "APPROVAL", "AUTO"):
        raise HTTPException(status_code=400, detail="Invalid trading mode.")

    # Guard live accounts from entering AUTO without explicit confirmation
    if mode == "AUTO" and not settings.MT5_DEMO_MODE and not payload.confirmed:
        raise HTTPException(status_code=403, detail="Live trading confirmation required to switch to AUTO.")

    settings.TRADING_MODE = mode
    db.log("INFO", "CONFIG", f"Trading mode updated to {mode}")
    return {"status": "ok", "trading_mode": settings.TRADING_MODE}


# -----------------------------------------------------------------------------
# MT5 Integration & Execution Endpoints
# -----------------------------------------------------------------------------
@app.post("/api/mt5/sync")
async def ingest_mt5_telemetry(payload: TelemetryPayload):
    """Telemetry sync endpoint called by Bandi.mq5 every few seconds."""
    res = mt5_bridge.ingest_telemetry(payload.model_dump())
    return res


@app.get("/api/mt5/orders/pending")
async def get_pending_orders():
    """Retrieve pending orders for the MT5 EA to execute."""
    orders = mt5_bridge.get_pending_orders()
    return {"orders": orders}


@app.post("/api/mt5/orders/result")
async def report_order_result(payload: OrderResultPayload):
    """Report execution outcome from MT5 EA back to the server."""
    mt5_bridge.record_order_result(payload.model_dump())
    status = "FILLED" if payload.success else "REJECTED"
    db.update_order_status(
        order_id=payload.order_id,
        status=status,
        ticket=payload.ticket if payload.success else None,
        error=payload.message if not payload.success else None
    )
    if payload.success:
        telegram_notifier.send_order_notice(
            {"direction": "EXECUTION", "symbol": payload.symbol or "MT5", "volume": 0.01, "sl": "Verified", "tp": "Verified"},
            ticket=payload.ticket or 0
        )
    return {"status": "ok"}


@app.post("/api/mt5/candles")
async def ingest_candles(payload: CandleBatchPayload):
    """Accept streamed historical or real-time candles from MT5 EA."""
    candles_data = [c.model_dump() for c in payload.candles]
    count = db.upsert_candles(candles_data)
    return {"status": "ok", "inserted": count}


@app.post("/api/mt5/compile")
async def compile_bandi_ea():
    """Deploy and compile Bandi.mq5 across detected MetaTrader 5 installations."""
    res = mql5_compiler.compile_ea()
    return res


# -----------------------------------------------------------------------------
# Signals & Decisions Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/signals")
async def get_signals():
    """Retrieve active trade signals."""
    active = db.get_active_signals()
    return {"count": len(active), "signals": active}


@app.post("/api/signals/{signal_id}/approve")
async def approve_signal(signal_id: str):
    """Manual dashboard approval for a pending signal."""
    sig = db.get_signal(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found.")

    if int(time.time()) > sig["expiry_ts"]:
        raise HTTPException(status_code=400, detail="Signal has expired.")

    db.update_signal_status(signal_id, "APPROVED")
    ord_id = mt5_bridge.queue_order({
        "signal_id": signal_id,
        "symbol": sig["symbol"],
        "direction": sig["direction"],
        "volume": settings.MAX_LOT,
        "entry_price": sig["entry_price"],
        "sl": sig["sl"],
        "tp": sig["tp"]
    })
    db.save_order({
        "order_id": ord_id,
        "signal_id": signal_id,
        "symbol": sig["symbol"],
        "direction": sig["direction"],
        "volume": settings.MAX_LOT,
        "entry_price": sig["entry_price"],
        "sl": sig["sl"],
        "tp": sig["tp"],
        "status": "PENDING"
    })
    return {"status": "approved", "order_id": ord_id}


@app.post("/api/signals/{signal_id}/skip")
async def skip_signal(signal_id: str):
    """Manual dashboard skip for a pending signal."""
    db.update_signal_status(signal_id, "SKIPPED")
    return {"status": "skipped"}


@app.get("/api/decisions")
async def get_decisions(limit: int = 50):
    """Retrieve audit history of trade decisions (TRADE, WATCH, SKIP)."""
    decisions = db.get_recent_decisions(limit=limit)
    return {"count": len(decisions), "decisions": decisions}


@app.get("/api/performance")
async def get_performance():
    """Retrieve system trading performance statistics."""
    perf = db.get_performance_metrics()
    return perf


# -----------------------------------------------------------------------------
# Economic Calendar & Research Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/calendar/events")
async def get_calendar_events(impact: Optional[str] = None, limit: int = 50):
    now_ts = int(time.time())
    events = db.get_upcoming_events(
        from_ts=now_ts - 43200,
        to_ts=now_ts + (settings.CALENDAR_RANGE_DAYS * 86400),
        high_impact_only=(impact == "high")
    )
    for ev in events:
        ev["release_time_sast"] = settings.ts_to_sast_str(ev["event_ts"])
        ev["seconds_remaining"] = ev["event_ts"] - now_ts
        ev["minutes_remaining"] = round((ev["event_ts"] - now_ts) / 60.0, 1)

    return {"count": len(events), "events": events[:limit]}


@app.get("/api/calendar/next")
async def get_next_high_impact_event():
    now_ts = int(time.time())
    events = db.get_upcoming_events(
        from_ts=now_ts,
        to_ts=now_ts + (settings.CALENDAR_RANGE_DAYS * 86400),
        high_impact_only=True
    )
    if not events:
        return {"has_event": False, "event": None, "seconds_remaining": 0}

    next_ev = events[0]
    seconds_rem = next_ev["event_ts"] - now_ts
    next_ev["release_time_sast"] = settings.ts_to_sast_str(next_ev["event_ts"])
    next_ev["seconds_remaining"] = seconds_rem
    next_ev["minutes_remaining"] = round(seconds_rem / 60.0, 1)

    return {"has_event": True, "event": next_ev, "seconds_remaining": seconds_rem}


@app.post("/api/calendar/sync")
async def sync_calendar():
    res = calendar_client.fetch_and_sync(force=True)
    return res


@app.get("/api/notifications")
async def get_notifications(limit: int = 50):
    history = db.get_notification_history(limit=limit)
    for n in history:
        n["sent_time_sast"] = settings.ts_to_sast_str(n["sent_ts"])
    return {"count": len(history), "notifications": history}


@app.post("/api/telegram/test")
async def send_telegram_test():
    res = telegram_notifier.send_test_alert()
    return res


@app.get("/api/research/overview")
async def get_research_overview():
    biases = fundamental_calculator.update_all_biases()
    snapshots = db.get_latest_market_snapshots()
    snapshot_map = {s["symbol"]: s for s in snapshots}
    strength = calculate_currency_strength(snapshot_map)
    macro = fundamental_engine.get_full_market_overview()
    return {
        "macro": macro,
        "fundamental_biases": biases,
        "currency_strength": strength
    }


@app.get("/api/watchlist")
async def get_watchlist():
    snapshots = db.get_latest_market_snapshots()
    snapshot_dict = {s["symbol"]: s for s in snapshots}
    biases = {b["symbol"]: b for b in db.get_fundamental_biases()}

    items = []
    for sym in WATCHLIST_SYMBOLS:
        info = get_standard_symbol_info(sym)
        snap = snapshot_dict.get(sym) or {}
        bias = biases.get(sym) or {}
        items.append({
            "symbol": sym,
            "name": info.get("name", sym),
            "asset_class": info.get("asset_class", "Forex"),
            "bid": snap.get("bid", 0.0),
            "ask": snap.get("ask", 0.0),
            "spread_points": snap.get("spread_points", 0.0),
            "bias_label": bias.get("bias_label", "NEUTRAL"),
            "bias_value": bias.get("bias_value", 0.0),
            "source": snap.get("source", "Market Watch"),
            "updated_at": snap.get("snapshot_time_utc", "Awaiting ticks")
        })

    return {"symbols": items}


@app.get("/api/logs")
async def get_system_logs(limit: int = 100):
    logs = db.get_logs(limit=limit)
    return {"count": len(logs), "logs": logs}
