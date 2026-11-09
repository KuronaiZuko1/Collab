"""
Deterministic Risk Management Module for BANDI.
Enforces hard safety boundaries, capital preservation rules, and trade execution locking.
Serves as the mandatory single gate that every order request must pass through.
AI, external scripts, and strategies CANNOT bypass these rules.
"""

from __future__ import annotations
import time
import logging
from typing import Tuple, Dict, Any, List, Optional
from datetime import datetime, timezone

from bandi.config import settings
from bandi.database.db import db

logger = logging.getLogger("bandi.risk")

# Supported sessions in UTC hours
SESSION_HOURS = {
    "London": (8, 17),    # 08:00 - 17:00 UTC
    "New York": (13, 22), # 13:00 - 22:00 UTC
    "Asian": (0, 9)       # 00:00 - 09:00 UTC
}


class RiskManager:
    def __init__(self):
        self.trading_mode = settings.TRADING_MODE
        self.trading_locked = settings.RISK_TRADING_LOCKED
        self.max_daily_drawdown_pct = settings.RISK_MAX_DAILY_DRAWDOWN_PCT
        self.weekly_loss_limit_pct = settings.WEEKLY_LOSS_LIMIT_PCT
        self.max_consecutive_losses = settings.MAX_CONSECUTIVE_LOSSES
        self.max_open_positions = settings.RISK_MAX_OPEN_POSITIONS
        self.max_spread_points = settings.RISK_MAX_SPREAD_POINTS
        self.max_lot = settings.MAX_LOT
        self.risk_per_trade_pct = settings.RISK_PER_TRADE_PCT
        self.min_rr = settings.MIN_RR
        self.max_trades_per_day = settings.MAX_TRADES_PER_DAY
        self.max_correlated_usd = settings.MAX_CORRELATED_USD_POSITIONS
        self.news_before_min = settings.NEWS_BLACKOUT_BEFORE_MIN
        self.news_after_min = settings.NEWS_BLACKOUT_AFTER_MIN
        self.allowed_sessions = [s.strip() for s in settings.ALLOWED_SESSIONS.split(",") if s.strip()]

    def is_within_session(self, current_dt_utc: Optional[datetime] = None) -> bool:
        """Check if current UTC time falls within configured allowed trading sessions."""
        now = current_dt_utc or datetime.now(timezone.utc)
        hour = now.hour

        # Check weekend filter: Friday post 21:00 UTC or Saturday/Sunday
        weekday = now.weekday()  # 0=Monday, ..., 4=Friday, 5=Saturday, 6=Sunday
        if weekday == 4 and hour >= 21:
            return False  # Friday late session
        if weekday in (5, 6):
            return False  # Weekend

        for session in self.allowed_sessions:
            if session in SESSION_HOURS:
                start_h, end_h = SESSION_HOURS[session]
                if start_h <= hour < end_h:
                    return True
        return False

    def is_in_news_blackout(self, symbol: str, current_ts: Optional[float] = None) -> Tuple[bool, str]:
        """
        Check if current time is within high-impact news blackout window for symbol's currencies.
        Default window: 30 mins before, 15 mins after release.
        """
        now = current_ts if current_ts is not None else time.time()
        before_sec = self.news_before_min * 60
        after_sec = self.news_after_min * 60

        # Query events from DB in window [now - after_sec, now + before_sec]
        try:
            events = db.get_upcoming_events(
                from_ts=int(now - after_sec),
                to_ts=int(now + before_sec),
                high_impact_only=True
            )
            for ev in events:
                affected = ev.get("affected_instruments") or []
                ev_currency = ev.get("currency", "")
                if symbol.upper().startswith(ev_currency) or symbol.upper().endswith(ev_currency) or symbol in affected:
                    ev_ts = ev["event_ts"]
                    diff_min = round((ev_ts - now) / 60.0, 1)
                    if diff_min >= 0:
                        return True, f"NEWS BLACKOUT: {ev['title']} ({ev_currency}) scheduled in {diff_min}m"
                    else:
                        return True, f"NEWS BLACKOUT: {ev['title']} ({ev_currency}) released {-diff_min}m ago"
        except Exception as e:
            logger.error("Error checking news blackout: %s", e)

        return False, ""

    def check_trade_permission(
        self,
        symbol: str,
        current_spread_points: float,
        daily_drawdown_pct: float,
        open_positions_count: int,
        requested_volume: float,
        sl: float = 0.0,
        tp: float = 0.0,
        account_trade_mode: str = "DEMO",
        telemetry_age_seconds: float = 0.0,
        weekly_drawdown_pct: float = 0.0,
        consecutive_losses: int = 0,
        today_trades_count: int = 0,
        open_usd_positions_count: int = 0,
        current_dt_utc: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Comprehensive order gate evaluation.
        Every single order candidate MUST pass this check before dispatch.
        Returns:
            (allowed: bool, reason: str)
        """
        # 1. Emergency Kill Switch Check
        if settings.is_kill_switch_active():
            return False, "EMERGENCY KILL SWITCH ACTIVE: All trading activities halted."

        # 2. Hard Trading Mode & Lock Check
        if self.trading_locked:
            return False, "SAFETY ENFORCED: Live order execution is locked in read-only mode."

        if settings.TRADING_MODE in ("OFF", "SIGNALS_ONLY"):
            return False, f"EXECUTION GUARD: Trading mode is {settings.TRADING_MODE}. Orders blocked."

        # 3. Live Account Protection Guard
        is_live_account = (account_trade_mode.upper() in ("REAL", "LIVE", "2"))
        if is_live_account:
            if settings.MT5_DEMO_MODE:
                return False, "DEMO MODE CONFIGURED: Terminal reports REAL account but MT5_DEMO_MODE is true."
            if not settings.LIVE_TRADING_CONFIRMED:
                return False, "SECURITY REFUSAL: Cannot trade live account without LIVE_TRADING_CONFIRMED=true."

        # 4. Telemetry Freshness Check
        if telemetry_age_seconds > 30.0:
            return False, f"STALE TELEMETRY: Last MT5 heartbeat was {telemetry_age_seconds:.1f}s ago (>30s limit)."

        # 5. Mandatory Stop Loss Check
        if sl <= 0.0:
            return False, "MANDATORY RISK: Orders without a verified stop loss are strictly prohibited."

        # 6. Volume Bounds Check
        if requested_volume <= 0.0:
            return False, "INVALID VOLUME: Order volume must be greater than 0.0."

        if requested_volume > self.max_lot:
            return False, f"LOT LIMIT: Requested volume ({requested_volume} lots) exceeds maximum allowable ({self.max_lot} lots)."

        # 7. Spread Check
        if current_spread_points > self.max_spread_points:
            return False, f"SPREAD PROTECTION: Current spread ({current_spread_points:.1f} pts) exceeds threshold ({self.max_spread_points} pts)."

        # 8. Daily Drawdown Limit
        if daily_drawdown_pct >= self.max_daily_drawdown_pct:
            return False, f"LIMIT BREACH: Daily drawdown ({daily_drawdown_pct:.2f}%) exceeds maximum allowable ({self.max_daily_drawdown_pct:.2f}%)."

        # 9. Weekly Drawdown Limit
        if weekly_drawdown_pct >= self.weekly_loss_limit_pct:
            return False, f"LIMIT BREACH: Weekly loss ({weekly_drawdown_pct:.2f}%) exceeds limit ({self.weekly_loss_limit_pct:.2f}%)."

        # 10. Consecutive Losses Pause
        if consecutive_losses >= self.max_consecutive_losses:
            return False, f"LOSS PAUSE: Consecutive losses ({consecutive_losses}) hit maximum threshold ({self.max_consecutive_losses}). Trading paused."

        # 11. Open Positions Count
        if open_positions_count >= self.max_open_positions:
            return False, f"LIMIT BREACH: Open positions count ({open_positions_count}) has reached maximum limit ({self.max_open_positions})."

        # 12. Maximum Trades Per Day
        if today_trades_count >= self.max_trades_per_day:
            return False, f"DAILY CAP: Daily trade limit ({self.max_trades_per_day}) reached for today."

        # 13. Correlated USD Exposure Filter
        if ("USD" in symbol.upper()) and (open_usd_positions_count >= self.max_correlated_usd):
            return False, f"CORRELATION LIMIT: Maximum concurrent USD exposure ({self.max_correlated_usd} positions) reached."

        # 14. Session Filter
        if not self.is_within_session(current_dt_utc):
            return False, f"SESSION FILTER: Outside allowed trading sessions ({', '.join(self.allowed_sessions)})."

        # 15. News Blackout Window
        ref_ts = current_dt_utc.timestamp() if current_dt_utc is not None else None
        in_blackout, blackout_reason = self.is_in_news_blackout(symbol, current_ts=ref_ts)
        if in_blackout:
            return False, blackout_reason

        return True, "Deterministic risk checks passed."

    def calculate_position_size(
        self,
        account_equity: float,
        stop_distance_points: float,
        point_value: float = 1.0,
        lot_step: float = 0.01,
        min_lot: float = 0.01
    ) -> float:
        """
        Calculate position size based on fixed fractional risk per trade.
        lot = (equity * risk_pct) / (stop_distance_points * point_value)
        """
        if account_equity <= 0 or stop_distance_points <= 0 or point_value <= 0:
            return min_lot

        risk_amount = account_equity * (self.risk_per_trade_pct / 100.0)
        risk_per_lot = stop_distance_points * point_value

        if risk_per_lot <= 0:
            return min_lot

        raw_lot = risk_amount / risk_per_lot
        # Round to lot step
        steps = round(raw_lot / lot_step)
        lot = max(min_lot, min(self.max_lot, steps * lot_step))
        return round(lot, 2)

    def get_status(self) -> Dict[str, Any]:
        """Return current risk engine parameters and state."""
        return {
            "trading_mode": settings.TRADING_MODE,
            "trading_locked": self.trading_locked,
            "kill_switch_active": settings.is_kill_switch_active(),
            "max_daily_drawdown_pct": self.max_daily_drawdown_pct,
            "weekly_loss_limit_pct": self.weekly_loss_limit_pct,
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_open_positions": self.max_open_positions,
            "max_spread_points": self.max_spread_points,
            "max_lot": self.max_lot,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "min_rr": self.min_rr,
            "max_trades_per_day": self.max_trades_per_day,
            "allowed_sessions": self.allowed_sessions,
            "news_blackout_before_min": self.news_before_min,
            "news_blackout_after_min": self.news_after_min
        }


# Global risk manager instance
risk_manager = RiskManager()
