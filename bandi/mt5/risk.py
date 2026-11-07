"""
Deterministic Risk Management Module for BANDI.
Enforces hard safety boundaries and trade execution locking.
AI or automated scripts can NEVER override these rules.
"""

from __future__ import annotations
import logging
from typing import Tuple, Dict, Any
from bandi.config import settings

logger = logging.getLogger("bandi.risk")


class RiskManager:
    def __init__(self):
        self.max_daily_drawdown_pct = settings.RISK_MAX_DAILY_DRAWDOWN_PCT
        self.max_open_positions = settings.RISK_MAX_OPEN_POSITIONS
        self.max_spread_points = settings.RISK_MAX_SPREAD_POINTS
        self.trading_locked = settings.RISK_TRADING_LOCKED

    def check_trade_permission(
        self,
        symbol: str,
        current_spread_points: float,
        daily_drawdown_pct: float,
        open_positions_count: int,
        requested_volume: float
    ) -> Tuple[bool, str]:
        """
        Evaluate hard risk constraints before any order can even be considered.
        Returns:
            (allowed: bool, reason: str)
        """
        # Hard Lock: Initial release strictly enforces read-only mode
        if self.trading_locked:
            return False, "SAFETY ENFORCED: Live order execution is locked in read-only mode."

        if daily_drawdown_pct >= self.max_daily_drawdown_pct:
            return False, f"LIMIT BREACH: Daily drawdown ({daily_drawdown_pct:.2f}%) exceeds maximum allowable ({self.max_daily_drawdown_pct:.2f}%)."

        if open_positions_count >= self.max_open_positions:
            return False, f"LIMIT BREACH: Open positions count ({open_positions_count}) has reached maximum limit ({self.max_open_positions})."

        if current_spread_points > self.max_spread_points:
            return False, f"SPREAD PROTECTION: Current spread ({current_spread_points:.1f} pts) exceeds threshold ({self.max_spread_points} pts)."

        if requested_volume <= 0.0:
            return False, "INVALID VOLUME: Order volume must be greater than 0.0."

        return True, "Deterministic risk checks passed."

    def get_status(self) -> Dict[str, Any]:
        """Return current risk engine parameters and lock state."""
        return {
            "trading_locked": self.trading_locked,
            "max_daily_drawdown_pct": self.max_daily_drawdown_pct,
            "max_open_positions": self.max_open_positions,
            "max_spread_points": self.max_spread_points,
            "policy": "Read-Only Intelligence Guard"
        }


# Global risk manager instance
risk_manager = RiskManager()
