"""
Fallback Economic Calendar Data for BANDI.
Provides verified benchmark schedules for major central bank interest rate decisions
and tier-1 economic releases to ensure system continuity if remote APIs fail.
Never invents data or fabricates forecasts.
"""

from __future__ import annotations
from typing import List, Dict, Any
from datetime import datetime, timezone

# Verified recurring high-impact releases and central bank schedule
FALLBACK_VERIFIED_SCHEDULES: List[Dict[str, Any]] = [
    {
        "id": "fomc-interest-rate-decision-benchmark",
        "title": "FOMC Interest Rate Decision",
        "currency": "USD",
        "country": "United States",
        "impact": "high",
        "period": "Scheduled FOMC Policy Release",
        "source": "Federal Reserve Official Schedule",
        "why_it_matters": "Federal Reserve key benchmark lending rate decision.",
        "affected_instruments": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US30", "NAS100"]
    },
    {
        "id": "us-cpi-inflation-benchmark",
        "title": "US Consumer Price Index (CPI) MoM / YoY",
        "currency": "USD",
        "country": "United States",
        "impact": "high",
        "period": "Monthly Benchmark",
        "source": "U.S. Bureau of Labor Statistics",
        "why_it_matters": "Principal monthly gauge of consumer inflation in the United States.",
        "affected_instruments": ["EURUSD", "USDJPY", "XAUUSD", "US30", "SPX500"]
    },
    {
        "id": "us-non-farm-payrolls-benchmark",
        "title": "US Non-Farm Payrolls (NFP)",
        "currency": "USD",
        "country": "United States",
        "impact": "high",
        "period": "Monthly Benchmark",
        "source": "U.S. Bureau of Labor Statistics",
        "why_it_matters": "Headline monthly change in US employment excluding agricultural workers.",
        "affected_instruments": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US30"]
    },
    {
        "id": "ecb-monetary-policy-decision",
        "title": "ECB Main Refinancing Rate Decision",
        "currency": "EUR",
        "country": "Eurozone",
        "impact": "high",
        "period": "ECB Governing Council",
        "source": "European Central Bank Official",
        "why_it_matters": "European Central Bank benchmark interest rate decision.",
        "affected_instruments": ["EURUSD", "GER40"]
    },
    {
        "id": "boe-official-bank-rate-decision",
        "title": "Bank of England Official Bank Rate",
        "currency": "GBP",
        "country": "United Kingdom",
        "impact": "high",
        "period": "BoE MPC Meeting",
        "source": "Bank of England Official",
        "why_it_matters": "BoE Monetary Policy Committee key lending rate.",
        "affected_instruments": ["GBPUSD"]
    }
]


def get_fallback_events() -> List[Dict[str, Any]]:
    """Return fallback event templates."""
    return list(FALLBACK_VERIFIED_SCHEDULES)
