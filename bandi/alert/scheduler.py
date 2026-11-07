"""
Precision Local Scheduler for BANDI.
Continuously scans SQLite database for scheduled tier-1 releases and dispatches
Telegram alerts exactly 30 minutes before release, enforcing late-alert policy and
persistent duplicate prevention.
"""

from __future__ import annotations
import time
import threading
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone

from bandi.config import settings
from bandi.database.db import db
from bandi.calendar.client import calendar_client
from bandi.alert.late_policy import evaluate_event_timing, AlertDecision
from bandi.telegram.bot import telegram_notifier

logger = logging.getLogger("bandi.scheduler")


class PrecisionScheduler:
    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._check_interval = settings.SCHEDULER_CHECK_INTERVAL_SECONDS
        self._calendar_poll_interval = settings.CALENDAR_POLL_INTERVAL_MINUTES * 60
        self._last_calendar_sync = 0.0

    def check_and_alert(self, current_ts: float | None = None) -> List[Dict[str, Any]]:
        """
        Scan SQLite DB for upcoming high-impact events and dispatch alerts
        when within the 30-minute alert window.
        Returns list of processed alert results.
        """
        now_ts = current_ts if current_ts is not None else time.time()
        
        # Look ahead up to 2 hours for high impact events
        horizon_from = int(now_ts)
        horizon_to = int(now_ts + 7200)

        upcoming = db.get_upcoming_events(from_ts=horizon_from - 3600, to_ts=horizon_to, high_impact_only=True)
        results: List[Dict[str, Any]] = []

        for event in upcoming:
            event_id = event["id"]
            event_ts = int(event["event_ts"])

            # Check if alert has already been sent to Telegram
            if db.is_notification_sent(event_id, channel="telegram"):
                continue

            decision, minutes_remaining = evaluate_event_timing(
                event_ts=event_ts,
                current_ts=now_ts,
                nominal_minutes=settings.ALERT_MINUTES_BEFORE,
                tolerance_window_minutes=1.5,
                late_cutoff_minutes=1.0
            )

            if decision == AlertDecision.ON_TIME:
                logger.info("Firing on-time 30-min alert for: %s (~%.1fm away)", event["title"], minutes_remaining)
                res = telegram_notifier.send_economic_alert(
                    event=event,
                    is_late=False,
                    minutes_until=minutes_remaining
                )
                results.append({"event_id": event_id, "decision": "on_time", "result": res})

            elif decision == AlertDecision.LATE:
                logger.warning("Firing LATE alert for: %s (~%.1fm away)", event["title"], minutes_remaining)
                res = telegram_notifier.send_economic_alert(
                    event=event,
                    is_late=True,
                    minutes_until=minutes_remaining
                )
                results.append({"event_id": event_id, "decision": "late", "result": res})

            elif decision == AlertDecision.TOO_LATE:
                # Mark as suppressed so we don't evaluate again
                db.record_notification(
                    event_id=event_id,
                    event_title=event["title"],
                    event_time_utc=event["event_time_utc"],
                    channel="telegram",
                    recipient=telegram_notifier.chat_id,
                    status="suppressed",
                    message_content="Suppressed: event occurred within 1 minute or in the past.",
                    minutes_before=minutes_remaining
                )
                logger.debug("Suppressed expired/imminent event: %s (%.1fm away)", event["title"], minutes_remaining)

        return results

    def _run_loop(self) -> None:
        logger.info("Precision scheduler background loop started (tick: %ss).", self._check_interval)
        while self._running:
            try:
                now = time.time()
                # 1. Periodic calendar sync from remote provider (rate-limited >=15m)
                if now - self._last_calendar_sync >= self._calendar_poll_interval:
                    logger.info("Running scheduled calendar sync...")
                    calendar_client.fetch_and_sync(force=False)
                    self._last_calendar_sync = now

                # 2. Frequent local check against SQLite DB
                self.check_and_alert(now)

            except Exception as e:
                logger.error("Exception in scheduler loop: %s", e)
                db.log("ERROR", "SCHEDULER", f"Exception in scheduler: {e}")

            time.sleep(self._check_interval)

    def start(self) -> None:
        """Start the background precision scheduler thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="BandiSchedulerThread", daemon=True)
        self._thread.start()
        logger.info("Precision scheduler started.")

    def stop(self) -> None:
        """Gracefully stop the precision scheduler."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Precision scheduler stopped.")


# Global precision scheduler instance
precision_scheduler = PrecisionScheduler()
