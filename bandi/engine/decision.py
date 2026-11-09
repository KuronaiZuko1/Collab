"""
Decision Engine for BANDI.
Orchestrates fundamental bias, price action signals, and deterministic risk management.
Produces auditable TRADE, WATCH, and SKIP decisions and coordinates Telegram alerts / MT5 order queuing.
"""

from __future__ import annotations
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from bandi.config import settings
from bandi.database.db import db
from bandi.strategy.price_action import Signal, Candle, price_action_strategy
from bandi.research.fundamental_engine import fundamental_calculator
from bandi.research.watchlist import WATCHLIST_SYMBOLS
from bandi.mt5.risk import risk_manager
from bandi.mt5.bridge import mt5_bridge
from bandi.telegram.bot import telegram_notifier

logger = logging.getLogger("bandi.engine")


class DecisionEngine:
    def __init__(self):
        self.processed_signals: set = set()

    def evaluate_symbol(
        self,
        symbol: str,
        h1_candles: List[Candle],
        h4_candles: List[Candle],
        account_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a single symbol across fundamentals, price action, and risk.
        Returns decision result dictionary.
        """
        sym = symbol.upper().strip()
        decision_id = f"dec_{sym}_{int(time.time())}"

        # 1. Fetch fundamental bias
        bias_record = fundamental_calculator.calculate_pair_bias(sym)
        bias_label = bias_record.get("bias_label", "NEUTRAL")

        # 2. Run price action strategy
        signal: Optional[Signal] = price_action_strategy.evaluate(
            symbol=sym,
            h1_candles=h1_candles,
            h4_candles=h4_candles,
            fundamental_bias_label=bias_label
        )

        if not signal:
            dec = {
                "decision_id": decision_id,
                "symbol": sym,
                "action": "WATCH",
                "reasons": ["No confirmed price action pattern or trend structure unclear."],
                "risk_checks_passed": True,
                "lot_size": 0.0,
                "equity": account_info.get("equity", 0.0) if account_info else 0.0
            }
            db.record_decision(dec)
            return dec

        # 3. Idempotency Check: ensure signal hasn't already been processed
        if signal.signal_id in self.processed_signals or db.get_signal(signal.signal_id) is not None:
            logger.info("Signal %s already processed. Skipping duplicate.", signal.signal_id)
            dec = {
                "decision_id": decision_id,
                "signal_id": signal.signal_id,
                "symbol": sym,
                "action": "SKIP",
                "reasons": ["Duplicate signal: already processed."],
                "risk_checks_passed": False
            }
            db.record_decision(dec)
            return dec

        # Save new signal to SQLite
        db.save_signal({
            "signal_id": signal.signal_id,
            "symbol": signal.symbol,
            "timeframe": signal.timeframe,
            "direction": signal.direction,
            "entry_price": signal.entry_price,
            "sl": signal.sl,
            "tp": signal.tp,
            "rr": signal.rr,
            "confidence": signal.confidence,
            "reasons": signal.reasons,
            "fundamental_bias": signal.fundamental_bias,
            "status": "ACTIVE",
            "expiry_ts": signal.expiry_ts
        })
        self.processed_signals.add(signal.signal_id)

        # 4. Position Sizing
        equity = account_info.get("equity", 10000.0) if account_info else 10000.0
        stop_dist_points = abs(signal.entry_price - signal.sl) * 10000.0 # approximate points
        lot_size = risk_manager.calculate_position_size(
            account_equity=equity,
            stop_distance_points=stop_dist_points
        )

        # 5. Risk Gatekeeper Evaluation
        open_positions = mt5_bridge._open_positions
        usd_positions = sum(1 for p in open_positions if "USD" in p.get("symbol", ""))
        telemetry_age = mt5_bridge.get_telemetry_age()
        trade_mode = account_info.get("trade_mode", "DEMO") if account_info else "DEMO"

        # Current spread
        spread = 15.0
        quote_data = mt5_bridge._symbol_quotes.get(sym)
        if quote_data:
            spread = quote_data.get("spread_points", 15.0)

        risk_allowed, risk_reason = risk_manager.check_trade_permission(
            symbol=sym,
            current_spread_points=spread,
            daily_drawdown_pct=0.0,
            open_positions_count=len(open_positions),
            requested_volume=lot_size,
            sl=signal.sl,
            tp=signal.tp,
            account_trade_mode=trade_mode,
            telemetry_age_seconds=telemetry_age,
            open_usd_positions_count=usd_positions
        )

        if not risk_allowed:
            reasons = [f"Risk Gate Rejection: {risk_reason}"] + signal.reasons
            dec = {
                "decision_id": decision_id,
                "signal_id": signal.signal_id,
                "symbol": sym,
                "action": "SKIP",
                "reasons": reasons,
                "risk_checks_passed": False,
                "lot_size": lot_size,
                "equity": equity
            }
            db.record_decision(dec)
            logger.warning("Trade decision for %s: SKIP (%s)", sym, risk_reason)
            return dec

        # 6. Action Execution by TRADING_MODE
        mode = settings.TRADING_MODE
        dec_action = "TRADE"
        reasons = [f"All risk checks passed in mode [{mode}]"] + signal.reasons

        # Dispatch Telegram Signal
        telegram_notifier.send_strategy_signal(signal=signal, lot_size=lot_size, risk_pct=settings.RISK_PER_TRADE_PCT)

        if mode == "AUTO":
            # Queue order directly in MT5 bridge
            order_payload = {
                "signal_id": signal.signal_id,
                "symbol": signal.symbol,
                "direction": signal.direction,
                "volume": lot_size,
                "entry_price": signal.entry_price,
                "sl": signal.sl,
                "tp": signal.tp
            }
            order_id = mt5_bridge.queue_order(order_payload)
            db.save_order({
                "order_id": order_id,
                "signal_id": signal.signal_id,
                "symbol": signal.symbol,
                "direction": signal.direction,
                "volume": lot_size,
                "entry_price": signal.entry_price,
                "sl": signal.sl,
                "tp": signal.tp,
                "status": "PENDING"
            })
            reasons.append(f"Auto-dispatched order #{order_id} to MT5 EA")

        dec = {
            "decision_id": decision_id,
            "signal_id": signal.signal_id,
            "symbol": sym,
            "action": dec_action,
            "reasons": reasons,
            "risk_checks_passed": True,
            "lot_size": lot_size,
            "equity": equity
        }
        db.record_decision(dec)
        return dec

    def run_cycle(self) -> List[Dict[str, Any]]:
        """Run decision cycle across all watchlist symbols using stored candles."""
        results = []
        acct = mt5_bridge._account_info if mt5_bridge.is_connected() else None

        for sym in WATCHLIST_SYMBOLS:
            raw_h1 = db.get_candles(sym, "H1", limit=100)
            raw_h4 = db.get_candles(sym, "H4", limit=50)

            if len(raw_h1) < 20 or len(raw_h4) < 15:
                continue

            h1_candles = [Candle(symbol=sym, timeframe="H1", ts=c["candle_ts"], open=c["open"], high=c["high"], low=c["low"], close=c["close"], volume=c["volume"]) for c in raw_h1]
            h4_candles = [Candle(symbol=sym, timeframe="H4", ts=c["candle_ts"], open=c["open"], high=c["high"], low=c["low"], close=c["close"], volume=c["volume"]) for c in raw_h4]

            dec = self.evaluate_symbol(sym, h1_candles, h4_candles, account_info=acct)
            results.append(dec)

        return results


# Global decision engine instance
decision_engine = DecisionEngine()
