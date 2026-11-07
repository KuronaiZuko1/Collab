"""
Telegram Alert Formatter for BANDI.
Produces clean, professional, high-clarity messages with BANDI branding,
SAST timestamps, affected instruments, and fundamental importance notes.
"""

from __future__ import annotations
from typing import Dict, Any, List
from datetime import datetime
from bandi.config import settings


def format_economic_alert(
    event: Dict[str, Any],
    is_late: bool = False,
    minutes_until: float = 30.0
) -> str:
    """
    Format a scheduled high-impact release alert for Telegram.
    Uses HTML formatting for maximum stability.
    """
    title = event.get("title", "Economic Event")
    currency = event.get("currency", "USD")
    country = event.get("country", currency)
    impact = str(event.get("impact", "HIGH")).upper()
    source = event.get("source", "showmytrades.com")
    why_it_matters = event.get("why_it_matters", "Major macroeconomic release.")
    
    event_ts = int(event.get("event_ts", 0))
    sast_release_str = settings.ts_to_sast_str(event_ts)
    now_sast_str = settings.now_sast().strftime("%Y-%m-%d %H:%M:%S SAST")

    affected = event.get("affected_instruments", [])
    if isinstance(affected, list):
        affected_str = ", ".join(affected) if affected else "Forex & Commodities"
    else:
        affected_str = str(affected)

    forecast = event.get("forecast") or "N/A"
    previous = event.get("previous") or "N/A"

    # Header banner
    late_banner = ""
    if is_late:
        late_banner = f"<b>⚠️ [LATE ALERT — SYSTEM RESTARTED]</b>\n<i>Alert dispatched ~{int(minutes_until)} mins before release.</i>\n\n"

    msg = (
        f"<b>🤖 BANDI | HIGH-IMPACT ECONOMIC ALERT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{late_banner}"
        f"<b>📊 Event:</b> {title}\n"
        f"<b>🌍 Country/Currency:</b> {country} ({currency})\n"
        f"<b>🔥 Importance:</b> 🔴 {impact}\n"
        f"<b>⏰ Release Time:</b> <code>{sast_release_str}</code>\n"
        f"<b>⏱️ Notice Time:</b> <code>{now_sast_str}</code> (~{int(minutes_until)}m prior)\n"
        f"<b>🎯 Affected Instruments:</b> <code>{affected_str}</code>\n\n"
        f"<b>📈 Figures:</b> Forecast: <code>{forecast}</code> | Previous: <code>{previous}</code>\n"
        f"<b>💡 Why It Matters:</b>\n{why_it_matters}\n\n"
        f"<b>📡 Data Source:</b> {source}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>BANDI Intelligence • Local-First Trading Engine</i>"
    )
    return msg


def format_test_message(bot_username: str, chat_id: str) -> str:
    """Format a test connectivity message."""
    now_sast_str = settings.now_sast().strftime("%Y-%m-%d %H:%M:%S SAST")
    return (
        f"<b>🤖 BANDI TELEGRAM CONNECTIVITY VERIFIED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Status:</b> Online & Operational\n"
        f"🤖 <b>Bot Username:</b> @{bot_username}\n"
        f"👤 <b>Target Chat ID:</b> <code>{chat_id}</code>\n"
        f"🕒 <b>Current Time:</b> <code>{now_sast_str}</code>\n"
        f"🌍 <b>Timezone:</b> {settings.DISPLAY_TIMEZONE_NAME}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>BANDI 30-minute high-impact alert engine is active.</i>"
    )
