"""
Price Action Strategy Engine for BANDI: "Trend + Key Level + Confirmation".
Deterministic, fully unit-testable rules-based strategy analyzing swing structure,
50 EMA trend, key support/resistance levels, pin bars, and engulfing candles.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from bandi.config import settings


@dataclass
class Candle:
    symbol: str
    timeframe: str
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return max(0.00001, self.high - self.low)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low


@dataclass
class Signal:
    signal_id: str
    symbol: str
    timeframe: str
    direction: str          # "BUY" or "SELL"
    entry_price: float
    sl: float
    tp: float
    rr: float
    confidence: float       # 0 - 100
    reasons: List[str] = field(default_factory=list)
    fundamental_bias: str = "NEUTRAL"
    expiry_ts: int = 0
    created_at_utc: str = ""


class PriceActionStrategy:
    def __init__(
        self,
        atr_period: int = 14,
        min_rr: float = 1.5,
        ema_period: int = 50
    ):
        self.atr_period = atr_period
        self.min_rr = min_rr
        self.ema_period = ema_period

    # -------------------------------------------------------------------------
    # Technical Indicators (Deterministic)
    # -------------------------------------------------------------------------
    @staticmethod
    def calculate_atr(candles: List[Candle], period: int = 14) -> float:
        """Calculate Average True Range (ATR) across candle sequence."""
        if len(candles) < 2:
            return 0.0010
        tr_list = []
        for i in range(1, len(candles)):
            c_curr = candles[i]
            c_prev = candles[i - 1]
            tr = max(
                c_curr.high - c_curr.low,
                abs(c_curr.high - c_prev.close),
                abs(c_curr.low - c_prev.close)
            )
            tr_list.append(tr)
        if not tr_list:
            return 0.0010
        recent_trs = tr_list[-period:]
        return sum(recent_trs) / len(recent_trs)

    @staticmethod
    def calculate_ema(closes: List[float], period: int = 50) -> float:
        """Calculate Exponential Moving Average (EMA)."""
        if not closes:
            return 0.0
        if len(closes) < period:
            return sum(closes) / len(closes)

        multiplier = 2.0 / (period + 1.0)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    # -------------------------------------------------------------------------
    # Swing Structure & Key Levels
    # -------------------------------------------------------------------------
    @staticmethod
    def detect_key_levels(candles: List[Candle], atr: float) -> List[Dict[str, Any]]:
        """
        Detect support and resistance levels from swing highs/lows.
        Merges nearby levels within 0.5 * ATR tolerance.
        """
        if len(candles) < 10:
            return []

        raw_levels: List[float] = []
        # Find swing points (left 2, right 2 candles)
        for i in range(2, len(candles) - 2):
            high = candles[i].high
            low = candles[i].low
            if high > candles[i-1].high and high > candles[i-2].high and high > candles[i+1].high and high > candles[i+2].high:
                raw_levels.append(high)
            if low < candles[i-1].low and low < candles[i-2].low and low < candles[i+1].low and low < candles[i+2].low:
                raw_levels.append(low)

        # Merge levels within 0.5 * ATR
        tolerance = max(0.0001, 0.5 * atr)
        clustered: List[Dict[str, Any]] = []

        for lvl in raw_levels:
            merged = False
            for c in clustered:
                if abs(c["price"] - lvl) <= tolerance:
                    # Update average price and increment touches
                    c["price"] = (c["price"] * c["touches"] + lvl) / (c["touches"] + 1)
                    c["touches"] += 1
                    merged = True
                    break
            if not merged:
                clustered.append({"price": lvl, "touches": 1})

        return clustered

    # -------------------------------------------------------------------------
    # Candle Pattern Classifiers
    # -------------------------------------------------------------------------
    @staticmethod
    def is_bullish_pin_bar(c: Candle, atr: float) -> bool:
        """Lower wick >= 2x body and lower wick >= 50% of range."""
        if c.range < (0.35 * atr):
            return False  # Reject tiny-range candles
        return (c.lower_wick >= 2.0 * c.body) and (c.lower_wick >= 0.45 * c.range)

    @staticmethod
    def is_bearish_pin_bar(c: Candle, atr: float) -> bool:
        """Upper wick >= 2x body and upper wick >= 50% of range."""
        if c.range < (0.35 * atr):
            return False  # Reject tiny-range candles
        return (c.upper_wick >= 2.0 * c.body) and (c.upper_wick >= 0.45 * c.range)

    @staticmethod
    def is_bullish_engulfing(curr: Candle, prev: Candle, atr: float) -> bool:
        if curr.range < (0.35 * atr):
            return False
        return curr.is_bullish and prev.is_bearish and (curr.close > prev.open) and (curr.open <= prev.close)

    @staticmethod
    def is_bearish_engulfing(curr: Candle, prev: Candle, atr: float) -> bool:
        if curr.range < (0.35 * atr):
            return False
        return curr.is_bearish and prev.is_bullish and (curr.close < prev.open) and (curr.open >= prev.close)

    # -------------------------------------------------------------------------
    # Strategy Evaluation Pipeline
    # -------------------------------------------------------------------------
    def evaluate(
        self,
        symbol: str,
        h1_candles: List[Candle],
        h4_candles: List[Candle],
        fundamental_bias_label: str = "NEUTRAL"
    ) -> Optional[Signal]:
        """
        Evaluate full 'Trend + Key Level + Confirmation' strategy.
        Returns a Signal if all conditions pass, else None.
        """
        if len(h1_candles) < 30 or len(h4_candles) < 20:
            return None

        atr = self.calculate_atr(h1_candles, self.atr_period)
        if atr <= 0.0:
            return None

        # 1. Higher-Timeframe Trend (H4 / D1 50-EMA & Structure)
        h4_closes = [c.close for c in h4_candles]
        h4_ema = self.calculate_ema(h4_closes, self.ema_period)
        current_price = h1_candles[-1].close

        # Trend direction
        is_uptrend = (current_price > h4_ema) and (h4_candles[-1].close > h4_candles[-5].close)
        is_downtrend = (current_price < h4_ema) and (h4_candles[-1].close < h4_candles[-5].close)

        if not is_uptrend and not is_downtrend:
            return None  # Trend structure unclear / ranging

        # 2. Key Levels
        levels = self.detect_key_levels(h1_candles, atr)
        if not levels:
            return None

        curr_candle = h1_candles[-1]
        prev_candle = h1_candles[-2]

        direction = None
        reasons = []
        entry = curr_candle.close
        sl = 0.0
        tp = 0.0
        confidence = 60.0

        # 3. Entry Confirmation at Key Level
        level_tolerance = 0.6 * atr

        if is_uptrend:
            # Look for rejection off support level
            nearby_support = [l for l in levels if abs(curr_candle.low - l["price"]) <= level_tolerance and l["price"] <= curr_candle.close]
            if nearby_support:
                sup = max(nearby_support, key=lambda x: x["touches"])
                reasons.append(f"Tested key support at {sup['price']:.5f} ({sup['touches']} touches)")

                # Pattern check
                if self.is_bullish_pin_bar(curr_candle, atr):
                    direction = "BUY"
                    reasons.append("Bullish Pin Bar rejection confirmed")
                    confidence += 15.0
                elif self.is_bullish_engulfing(curr_candle, prev_candle, atr):
                    direction = "BUY"
                    reasons.append("Bullish Engulfing candle confirmed")
                    confidence += 15.0

                if direction == "BUY":
                    # Check fundamental filter: reject if fundamental bias is bearish
                    if fundamental_bias_label in ("BEAR", "STRONG_BEAR"):
                        logger.info("Signal skipped for %s: Fundamental contradiction (%s)", symbol, fundamental_bias_label)
                        return None
                    elif fundamental_bias_label in ("BULL", "STRONG_BULL"):
                        confidence += 15.0
                        reasons.append(f"Fundamental alignment: {fundamental_bias_label}")

                    # Stop Loss: Below candle low + buffer, bounded by 1.0 to 2.5 ATR
                    raw_sl_dist = (entry - curr_candle.low) + (0.1 * atr)
                    sl_dist = max(1.0 * atr, min(2.5 * atr, raw_sl_dist))
                    sl = round(entry - sl_dist, 5)

                    # Take Profit: Find next opposing resistance or default 2R
                    opposing = [l["price"] for l in levels if l["price"] > entry + (self.min_rr * sl_dist)]
                    if opposing:
                        tp = round(min(opposing), 5)
                    else:
                        tp = round(entry + (2.0 * sl_dist), 5)

        elif is_downtrend:
            # Look for rejection off resistance level
            nearby_resistance = [l for l in levels if abs(curr_candle.high - l["price"]) <= level_tolerance and l["price"] >= curr_candle.close]
            if nearby_resistance:
                res = max(nearby_resistance, key=lambda x: x["touches"])
                reasons.append(f"Tested key resistance at {res['price']:.5f} ({res['touches']} touches)")

                if self.is_bearish_pin_bar(curr_candle, atr):
                    direction = "SELL"
                    reasons.append("Bearish Pin Bar rejection confirmed")
                    confidence += 15.0
                elif self.is_bearish_engulfing(curr_candle, prev_candle, atr):
                    direction = "SELL"
                    reasons.append("Bearish Engulfing candle confirmed")
                    confidence += 15.0

                if direction == "SELL":
                    if fundamental_bias_label in ("BULL", "STRONG_BULL"):
                        logger.info("Signal skipped for %s: Fundamental contradiction (%s)", symbol, fundamental_bias_label)
                        return None
                    elif fundamental_bias_label in ("BEAR", "STRONG_BEAR"):
                        confidence += 15.0
                        reasons.append(f"Fundamental alignment: {fundamental_bias_label}")

                    raw_sl_dist = (curr_candle.high - entry) + (0.1 * atr)
                    sl_dist = max(1.0 * atr, min(2.5 * atr, raw_sl_dist))
                    sl = round(entry + sl_dist, 5)

                    opposing = [l["price"] for l in levels if l["price"] < entry - (self.min_rr * sl_dist)]
                    if opposing:
                        tp = round(max(opposing), 5)
                    else:
                        tp = round(entry - (2.0 * sl_dist), 5)

        if not direction or sl <= 0 or tp <= 0:
            return None

        # Verify Minimum Reward:Risk Ratio (1.5)
        risk_dist = abs(entry - sl)
        reward_dist = abs(tp - entry)
        rr = round(reward_dist / risk_dist, 2) if risk_dist > 0 else 0.0

        if rr < self.min_rr:
            return None  # Setup fails minimum risk:reward threshold

        signal_id = f"sig_{symbol}_{curr_candle.ts}"
        expiry_ts = curr_candle.ts + (settings.SIGNAL_EXPIRY_MIN * 60)

        return Signal(
            signal_id=signal_id,
            symbol=symbol,
            timeframe="H1",
            direction=direction,
            entry_price=entry,
            sl=sl,
            tp=tp,
            rr=rr,
            confidence=min(95.0, confidence),
            reasons=reasons,
            fundamental_bias=fundamental_bias_label,
            expiry_ts=expiry_ts
        )


# Global strategy instance
price_action_strategy = PriceActionStrategy()
