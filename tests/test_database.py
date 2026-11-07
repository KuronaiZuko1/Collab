"""
Unit tests for BANDI database layer.
"""

import time
import pytest
from bandi.database.db import Database
from bandi.database.schema import SCHEMA_VERSION


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_bandi.db"
    db_instance = Database(db_file)
    db_instance.init_db()
    return db_instance


def test_db_initialization(test_db):
    with test_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_version")
        row = cursor.fetchone()
        assert row is not None
        assert row["version"] == SCHEMA_VERSION


def test_event_upsert_and_retrieval(test_db):
    now_ts = int(time.time())
    event = {
        "id": "test-cpi-01",
        "title": "US Consumer Price Index",
        "country": "United States",
        "currency": "USD",
        "impact": "high",
        "event_time_utc": "2026-11-09T13:30:00Z",
        "event_ts": now_ts + 3600,
        "forecast": "0.3%",
        "previous": "0.2%",
        "actual": "",
        "status": "scheduled",
        "source": "test",
        "why_it_matters": "US inflation indicator",
        "affected_instruments": ["EURUSD", "XAUUSD"]
    }

    # First insert
    inserted = test_db.upsert_economic_event(event)
    assert inserted is True

    # Retrieve
    retrieved = test_db.get_event_by_id("test-cpi-01")
    assert retrieved is not None
    assert retrieved["title"] == "US Consumer Price Index"
    assert "EURUSD" in retrieved["affected_instruments"]

    # Re-insert with updated forecast
    event["forecast"] = "0.4%"
    updated = test_db.upsert_economic_event(event)
    assert updated is False  # Was updated, not newly inserted

    re_retrieved = test_db.get_event_by_id("test-cpi-01")
    assert re_retrieved["forecast"] == "0.4%"


def test_notification_duplicate_prevention(test_db):
    event_id = "test-nfp-99"

    # First notification record
    res1 = test_db.record_notification(
        event_id=event_id,
        event_title="US Non-Farm Payrolls",
        event_time_utc="2026-11-10T13:30:00Z",
        channel="telegram",
        recipient="12345",
        status="sent",
        message_content="Alert content",
        minutes_before=30.0
    )
    assert res1 is True
    assert test_db.is_notification_sent(event_id, "telegram") is True

    # Duplicate attempt on same channel
    res2 = test_db.record_notification(
        event_id=event_id,
        event_title="US Non-Farm Payrolls",
        event_time_utc="2026-11-10T13:30:00Z",
        channel="telegram",
        recipient="12345",
        status="sent",
        message_content="Duplicate attempt",
        minutes_before=30.0
    )
    assert res2 is False  # Prevented by UNIQUE constraint


def test_system_logs(test_db):
    test_db.log("INFO", "UNIT_TEST", "Test log message", "Details string")
    logs = test_db.get_logs(10)
    assert len(logs) >= 1
    assert logs[0]["component"] == "UNIT_TEST"
    assert logs[0]["message"] == "Test log message"
