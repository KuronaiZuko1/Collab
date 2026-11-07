"""
Unit tests for deterministic risk manager, symbol resolution, and MT5 bridge.
"""

from bandi.mt5.risk import RiskManager
from bandi.research.watchlist import resolve_broker_symbol, get_standard_symbol_info
from bandi.mt5.bridge import MT5Bridge


def test_deterministic_risk_manager_hard_lock():
    rm = RiskManager()
    rm.trading_locked = True

    # Even with all good numbers, live execution must be rejected
    allowed, reason = rm.check_trade_permission(
        symbol="EURUSD",
        current_spread_points=12.0,
        daily_drawdown_pct=0.5,
        open_positions_count=1,
        requested_volume=0.01
    )
    assert allowed is False
    assert "READ-ONLY" in reason.upper()


def test_risk_manager_limits_when_unlocked():
    rm = RiskManager()
    rm.trading_locked = False
    rm.max_daily_drawdown_pct = 3.0
    rm.max_spread_points = 30.0
    rm.max_open_positions = 5

    # Passing case
    ok, _ = rm.check_trade_permission("EURUSD", current_spread_points=15.0, daily_drawdown_pct=1.0, open_positions_count=2, requested_volume=0.05)
    assert ok is True

    # Spread breach
    ok, reason = rm.check_trade_permission("EURUSD", current_spread_points=45.0, daily_drawdown_pct=1.0, open_positions_count=2, requested_volume=0.05)
    assert ok is False
    assert "SPREAD PROTECTION" in reason

    # Drawdown breach
    ok, reason = rm.check_trade_permission("EURUSD", current_spread_points=15.0, daily_drawdown_pct=3.5, open_positions_count=2, requested_volume=0.05)
    assert ok is False
    assert "LIMIT BREACH" in reason


def test_broker_symbol_resolution():
    broker_symbols = ["EURUSDm", "GOLDm", "DE40", "US30Cash", "GBPUSD."]

    assert resolve_broker_symbol("EURUSD", broker_symbols) == "EURUSDm"
    assert resolve_broker_symbol("XAUUSD", broker_symbols) == "GOLDm"
    assert resolve_broker_symbol("GER40", broker_symbols) == "DE40"
    assert resolve_broker_symbol("US30", broker_symbols) == "US30Cash"
    assert resolve_broker_symbol("GBPUSD", broker_symbols) == "GBPUSD."
    assert resolve_broker_symbol("NZDUSD", broker_symbols) is None


def test_mt5_bridge_disconnected_graceful_handling():
    bridge = MT5Bridge()
    # No ticks received yet
    assert bridge.is_connected() is False
    status = bridge.get_status()
    assert status["connected"] is False
    assert status["account"] is None
