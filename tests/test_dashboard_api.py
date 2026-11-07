"""
Unit tests for FastAPI dashboard endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from bandi.dashboard.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root_dashboard_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "BANDI" in response.text


def test_api_status_endpoint(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "app_name" in data
    assert "time_sast" in data
    assert "telegram" in data
    assert "mt5" in data


def test_api_calendar_events_endpoint(client):
    response = client.get("/api/calendar/events?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert "count" in data


def test_api_research_overview_endpoint(client):
    response = client.get("/api/research/overview")
    assert response.status_code == 200
    data = response.json()
    assert "macro" in data
    assert "currency_strength" in data


def test_api_watchlist_endpoint(client):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert "symbols" in data
    assert len(data["symbols"]) == 12  # All 12 watchlist symbols present
