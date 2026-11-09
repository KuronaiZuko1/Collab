"""
Backtesting Simulation Engine for BANDI.
Replays historical OHLC candles through the exact same price action strategy
and risk management parameters used live.
Models spread, slippage, commission, and bar-by-bar position execution with no look-ahead bias.
"""

from __future__ import annotations
import csv
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from bandi.strategy.price_action import Candle, Signal, PriceActionStrategy
from bandi.backtest.metrics import calculate_backtest_metrics

logger = logging.getLogger("bandi.backtest")


class BacktestEngine:
    def __init__(
        self,
        initial_balance: float = 10000.0,
        risk_per_trade_pct: float = 1.0,
        spread_points: float = 15.0,  # 1.5 pips
        slippage_points: float = 5.0,  # 0.5 pips
        commission_per_lot: float = 7.0, # $7 round-turn
        point_size: float = 0.0001,
        auto_breakeven_1r: bool = True
    ):
        self.initial_balance = initial_balance
        self.risk_pct = risk_per_trade_pct
        self.spread_points = spread_points
        self.slippage_points = slippage_points
        self.commission_per_lot = commission_per_lot
        self.point_size = point_size
        self.auto_be = auto_breakeven_1r
        self.strategy = PriceActionStrategy()

    def run(
        self,
        candles_h1: List[Candle],
        candles_h4: List[Candle],
        split_ratio: float = 0.70 # 70% In-sample, 30% Out-of-sample
    ) -> Dict[str, Any]:
        """
        Execute historical simulation across candle sequences.
        Avoids look-ahead bias by passing only historical bars available at bar time t.
        """
        if len(candles_h1) < 50:
            return {"error": "Insufficient candle data (need >= 50 H1 candles)"}

        closed_trades: List[Dict[str, Any]] = []
        open_trade: Optional[Dict[str, Any]] = None
        balance = self.initial_balance

        # Group H4 timestamps for lookback mapping
        h4_by_ts = {c.ts: c for c in candles_h4}

        # Step through H1 candles bar by bar
        for i in range(40, len(candles_h1)):
            current_bar = candles_h1[i]
            historical_h1 = candles_h1[:i+1]
            historical_h4 = [c for c in candles_h4 if c.ts <= current_bar.ts]

            # 1. Manage existing open trade
            if open_trade:
                trade_closed = False
                pos_dir = open_trade["direction"]
                entry_pr = open_trade["entry_price"]
                sl = open_trade["sl"]
                tp = open_trade["tp"]
                r_dist = open_trade["r_distance"]
                vol = open_trade["volume"]

                # Check Breakeven Movement at +1R
                if self.auto_be and not open_trade["be_moved"]:
                    if pos_dir == "BUY" and current_bar.high >= (entry_pr + r_dist):
                        open_trade["sl"] = entry_pr
                        open_trade["be_moved"] = True
                    elif pos_dir == "SELL" and current_bar.low <= (entry_pr - r_dist):
                        open_trade["sl"] = entry_pr
                        open_trade["be_moved"] = True

                # Check SL/TP Hits
                if pos_dir == "BUY":
                    if current_bar.low <= open_trade["sl"]:
                        # SL hit
                        exit_price = open_trade["sl"]
                        pnl_points = (exit_price - entry_pr) / self.point_size
                        pnl_usd = (pnl_points * 10.0 * vol) - (self.commission_per_lot * vol)
                        r_mult = -1.0 if not open_trade["be_moved"] else 0.0
                        trade_closed = True
                        close_reason = "STOP_LOSS" if not open_trade["be_moved"] else "BREAKEVEN"

                    elif current_bar.high >= tp:
                        # TP hit
                        exit_price = tp
                        pnl_points = (exit_price - entry_pr) / self.point_size
                        pnl_usd = (pnl_points * 10.0 * vol) - (self.commission_per_lot * vol)
                        r_mult = open_trade["rr"]
                        trade_closed = True
                        close_reason = "TAKE_PROFIT"

                elif pos_dir == "SELL":
                    if current_bar.high >= open_trade["sl"]:
                        exit_price = open_trade["sl"]
                        pnl_points = (entry_pr - exit_price) / self.point_size
                        pnl_usd = (pnl_points * 10.0 * vol) - (self.commission_per_lot * vol)
                        r_mult = -1.0 if not open_trade["be_moved"] else 0.0
                        trade_closed = True
                        close_reason = "STOP_LOSS" if not open_trade["be_moved"] else "BREAKEVEN"

                    elif current_bar.low <= tp:
                        exit_price = tp
                        pnl_points = (entry_pr - exit_price) / self.point_size
                        pnl_usd = (pnl_points * 10.0 * vol) - (self.commission_per_lot * vol)
                        r_mult = open_trade["rr"]
                        trade_closed = True
                        close_reason = "TAKE_PROFIT"

                if trade_closed:
                    balance += pnl_usd
                    closed_record = {
                        "trade_id": open_trade["trade_id"],
                        "symbol": open_trade["symbol"],
                        "direction": pos_dir,
                        "volume": vol,
                        "entry_price": entry_pr,
                        "exit_price": exit_price,
                        "sl": open_trade["sl"],
                        "tp": tp,
                        "pnl": round(pnl_usd, 2),
                        "r_multiple": round(r_mult, 2),
                        "close_reason": close_reason,
                        "entry_ts": open_trade["entry_ts"],
                        "exit_ts": current_bar.ts,
                        "index": i
                    }
                    closed_trades.append(closed_record)
                    open_trade = None

            # 2. Check for new setup if flat
            if not open_trade:
                sig = self.strategy.evaluate(
                    symbol=current_bar.symbol,
                    h1_candles=historical_h1,
                    h4_candles=historical_h4,
                    fundamental_bias_label="NEUTRAL" # or historical bias
                )

                if sig:
                    # Apply slippage & spread to entry
                    spread_offset = (self.spread_points + self.slippage_points) * self.point_size
                    adjusted_entry = sig.entry_price + spread_offset if sig.direction == "BUY" else sig.entry_price - spread_offset

                    r_distance = abs(adjusted_entry - sig.sl)
                    if r_distance > 0:
                        risk_amt = balance * (self.risk_pct / 100.0)
                        dist_points = r_distance / self.point_size
                        vol = max(0.01, min(5.0, round(risk_amt / (dist_points * 10.0), 2)))

                        open_trade = {
                            "trade_id": f"bt_{i}",
                            "symbol": sig.symbol,
                            "direction": sig.direction,
                            "entry_price": round(adjusted_entry, 5),
                            "sl": sig.sl,
                            "tp": sig.tp,
                            "rr": sig.rr,
                            "r_distance": r_distance,
                            "volume": vol,
                            "be_moved": False,
                            "entry_ts": current_bar.ts
                        }

        # Split In-Sample vs Out-of-Sample
        split_idx = int(len(candles_h1) * split_ratio)
        split_ts = candles_h1[split_idx].ts

        in_sample_trades = [t for t in closed_trades if t["entry_ts"] <= split_ts]
        out_sample_trades = [t for t in closed_trades if t["entry_ts"] > split_ts]

        full_metrics = calculate_backtest_metrics(closed_trades, self.initial_balance)
        in_metrics = calculate_backtest_metrics(in_sample_trades, self.initial_balance)
        out_metrics = calculate_backtest_metrics(out_sample_trades, self.initial_balance)

        return {
            "status": "completed",
            "total_bars_simulated": len(candles_h1),
            "split_ratio": split_ratio,
            "overall": full_metrics,
            "in_sample": in_metrics,
            "out_of_sample": out_metrics,
            "trades": closed_trades
        }


# Global backtest engine instance
backtest_engine = BacktestEngine()
