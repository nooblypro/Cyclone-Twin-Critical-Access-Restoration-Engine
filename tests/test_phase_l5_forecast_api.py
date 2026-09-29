"""
Phase L5 — Forecast API & Integration Contract Unit Tests
Verifies REST API endpoints (/forecast, /forecast/timeline, /forecast/vulnerability),
query validation, read-only guarantees, isolation, provenance, non-leakage of secrets,
and OpenAPI schema validity.
"""

import pytest
from fastapi.testclient import TestClient
from cyclone_twin.main import app, state
from cyclone_twin.network_engine import NetworkEngine


@pytest.fixture
def client():
    return TestClient(app)


def test_get_forecast_200(client):
    response = client.get("/forecast")
    assert response.status_code == 200
    data = response.json()
    assert "precipitation_mm" in data or "rainfall_mm" in data
    assert "provider" in data or "weather_source" in data
    assert data.get("is_projected_forecast") is True


def test_get_forecast_timeline_200(client):
    response = client.get("/forecast/timeline?horizon=NOW")
    assert response.status_code == 200
    data = response.json()
    assert data["horizon"] == "NOW"
    assert "vulnerability_forecast" in data
    assert data["is_projected_forecast"] is True


def test_get_forecast_vulnerability_now_200(client):
    response = client.get("/forecast/vulnerability?horizon=NOW")
    assert response.status_code == 200
    data = response.json()
    assert data["horizon"] == "NOW"
    assert data["horizon_hours"] == 0
    assert "vulnerability_summary" in data
    assert "vulnerability_assessments" in data
    assert data["is_projected_forecast"] is True


def test_plus_2h_vulnerability_forecast(client):
    response = client.get("/forecast/vulnerability?horizon=+2H")
    assert response.status_code == 200
    data = response.json()
    assert data["horizon"] == "+2H"
    assert data["horizon_hours"] == 2


def test_plus_4h_vulnerability_forecast(client):
    response = client.get("/forecast/vulnerability?horizon=+4H")
    assert response.status_code == 200
    data = response.json()
    assert data["horizon"] == "+4H"
    assert data["horizon_hours"] == 4


def test_plus_8h_vulnerability_forecast(client):
    response = client.get("/forecast/vulnerability?horizon=+8H")
    assert response.status_code == 200
    data = response.json()
    assert data["horizon"] == "+8H"
    assert data["horizon_hours"] == 8


def test_invalid_vulnerability_horizon_handled(client):
    response = client.get("/forecast/vulnerability?horizon=garbage")
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Invalid forecast horizon 'garbage'" in data["detail"]


def test_forecast_response_contains_provenance(client):
    response = client.get("/forecast/vulnerability?horizon=+2H")
    assert response.status_code == 200
    data = response.json()
    assert "provenance" in data
    assert "weather_source" in data
    assert "flood_model" in data


def test_vulnerability_response_contains_assessments(client):
    response = client.get("/forecast/vulnerability?horizon=+2H")
    assert response.status_code == 200
    data = response.json()
    assessments = data["vulnerability_assessments"]
    assert isinstance(assessments, list)
    if assessments:
        ass = assessments[0]
        assert "segment_id" in ass
        assert "vulnerability_score" in ass
        assert "explanation" in ass


def test_vulnerability_response_contains_summary(client):
    response = client.get("/forecast/vulnerability?horizon=+4H")
    assert response.status_code == 200
    data = response.json()
    summary = data["vulnerability_summary"]
    assert "total_assessed_segments" in summary
    assert "max_vulnerability_score" in summary


def test_vulnerability_response_does_not_contain_intervention_priority(client):
    response = client.get("/forecast/vulnerability?horizon=+2H")
    assert response.status_code == 200
    data = response.json()
    assert "recommended_interventions" not in data
    assert "restoration_priority" not in data
    assert "priority_rank" not in data


def test_forecast_endpoints_do_not_mutate_disaster_state(client):
    ver_before = state.disaster_state_manager.current_version
    _ = client.get("/forecast")
    _ = client.get("/forecast/timeline?horizon=+4H")
    _ = client.get("/forecast/vulnerability?horizon=+8H")
    ver_after = state.disaster_state_manager.current_version
    assert ver_after == ver_before


def test_forecast_endpoints_do_not_mutate_network_engine(client):
    state.initialize()
    disabled_before = set(state.network_engine.disabled_segments)
    _ = client.get("/forecast/vulnerability?horizon=+4H")
    disabled_after = set(state.network_engine.disabled_segments)
    assert disabled_after == disabled_before


def test_forecast_endpoints_do_not_mutate_observations(client):
    obs_before = len(state.disaster_state_manager.observation_pipeline.get_active_observations()) if hasattr(state.disaster_state_manager, "observation_pipeline") else 0
    _ = client.get("/forecast/vulnerability?horizon=+2H")
    obs_after = len(state.disaster_state_manager.observation_pipeline.get_active_observations()) if hasattr(state.disaster_state_manager, "observation_pipeline") else 0
    assert obs_after == obs_before


def test_forecast_endpoints_do_not_mutate_interventions(client):
    int_before = len(state.intervention_manager.interventions)
    _ = client.get("/forecast/vulnerability?horizon=+4H")
    int_after = len(state.intervention_manager.interventions)
    assert int_after == int_before


def test_repeated_identical_requests_are_deterministic(client):
    res1 = client.get("/forecast/vulnerability?horizon=+4H").json()
    res2 = client.get("/forecast/vulnerability?horizon=+4H").json()
    assert res1["vulnerability_summary"]["max_vulnerability_score"] == res2["vulnerability_summary"]["max_vulnerability_score"]
    assert len(res1["vulnerability_assessments"]) == len(res2["vulnerability_assessments"])


def test_forecast_horizons_are_isolated(client):
    res_now = client.get("/forecast/vulnerability?horizon=NOW").json()
    res_8h = client.get("/forecast/vulnerability?horizon=+8H").json()
    assert res_now["horizon"] == "NOW"
    assert res_8h["horizon"] == "+8H"


def test_existing_l1_timeline_remains_compatible(client):
    res = client.get("/forecast/timeline?horizon=NOW")
    assert res.status_code == 200
    data = res.json()
    assert "weather" in data
    assert "flood" in data
    assert "predicted_accessibility" in data


def test_l2_domain_models_remain_valid():
    from cyclone_twin.domain.entities import RoadVulnerability, VulnerabilityForecast
    vuln = RoadVulnerability(segment_id="SEG-L2", predicted_depth_m=0.5)
    assert vuln.segment_id == "SEG-L2"


def test_l3_forecast_generation_remains_valid():
    from cyclone_twin.providers.flood_model import TimeIndexedFloodForecaster
    forecaster = TimeIndexedFloodForecaster()
    fcst = forecaster.generate_horizon_forecast(horizon_hours=2)
    assert fcst.horizon_hours == 2


def test_l4_scoring_remains_valid():
    from cyclone_twin.providers.vulnerability_engine import DeterministicVulnerabilityEngine
    from cyclone_twin.providers.flood_model import TimeIndexedFloodForecaster
    forecaster = TimeIndexedFloodForecaster()
    fcst = forecaster.generate_horizon_forecast(horizon_hours=4)
    engine = DeterministicVulnerabilityEngine()
    summary = engine.evaluate_forecast(fcst)
    assert summary.total_assessed_segments >= 0


def test_phase_k_remains_valid(client):
    res = client.get("/interventions")
    assert res.status_code == 200


def test_no_stack_traces_exposed_on_controlled_provider_failure(client):
    res = client.get("/forecast/vulnerability?horizon=invalid_horizon_val")
    assert res.status_code == 400
    text = res.text
    assert "Traceback" not in text
    assert "/Users/" not in text
    assert "File \"" not in text


def test_no_secrets_exposed_in_responses(client):
    res = client.get("/forecast/vulnerability?horizon=+2H")
    text = res.text.lower()
    assert "gemini_api_key" not in text
    assert "secret" not in text
    assert "private_key" not in text


def test_openapi_schema_generation(client):
    res = client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    paths = schema.get("paths", {})
    assert "/forecast" in paths
    assert "/forecast/timeline" in paths
    assert "/forecast/vulnerability" in paths
