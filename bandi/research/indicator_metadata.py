"""
Macroeconomic Indicator Metadata and Surprise Parameters for BANDI.
Defines polarities, weights, and typical historical surprise standard deviations
for major economic announcements.
Polarity: +1 if higher than forecast is bullish for the reporting currency.
          -1 if higher than forecast is bearish for the reporting currency.
"""

from __future__ import annotations
import re
from typing import Dict, Any, List, Optional

INDICATOR_METADATA: List[Dict[str, Any]] = [
    {
        "pattern": r"non-?farm payrolls|nonfarm payrolls|nfp",
        "name": "Non-Farm Payrolls",
        "polarity": 1,
        "weight": 1.0,
        "default_stdev": 50.0, # in thousands (e.g. 50k variance)
        "unit": "K",
        "category": "Employment"
    },
    {
        "pattern": r"consumer price index|cpi|core cpi",
        "name": "Consumer Price Index (CPI)",
        "polarity": 1,
        "weight": 1.0,
        "default_stdev": 0.2, # in percentage points
        "unit": "%",
        "category": "Inflation"
    },
    {
        "pattern": r"producer price index|ppi|core ppi",
        "name": "Producer Price Index (PPI)",
        "polarity": 1,
        "weight": 0.7,
        "default_stdev": 0.3,
        "unit": "%",
        "category": "Inflation"
    },
    {
        "pattern": r"interest rate decision|rate decision|refinancing rate|policy rate",
        "name": "Central Bank Interest Rate Decision",
        "polarity": 1,
        "weight": 1.2,
        "default_stdev": 0.25,
        "unit": "%",
        "category": "Monetary Policy"
    },
    {
        "pattern": r"gross domestic product|gdp",
        "name": "Gross Domestic Product (GDP)",
        "polarity": 1,
        "weight": 0.9,
        "default_stdev": 0.3,
        "unit": "%",
        "category": "Economic Growth"
    },
    {
        "pattern": r"unemployment rate|jobless rate",
        "name": "Unemployment Rate",
        "polarity": -1, # Higher unemployment is bearish for currency
        "weight": 0.9,
        "default_stdev": 0.2,
        "unit": "%",
        "category": "Employment"
    },
    {
        "pattern": r"initial jobless claims",
        "name": "Initial Jobless Claims",
        "polarity": -1, # Higher claims is bearish for currency
        "weight": 0.5,
        "default_stdev": 15.0, # in thousands
        "unit": "K",
        "category": "Employment"
    },
    {
        "pattern": r"retail sales|core retail sales",
        "name": "Retail Sales",
        "polarity": 1,
        "weight": 0.8,
        "default_stdev": 0.4,
        "unit": "%",
        "category": "Consumer Spending"
    },
    {
        "pattern": r"pce price index|core pce",
        "name": "PCE Price Index",
        "polarity": 1,
        "weight": 1.0,
        "default_stdev": 0.15,
        "unit": "%",
        "category": "Inflation"
    },
    {
        "pattern": r"pmi|ism manufacturing|ism services",
        "name": "Purchasing Managers Index (PMI / ISM)",
        "polarity": 1,
        "weight": 0.8,
        "default_stdev": 1.5,
        "unit": "Index",
        "category": "Activity"
    }
]


def match_indicator_metadata(title: str) -> Optional[Dict[str, Any]]:
    """Match event title against configured indicator patterns."""
    clean_title = title.lower()
    for meta in INDICATOR_METADATA:
        if re.search(meta["pattern"], clean_title):
            return meta
    return None


def parse_numeric_figure(val_str: Any) -> Optional[float]:
    """Parse numeric values from strings like '0.8%', '180K', '25.4B', '3.25%'."""
    if val_str is None:
        return None
    s = str(val_str).strip().replace(",", "")
    if not s:
        return None

    multiplier = 1.0
    if s.endswith("%"):
        s = s[:-1].strip()
    elif s.endswith("K") or s.endswith("k"):
        multiplier = 1.0 # Standardized in thousands
        s = s[:-1].strip()
    elif s.endswith("M") or s.endswith("m"):
        multiplier = 1000.0
        s = s[:-1].strip()
    elif s.endswith("B") or s.endswith("b"):
        multiplier = 1000000.0
        s = s[:-1].strip()

    try:
        return float(s) * multiplier
    except ValueError:
        return None
