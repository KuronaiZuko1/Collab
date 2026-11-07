"""
Telegram Bot Integration for BANDI.
Handles API communication with official Telegram Bot API,
delivering high-impact economic alerts and connectivity health checks.
"""

from __future__ import annotations
import logging
import requests
from typing import Dict, Any, Optional

from bandi.config import settings
from bandi.database.db import db
from bandi.telegram.formatter import format_economic_alert, format_test_message

logger = logging.getLogger("bandi.telegram")


class TelegramNotifier:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: Optional[bool] = None
    ):
        self.bot_token = (bot_token or settings.TELEGRAM_BOT_TOKEN).strip()
        self.chat_id = (chat_id or settings.TELEGRAM_CHAT_ID).strip()
        self.enabled = settings.TELEGRAM_ENABLED if enabled is None else enabled
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"
        self.session = requests.Session()

    def test_connection(self) -> Dict[str, Any]:
        """Verify bot token and connection status with Telegram Bot API."""
        if not self.bot_token:
            return {"ok": False, "error": "TELEGRAM_BOT_TOKEN is not configured in .env"}

        try:
            resp = self.session.get(f"{self.api_base}/getMe", timeout=10.0)
            data = resp.json()
            if data.get("ok"):
                user_info = data.get("result", {})
                return {
                    "ok": True,
                    "id": user_info.get("id"),
                    "first_name": user_info.get("first_name"),
                    "username": user_info.get("username"),
                    "chat_id_configured": bool(self.chat_id)
                }
            else:
                return {"ok": False, "error": data.get("description", "Unknown Telegram API error")}
        except Exception as e:
            return {"ok": False, "error": f"Connection error: {str(e)}"}

    def send_message(self, text: str, chat_id: Optional[str] = None) -> Dict[str, Any]:
        """Send an HTML-formatted message to the designated Telegram chat."""
        target_chat = (chat_id or self.chat_id).strip()

        if not self.enabled:
            return {"ok": False, "error": "Telegram notifications are disabled in settings"}
        if not self.bot_token:
            return {"ok": False, "error": "Telegram bot token is not configured"}
        if not target_chat:
            return {"ok": False, "error": "Target chat ID is not configured"}

        url = f"{self.api_base}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            resp = self.session.post(url, json=payload, timeout=10.0)
            data = resp.json()
            if data.get("ok"):
                logger.info("Telegram message delivered to %s (message_id: %s)", target_chat, data.get("result", {}).get("message_id"))
                return {"ok": True, "message_id": data.get("result", {}).get("message_id")}
            else:
                err = data.get("description", "Failed to deliver message")
                logger.error("Telegram API error: %s", err)
                return {"ok": False, "error": err}
        except Exception as e:
            err = f"Failed to send Telegram message: {str(e)}"
            logger.error(err)
            return {"ok": False, "error": err}

    def send_test_alert(self) -> Dict[str, Any]:
        """Send a test connectivity confirmation to the configured chat."""
        conn_check = self.test_connection()
        if not conn_check.get("ok"):
            return conn_check

        username = conn_check.get("username", "BANDI_Bot")
        test_msg = format_test_message(username, self.chat_id)
        result = self.send_message(test_msg)
        if result.get("ok"):
            db.log("INFO", "TELEGRAM", "Telegram test message delivered successfully.")
        else:
            db.log("ERROR", "TELEGRAM", f"Failed to send test message: {result.get('error')}")
        return result

    def send_economic_alert(
        self,
        event: Dict[str, Any],
        is_late: bool = False,
        minutes_until: float = 30.0
    ) -> Dict[str, Any]:
        """Dispatch formatted economic alert for an upcoming release."""
        msg = format_economic_alert(event, is_late=is_late, minutes_until=minutes_until)
        result = self.send_message(msg)

        # Record to notification history
        status = "sent" if result.get("ok") else "failed"
        if result.get("ok") and is_late:
            status = "late"

        db.record_notification(
            event_id=event["id"],
            event_title=event["title"],
            event_time_utc=event["event_time_utc"],
            channel="telegram",
            recipient=self.chat_id,
            status=status,
            message_content=msg,
            minutes_before=minutes_until,
            error_message=result.get("error")
        )

        return result


# Global notifier instance
telegram_notifier = TelegramNotifier()
