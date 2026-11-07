"""
Database operations for BANDI.
Provides connection pooling / context manager, WAL mode initialization,
and robust transactional helper functions.
"""

from __future__ import annotations
import sqlite3
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
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
        # Performance and integrity optimizations
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        """Initialise database schema and record version."""
        with self.get_connection() as conn:
            conn.executescript(CREATE_TABLES_SQL)
            # Record or verify schema version
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM schema_version WHERE version = ?", (SCHEMA_VERSION,))
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    "INSERT INTO schema_version (version, applied_at_utc) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat())
                )
            conn.commit()
            logger.info("Database initialised successfully at %s", self.db_path)

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
            # Fallback to standard logging if DB write fails
            logger.error("Failed to write system log to DB: %s", e)

    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve recent system logs."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM system_logs ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Economic Events
    # -------------------------------------------------------------------------
    def upsert_economic_event(self, event: Dict[str, Any]) -> bool:
        """
        Insert or update an economic event.
        Detects if scheduled time or status changed.
        Returns True if newly inserted or updated.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        affected = event.get("affected_instruments")
        if isinstance(affected, list):
            affected_str = json.dumps(affected)
        else:
            affected_str = str(affected or "[]")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT event_ts, status, event_time_utc FROM economic_events WHERE id = ?", (event["id"],))
            existing = cursor.fetchone()

            if existing:
                moved_from = event.get("moved_from") or ""
                # Detect change in time
                if existing["event_ts"] != event["event_ts"]:
                    moved_from = f"Changed from {existing['event_time_utc']} to {event['event_time_utc']}"

                cursor.execute(
                    """
                    UPDATE economic_events SET
                        title = ?,
                        country = ?,
                        currency = ?,
                        impact = ?,
                        event_time_utc = ?,
                        event_ts = ?,
                        forecast = ?,
                        previous = ?,
                        actual = ?,
                        status = ?,
                        moved_from = ?,
                        period = ?,
                        source = ?,
                        retrieval_time_utc = ?,
                        updated_at_utc = ?,
                        affected_instruments = ?,
                        why_it_matters = ?
                    WHERE id = ?
                    """,
                    (
                        event["title"],
                        event.get("country", ""),
                        event["currency"],
                        event["impact"].lower(),
                        event["event_time_utc"],
                        int(event["event_ts"]),
                        event.get("forecast", ""),
                        event.get("previous", ""),
                        event.get("actual", ""),
                        event.get("status", "scheduled"),
                        moved_from,
                        event.get("period", ""),
                        event.get("source", "showmytrades"),
                        event.get("retrieval_time_utc", now_utc),
                        now_utc,
                        affected_str,
                        event.get("why_it_matters", ""),
                        event["id"]
                    )
                )
                conn.commit()
                return False  # Updated existing
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
                        event["id"],
                        event["title"],
                        event.get("country", ""),
                        event["currency"],
                        event["impact"].lower(),
                        event["event_time_utc"],
                        int(event["event_ts"]),
                        event.get("forecast", ""),
                        event.get("previous", ""),
                        event.get("actual", ""),
                        event.get("status", "scheduled"),
                        event.get("moved_from", ""),
                        event.get("period", ""),
                        event.get("source", "showmytrades"),
                        event.get("retrieval_time_utc", now_utc),
                        now_utc,
                        affected_str,
                        event.get("why_it_matters", "")
                    )
                )
                conn.commit()
                return True  # Newly inserted

    def get_upcoming_events(self, from_ts: int, to_ts: int, high_impact_only: bool = False) -> List[Dict[str, Any]]:
        """Retrieve events scheduled between from_ts and to_ts."""
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
        """Retrieve single event by ID."""
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
    # Notification History & Duplicate Prevention
    # -------------------------------------------------------------------------
    def is_notification_sent(self, event_id: str, channel: str = "telegram") -> bool:
        """Check if an alert was already sent or recorded for this event and channel."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM notification_history WHERE event_id = ? AND channel = ?",
                (event_id, channel)
            )
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
        """
        Record a notification to prevent duplicates and maintain full audit trail.
        Returns True on successful record, False if constraint violation (duplicate).
        """
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
                        event_id,
                        event_title,
                        event_time_utc,
                        channel,
                        recipient,
                        status,
                        message_content,
                        now.isoformat(),
                        int(now.timestamp()),
                        round(minutes_before, 2),
                        error_message
                    )
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            logger.warning("Duplicate notification prevented for event_id=%s channel=%s", event_id, channel)
            return False

    def get_notification_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent notifications sent."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM notification_history ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Market Snapshots
    # -------------------------------------------------------------------------
    def record_market_snapshot(self, symbol: str, bid: float, ask: float, spread: float, source: str = "MT5") -> None:
        """Record live bid/ask/spread for symbol tracking."""
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
        """Get the latest snapshot for each tracked symbol."""
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
    # Fundamental Research Records
    # -------------------------------------------------------------------------
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
                (
                    category,
                    subject,
                    analysis_text,
                    confirmed_facts,
                    interpretation,
                    confidence_score,
                    1 if is_data_sufficient else 0,
                    now_utc
                )
            )
            conn.commit()

    def get_latest_research(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM market_research ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Trading Journal
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


# Global Database Instance
db = Database()
