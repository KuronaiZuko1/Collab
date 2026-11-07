"""
FastAPI Server and REST API for BANDI Dashboard.
Provides high-performance, low-memory HTTP endpoints and serves static UI assets.
"""

from __future__ import annotations
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from bandi.config import settings
from bandi.database.db import db
from bandi.calendar.client import calendar_client
from bandi.telegram.bot import telegram_notifier
from bandi.research.macro import fundamental_engine
from bandi.research.currency_strength import calculate_currency_strength
from bandi.research.watchlist import WATCHLIST_SYMBOLS, get_standard_symbol_info
from bandi.mt5.bridge import mt5_bridge
from bandi.mt5.risk import risk_manager
from bandi.mt5.compiler import mql5_compiler

logger = logging.getLogger("bandi.dashboard")

app = FastAPI(
    title="BANDI - Trading Intelligence Platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None
)

# Static files directory
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


class JournalPayload(BaseModel):
    symbol: str
    action: str
    volume: float = 0.01
    price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    pnl: float = 0.0
    strategy_reason: str = ""
    economic_context: str = ""
    risk_assessment: str = ""


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
# API Routes
# -----------------------------------------------------------------------------
@app.get("/api/status")
async def get_system_status():
    """Retrieve full system health, timezone info, and component statuses."""
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
        "telegram": {
            "enabled": settings.TELEGRAM_ENABLED,
            "connected": tg_check.get("ok", False),
            "username": tg_check.get("username", "Unconfigured"),
            "chat_id": settings.TELEGRAM_CHAT_ID[:4] + "***" if settings.TELEGRAM_CHAT_ID else "None",
            "details": tg_check
        },
        "mt5": mt5_stat,
        "risk": risk_manager.get_status()
    }


@app.get("/api/calendar/events")
async def get_calendar_events(impact: Optional[str] = None, limit: int = 50):
    """Retrieve scheduled economic events."""
    now_ts = int(time.time())
    # Retrieve past 12h to next 7 days
    events = db.get_upcoming_events(
        from_ts=now_ts - 43200,
        to_ts=now_ts + (settings.CALENDAR_RANGE_DAYS * 86400),
        high_impact_only=(impact == "high")
    )
    # Add human readable SAST time and time remaining
    for ev in events:
        ev["release_time_sast"] = settings.ts_to_sast_str(ev["event_ts"])
        ev["seconds_remaining"] = ev["event_ts"] - now_ts
        ev["minutes_remaining"] = round((ev["event_ts"] - now_ts) / 60.0, 1)

    return {"count": len(events), "events": events[:limit]}


@app.get("/api/calendar/next")
async def get_next_high_impact_event():
    """Return the very next scheduled high-impact release and exact seconds countdown."""
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
    """Trigger on-demand economic calendar sync."""
    res = calendar_client.fetch_and_sync(force=True)
    return res


@app.get("/api/notifications")
async def get_notifications(limit: int = 50):
    """Retrieve history of dispatched alerts."""
    history = db.get_notification_history(limit=limit)
    for n in history:
        n["sent_time_sast"] = settings.ts_to_sast_str(n["sent_ts"])
    return {"count": len(history), "notifications": history}


@app.post("/api/telegram/test")
async def send_telegram_test():
    """Trigger a live test alert to the configured Telegram chat."""
    res = telegram_notifier.send_test_alert()
    return res


@app.get("/api/research/overview")
async def get_research_overview():
    """Retrieve multi-asset fundamental research and currency strength ratings."""
    macro = fundamental_engine.get_full_market_overview()
    snapshots = db.get_latest_market_snapshots()
    snapshot_map = {s["symbol"]: s for s in snapshots}
    strength = calculate_currency_strength(snapshot_map)
    return {"macro": macro, "currency_strength": strength}


@app.get("/api/watchlist")
async def get_watchlist():
    """Retrieve prices and specs for all 12 core watchlist instruments."""
    snapshots = db.get_latest_market_snapshots()
    snapshot_dict = {s["symbol"]: s for s in snapshots}

    items = []
    for sym in WATCHLIST_SYMBOLS:
        info = get_standard_symbol_info(sym)
        snap = snapshot_dict.get(sym) or {}
        items.append({
            "symbol": sym,
            "name": info.get("name", sym),
            "asset_class": info.get("asset_class", "Forex"),
            "bid": snap.get("bid", 0.0),
            "ask": snap.get("ask", 0.0),
            "spread_points": snap.get("spread_points", 0.0),
            "source": snap.get("source", "Market Watch"),
            "updated_at": snap.get("snapshot_time_utc", "Awaiting ticks")
        })

    return {"symbols": items}


@app.post("/api/mt5/sync")
async def ingest_mt5_telemetry(payload: TelemetryPayload):
    """Receive live broker ticks and account telemetry from Bandi.mq5."""
    res = mt5_bridge.ingest_telemetry(payload.model_dump())
    return res


@app.post("/api/mt5/compile")
async def compile_bandi_ea():
    """Deploy and compile Bandi.mq5 across detected MetaTrader 5 installations."""
    res = mql5_compiler.compile_ea()
    return res


@app.get("/api/logs")
async def get_system_logs(limit: int = 100):
    """Retrieve audit trail of system events."""
    logs = db.get_logs(limit=limit)
    return {"count": len(logs), "logs": logs}


@app.get("/api/journal")
async def get_journal():
    """Retrieve trading journal records."""
    entries = db.get_journal_entries(limit=50)
    return {"count": len(entries), "journal": entries}


@app.post("/api/journal")
async def create_journal_entry(entry: JournalPayload):
    """Record a trade hypothesis or observation in the trading journal."""
    record_id = db.add_journal_entry(
        symbol=entry.symbol,
        action=entry.action,
        volume=entry.volume,
        price=entry.price,
        sl=entry.sl,
        tp=entry.tp,
        pnl=entry.pnl,
        strategy_reason=entry.strategy_reason,
        economic_context=entry.economic_context,
        risk_assessment=entry.risk_assessment
    )
    return {"status": "ok", "entry_id": record_id}
