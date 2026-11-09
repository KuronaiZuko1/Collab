"""
MetaTrader 5 Bridge and Quote Ingestion for BANDI.
Coordinates communication between the local MetaTrader 5 terminal,
Bandi.mq5 Expert Advisor, and SQLite storage.
Handles connection state, account info, broker symbol quotes, and order queues.
"""

from __future__ import annotations
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from bandi.config import settings
from bandi.database.db import db
from bandi.research.watchlist import WATCHLIST_SYMBOLS, resolve_broker_symbol

logger = logging.getLogger("bandi.mt5")


class MT5Bridge:
    def __init__(self):
        self._last_heartbeat_ts: float = 0.0
        self._account_info: Dict[str, Any] = {
            "connected": False,
            "login": 0,
            "broker": "None",
            "balance": 0.0,
            "equity": 0.0,
            "margin_free": 0.0,
            "trade_mode": "DEMO",
            "last_seen_utc": None
        }
        self._symbol_quotes: Dict[str, Dict[str, Any]] = {}
        self._discovered_symbols: List[str] = list(WATCHLIST_SYMBOLS)
        self._open_positions: List[Dict[str, Any]] = []
        self._pending_orders: List[Dict[str, Any]] = []
        self._order_results: List[Dict[str, Any]] = []

    def is_connected(self) -> bool:
        """Check if terminal telemetry was received within the last 30 seconds."""
        return (time.time() - self._last_heartbeat_ts) < 30.0

    def get_telemetry_age(self) -> float:
        """Return elapsed seconds since last telemetry received."""
        if self._last_heartbeat_ts == 0.0:
            return 999999.0
        return max(0.0, time.time() - self._last_heartbeat_ts)

    def queue_order(self, order: Dict[str, Any]) -> str:
        """Queue an approved order for the EA to execute."""
        order_id = order.get("order_id") or f"ord_{int(time.time()*1000)}"
        order["order_id"] = order_id
        order["created_at_utc"] = datetime.now(timezone.utc).isoformat()
        order["status"] = "pending"
        self._pending_orders.append(order)
        logger.info("Queued order for EA execution: %s", order)
        return order_id

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Retrieve and clear pending orders for the EA."""
        orders = list(self._pending_orders)
        self._pending_orders.clear()
        return orders

    def record_order_result(self, result: Dict[str, Any]) -> None:
        """Record order execution result reported back from EA."""
        result["received_at_utc"] = datetime.now(timezone.utc).isoformat()
        self._order_results.append(result)
        logger.info("Recorded order result from EA: %s", result)

    def ingest_telemetry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process live incoming telemetry from Bandi.mq5 or terminal IPC.
        Records bid, ask, spread into SQLite market snapshots.
        Returns live trading mode, lock state, and next economic event to the EA.
        """
        now = time.time()
        now_utc = datetime.now(timezone.utc).isoformat()
        self._last_heartbeat_ts = now

        # Update account info
        account_id = payload.get("account", 0)
        broker = payload.get("broker", "MetaTrader 5")
        balance = float(payload.get("balance", 0.0))
        equity = float(payload.get("equity", 0.0))
        trade_mode_val = payload.get("trade_mode", "DEMO")
        # Format string mode (0=Demo, 1=Contest, 2=Real in MT5)
        if str(trade_mode_val) in ("2", "REAL", "Real"):
            trade_mode_str = "REAL"
        elif str(trade_mode_val) in ("1", "CONTEST"):
            trade_mode_str = "CONTEST"
        else:
            trade_mode_str = "DEMO"

        self._account_info = {
            "connected": True,
            "login": account_id,
            "broker": broker,
            "balance": balance,
            "equity": equity,
            "trade_mode": trade_mode_str,
            "last_seen_utc": now_utc
        }

        # Update positions if provided
        positions = payload.get("positions")
        if isinstance(positions, list):
            self._open_positions = positions

        # Update quote info
        symbol = str(payload.get("symbol", "")).strip().upper()
        bid = float(payload.get("bid", 0.0))
        ask = float(payload.get("ask", 0.0))
        spread = float(payload.get("spread", 0.0))

        if symbol and (bid > 0 or ask > 0):
            if symbol not in self._discovered_symbols:
                self._discovered_symbols.append(symbol)

            self._symbol_quotes[symbol] = {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "spread_points": spread,
                "timestamp_utc": now_utc
            }

            # Record to persistent SQLite snapshot
            db.record_market_snapshot(symbol=symbol, bid=bid, ask=ask, spread=spread, source="MT5_Bridge")

        # Get next high-impact release from DB for EA on-chart monitor
        next_event_data = {"title": "No tier-1 release scheduled", "time_sast": "30m Alert Guard Active", "seconds": 0}
        try:
            upcoming = db.get_upcoming_events(from_ts=int(now), to_ts=int(now + 604800), high_impact_only=True)
            if upcoming:
                ev = upcoming[0]
                sast_str = settings.ts_to_sast_str(ev["event_ts"])
                secs = max(0, ev["event_ts"] - int(now))
                next_event_data = {
                    "title": f"{ev['title']} ({ev['currency']})",
                    "time_sast": sast_str,
                    "seconds": secs
                }
        except Exception:
            pass

        # Return real execution mode and safety state to the EA
        return {
            "status": "ok",
            "server_time_utc": now_utc,
            "account_connected": True,
            "trading_mode": settings.TRADING_MODE,
            "trading_locked": settings.RISK_TRADING_LOCKED,
            "kill_switch_active": settings.is_kill_switch_active(),
            "next_event": next_event_data,
            "pending_orders": self.get_pending_orders()
        }

    def get_status(self) -> Dict[str, Any]:
        """Return comprehensive MT5 bridge health and quotes."""
        connected = self.is_connected()
        return {
            "connected": connected,
            "terminal_path": settings.MT5_TERMINAL_PATH,
            "account": self._account_info if connected else None,
            "quotes_count": len(self._symbol_quotes),
            "quotes": self._symbol_quotes,
            "open_positions": self._open_positions,
            "open_positions_count": len(self._open_positions),
            "discovered_symbols": self._discovered_symbols,
            "trading_mode": settings.TRADING_MODE,
            "trading_locked": settings.RISK_TRADING_LOCKED,
            "kill_switch_active": settings.is_kill_switch_active(),
            "message": "Connected to MT5 terminal" if connected else "Waiting for MT5 / Bandi EA telemetry"
        }


# Global bridge instance
mt5_bridge = MT5Bridge()
