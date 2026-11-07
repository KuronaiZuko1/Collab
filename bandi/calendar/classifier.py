"""
Economic Event Classifier and Impact Analysis for BANDI.
Categorizes financial news releases, maps affected instruments,
and generates deterministic context explanations.
"""

from __future__ import annotations
import re
from typing import Dict, List, Tuple

# Key high-impact release patterns
HIGH_IMPACT_PATTERNS = [
    (r"non-?farm payrolls|nonfarm payrolls|nfp", "Employment", "NFP is the primary gauge of US job growth, heavily influencing Fed monetary policy, USD valuation, and global market risk sentiment."),
    (r"consumer price index|cpi|core cpi", "Inflation", "CPI is the benchmark consumer inflation indicator. Higher figures increase rate-hike expectations, boosting the local currency and pressuring gold/indices."),
    (r"producer price index|ppi|core ppi", "Inflation", "PPI tracks wholesale price changes, serving as a leading indicator of consumer inflation and central bank policy adjustments."),
    (r"fomc|fed interest rate decision|funds rate", "Monetary Policy", "FOMC rate decisions dictate US monetary policy, directly impacting yields, the USD, commodities, and worldwide equity indices."),
    (r"ecb interest rate|main refinancing rate", "Monetary Policy", "ECB rate announcements determine eurozone borrowing conditions, directly driving EUR/USD and European equity markets like GER40."),
    (r"bank of england|boe interest rate|official bank rate", "Monetary Policy", "BoE policy decisions dictate UK monetary stance, creating high volatility in GBP pairs."),
    (r"bank of japan|boj policy rate|boj rate decision", "Monetary Policy", "BoJ interest decisions impact the Japanese Yen carry trade, heavily influencing USD/JPY and cross-JPY liquidity."),
    (r"gross domestic product|gdp", "Economic Growth", "GDP reflects overall economic health and expansion rate. Significant deviations alter rate projections and national currency strength."),
    (r"unemployment rate|jobless rate", "Employment", "Unemployment rate indicates labor market capacity. Sustained tight labor markets spur wage inflation and hawkish monetary policy."),
    (r"initial jobless claims", "Employment", "Weekly initial claims provide high-frequency insight into layoffs and labor market softening."),
    (r"retail sales|core retail sales", "Consumer Spending", "Retail sales measure consumer demand, accounting for two-thirds of GDP. Strong figures suggest resilient consumer spending."),
    (r"pce price index|core pce", "Inflation", "Core PCE is the Federal Reserve's preferred inflation benchmark. Elevated readings reinforce higher-for-longer policy stances."),
    (r"pmi|ism manufacturing|ism services|purchasing managers", "Activity Index", "PMI/ISM indexes gauge private sector health. Levels above 50 signal expansion; below 50 indicate contraction."),
    (r"jolts", "Employment", "JOLTS job openings measure labor demand and vacancy trends, monitored closely by central bankers.")
]

# Currency to Watchlist instrument mapping
CURRENCY_INSTRUMENT_MAP: Dict[str, List[str]] = {
    "USD": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD", "US30", "NAS100", "SPX500"],
    "EUR": ["EURUSD", "GER40"],
    "GBP": ["GBPUSD"],
    "JPY": ["USDJPY"],
    "AUD": ["AUDUSD"],
    "CAD": ["USDCAD"],
    "CHF": ["USDCHF"],
    "NZD": ["NZDUSD"],
    "CNY": ["AUDUSD", "XAUUSD"],  # Chinese data heavily affects Australian exports and global commodity demand
    "ZAR": ["USDZAR"]
}


def classify_event(title: str, currency: str, provider_impact: str = "") -> Tuple[str, List[str], str]:
    """
    Classify an event by impact level, affected instruments, and context.
    Returns:
        (impact_level, affected_instruments, why_it_matters)
    """
    clean_title = title.lower()
    clean_currency = currency.upper().strip()
    
    # Deterministic matching
    matched_impact = provider_impact.lower().strip() if provider_impact else "low"
    why_it_matters = f"Scheduled {clean_currency} economic announcement that may affect market volatility."
    
    for pattern, category, explanation in HIGH_IMPACT_PATTERNS:
        if re.search(pattern, clean_title):
            matched_impact = "high"
            why_it_matters = f"[{category}] {explanation}"
            break
            
    # Default affected instruments from currency
    affected_instruments = CURRENCY_INSTRUMENT_MAP.get(clean_currency, ["EURUSD", "USDJPY"])
    
    # If high-impact USD or Inflation/Rates, ensure Gold and Indices are tagged
    if clean_currency == "USD" or matched_impact == "high":
        if "XAUUSD" not in affected_instruments:
            affected_instruments.append("XAUUSD")
        if "US30" not in affected_instruments:
            affected_instruments.append("US30")

    return matched_impact, affected_instruments, why_it_matters
