"""
Economic Calendar Ingestion Client for BANDI.
Connects to showmytrades.com API, enforces the 15-minute rate limit,
normalizes event timestamps to UTC, runs classification, and updates the local SQLite database.
"""

from __future__ import annotations
import json
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import requests

from bandi.config import settings
from bandi.database.db import db
from bandi.calendar.classifier import classify_event
from bandi.calendar.fallback import get_fallback_events

logger = logging.getLogger("bandi.calendar")


class CalendarClient:
    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or settings.CALENDAR_API_URL
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"{settings.APP_NAME}-Intelligence/1.0",
            "Accept": "application/json"
        })
        self._last_fetch_ts: float = 0.0

    def can_fetch(self, min_interval_seconds: int = 900) -> bool:
        """Check if 15 minutes (900 seconds) have elapsed since the last fetch."""
        now = time.time()
        if now - self._last_fetch_ts < min_interval_seconds:
            return False
        # Also check persistent setting in DB
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM application_settings WHERE key = 'calendar_last_fetch_ts'")
            row = cursor.fetchone()
            if row:
                try:
                    last_ts = float(row["value"])
                    if now - last_ts < min_interval_seconds:
                        return False
                except ValueError:
                    pass
        return True

    def fetch_and_sync(self, force: bool = False, days: int = 7) -> Dict[str, Any]:
        """
        Fetch economic releases from API and upsert into the local database.
        Respects the 15-minute rate limit unless force=True.
        """
        now_utc = datetime.now(timezone.utc)
        now_ts = now_utc.timestamp()

        if not force and not self.can_fetch():
            elapsed = int(now_ts - self._last_fetch_ts)
            msg = f"Rate-limit guard: last fetch was {elapsed}s ago. Minimum interval is {settings.CALENDAR_POLL_INTERVAL_MINUTES} minutes."
            logger.info(msg)
            return {"status": "throttled", "message": msg, "count": 0}

        url = f"{self.api_url}?days={days}"
        logger.info("Fetching economic calendar from %s", url)

        try:
            resp = self.session.get(url, timeout=12.0)
            if resp.status_code != 200:
                err_msg = f"Calendar provider returned HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error(err_msg)
                db.log("ERROR", "CALENDAR", err_msg)
                return {"status": "error", "message": err_msg, "count": 0}

            data = resp.json()
            events_raw = data.get("events", [])
            retrieval_time_iso = now_utc.isoformat()

            upserted_count = 0
            for item in events_raw:
                event_id = str(item.get("id") or "").strip()
                title = str(item.get("title") or "").strip()
                currency = str(item.get("currency") or "").strip().upper()
                event_ts = item.get("ts")
                time_str = item.get("time") or ""

                # Rule 11: Do not send/process an ordinary alert for an event whose time is unknown
                if not event_id or not title or not currency or not event_ts or int(event_ts) <= 0:
                    logger.debug("Skipping event with incomplete or unknown time: %s", item)
                    continue

                provider_impact = str(item.get("impact") or "").lower()
                impact, affected_instruments, why_it_matters = classify_event(title, currency, provider_impact)

                # Ensure ISO string is UTC
                try:
                    dt = datetime.fromtimestamp(int(event_ts), tz=timezone.utc)
                    event_time_utc = dt.isoformat()
                except Exception:
                    event_time_utc = time_str or now_utc.isoformat()

                event_record = {
                    "id": event_id,
                    "title": title,
                    "country": str(item.get("country") or currency),
                    "currency": currency,
                    "impact": impact,
                    "event_time_utc": event_time_utc,
                    "event_ts": int(event_ts),
                    "forecast": str(item.get("forecast") or ""),
                    "previous": str(item.get("previous") or ""),
                    "actual": str(item.get("actual") or ""),
                    "status": str(item.get("status") or "scheduled"),
                    "moved_from": str(item.get("moved_from") or ""),
                    "period": str(item.get("period") or ""),
                    "source": "showmytrades.com",
                    "retrieval_time_utc": retrieval_time_iso,
                    "affected_instruments": affected_instruments,
                    "why_it_matters": why_it_matters
                }

                db.upsert_economic_event(event_record)
                upserted_count += 1

            # Update fetch timestamp
            self._last_fetch_ts = now_ts
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO application_settings (key, value, updated_at_utc) VALUES (?, ?, ?)",
                    ("calendar_last_fetch_ts", str(now_ts), retrieval_time_iso)
                )
                conn.commit()

            msg = f"Successfully synced {upserted_count} economic events from provider."
            logger.info(msg)
            db.log("INFO", "CALENDAR", msg, f"Provider raw events: {len(events_raw)}")

            return {
                "status": "ok",
                "count": upserted_count,
                "raw_total": len(events_raw),
                "retrieval_time_utc": retrieval_time_iso,
                "attribution": data.get("attribution", {})
            }

        except Exception as e:
            err_msg = f"Network or parsing exception while connecting to calendar provider: {e}"
            logger.error(err_msg)
            db.log("WARNING", "CALENDAR", err_msg)
            return {"status": "error", "message": err_msg, "count": 0}


# Global client instance
calendar_client = CalendarClient()
