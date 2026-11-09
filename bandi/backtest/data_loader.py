"""
Historical Candle Data Loader for Backtesting.
Reads candles from CSV files, SQLite database, or generates realistic test fixtures.
"""

from __future__ import annotations
import csv
import math
import random
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

from bandi.strategy.price_action import Candle
from bandi.database.db import db


def load_candles_from_csv(file_path: Path, symbol: str = "EURUSD", timeframe: str = "H1") -> List[Candle]:
    """Load candles from a standard CSV file with headers: Date/Time, Open, High, Low, Close, Volume."""
    candles: List[Candle] = []
    if not file_path.exists():
        return candles

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Support various column names
                time_str = row.get("Time") or row.get("Date") or row.get("timestamp") or ""
                try:
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    ts = int(dt.timestamp())
                except Exception:
                    ts = int(float(time_str))

                c = Candle(
                    symbol=symbol.upper(),
                    timeframe=timeframe.upper(),
                    ts=ts,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0.0))
                )
                candles.append(c)
            except Exception:
                continue

    return candles


def load_candles_from_db(symbol: str, timeframe: str, limit: int = 2000) -> List[Candle]:
    """Load stored candles directly from SQLite database."""
    raw = db.get_candles(symbol, timeframe, limit=limit)
    return [
        Candle(
            symbol=r["symbol"],
            timeframe=r["timeframe"],
            ts=r["candle_ts"],
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"]
        )
        for r in raw
    ]


def generate_benchmark_candles(
    symbol: str = "EURUSD",
    timeframe: str = "H1",
    count: int = 500,
    start_price: float = 1.0850,
    seed: int = 42
) -> List[Candle]:
    """
    Generate realistic deterministic OHLC sequence with genuine support/resistance levels,
    trends, pin bars, and retests for reproducible backtesting and unit testing.
    """
    random.seed(seed)
    candles: List[Candle] = []
    curr_price = start_price
    base_ts = 1704067200  # 2024-01-01 00:00:00 UTC

    for i in range(count):
        ts = base_ts + (i * 3600)
        # Macro drift + oscillating cycle for support/resistance structure
        cycle = math.sin(i / 15.0) * 0.0030
        drift = math.cos(i / 40.0) * 0.0015
        noise = (random.random() - 0.5) * 0.0020

        candle_open = curr_price
        candle_close = round(candle_open + cycle + drift + noise, 5)

        # Create occasional rejection wicks (pin bars)
        upper_wick = random.random() * 0.0015
        lower_wick = random.random() * 0.0015
        if i % 18 == 0:
            # Bullish pin bar off support
            lower_wick = abs(candle_close - candle_open) * 2.5 + 0.0010
        elif i % 25 == 0:
            # Bearish pin bar off resistance
            upper_wick = abs(candle_close - candle_open) * 2.5 + 0.0010

        candle_high = round(max(candle_open, candle_close) + upper_wick, 5)
        candle_low = round(min(candle_open, candle_close) - lower_wick, 5)

        c = Candle(
            symbol=symbol.upper(),
            timeframe=timeframe.upper(),
            ts=ts,
            open=candle_open,
            high=candle_high,
            low=candle_low,
            close=candle_close,
            volume=random.randint(200, 2500)
        )
        candles.append(c)
        curr_price = candle_close

    return candles
