"""
Fundamental Analysis and Currency Scoring Engine for BANDI.
Processes economic indicator surprise deviations, calculates time-decayed
currency fundamental strength (-100 to +100), and produces pair biases.
"""

from __future__ import annotations
import math
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from bandi.database.db import db
from bandi.research.indicator_metadata import match_indicator_metadata, parse_numeric_figure
from bandi.research.watchlist import WATCHLIST_SYMBOLS, get_standard_symbol_info

logger = logging.getLogger("bandi.fundamental")

# Default Central Bank Stances (Hawkish: +35, Neutral: 0, Dovish: -35)
CENTRAL_BANK_STANCES: Dict[str, Dict[str, Any]] = {
    "USD": {"stance": "Neutral", "score": 5.0, "rate": 4.75, "bias_summary": "Accommodative recalibration with balanced labor data."},
    "EUR": {"stance": "Dovish", "score": -20.0, "rate": 3.25, "bias_summary": "Gradual easing cycle due to converging inflation and sluggish growth."},
    "GBP": {"stance": "Neutral", "score": 0.0, "rate": 4.75, "bias_summary": "Services inflation vigilance tempering quarterly rate reductions."},
    "JPY": {"stance": "Hawkish", "score": 30.0, "rate": 0.25, "bias_summary": "Active normalization and rate-hike posture relative to global peers."},
    "AUD": {"stance": "Hawkish", "score": 20.0, "rate": 4.35, "bias_summary": "Sticky core inflation delaying RBA rate cuts."},
    "CAD": {"stance": "Dovish", "score": -25.0, "rate": 3.75, "bias_summary": "Accelerated easing driven by consumer softening and per-capita contraction."},
    "CHF": {"stance": "Dovish", "score": -30.0, "rate": 1.00, "bias_summary": "SNB sub-1% inflation targeting and currency appreciation containment."},
    "NZD": {"stance": "Dovish", "score": -25.0, "rate": 4.75, "bias_summary": "RBNZ rapid normalization cycle."}
}


class FundamentalEngine:
    def __init__(self):
        self.decay_half_life_days = 10.0  # Events decay to 50% impact after 10 days

    def process_event_surprises(self) -> int:
        """
        Scan completed economic events in database that have actual & forecast values.
        Computes normalized surprise and records to event_scores table.
        """
        # Query recent events with actual data
        now_ts = int(time.time())
        from_ts = now_ts - (35 * 86400) # Past 35 days
        events = db.get_upcoming_events(from_ts=from_ts, to_ts=now_ts)

        scored_count = 0
        for ev in events:
            actual_str = ev.get("actual")
            forecast_str = ev.get("forecast")
            prev_str = ev.get("previous")

            if not actual_str or not forecast_str:
                continue

            act = parse_numeric_figure(actual_str)
            fcst = parse_numeric_figure(forecast_str)
            prev = parse_numeric_figure(prev_str)

            if act is None or fcst is None:
                continue

            meta = match_indicator_metadata(ev["title"])
            if not meta:
                continue

            raw_surprise = act - fcst
            stdev = meta.get("default_stdev", 1.0)
            if stdev <= 0:
                stdev = 1.0

            # Clamp normalized surprise to range [-3.0, +3.0] to prevent distortion
            normalized_surprise = max(-3.0, min(3.0, raw_surprise / stdev))
            direction_score = normalized_surprise * meta["polarity"] * meta["weight"]

            db.record_event_score(
                event_id=ev["id"],
                title=ev["title"],
                currency=ev["currency"],
                actual=act,
                forecast=fcst,
                previous=prev,
                raw_surprise=round(raw_surprise, 4),
                normalized_surprise=round(normalized_surprise, 4),
                direction_score=round(direction_score, 4),
                event_time_utc=ev["event_time_utc"]
            )
            scored_count += 1

        logger.info("Processed %d economic event surprise scores.", scored_count)
        return scored_count

    def calculate_currency_score(self, currency: str, current_ts: Optional[float] = None) -> Dict[str, Any]:
        """
        Calculate time-decayed fundamental score (-100 to +100) for a currency.
        Combines event surprises with central bank stance.
        """
        now = current_ts if current_ts is not None else time.time()
        ccy = currency.upper().strip()

        cb_info = CENTRAL_BANK_STANCES.get(ccy, {"stance": "Neutral", "score": 0.0, "rate": 0.0, "bias_summary": "Insufficient official benchmark."})
        cb_score = cb_info.get("score", 0.0)

        # Get recent event scores
        scores = db.get_event_scores(currency=ccy, limit=30)
        accumulated_surprise = 0.0
        total_weight = 0.0
        contributing = []

        for sc in scores:
            try:
                ev_dt = datetime.fromisoformat(sc["event_time_utc"])
                ev_ts = ev_dt.timestamp()
                days_ago = max(0.0, (now - ev_ts) / 86400.0)
                # Exponential decay factor: e^(-lambda * t) where lambda = ln(2) / half_life
                decay = math.exp(-0.693 * (days_ago / self.decay_half_life_days))

                weighted_val = sc["direction_score"] * decay
                accumulated_surprise += weighted_val * 15.0 # Scale surprise impact
                total_weight += decay

                contributing.append({
                    "title": sc["title"],
                    "surprise": sc["raw_surprise"],
                    "direction_score": sc["direction_score"],
                    "days_ago": round(days_ago, 1),
                    "decayed_weight": round(decay, 2)
                })
            except Exception:
                continue

        # Combine central bank policy + economic surprises
        raw_score = cb_score + accumulated_surprise
        # Clamp within -100 to +100
        final_score = max(-100.0, min(100.0, round(raw_score, 1)))

        return {
            "currency": ccy,
            "score": final_score,
            "central_bank_score": cb_score,
            "central_bank_stance": cb_info.get("stance", "Neutral"),
            "policy_rate": cb_info.get("rate", 0.0),
            "bias_summary": cb_info.get("bias_summary", ""),
            "events_count": len(contributing),
            "contributing_events": contributing[:5]
        }

    def calculate_pair_bias(self, symbol: str) -> Dict[str, Any]:
        """
        Calculate fundamental bias and direction label for any watchlist symbol.
        """
        sym = symbol.upper().strip()
        info = get_standard_symbol_info(sym)
        asset_class = info.get("asset_class", "Forex")
        base = info.get("base", "")
        quote = info.get("quote", "")

        contributing = []
        bias_val = 0.0
        central_bank_contrib = 0.0

        if asset_class == "Forex" and base and quote:
            base_data = self.calculate_currency_score(base)
            quote_data = self.calculate_currency_score(quote)
            bias_val = base_data["score"] - quote_data["score"]
            central_bank_contrib = base_data["central_bank_score"] - quote_data["central_bank_score"]
            contributing = base_data["contributing_events"] + quote_data["contributing_events"]

        elif sym == "XAUUSD":
            # Gold: Inversely correlated with USD strength + real yield stance
            usd_data = self.calculate_currency_score("USD")
            # Strong USD is bearish for Gold; Dovish USD is bullish for Gold
            bias_val = (-1.0 * usd_data["score"]) + 10.0 # Structural central-bank physical accumulation buffer
            central_bank_contrib = -1.0 * usd_data["central_bank_score"]
            contributing = usd_data["contributing_events"]

        elif sym in ("US30", "NAS100", "SPX500"):
            # US Indices: Moderate inverse correlation with aggressive Fed hikes, positive on easing
            usd_data = self.calculate_currency_score("USD")
            bias_val = (-0.5 * usd_data["score"]) + 15.0 # Equity corporate earnings premium
            central_bank_contrib = -0.5 * usd_data["central_bank_score"]
            contributing = usd_data["contributing_events"]

        elif sym == "GER40":
            eur_data = self.calculate_currency_score("EUR")
            bias_val = (-0.5 * eur_data["score"]) + 10.0
            central_bank_contrib = -0.5 * eur_data["central_bank_score"]
            contributing = eur_data["contributing_events"]

        # Clamp bias to -100 .. +100
        bias_val = max(-100.0, min(100.0, round(bias_val, 1)))

        # Assign label
        if bias_val >= 35.0:
            label = "STRONG_BULL"
        elif bias_val >= 15.0:
            label = "BULL"
        elif bias_val <= -35.0:
            label = "STRONG_BEAR"
        elif bias_val <= -15.0:
            label = "BEAR"
        else:
            label = "NEUTRAL"

        # Persist in fundamental_bias table
        db.upsert_fundamental_bias(
            symbol=sym,
            bias_value=bias_val,
            bias_label=label,
            contributing_events=contributing[:5],
            central_bank_score=central_bank_contrib
        )

        return {
            "symbol": sym,
            "bias_value": bias_val,
            "bias_label": label,
            "central_bank_score": central_bank_contrib,
            "contributing_events": contributing[:5],
            "updated_at_utc": datetime.now(timezone.utc).isoformat()
        }

    def update_all_biases(self) -> Dict[str, Any]:
        """Recalculate and update biases for all watchlist symbols."""
        self.process_event_surprises()
        results = {}
        for sym in WATCHLIST_SYMBOLS:
            results[sym] = self.calculate_pair_bias(sym)
        return results


# Global fundamental engine instance
fundamental_calculator = FundamentalEngine()
