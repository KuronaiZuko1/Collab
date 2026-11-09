"""
Telegram Bot Integration for BANDI.
Handles API communication with official Telegram Bot API, delivering high-impact economic alerts,
trade strategy signals with inline approval buttons, and interactive bot commands (/status, /halt, /positions).
"""

from __future__ import annotations
import time
import threading
import logging
import requests
from typing import Dict, Any, Optional, List

from bandi.config import settings
from bandi.database.db import db
from bandi.telegram.formatter import (
    format_economic_alert,
    format_strategy_signal,
    format_order_execution_notice,
    format_test_message
)

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
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None
        self._last_update_id = 0

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

    def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send an HTML-formatted message to the designated Telegram chat."""
        target_chat = (chat_id or self.chat_id).strip()

        if not self.enabled:
            return {"ok": False, "error": "Telegram notifications are disabled in settings"}
        if not self.bot_token:
            return {"ok": False, "error": "Telegram bot token is not configured"}
        if not target_chat:
            return {"ok": False, "error": "Target chat ID is not configured"}

        url = f"{self.api_base}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

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

    def send_strategy_signal(
        self,
        signal: Any,
        lot_size: float = 0.01,
        risk_pct: float = 1.0
    ) -> Dict[str, Any]:
        """Dispatch trade signal to Telegram, with approval inline buttons if in APPROVAL mode."""
        msg = format_strategy_signal(signal, lot_size=lot_size, risk_pct=risk_pct)
        reply_markup = None

        if settings.TRADING_MODE == "APPROVAL":
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve Trade", "callback_data": f"appr_{signal.signal_id}"},
                        {"text": "❌ Skip", "callback_data": f"skip_{signal.signal_id}"}
                    ]
                ]
            }

        return self.send_message(msg, reply_markup=reply_markup)

    def send_order_notice(self, order: Dict[str, Any], ticket: int = 0) -> Dict[str, Any]:
        """Dispatch order opened notification."""
        msg = format_order_execution_notice(order, ticket)
        return self.send_message(msg)

    # -------------------------------------------------------------------------
    # Telegram Interactive Command Polling
    # -------------------------------------------------------------------------
    def _handle_command(self, cmd: str, user_id: str) -> None:
        """Handle incoming command from user with strict authentication check."""
        if str(user_id) != str(self.chat_id):
            logger.warning("Unauthorized command attempt from user %s: %s", user_id, cmd)
            return

        cmd = cmd.strip().lower()
        from bandi.mt5.bridge import mt5_bridge
        from bandi.research.fundamental_engine import fundamental_calculator

        if cmd == "/status":
            stat = mt5_bridge.get_status()
            acct = stat.get("account") or {}
            kill = "🚨 ACTIVE" if settings.is_kill_switch_active() else "NORMAL"
            reply = (
                f"<b>🤖 BANDI STATUS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Trading Mode:</b> [{settings.TRADING_MODE}]\n"
                f"<b>Lock State:</b> {'LOCKED' if settings.RISK_TRADING_LOCKED else 'UNLOCKED'}\n"
                f"<b>Kill Switch:</b> {kill}\n"
                f"<b>MT5 Terminal:</b> {'CONNECTED' if stat['connected'] else 'MONITORING'}\n"
                f"<b>Account:</b> #{acct.get('login', 0)} ({acct.get('broker', 'None')})\n"
                f"<b>Balance:</b> ${acct.get('balance', 0.0):.2f} | <b>Equity:</b> ${acct.get('equity', 0.0):.2f}\n"
                f"<b>Open Positions:</b> {len(stat.get('open_positions', []))}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.send_message(reply)

        elif cmd == "/halt":
            settings.set_kill_switch(True)
            db.log("WARNING", "KILL_SWITCH", "Emergency kill switch activated via Telegram /halt command.")
            self.send_message("<b>🚨 EMERGENCY KILL SWITCH ENGAGED!</b>\nAll order dispatching is halted.")

        elif cmd == "/resume":
            settings.set_kill_switch(False)
            db.log("INFO", "KILL_SWITCH", "Kill switch deactivated via Telegram /resume command.")
            self.send_message("<b>✅ KILL SWITCH DISENGAGED.</b>\nNormal system rules resumed.")

        elif cmd == "/positions":
            positions = mt5_bridge._open_positions
            if not positions:
                self.send_message("<b>📊 No open positions currently in MT5.</b>")
                return
            lines = ["<b>📊 ACTIVE OPEN POSITIONS:</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
            for p in positions:
                lines.append(f"• #{p.get('ticket')} {p.get('type')} {p.get('volume')} {p.get('symbol')} @ {p.get('price_open')} | PnL: ${p.get('profit', 0.0):.2f}")
            self.send_message("\n".join(lines))

        elif cmd == "/pnl":
            perf = db.get_performance_metrics()
            reply = (
                f"<b>📈 BANDI PERFORMANCE SUMMARY</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Total Closed Trades:</b> {perf['total_trades']}\n"
                f"<b>Win Rate:</b> {perf['win_rate_pct']}%\n"
                f"<b>Average R:</b> {perf['average_r']}\n"
                f"<b>Profit Factor:</b> {perf['profit_factor']}\n"
                f"<b>Net PnL:</b> ${perf['net_pnl']:.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.send_message(reply)

        elif cmd == "/bias":
            biases = fundamental_calculator.update_all_biases()
            lines = ["<b>🧠 CURRENT FUNDAMENTAL BIASES:</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
            for sym, b in biases.items():
                lines.append(f"• <b>{sym}:</b> {b['bias_label']} ({b['bias_value']:+.0f})")
            self.send_message("\n".join(lines))

        elif cmd == "/signals":
            active = db.get_active_signals()
            if not active:
                self.send_message("<b>⏳ No active signals at this moment.</b>")
                return
            lines = ["<b>🎯 ACTIVE STRATEGY SIGNALS:</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
            for s in active:
                lines.append(f"• {s['direction']} {s['symbol']} @ {s['entry_price']} | SL: {s['sl']} | TP: {s['tp']} (RR {s['rr']})")
            self.send_message("\n".join(lines))

        elif cmd == "/mode":
            self.send_message(f"Current TRADING_MODE: <code>{settings.TRADING_MODE}</code> (Lock: {settings.RISK_TRADING_LOCKED})")

    def _handle_callback_query(self, query: Dict[str, Any]) -> None:
        """Handle inline button approvals."""
        from_id = str(query.get("from", {}).get("id", ""))
        if from_id != str(self.chat_id):
            return

        data = query.get("data", "")
        query_id = query.get("id")

        from bandi.mt5.bridge import mt5_bridge
        if data.startswith("appr_"):
            sig_id = data[5:]
            sig = db.get_signal(sig_id)
            if sig:
                now_ts = int(time.time())
                if now_ts > sig["expiry_ts"]:
                    self.send_message(f"⚠️ Signal #{sig_id} has expired! Cannot execute.")
                else:
                    db.update_signal_status(sig_id, "APPROVED")
                    # Queue order in MT5
                    order_payload = {
                        "signal_id": sig_id,
                        "symbol": sig["symbol"],
                        "direction": sig["direction"],
                        "volume": settings.MAX_LOT, # or sized lot
                        "entry_price": sig["entry_price"],
                        "sl": sig["sl"],
                        "tp": sig["tp"]
                    }
                    ord_id = mt5_bridge.queue_order(order_payload)
                    db.save_order({
                        "order_id": ord_id,
                        "signal_id": sig_id,
                        "symbol": sig["symbol"],
                        "direction": sig["direction"],
                        "volume": settings.MAX_LOT,
                        "entry_price": sig["entry_price"],
                        "sl": sig["sl"],
                        "tp": sig["tp"],
                        "status": "PENDING"
                    })
                    self.send_message(f"✅ <b>Approved!</b> Order #{ord_id} queued for EA execution on {sig['symbol']}.")

        elif data.startswith("skip_"):
            sig_id = data[5:]
            db.update_signal_status(sig_id, "SKIPPED")
            self.send_message(f"❌ Signal #{sig_id} skipped.")

        # Acknowledge callback query
        try:
            self.session.post(f"{self.api_base}/answerCallbackQuery", json={"callback_query_id": query_id})
        except Exception:
            pass

    def _poll_updates(self) -> None:
        """Polling loop for incoming Telegram commands and inline approvals."""
        while self._polling:
            try:
                url = f"{self.api_base}/getUpdates?offset={self._last_update_id + 1}&timeout=5"
                resp = self.session.get(url, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        self._last_update_id = update["update_id"]
                        if "message" in update and "text" in update["message"]:
                            text = update["message"]["text"]
                            user_id = str(update["message"]["from"]["id"])
                            if text.startswith("/"):
                                self._handle_command(text, user_id)
                        elif "callback_query" in update:
                            self._handle_callback_query(update["callback_query"])
            except Exception as e:
                logger.debug("Telegram polling transient error: %s", e)
            time.sleep(2)

    def start_polling(self) -> None:
        """Start Telegram command poller in background thread."""
        if self._polling or not self.enabled or not self.bot_token:
            return
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_updates, name="BandiTelegramPollThread", daemon=True)
        self._poll_thread.start()
        logger.info("Telegram command polling started.")

    def stop_polling(self) -> None:
        """Stop Telegram poller."""
        self._polling = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)


# Global notifier instance
telegram_notifier = TelegramNotifier()
