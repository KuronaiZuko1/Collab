"""
Deterministic Currency Strength Engine for BANDI.
Calculates relative strength matrix across 8 major currencies
(USD, EUR, GBP, JPY, AUD, CAD, CHF, NZD).
"""

from __future__ import annotations
from typing import Dict, List, Any


CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]


def calculate_currency_strength(price_snapshots: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    """
    Calculate deterministic currency strength ratings from market quotes.
    Scores range from 0.0 (extremely weak) to 10.0 (extremely strong), centered at 5.0.
    """
    scores: Dict[str, float] = {ccy: 5.0 for ccy in CURRENCIES}
    counts: Dict[str, int] = {ccy: 0 for ccy in CURRENCIES}

    # Reference major pairs
    pair_weights = {
        "EURUSD": ("EUR", "USD"),
        "GBPUSD": ("GBP", "USD"),
        "USDJPY": ("USD", "JPY"),
        "AUDUSD": ("AUD", "USD"),
        "USDCAD": ("USD", "CAD"),
        "USDCHF": ("USD", "CHF"),
        "NZDUSD": ("NZD", "USD")
    }

    data_points_found = 0

    for pair, (base, quote) in pair_weights.items():
        quote_data = price_snapshots.get(pair)
        if not quote_data:
            continue

        bid = quote_data.get("bid", 0.0)
        ask = quote_data.get("ask", 0.0)
        mid = (bid + ask) / 2.0 if (bid and ask) else bid

        if mid > 0:
            data_points_found += 1
            # Check price relative to reference base (normalized spread)
            spread = quote_data.get("spread_points", 0.0)
            # If mid is available, calculate basic directional momentum if open/prev available
            prev = quote_data.get("prev_close", mid)
            if prev and prev > 0:
                pct_change = ((mid - prev) / prev) * 100.0
                # Clamp change contribution
                shift = max(-2.5, min(2.5, pct_change * 2.0))
                scores[base] += shift
                scores[quote] -= shift
                counts[base] += 1
                counts[quote] += 1

    # Normalize within 0.0 to 10.0
    normalized_scores: Dict[str, float] = {}
    for ccy in CURRENCIES:
        raw = scores[ccy]
        norm = max(1.0, min(9.5, round(raw, 1)))
        normalized_scores[ccy] = norm

    # Rank sorted from strongest to weakest
    ranked = sorted(normalized_scores.items(), key=lambda x: x[1], reverse=True)

    is_sufficient = data_points_found >= 3

    return {
        "is_data_sufficient": is_sufficient,
        "data_points_count": data_points_found,
        "scores": normalized_scores,
        "ranking": [{"currency": c[0], "score": c[1]} for c in ranked],
        "strongest": ranked[0][0] if ranked else "N/A",
        "weakest": ranked[-1][0] if ranked else "N/A"
    }
