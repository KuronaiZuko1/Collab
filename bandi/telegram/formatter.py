"""
Telegram Alert and Signal Formatter for BANDI.
Produces clean, professional, high-clarity HTML messages for economic alerts,
trade strategy signals, approval requests, and execution notices.
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
    """Format scheduled high-impact release alert for Telegram."""
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
    affected_str = ", ".join(affected) if isinstance(affected, list) else str(affected)

    forecast = event.get("forecast") or "N/A"
    previous = event.get("previous") or "N/A"

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


def format_strategy_signal(
    signal: Any,
    lot_size: float = 0.01,
    risk_pct: float = 1.0
) -> str:
    """Format trade strategy signal message."""
    dir_icon = "🟢" if signal.direction == "BUY" else "🔴"
    reasons_str = "\n".join([f"  • {r}" for r in signal.reasons])
    expiry_sast = settings.ts_to_sast_str(signal.expiry_ts)

    msg = (
        f"<b>{dir_icon} BANDI SIGNAL | {signal.direction} {signal.symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Timeframe:</b> {signal.timeframe} | <b>Confidence:</b> {signal.confidence:.0f}%\n"
        f"<b>Entry Price:</b> <code>{signal.entry_price:.5f}</code>\n"
        f"<b>Stop Loss:</b> <code>{signal.sl:.5f}</code>\n"
        f"<b>Take Profit:</b> <code>{signal.tp:.5f}</code>\n"
        f"<b>Risk:Reward:</b> 1 : {signal.rr:.2f}\n"
        f"<b>Recommended Lot:</b> <code>{lot_size:.2f}</code> (~{risk_pct:.1f}% risk)\n\n"
        f"<b>🧠 Fundamental Bias:</b> <code>{signal.fundamental_bias}</code>\n"
        f"<b>📊 Price Action Triggers:</b>\n{reasons_str}\n\n"
        f"<b>⏳ Signal Valid Until:</b> <code>{expiry_sast}</code>\n"
        f"<b>🆔 ID:</b> <code>{signal.signal_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Mode: [{settings.TRADING_MODE}]</i>"
    )
    return msg


def format_order_execution_notice(order: Dict[str, Any], ticket: int = 0) -> str:
    """Format order execution notification."""
    dir_icon = "🟢" if order.get("direction") == "BUY" else "🔴"
    return (
        f"<b>⚡ BANDI ORDER EXECUTED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{dir_icon} <b>Action:</b> {order.get('direction')} {order.get('symbol')}\n"
        f"<b>Volume:</b> {order.get('volume')} lots\n"
        f"<b>Ticket:</b> <code>#{ticket}</code>\n"
        f"<b>Stop Loss:</b> <code>{order.get('sl')}</code>\n"
        f"<b>Take Profit:</b> <code>{order.get('tp')}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Order managed by Bandi MT5 Bridge</i>"
    )


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
        f"⚙️ <b>Trading Mode:</b> [{settings.TRADING_MODE}]\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>BANDI 30-minute alert & signal engine active.</i>"
    )
