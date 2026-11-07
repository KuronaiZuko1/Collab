"""
Unit tests for economic calendar classification and ingestion rate-limiting.
"""

from bandi.calendar.classifier import classify_event
from bandi.calendar.fallback import get_fallback_events
from bandi.calendar.client import CalendarClient


def test_classify_high_impact_events():
    # NFP test
    impact, instruments, why = classify_event("US Non-Farm Payrolls", "USD", "high")
    assert impact == "high"
    assert "EURUSD" in instruments
    assert "XAUUSD" in instruments
    assert "US30" in instruments
    assert "NFP" in why

    # CPI test
    impact, instruments, why = classify_event("Consumer Price Index YoY", "EUR", "medium")
    assert impact == "high"  # Elevated to high due to CPI pattern
    assert "EURUSD" in instruments
    assert "Inflation" in why

    # FOMC rate decision test
    impact, instruments, why = classify_event("FOMC Interest Rate Decision", "USD", "low")
    assert impact == "high"
    assert "Monetary Policy" in why


def test_fallback_events_structure():
    fallbacks = get_fallback_events()
    assert len(fallbacks) >= 4
    for fb in fallbacks:
        assert fb["impact"] == "high"
        assert "affected_instruments" in fb
        assert len(fb["affected_instruments"]) > 0


def test_calendar_rate_limiting():
    from bandi.database.db import db
    client = CalendarClient()
    
    # Simulate DB last_fetch was 2000 seconds ago
    with db.get_connection() as conn:
        conn.execute("UPDATE application_settings SET value = ? WHERE key = 'calendar_last_fetch_ts'", (str(1000.0),))
        conn.commit()

    client._last_fetch_ts = 1000.0
    assert client.can_fetch(min_interval_seconds=900) is True

    # Simulate fetch just happened 30 seconds ago
    import time
    now = time.time()
    client._last_fetch_ts = now
    with db.get_connection() as conn:
        conn.execute("UPDATE application_settings SET value = ? WHERE key = 'calendar_last_fetch_ts'", (str(now),))
        conn.commit()
    assert client.can_fetch(min_interval_seconds=900) is False
