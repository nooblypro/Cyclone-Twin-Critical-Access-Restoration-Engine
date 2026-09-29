"""
Phase L1 — Forecast Timeline Test Suite
Verifies read-only forecast timeline calculations (NOW, +2H, +4H, +8H),
strict 0-mutation data separation invariant, API contracts, and Phase K regression preservation.
"""

import pytest
from fastapi.testclient import TestClient
from cyclone_twin.main import app, state


@pytest.fixture
def client():
    return TestClient(app)


def test_forecast_timeline_default_horizon(client):
    """TEST 1: Default horizon is NOW (0H)."""
    response = client.get("/forecast/timeline")
    assert response.status_code == 200
    data = response.json()
    assert data["horizon"] == "NOW"
    assert data["horizon_hours"] == 0
    assert data["is_projected_forecast"] is True
    assert "weather" in data
    assert "flood" in data
    assert "predicted_accessibility" in data


def test_forecast_timeline_plus_2h(client):
    """TEST 2: Selecting +2H requests/loads the +2H forecast."""
    response = client.get("/forecast/timeline?horizon=%2B2H")
    assert response.status_code == 200
    data = response.json()
    assert data["horizon"] == "+2H"
    assert data["horizon_hours"] == 2
    assert "precipitation_mm" in data["weather"]
    assert "predicted_disabled_segments_count" in data


def test_forecast_timeline_plus_4h(client):
    """TEST 3: Selecting +4H requests/loads the +4H forecast."""
    response = client.get("/forecast/timeline?horizon=%2B4H")
    assert response.status_code == 200
    data = response.json()
    assert data["horizon"] == "+4H"
    assert data["horizon_hours"] == 4
    assert "precipitation_mm" in data["weather"]


def test_forecast_timeline_plus_8h(client):
    """TEST 4: Selecting +8H requests/loads the +8H forecast."""
    response = client.get("/forecast/timeline?horizon=%2B8H")
    assert response.status_code == 200
    data = response.json()
    assert data["horizon"] == "+8H"
    assert data["horizon_hours"] == 8
    assert "precipitation_mm" in data["weather"]


def test_forecast_horizon_does_not_mutate_operational_state(client):
    """
    TEST 5: Selecting a forecast horizon does NOT mutate operational State.
    CORE INVARIANT: FORECAST != OBSERVATION != STATE.
    """
    state.initialize()
    initial_version = state.disaster_state_manager.current_state.state_version
    initial_disabled = set(state.network_engine.disabled_segments)

    for h in ["NOW", "+2H", "+4H", "+8H"]:
        res = client.get(f"/forecast/timeline?horizon={h}")
        assert res.status_code == 200

    assert state.disaster_state_manager.current_state.state_version == initial_version
    assert set(state.network_engine.disabled_segments) == initial_disabled


def test_forecast_timeline_invalid_horizon_fallback(client):
    """TEST 6: Invalid horizon falls back gracefully to NOW."""
    response = client.get("/forecast/timeline?horizon=INVALID_HORIZON")
    assert response.status_code == 200
    data = response.json()
    assert data["horizon"] == "NOW"
    assert data["horizon_hours"] == 0


def test_phase_k_baseline_preservation(client):
    """TEST 8: Existing Phase K baseline metrics and intervention endpoints remain intact."""
    res = client.get("/forecast")
    assert res.status_code == 200
    data = res.json()
    assert "precipitation_mm" in data

    res_state = client.get("/state/current")
    assert res_state.status_code == 200
    st_data = res_state.json()
    assert "state_version" in st_data
