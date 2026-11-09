"""
Database operations for BANDI.
Provides connection pooling, WAL mode initialization, versioned migrations,
candle persistence, decision logs, signals, and order management.
"""

from __future__ import annotations
import sqlite3
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
from bandi.config import settings
from bandi.database.schema import CREATE_TABLES_SQL, SCHEMA_VERSION

logger = logging.getLogger("bandi.database")


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create and configure a SQLite connection."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=15.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # Performance and integrity optimizations for low-end hardware
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        """Initialise or migrate database schema without breaking existing data."""
        with self.get_connection() as conn:
            conn.executescript(CREATE_TABLES_SQL)
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM schema_version WHERE version = ?", (SCHEMA_VERSION,))
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    "INSERT INTO schema_version (version, applied_at_utc) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat())
                )
            conn.commit()
            logger.info("Database initialised at schema version %d (%s)", SCHEMA_VERSION, self.db_path)

    # -------------------------------------------------------------------------
    # System Logs
    # -------------------------------------------------------------------------
    def log(self, level: str, component: str, message: str, details: Optional[str] = None) -> None:
        """Write a log record to the database."""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO system_logs (level, component, message, details, created_at_utc)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (level.upper(), component, message, details, datetime.now(timezone.utc).isoformat())
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to write system log to DB: %s", e)

    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM system_logs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def prune_old_data(self, days_logs: int = 30, days_candles: int = 90) -> Dict[str, int]:
        """Prune older logs and historical candles to maintain low memory/disk footprint."""
        now = datetime.now(timezone.utc)
        log_cutoff = (now - timedelta(days=days_logs)).isoformat()
        candle_cutoff = int((now - timedelta(days=days_candles)).timestamp())

        with self.get_connection() as conn:
            c1 = conn.execute("DELETE FROM system_logs WHERE created_at_utc < ?", (log_cutoff,)).rowcount
            c2 = conn.execute("DELETE FROM candles WHERE candle_ts < ?", (candle_cutoff,)).rowcount
            conn.commit()
            return {"pruned_logs": c1, "pruned_candles": c2}

    # -------------------------------------------------------------------------
    # Economic Events
    # -------------------------------------------------------------------------
    def upsert_economic_event(self, event: Dict[str, Any]) -> bool:
        now_utc = datetime.now(timezone.utc).isoformat()
        affected = event.get("affected_instruments")
        affected_str = json.dumps(affected) if isinstance(affected, list) else str(affected or "[]")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT event_ts, status, event_time_utc FROM economic_events WHERE id = ?", (event["id"],))
            existing = cursor.fetchone()

            if existing:
                moved_from = event.get("moved_from") or ""
                if existing["event_ts"] != event["event_ts"]:
                    moved_from = f"Changed from {existing['event_time_utc']} to {event['event_time_utc']}"

                cursor.execute(
                    """
                    UPDATE economic_events SET
                        title = ?, country = ?, currency = ?, impact = ?,
                        event_time_utc = ?, event_ts = ?, forecast = ?, previous = ?,
                        actual = ?, status = ?, moved_from = ?, period = ?,
                        source = ?, retrieval_time_utc = ?, updated_at_utc = ?,
                        affected_instruments = ?, why_it_matters = ?
                    WHERE id = ?
                    """,
                    (
                        event["title"], event.get("country", ""), event["currency"], event["impact"].lower(),
                        event["event_time_utc"], int(event["event_ts"]), event.get("forecast", ""), event.get("previous", ""),
                        event.get("actual", ""), event.get("status", "scheduled"), moved_from, event.get("period", ""),
                        event.get("source", "showmytrades"), event.get("retrieval_time_utc", now_utc), now_utc,
                        affected_str, event.get("why_it_matters", ""), event["id"]
                    )
                )
                conn.commit()
                return False
            else:
                cursor.execute(
                    """
                    INSERT INTO economic_events (
                        id, title, country, currency, impact, event_time_utc, event_ts,
                        forecast, previous, actual, status, moved_from, period,
                        source, retrieval_time_utc, updated_at_utc, affected_instruments, why_it_matters
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["id"], event["title"], event.get("country", ""), event["currency"], event["impact"].lower(),
                        event["event_time_utc"], int(event["event_ts"]), event.get("forecast", ""), event.get("previous", ""),
                        event.get("actual", ""), event.get("status", "scheduled"), event.get("moved_from", ""), event.get("period", ""),
                        event.get("source", "showmytrades"), event.get("retrieval_time_utc", now_utc), now_utc,
                        affected_str, event.get("why_it_matters", "")
                    )
                )
                conn.commit()
                return True

    def get_upcoming_events(self, from_ts: int, to_ts: int, high_impact_only: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM economic_events WHERE event_ts >= ? AND event_ts <= ?"
        params: List[Any] = [from_ts, to_ts]
        if high_impact_only:
            query += " AND impact = 'high'"
        query += " ORDER BY event_ts ASC"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]
            for r in rows:
                try:
                    r["affected_instruments"] = json.loads(r["affected_instruments"] or "[]")
                except Exception:
                    r["affected_instruments"] = []
            return rows

    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM economic_events WHERE id = ?", (event_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                try:
                    d["affected_instruments"] = json.loads(d["affected_instruments"] or "[]")
                except Exception:
                    d["affected_instruments"] = []
                return d
            return None

    # -------------------------------------------------------------------------
    # Notification History
    # -------------------------------------------------------------------------
    def is_notification_sent(self, event_id: str, channel: str = "telegram") -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM notification_history WHERE event_id = ? AND channel = ?", (event_id, channel))
            return cursor.fetchone() is not None

    def record_notification(
        self,
        event_id: str,
        event_title: str,
        event_time_utc: str,
        channel: str,
        recipient: str,
        status: str,
        message_content: str,
        minutes_before: float,
        error_message: Optional[str] = None
    ) -> bool:
        now = datetime.now(timezone.utc)
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO notification_history (
                        event_id, event_title, event_time_utc, channel, recipient,
                        status, message_content, sent_at_utc, sent_ts, minutes_before, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id, event_title, event_time_utc, channel, recipient,
                        status, message_content, now.isoformat(), int(now.timestamp()),
                        round(minutes_before, 2), error_message
                    )
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def get_notification_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notification_history ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Market Snapshots
    # -------------------------------------------------------------------------
    def record_market_snapshot(self, symbol: str, bid: float, ask: float, spread: float, source: str = "MT5") -> None:
        now = datetime.now(timezone.utc)
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO market_snapshots (symbol, bid, ask, spread_points, snapshot_time_utc, snapshot_ts, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (symbol, bid, ask, spread, now.isoformat(), int(now.timestamp()), source)
            )
            conn.commit()

    def get_latest_market_snapshots(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT m.* FROM market_snapshots m
                INNER JOIN (
                    SELECT symbol, MAX(id) as max_id
                    FROM market_snapshots
                    GROUP BY symbol
                ) latest ON m.id = latest.max_id
                ORDER BY m.symbol ASC
                """
            )
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Candles
    # -------------------------------------------------------------------------
    def upsert_candles(self, candles_list: List[Dict[str, Any]]) -> int:
        """Batch upsert OHLC candles into database."""
        if not candles_list:
            return 0
        inserted = 0
        with self.get_connection() as conn:
            for c in candles_list:
                sym = c["symbol"].upper()
                tf = c["timeframe"].upper()
                ts = int(c["candle_ts"])
                time_utc = c.get("candle_time_utc") or datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                try:
                    conn.execute(
                        """
                        INSERT INTO candles (symbol, timeframe, candle_time_utc, candle_ts, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(symbol, timeframe, candle_ts) DO UPDATE SET
                            open = excluded.open,
                            high = excluded.high,
                            low = excluded.low,
                            close = excluded.close,
                            volume = excluded.volume
                        """,
                        (sym, tf, time_utc, ts, float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"]), float(c.get("volume", 0.0)))
                    )
                    inserted += 1
                except Exception as e:
                    logger.debug("Candle upsert skipped: %s", e)
            conn.commit()
        return inserted

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Retrieve recent candles ordered chronologically (oldest to newest)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT symbol, timeframe, candle_time_utc, candle_ts, open, high, low, close, volume
                FROM candles
                WHERE symbol = ? AND timeframe = ?
                ORDER BY candle_ts DESC LIMIT ?
                """,
                (symbol.upper(), timeframe.upper(), limit)
            )
            rows = [dict(r) for r in cursor.fetchall()]
            rows.reverse()  # Return in chronological order (oldest -> newest)
            return rows

    # -------------------------------------------------------------------------
    # Event Scores & Fundamental Bias
    # -------------------------------------------------------------------------
    def record_event_score(
        self,
        event_id: str,
        title: str,
        currency: str,
        actual: Optional[float],
        forecast: Optional[float],
        previous: Optional[float],
        raw_surprise: float,
        normalized_surprise: float,
        direction_score: float,
        event_time_utc: str
    ) -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO event_scores (
                    event_id, title, currency, actual, forecast, previous,
                    raw_surprise, normalized_surprise, direction_score, event_time_utc, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    actual = excluded.actual,
                    forecast = excluded.forecast,
                    previous = excluded.previous,
                    raw_surprise = excluded.raw_surprise,
                    normalized_surprise = excluded.normalized_surprise,
                    direction_score = excluded.direction_score
                """,
                (
                    event_id, title, currency.upper(), actual, forecast, previous,
                    raw_surprise, normalized_surprise, direction_score, event_time_utc, now_utc
                )
            )
            conn.commit()

    def get_event_scores(self, currency: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        query = "SELECT * FROM event_scores"
        params = []
        if currency:
            query += " WHERE currency = ?"
            params.append(currency.upper())
        query += " ORDER BY event_time_utc DESC LIMIT ?"
        params.append(limit)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def upsert_fundamental_bias(
        self,
        symbol: str,
        bias_value: float,
        bias_label: str,
        contributing_events: List[Dict[str, Any]],
        central_bank_score: float = 0.0
    ) -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        events_json = json.dumps(contributing_events)
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO fundamental_bias (symbol, bias_value, bias_label, contributing_events, central_bank_score, updated_at_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    bias_value = excluded.bias_value,
                    bias_label = excluded.bias_label,
                    contributing_events = excluded.contributing_events,
                    central_bank_score = excluded.central_bank_score,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (symbol.upper(), round(bias_value, 1), bias_label, events_json, round(central_bank_score, 1), now_utc)
            )
            conn.commit()

    def get_fundamental_biases(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM fundamental_bias ORDER BY symbol ASC")
            rows = [dict(r) for r in cursor.fetchall()]
            for r in rows:
                try:
                    r["contributing_events"] = json.loads(r["contributing_events"] or "[]")
                except Exception:
                    r["contributing_events"] = []
            return rows

    # -------------------------------------------------------------------------
    # Signals & Decisions
    # -------------------------------------------------------------------------
    def save_signal(self, signal: Dict[str, Any]) -> bool:
        reasons_json = json.dumps(signal.get("reasons", []))
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO signals (
                        signal_id, symbol, timeframe, direction, entry_price, sl, tp,
                        rr, confidence, reasons, fundamental_bias, status, expiry_ts, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal["signal_id"], signal["symbol"], signal["timeframe"], signal["direction"],
                        signal["entry_price"], signal["sl"], signal["tp"], signal["rr"], signal["confidence"],
                        reasons_json, signal.get("fundamental_bias", "NEUTRAL"), signal.get("status", "ACTIVE"),
                        int(signal["expiry_ts"]), signal.get("created_at_utc", datetime.now(timezone.utc).isoformat())
                    )
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def get_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["reasons"] = json.loads(d["reasons"] or "[]")
                return d
            return None

    def update_signal_status(self, signal_id: str, status: str) -> None:
        with self.get_connection() as conn:
            conn.execute("UPDATE signals SET status = ? WHERE signal_id = ?", (status, signal_id))
            conn.commit()

    def get_active_signals(self) -> List[Dict[str, Any]]:
        now_ts = int(time.time())
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM signals WHERE status = 'ACTIVE' AND expiry_ts > ? ORDER BY expiry_ts ASC",
                (now_ts,)
            )
            rows = [dict(r) for r in cursor.fetchall()]
            for r in rows:
                r["reasons"] = json.loads(r["reasons"] or "[]")
            return rows

    def record_decision(self, decision: Dict[str, Any]) -> None:
        reasons_json = json.dumps(decision.get("reasons", []))
        now_utc = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO decisions (
                    decision_id, signal_id, symbol, action, reasons, risk_checks_passed, lot_size, equity, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision["decision_id"], decision.get("signal_id"), decision["symbol"], decision["action"],
                    reasons_json, 1 if decision.get("risk_checks_passed") else 0,
                    decision.get("lot_size", 0.0), decision.get("equity", 0.0), now_utc
                )
            )
            conn.commit()

    def get_recent_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))
            rows = [dict(r) for r in cursor.fetchall()]
            for r in rows:
                r["reasons"] = json.loads(r["reasons"] or "[]")
            return rows

    # -------------------------------------------------------------------------
    # Orders & Trade Results
    # -------------------------------------------------------------------------
    def save_order(self, order: Dict[str, Any]) -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    order_id, signal_id, symbol, direction, volume, entry_price, sl, tp, status, ticket, error_message, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["order_id"], order.get("signal_id"), order["symbol"], order["direction"],
                    order["volume"], order.get("entry_price", 0.0), order["sl"], order["tp"],
                    order.get("status", "PENDING"), order.get("ticket"), order.get("error_message"),
                    now_utc, now_utc
                )
            )
            conn.commit()

    def update_order_status(self, order_id: str, status: str, ticket: Optional[int] = None, error: Optional[str] = None) -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE orders SET status = ?, ticket = COALESCE(?, ticket), error_message = ?, updated_at_utc = ?
                WHERE order_id = ?
                """,
                (status, ticket, error, now_utc, order_id)
            )
            conn.commit()

    def record_trade_result(
        self,
        ticket: int,
        symbol: str,
        direction: str,
        volume: float,
        open_price: float,
        close_price: float,
        sl: float,
        tp: float,
        pnl: float,
        r_multiple: float,
        close_reason: str,
        open_time_utc: str,
        close_time_utc: str
    ) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO trade_results (
                    ticket, symbol, direction, volume, open_price, close_price, sl, tp,
                    pnl, r_multiple, close_reason, open_time_utc, close_time_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket, symbol, direction, volume, open_price, close_price, sl, tp,
                    pnl, round(r_multiple, 2), close_reason, open_time_utc, close_time_utc
                )
            )
            conn.commit()

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Calculate live trading performance metrics from trade_results."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trade_results ORDER BY close_time_utc ASC")
            trades = [dict(r) for r in cursor.fetchall()]

        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": 0.0,
                "average_r": 0.0,
                "profit_factor": 0.0,
                "net_pnl": 0.0,
                "max_drawdown_pct": 0.0
            }

        total = len(trades)
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] < 0]
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        win_rate = round((len(wins) / total) * 100.0, 1)
        avg_r = round(sum(t["r_multiple"] for t in trades) / total, 2)
        net_pnl = round(sum(t["pnl"] for t in trades), 2)

        return {
            "total_trades": total,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": win_rate,
            "average_r": avg_r,
            "profit_factor": profit_factor,
            "net_pnl": net_pnl
        }

    # -------------------------------------------------------------------------
    # Trading Journal & Research
    # -------------------------------------------------------------------------
    def add_journal_entry(
        self,
        symbol: str,
        action: str,
        volume: float,
        price: float,
        sl: float = 0.0,
        tp: float = 0.0,
        pnl: float = 0.0,
        strategy_reason: str = "",
        economic_context: str = "",
        risk_assessment: str = "",
        ticket: Optional[int] = None
    ) -> int:
        now_utc = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trading_journal (
                    ticket, symbol, action, volume, price, sl, tp, pnl,
                    strategy_reason, economic_context, risk_assessment, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ticket, symbol, action, volume, price, sl, tp, pnl, strategy_reason, economic_context, risk_assessment, now_utc)
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_journal_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trading_journal ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def record_research(
        self,
        category: str,
        subject: str,
        analysis_text: str,
        confirmed_facts: str,
        interpretation: str,
        confidence_score: float = 1.0,
        is_data_sufficient: bool = True
    ) -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO market_research (
                    category, subject, analysis_text, confirmed_facts, interpretation,
                    confidence_score, is_data_sufficient, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (category, subject, analysis_text, confirmed_facts, interpretation, confidence_score, 1 if is_data_sufficient else 0, now_utc)
            )
            conn.commit()

    def get_latest_research(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM market_research ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]


# Global Database Instance
db = Database()
