"""
MetaTrader 5 Bridge and Quote Ingestion for BANDI.
Coordinates communication between the local MetaTrader 5 terminal,
Bandi.mq5 Expert Advisor, and SQLite storage.
Handles connection state, account info, and broker symbol quotes safely.
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
            "currency": "USD",
            "last_seen_utc": None
        }
        self._symbol_quotes: Dict[str, Dict[str, Any]] = {}
        self._discovered_symbols: List[str] = list(WATCHLIST_SYMBOLS)

    def is_connected(self) -> bool:
        """Check if terminal telemetry was received within the last 30 seconds."""
        return (time.time() - self._last_heartbeat_ts) < 30.0

    def ingest_telemetry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process live incoming telemetry from Bandi.mq5 or terminal IPC.
        Records bid, ask, spread into SQLite market snapshots.
        """
        now = time.time()
        now_utc = datetime.now(timezone.utc).isoformat()
        self._last_heartbeat_ts = now

        # Update account info
        account_id = payload.get("account", 0)
        broker = payload.get("broker", "JustMarkets")
        balance = float(payload.get("balance", 0.0))
        equity = float(payload.get("equity", 0.0))

        self._account_info = {
            "connected": True,
            "login": account_id,
            "broker": broker,
            "balance": balance,
            "equity": equity,
            "last_seen_utc": now_utc
        }

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

        return {
            "status": "ok",
            "server_time_utc": now_utc,
            "account_connected": True
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
            "discovered_symbols": self._discovered_symbols,
            "trading_locked": True,
            "message": "Connected to MT5 terminal" if connected else "Waiting for MT5 / Bandi EA telemetry"
        }


# Global bridge instance
mt5_bridge = MT5Bridge()
