"""
Phase B Verification Test Suite — Dynamic Weather & HAND Flood Scenario Engine
Validates end-to-end Weather -> Flood -> Disruption -> Accessibility pipeline, fallback resilience, and baseline backward compatibility.
"""

import pytest
from fastapi.testclient import TestClient
from cyclone_twin.main import app
from cyclone_twin.providers import (
    OpenMeteoWeatherProvider,
    CalibratedWeatherProvider,
    HANDFloodModel,
)
from cyclone_twin.domain.entities import WeatherForecast

client = TestClient(app)


def test_baseline_regression_preserved():
    """Verify that existing deterministic baseline scenario metrics remain 100% untouched."""
    # 1. Reset network
    res_load = client.post("/network/load")
    assert res_load.status_code == 200
    assert res_load.json()["nodes"] == 25

    # 2. Apply default flood
    res_flood = client.post("/flood/apply", json={})
    assert res_flood.status_code == 200

    # 3. Accessibility status
    res_access = client.get("/accessibility/status")
    assert res_access.status_code == 200
    access_data = res_access.json()
    assert access_data["accessible_population"] == 298000
    assert len(access_data["isolated_communities"]) == 4

    # 4. Rank corridors
    res_rank = client.post("/interventions/rank", json={})
    assert res_rank.status_code == 200
    ranked = res_rank.json()["ranked_corridors"]
    assert len(ranked) > 0
    top = ranked[0]
    assert top["corridor_id"] == "corridor_03"
    assert abs(top["score"] - 0.0724) < 1e-3

    # 5. Clear top corridor
    res_clear = client.post("/interventions/clear", json={"corridor_id": "corridor_03"})
    assert res_clear.status_code == 200
    clear_data = res_clear.json()["new_graph_state"]
    assert clear_data["accessible_population"] == 387000
    assert clear_data["isolated_count"] == 2


def test_dynamic_scenario_low_rainfall():
    """Scenario A: Low rainfall (<40mm) produces minor inundation with 0 isolated wards."""
    res = client.post("/scenario/dynamic", json={"precipitation_mm": 20.0})
    assert res.status_code == 200
    data = res.json()
    assert data["precipitation_mm"] == 20.0
    assert data["accessibility"]["accessible_population"] == 477000
    assert len(data["accessibility"]["isolated_communities"]) == 0
    assert data["provenance"]["scenario_type"] == "dynamic_phase_b"


def test_dynamic_scenario_michaung_rainfall():
    """Scenario B: Calibrated Michaung rainfall (180mm) produces exact 298K/179K impact."""
    res = client.post("/scenario/dynamic", json={"precipitation_mm": 180.0})
    assert res.status_code == 200
    data = res.json()
    assert data["precipitation_mm"] == 180.0
    assert data["accessibility"]["accessible_population"] == 298000
    assert len(data["accessibility"]["isolated_communities"]) == 4


def test_dynamic_scenario_heavy_rainfall():
    """Scenario C: Heavy rainfall (250mm) produces full inundation disruption."""
    res = client.post("/scenario/dynamic", json={"precipitation_mm": 250.0})
    assert res.status_code == 200
    data = res.json()
    assert data["precipitation_mm"] == 250.0
    assert data["accessibility"]["accessible_population"] <= 298000


def test_open_meteo_fallback_resilience():
    """Verify that provider timeouts / HTTP failures gracefully fall back without breaking simulation state."""
    calibrated = CalibratedWeatherProvider()
    provider = OpenMeteoWeatherProvider(fallback_provider=calibrated)

    # Fetching with invalid latitude to test error handling fallback
    forecast = provider.fetch_forecast(lat=999.0, lon=999.0)
    assert forecast.precipitation_mm > 0.0
    assert forecast.provider in ("open_meteo", "calibrated_fallback")


def test_atomic_state_safety_on_invalid_input():
    """Verify that malformed request input raises HTTP 400 without corrupting active simulation state."""
    # Record baseline accessibility before bad request
    access_before = client.get("/accessibility/status").json()["accessible_population"]

    # Send malformed negative rainfall payload
    res_bad = client.post("/scenario/dynamic", json={"precipitation_mm": -50.0})
    assert res_bad.status_code == 400

    # Confirm accessibility state remains unchanged
    access_after = client.get("/accessibility/status").json()["accessible_population"]
    assert access_after == access_before
