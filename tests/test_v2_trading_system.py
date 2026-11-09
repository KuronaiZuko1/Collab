"""
Comprehensive Unit and Integration Tests for BANDI V2 Trading System.
Verifies fundamental surprise scoring, pair biases, price action patterns,
strategy evaluation, position sizing, deterministic risk rules, idempotency,
Telegram approval authorization, and EA telemetry/order integration.
"""

import time
import pytest
from datetime import datetime, timezone

from bandi.config import settings
from bandi.database.db import db
from bandi.strategy.price_action import Candle, PriceActionStrategy
from bandi.research.fundamental_engine import FundamentalEngine
from bandi.research.indicator_metadata import match_indicator_metadata, parse_numeric_figure
from bandi.mt5.risk import RiskManager
from bandi.mt5.bridge import MT5Bridge
from bandi.engine.decision import DecisionEngine
from bandi.telegram.bot import TelegramNotifier


# -----------------------------------------------------------------------------
# 1. Fundamental & Surprise Scoring Tests
# -----------------------------------------------------------------------------
def test_indicator_metadata_matching():
    cpi_meta = match_indicator_metadata("Core Consumer Price Index YoY")
    assert cpi_meta is not None
    assert cpi_meta["polarity"] == 1
    assert cpi_meta["weight"] == 1.0

    unemp_meta = match_indicator_metadata("Unemployment Rate")
    assert unemp_meta is not None
    assert unemp_meta["polarity"] == -1  # Higher unemployment is bearish

    assert parse_numeric_figure("254K") == 254.0
    assert parse_numeric_figure("3.2%") == 3.2


def test_surprise_scoring_and_pair_bias():
    fe = FundamentalEngine()
    # Process event surprise for test event
    ev = {
        "id": "test-cpi-event-99",
        "title": "Consumer Price Index YoY",
        "currency": "USD",
        "impact": "high",
        "event_time_utc": datetime.now(timezone.utc).isoformat(),
        "event_ts": int(time.time()),
        "forecast": "2.4%",
        "previous": "2.3%",
        "actual": "2.7%",  # Surprise beat of +0.3%
        "status": "completed",
        "source": "test"
    }
    db.upsert_economic_event(ev)
    fe.process_event_surprises()

    # Verify score in DB
    scores = db.get_event_scores("USD", limit=5)
    assert len(scores) >= 1
    assert scores[0]["raw_surprise"] > 0

    # Calculate currency score
    usd_score = fe.calculate_currency_score("USD")
    assert usd_score["score"] > 0

    # Calculate pair bias for EURUSD (USD strong -> EURUSD bearish)
    bias = fe.calculate_pair_bias("EURUSD")
    assert bias["symbol"] == "EURUSD"
    assert bias["bias_label"] in ("BEAR", "STRONG_BEAR", "NEUTRAL")


# -----------------------------------------------------------------------------
# 2. Price Action Patterns & Key Level Tests
# -----------------------------------------------------------------------------
def test_pin_bar_patterns():
    strat = PriceActionStrategy()
    atr = 0.0010

    # Bullish Pin Bar: small body, huge lower wick
    bull_pin = Candle("EURUSD", "H1", 1000, open=1.0820, high=1.0822, low=1.0790, close=1.0821)
    assert strat.is_bullish_pin_bar(bull_pin, atr) is True
    assert strat.is_bearish_pin_bar(bull_pin, atr) is False

    # Bearish Pin Bar: small body, huge upper wick
    bear_pin = Candle("EURUSD", "H1", 2000, open=1.0880, high=1.0910, low=1.0878, close=1.0879)
    assert strat.is_bearish_pin_bar(bear_pin, atr) is True
    assert strat.is_bullish_pin_bar(bear_pin, atr) is False


def test_engulfing_patterns():
    strat = PriceActionStrategy()
    atr = 0.0010

    # Bullish Engulfing
    c_prev = Candle("EURUSD", "H1", 1000, open=1.0850, high=1.0855, low=1.0830, close=1.0832) # Bearish
    c_curr = Candle("EURUSD", "H1", 2000, open=1.0830, high=1.0865, low=1.0828, close=1.0860) # Bullish engulfing
    assert strat.is_bullish_engulfing(c_curr, c_prev, atr) is True

    # Bearish Engulfing
    c_prev_bull = Candle("EURUSD", "H1", 3000, open=1.0830, high=1.0860, low=1.0828, close=1.0858)
    c_curr_bear = Candle("EURUSD", "H1", 4000, open=1.0860, high=1.0862, low=1.0820, close=1.0825)
    assert strat.is_bearish_engulfing(c_curr_bear, c_prev_bull, atr) is True


def test_key_level_detection():
    strat = PriceActionStrategy()
    atr = 0.0010
    # Sequence testing swing high at 1.0900
    candles = [
        Candle("EURUSD", "H1", 100, 1.0850, 1.0860, 1.0840, 1.0855),
        Candle("EURUSD", "H1", 200, 1.0855, 1.0880, 1.0850, 1.0875),
        Candle("EURUSD", "H1", 300, 1.0875, 1.0900, 1.0870, 1.0890), # Swing high
        Candle("EURUSD", "H1", 400, 1.0890, 1.0885, 1.0860, 1.0870),
        Candle("EURUSD", "H1", 500, 1.0870, 1.0865, 1.0840, 1.0850),
        Candle("EURUSD", "H1", 600, 1.0850, 1.0860, 1.0835, 1.0845),
        Candle("EURUSD", "H1", 700, 1.0845, 1.0855, 1.0830, 1.0840),
        Candle("EURUSD", "H1", 800, 1.0840, 1.0850, 1.0825, 1.0835),
        Candle("EURUSD", "H1", 900, 1.0835, 1.0845, 1.0820, 1.0830),
        Candle("EURUSD", "H1", 1000, 1.0830, 1.0840, 1.0815, 1.0825),
    ]
    levels = strat.detect_key_levels(candles, atr)
    assert len(levels) >= 1
    level_prices = [l["price"] for l in levels]
    assert any(abs(p - 1.0900) < 0.0005 for p in level_prices)


# -----------------------------------------------------------------------------
# 3. Risk Management & Order Gate Tests
# -----------------------------------------------------------------------------
def test_risk_gate_mandatory_stop_loss():
    rm = RiskManager()
    rm.trading_locked = False
    settings.TRADING_MODE = "AUTO"

    # Order without SL must be blocked
    ok, reason = rm.check_trade_permission(
        symbol="EURUSD",
        current_spread_points=12.0,
        daily_drawdown_pct=0.5,
        open_positions_count=1,
        requested_volume=0.1,
        sl=0.0 # Missing SL
    )
    assert ok is False
    assert "MANDATORY RISK" in reason


def test_risk_gate_kill_switch():
    rm = RiskManager()
    rm.trading_locked = False
    settings.TRADING_MODE = "AUTO"

    # Engage kill switch
    settings.set_kill_switch(True)
    ok, reason = rm.check_trade_permission(
        symbol="EURUSD",
        current_spread_points=12.0,
        daily_drawdown_pct=0.5,
        open_positions_count=1,
        requested_volume=0.1,
        sl=1.0800
    )
    assert ok is False
    assert "EMERGENCY KILL SWITCH" in reason
    # Disengage
    settings.set_kill_switch(False)


def test_risk_gate_live_account_refusal_without_confirmation():
    rm = RiskManager()
    rm.trading_locked = False
    settings.TRADING_MODE = "AUTO"
    settings.MT5_DEMO_MODE = False
    settings.LIVE_TRADING_CONFIRMED = False

    # Live account rejected without confirmation
    ok, reason = rm.check_trade_permission(
        symbol="EURUSD",
        current_spread_points=12.0,
        daily_drawdown_pct=0.5,
        open_positions_count=1,
        requested_volume=0.1,
        sl=1.0800,
        account_trade_mode="REAL"
    )
    assert ok is False
    assert "SECURITY REFUSAL" in reason

    # Restore settings
    settings.MT5_DEMO_MODE = True
    settings.LIVE_TRADING_CONFIRMED = False
    settings.TRADING_MODE = "OFF"
    rm.trading_locked = True


def test_position_sizing_calculation():
    rm = RiskManager()
    rm.risk_per_trade_pct = 1.0
    # $10,000 equity, 20 pips SL (200 points), $10/pip standard lot -> 1% risk = $100 -> lot = 0.50
    lot = rm.calculate_position_size(
        account_equity=10000.0,
        stop_distance_points=200.0,
        point_value=1.0
    )
    assert lot == 0.50


# -----------------------------------------------------------------------------
# 4. Telegram Authorization & Signal Idempotency Tests
# -----------------------------------------------------------------------------
def test_telegram_unauthorized_user_ignored():
    tn = TelegramNotifier(bot_token="test_token", chat_id="1916380095", enabled=True)
    # Simulate command from unauthorized user ID
    tn._handle_command("/halt", user_id="999999999")
    # Kill switch should NOT be engaged by stranger
    assert settings.is_kill_switch_active() is False


def test_signal_idempotency(tmp_path):
    engine = DecisionEngine()
    sig_id = f"sig_TEST_IDEMPOTENCY_{int(time.time() * 1000)}"
    signal_dict = {
        "signal_id": sig_id,
        "symbol": "EURUSD",
        "timeframe": "H1",
        "direction": "BUY",
        "entry_price": 1.0850,
        "sl": 1.0810,
        "tp": 1.0930,
        "rr": 2.0,
        "confidence": 85.0,
        "reasons": ["Test pattern"],
        "status": "ACTIVE",
        "expiry_ts": int(time.time() + 3600)
    }

    # First save succeeds
    res1 = db.save_signal(signal_dict)
    assert res1 is True

    # Duplicate save with same ID fails gracefully
    res2 = db.save_signal(signal_dict)
    assert res2 is False


# -----------------------------------------------------------------------------
# 5. Integration Test: Telemetry, Orders, and Execution
# -----------------------------------------------------------------------------
def test_ea_telemetry_order_fill_integration():
    bridge = MT5Bridge()

    # Step 1: EA posts telemetry
    telemetry = {
        "symbol": "EURUSD",
        "bid": 1.08450,
        "ask": 1.08465,
        "spread": 15.0,
        "balance": 10500.0,
        "equity": 10520.0,
        "account": 1234567,
        "broker": "JustMarkets",
        "trade_mode": "DEMO"
    }
    sync_resp = bridge.ingest_telemetry(telemetry)
    assert sync_resp["status"] == "ok"
    assert bridge.is_connected() is True

    # Step 2: Server queues an order for EA
    order_id = bridge.queue_order({
        "signal_id": "sig_test_01",
        "symbol": "EURUSD",
        "direction": "BUY",
        "volume": 0.05,
        "entry_price": 1.08465,
        "sl": 1.08100,
        "tp": 1.09200
    })
    assert order_id.startswith("ord_")

    # Step 3: EA polls pending orders
    pending = bridge.get_pending_orders()
    assert len(pending) == 1
    assert pending[0]["order_id"] == order_id

    # Step 4: EA reports execution result
    bridge.record_order_result({
        "order_id": order_id,
        "success": True,
        "ticket": 7891011,
        "message": "Executed at retcode 10009"
    })
    assert len(bridge._order_results) == 1
    assert bridge._order_results[0]["ticket"] == 7891011
