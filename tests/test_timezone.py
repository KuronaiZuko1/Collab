"""
Unit tests for BANDI timezone handling and SAST display calculations.
"""

from datetime import datetime, timezone
from bandi.config import settings


def test_timezone_configuration():
    assert settings.DISPLAY_TIMEZONE_NAME == "Africa/Johannesburg"


def test_utc_to_sast_conversion():
    # 2026-11-07 12:00:00 UTC should be 2026-11-07 14:00:00 SAST (UTC+2)
    dt_utc = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)
    dt_sast = settings.utc_to_sast(dt_utc)

    assert dt_sast.hour == 14
    assert dt_sast.minute == 0
    assert "SAST" in settings.ts_to_sast_str(dt_utc.timestamp())


def test_timestamp_formatting():
    # Unix timestamp 1794187800 = 2026-11-09 01:30:00 UTC -> 03:30:00 SAST
    ts = 1794187800
    formatted = settings.ts_to_sast_str(ts)
    assert "2026-11-09" in formatted
    assert "03:30:00" in formatted
    assert "SAST" in formatted
