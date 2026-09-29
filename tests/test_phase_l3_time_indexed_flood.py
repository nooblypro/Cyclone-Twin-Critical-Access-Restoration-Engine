"""
Phase L3 — Time-Indexed Flood Forecasting Test Suite
Verifies time-indexed flood forecasting pipeline across operational horizons (NOW, +2H, +4H, +8H),
temporal offset correctness, provenance, isolated projected network calculation,
strict 0-mutation operational state invariant, and Phase K/L1/L2 baseline preservation.
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from cyclone_twin.domain.entities import RoadVulnerability, VulnerabilityForecast
from cyclone_twin.providers.flood_model import TimeIndexedFloodForecaster, HANDFloodModel
from cyclone_twin.providers.weather_provider import CalibratedWeatherProvider
from cyclone_twin.main import app, state


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def forecaster():
    return TimeIndexedFloodForecaster(
        weather_provider=CalibratedWeatherProvider(),
        flood_model=HANDFloodModel(),
    )


def test_now_forecast_generated(forecaster):
    """TEST 1: NOW (0H) forecast generated successfully."""
    vf = forecaster.generate_horizon_forecast(horizon_hours=0)
    assert vf.horizon_hours == 0
    assert vf.rainfall_mm >= 0.0
    assert vf.is_projected_forecast is True


def test_plus_2h_forecast_generated(forecaster):
    """TEST 2: +2H forecast generated successfully."""
    vf = forecaster.generate_horizon_forecast(horizon_hours=2)
    assert vf.horizon_hours == 2
    assert vf.rainfall_mm >= 30.0
    assert vf.is_projected_forecast is True


def test_plus_4h_forecast_generated(forecaster):
    """TEST 3: +4H forecast generated successfully."""
    vf = forecaster.generate_horizon_forecast(horizon_hours=4)
    assert vf.horizon_hours == 4
    assert vf.rainfall_mm >= 130.0
    assert vf.is_projected_forecast is True


def test_plus_8h_forecast_generated(forecaster):
    """TEST 4: +8H forecast generated successfully."""
    vf = forecaster.generate_horizon_forecast(horizon_hours=8)
    assert vf.horizon_hours == 8
    assert vf.rainfall_mm >= 180.0
    assert vf.is_projected_forecast is True


def test_forecast_time_equals_reference_plus_horizon(forecaster):
    """TEST 5: forecast_time correctly equals reference_time + horizon."""
    ref_time = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    for h in [0, 2, 4, 8]:
        vf = forecaster.generate_horizon_forecast(horizon_hours=h, reference_time=ref_time)
        expected_target = ref_time + timedelta(hours=h)
        assert vf.forecast_time == expected_target
        assert vf.reference_time == ref_time


def test_all_horizons_have_valid_provenance(forecaster):
    """TEST 6: All horizons have valid provenance."""
    for h in [0, 2, 4, 8]:
        vf = forecaster.generate_horizon_forecast(horizon_hours=h)
        assert "weather_provider" in vf.provenance
        assert "flood_model" in vf.provenance
        assert vf.weather_source == "calibrated_fallback"
        assert vf.flood_model == "hand_model"


def test_all_horizons_contain_projected_forecast_metadata(forecaster):
    """TEST 7: All horizons contain projected forecast metadata."""
    for h in [0, 2, 4, 8]:
        vf = forecaster.generate_horizon_forecast(horizon_hours=h)
        assert vf.is_projected_forecast is True
        assert len(vf.assumptions) > 0
        assert len(vf.limitations) > 0
        assert "HAND-based inundation model" in vf.limitations[0]


def test_flood_model_receives_correct_weather_input(forecaster):
    """TEST 8: Flood model receives the correct time-indexed weather input."""
    vf_now = forecaster.generate_horizon_forecast(horizon_hours=0)
    vf_8h = forecaster.generate_horizon_forecast(horizon_hours=8)
    assert vf_now.rainfall_mm < vf_8h.rainfall_mm
    assert vf_now.water_level_m <= vf_8h.water_level_m


def test_road_vulnerabilities_contain_correct_forecast_time(forecaster):
    """TEST 9: Projected road vulnerability records contain correct forecast_time."""
    state.initialize()
    ref_time = datetime(2026, 9, 27, 14, 0, 0, tzinfo=timezone.utc)
    vf = forecaster.generate_horizon_forecast(
        horizon_hours=4,
        reference_time=ref_time,
        graph=state.data_loader.graph,
    )
    expected_target = ref_time + timedelta(hours=4)
    for rv in vf.road_vulnerabilities:
        assert rv.forecast_time == expected_target
        assert rv.is_predicted is True


def test_forecast_generation_does_not_mutate_network_engine(forecaster):
    """TEST 10: Forecast generation does not mutate operational NetworkEngine state."""
    state.initialize()
    initial_disabled = list(state.network_engine.disabled_segments)

    _ = forecaster.generate_horizon_forecast(
        horizon_hours=8,
        graph=state.data_loader.graph,
        communities=state.data_loader.communities,
        facilities=state.data_loader.facilities,
    )

    assert list(state.network_engine.disabled_segments) == initial_disabled


def test_forecast_generation_does_not_mutate_disaster_state(forecaster):
    """TEST 11: Forecast generation does not mutate DisasterState."""
    state.initialize()
    initial_version = state.disaster_state_manager.current_state.state_version

    _ = forecaster.generate_horizon_forecast(horizon_hours=4)

    assert state.disaster_state_manager.current_state.state_version == initial_version


def test_multiple_horizons_do_not_contaminate_one_another(forecaster):
    """TEST 12: Multiple horizons generated independently do not contaminate one another."""
    ref_time = datetime.now(timezone.utc)
    vf_0 = forecaster.generate_horizon_forecast(horizon_hours=0, reference_time=ref_time)
    vf_2 = forecaster.generate_horizon_forecast(horizon_hours=2, reference_time=ref_time)
    vf_4 = forecaster.generate_horizon_forecast(horizon_hours=4, reference_time=ref_time)
    vf_8 = forecaster.generate_horizon_forecast(horizon_hours=8, reference_time=ref_time)

    assert vf_0.horizon_hours == 0
    assert vf_2.horizon_hours == 2
    assert vf_4.horizon_hours == 4
    assert vf_8.horizon_hours == 8

    assert vf_0.forecast_time < vf_2.forecast_time < vf_4.forecast_time < vf_8.forecast_time


def test_existing_l1_timeline_endpoint_works(client):
    """TEST 13: Existing L1 timeline endpoint still works."""
    for h in ["NOW", "%2B2H", "%2B4H", "%2B8H"]:
        res = client.get(f"/forecast/timeline?horizon={h}")
        assert res.status_code == 200
        data = res.json()
        assert "vulnerability_forecast" in data
        assert data["is_projected_forecast"] is True


def test_existing_l2_domain_validation_works():
    """TEST 14: Existing L2 domain validation still works."""
    with pytest.raises(Exception):
        _ = VulnerabilityForecast(forecast_id="ERR", confidence=1.5)


def test_phase_k_intervention_flow_unchanged(client):
    """TEST 15: Phase K intervention flow remains unchanged."""
    res = client.get("/interventions")
    assert res.status_code == 200
    assert "interventions" in res.json()


def test_baseline_operational_state_unchanged_after_all_forecasts(client):
    """TEST 16: Baseline operational state remains unchanged after executing all four forecasts."""
    state.initialize()
    initial_ver = state.disaster_state_manager.current_state.state_version
    initial_disabled_count = len(state.network_engine.disabled_segments)

    for h in ["NOW", "%2B2H", "%2B4H", "%2B8H"]:
        _ = client.get(f"/forecast/timeline?horizon={h}")

    assert state.disaster_state_manager.current_state.state_version == initial_ver
    assert len(state.network_engine.disabled_segments) == initial_disabled_count
