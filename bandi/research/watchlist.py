"""
Watchlist and Broker Symbol Normalization for BANDI.
Defines supported trading instruments and maps broker-specific ticker aliases.
"""

from __future__ import annotations
from typing import Dict, List, Optional

# Core Watchlist
WATCHLIST_SYMBOLS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "USDCHF",
    "NZDUSD",
    "XAUUSD",
    "US30",
    "NAS100",
    "SPX500",
    "GER40"
]

# Broker Alias Mapping (Standardised -> Common Broker Variants)
BROKER_SYMBOL_ALIASES: Dict[str, List[str]] = {
    "EURUSD": ["EURUSD", "EURUSDm", "EURUSD.a", "EURUSD.", "EURUSDpro"],
    "GBPUSD": ["GBPUSD", "GBPUSDm", "GBPUSD.a", "GBPUSD.", "GBPUSDpro"],
    "USDJPY": ["USDJPY", "USDJPYm", "USDJPY.a", "USDJPY.", "USDJPYpro"],
    "AUDUSD": ["AUDUSD", "AUDUSDm", "AUDUSD.a", "AUDUSD.", "AUDUSDpro"],
    "USDCAD": ["USDCAD", "USDCADm", "USDCAD.a", "USDCAD.", "USDCADpro"],
    "USDCHF": ["USDCHF", "USDCHFm", "USDCHF.a", "USDCHF.", "USDCHFpro"],
    "NZDUSD": ["NZDUSD", "NZDUSDm", "NZDUSD.a", "NZDUSD.", "NZDUSDpro"],
    "XAUUSD": ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLDm", "XAUUSDpro"],
    "US30": ["US30", "DJ30", "WallStreet30", "US30Cash", "WS30", "US30m"],
    "NAS100": ["NAS100", "USTEC", "US100", "NDX100", "NAS100Cash", "USTECHm"],
    "SPX500": ["SPX500", "US500", "SP500", "US500Cash", "SPX500m"],
    "GER40": ["GER40", "DE40", "DAX40", "GER30", "DE30", "GER40Cash"]
}


def resolve_broker_symbol(standard_symbol: str, available_broker_symbols: List[str]) -> Optional[str]:
    """
    Find the matching broker symbol from the list of available symbols in MT5.
    Returns the broker's exact symbol name if found, else None.
    """
    aliases = BROKER_SYMBOL_ALIASES.get(standard_symbol, [standard_symbol])
    for alias in aliases:
        for available in available_broker_symbols:
            if available.upper() == alias.upper():
                return available
    return None


def get_standard_symbol_info(symbol: str) -> Dict[str, str]:
    """Return asset class and description for a watchlist symbol."""
    info_map = {
        "EURUSD": {"asset_class": "Forex", "name": "Euro / US Dollar", "base": "EUR", "quote": "USD"},
        "GBPUSD": {"asset_class": "Forex", "name": "British Pound / US Dollar", "base": "GBP", "quote": "USD"},
        "USDJPY": {"asset_class": "Forex", "name": "US Dollar / Japanese Yen", "base": "USD", "quote": "JPY"},
        "AUDUSD": {"asset_class": "Forex", "name": "Australian Dollar / US Dollar", "base": "AUD", "quote": "USD"},
        "USDCAD": {"asset_class": "Forex", "name": "US Dollar / Canadian Dollar", "base": "USD", "quote": "CAD"},
        "USDCHF": {"asset_class": "Forex", "name": "US Dollar / Swiss Franc", "base": "USD", "quote": "CHF"},
        "NZDUSD": {"asset_class": "Forex", "name": "New Zealand Dollar / US Dollar", "base": "NZD", "quote": "USD"},
        "XAUUSD": {"asset_class": "Commodities", "name": "Gold / US Dollar", "base": "XAU", "quote": "USD"},
        "US30": {"asset_class": "Indices", "name": "Dow Jones Industrial Average", "base": "USD", "quote": "USD"},
        "NAS100": {"asset_class": "Indices", "name": "Nasdaq 100 Index", "base": "USD", "quote": "USD"},
        "SPX500": {"asset_class": "Indices", "name": "S&P 500 Index", "base": "USD", "quote": "USD"},
        "GER40": {"asset_class": "Indices", "name": "DAX 40 Germany", "base": "EUR", "quote": "EUR"}
    }
    return info_map.get(symbol, {"asset_class": "Unknown", "name": symbol, "base": "", "quote": ""})
