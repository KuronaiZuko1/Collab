"""
Unit tests for Telegram formatting and notifier.
"""

from bandi.telegram.formatter import format_economic_alert, format_test_message


def test_economic_alert_formatting():
    event = {
        "title": "US Non-Farm Payrolls",
        "country": "United States",
        "currency": "USD",
        "impact": "high",
        "event_ts": 1794187800,
        "forecast": "180K",
        "previous": "210K",
        "source": "showmytrades.com",
        "why_it_matters": "Primary indicator of labor market health.",
        "affected_instruments": ["EURUSD", "GBPUSD", "XAUUSD", "US30"]
    }

    msg = format_economic_alert(event, is_late=False, minutes_until=30.0)

    # Verify essential brand and content elements
    assert "BANDI | HIGH-IMPACT ECONOMIC ALERT" in msg
    assert "US Non-Farm Payrolls" in msg
    assert "United States (USD)" in msg
    assert "HIGH" in msg
    assert "EURUSD, GBPUSD, XAUUSD, US30" in msg
    assert "Primary indicator of labor market health" in msg
    assert "showmytrades.com" in msg
    assert "SAST" in msg


def test_late_alert_banner():
    event = {
        "title": "ECB Interest Rate Decision",
        "country": "Eurozone",
        "currency": "EUR",
        "impact": "high",
        "event_ts": 1794187800,
        "forecast": "3.25%",
        "previous": "3.50%",
        "source": "showmytrades.com",
        "why_it_matters": "ECB rate decision.",
        "affected_instruments": ["EURUSD", "GER40"]
    }

    msg = format_economic_alert(event, is_late=True, minutes_until=15.0)
    assert "[LATE ALERT — SYSTEM RESTARTED]" in msg


def test_test_message_formatting():
    msg = format_test_message("test_bot", "1916380095")
    assert "BANDI TELEGRAM CONNECTIVITY VERIFIED" in msg
    assert "@test_bot" in msg
    assert "1916380095" in msg
