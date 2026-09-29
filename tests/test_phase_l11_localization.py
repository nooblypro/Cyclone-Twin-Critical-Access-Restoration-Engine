"""
Phase L11 — Localization / Internationalization Tests
Verifies frontend dictionary structure, key completeness, locale independence of API contracts,
machine-readable enum immutability, zero state mutation, and non-translation of domain codes.
"""

import json
import os
import pytest
from fastapi.testclient import TestClient

from cyclone_twin.main import app, state


@pytest.fixture
def test_client():
    client = TestClient(app)
    yield client


# -----------------------------------------------------------------------------
# 1. Locale Dictionary Files Integrity & Structure
# -----------------------------------------------------------------------------

def test_l11_en_dictionary_exists():
    path = os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "i18n", "locales", "en.js")
    assert os.path.exists(path), "en.js locale file must exist"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "export const en =" in content
    assert "title: \"CYCLONE TWIN\"" in content or "title:" in content
    assert "ROAD_FLOODED" in content
    assert "SUBMITTED" in content


def test_l11_ta_dictionary_exists():
    path = os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "i18n", "locales", "ta.js")
    assert os.path.exists(path), "ta.js locale file must exist"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "export const ta =" in content
    assert "ROAD_FLOODED" in content
    assert "SUBMITTED" in content


def test_l11_i18n_context_exists():
    path = os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "i18n", "i18nContext.jsx")
    assert os.path.exists(path), "i18nContext.jsx must exist"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "createContext" in content
    assert "useI18n" in content
    assert "SUPPORTED_LOCALES" in content
    assert "formatNumber" in content
    assert "formatDate" in content
    assert "getReportTypeLabel" in content


# -----------------------------------------------------------------------------
# 2. Machine-Readable Enum Immutability Under Localization
# -----------------------------------------------------------------------------

def test_l11_machine_enum_road_flooded_preserved(test_client):
    payload = {
        "report_type": "ROAD_FLOODED",
        "lat": 13.0450,
        "lon": 80.2210,
        "description": "Flooded road near Saidapet",
    }
    # Pass Accept-Language header to test API neutrality
    resp = test_client.post("/observations/citizen", json=payload, headers={"Accept-Language": "ta-IN,ta;q=0.9"})
    assert resp.status_code == 200
    data = resp.json()

    # Machine-readable report_type MUST remain "ROAD_FLOODED", NOT translated string
    assert data["citizen_report"]["report_type"] == "ROAD_FLOODED"
    assert data["citizen_report"]["provenance"]["source"] == "citizen_pgis"


def test_l11_machine_enum_road_passable_preserved(test_client):
    payload = {
        "report_type": "ROAD_PASSABLE",
        "lat": 13.0400,
        "lon": 80.2200,
        "description": "Clear road",
    }
    resp = test_client.post("/observations/citizen", json=payload, headers={"Accept-Language": "ta-IN"})
    assert resp.status_code == 200
    assert resp.json()["citizen_report"]["report_type"] == "ROAD_PASSABLE"


def test_l11_machine_enum_drain_overflow_preserved(test_client):
    payload = {
        "report_type": "DRAIN_OVERFLOW",
        "lat": 13.0500,
        "lon": 80.2300,
        "description": "Storm drain overflowing",
    }
    resp = test_client.post("/observations/citizen", json=payload, headers={"Accept-Language": "en-US"})
    assert resp.status_code == 200
    assert resp.json()["citizen_report"]["report_type"] == "DRAIN_OVERFLOW"


def test_l11_machine_enum_hospital_access_blocked_preserved(test_client):
    payload = {
        "report_type": "HOSPITAL_ACCESS_BLOCKED",
        "lat": 13.0600,
        "lon": 80.2400,
        "description": "Hospital entrance blocked",
    }
    resp = test_client.post("/observations/citizen", json=payload)
    assert resp.status_code == 200
    assert resp.json()["citizen_report"]["report_type"] == "HOSPITAL_ACCESS_BLOCKED"


# -----------------------------------------------------------------------------
# 3. Data vs Presentation Separation — API Output Neutrality
# -----------------------------------------------------------------------------

def test_l11_api_forecast_unaffected_by_locale_headers(test_client):
    resp_en = test_client.get("/forecast", headers={"Accept-Language": "en-US"})
    resp_ta = test_client.get("/forecast", headers={"Accept-Language": "ta-IN"})

    assert resp_en.status_code == 200
    assert resp_ta.status_code == 200

    data_en = resp_en.json()
    data_ta = resp_ta.json()

    # Domain values must be identical regardless of Accept-Language
    assert data_en["horizon_hours"] == data_ta["horizon_hours"]
    assert data_en.get("is_projected_forecast") == data_ta.get("is_projected_forecast")


def test_l11_api_counterfactual_ranking_unaffected_by_locale(test_client):
    # Apply flood first
    test_client.post("/flood/apply", json={})
    resp = test_client.post("/interventions/rank", json={"weights": {"w_h": 0.4, "w_p": 0.3, "w_t": 0.2, "w_d": 0.1}}, headers={"Accept-Language": "ta-IN"})
    assert resp.status_code == 200
    ranked = resp.json()["ranked_corridors"]
    assert len(ranked) > 0
    # Field names must remain English machine keys
    assert "corridor_id" in ranked[0]
    assert "score" in ranked[0]
    assert "score_breakdown" in ranked[0]


def test_l11_api_drainage_unaffected_by_locale(test_client):
    resp = test_client.get("/infrastructure/drainage", headers={"Accept-Language": "ta-IN"})
    assert resp.status_code == 200
    data = resp.json()
    assert "assets" in data
    assert data["assets"][0]["blockage_status"] in ["open", "partially_blocked", "inoperable"]


def test_l11_api_disaster_state_unaffected_by_locale(test_client):
    resp = test_client.get("/state/current", headers={"Accept-Language": "ta-IN"})
    assert resp.status_code == 200
    data = resp.json()
    assert "state_version" in data
    assert "scenario_id" in data


# -----------------------------------------------------------------------------
# 4. Zero State Mutation Invariant Under Localization
# -----------------------------------------------------------------------------

def test_l11_citizen_report_with_locale_zero_state_mutation(test_client):
    state_before = test_client.get("/state/current").json()
    payload = {
        "report_type": "ROAD_FLOODED",
        "lat": 13.0150,
        "lon": 80.2010,
        "description": "Flooded road in Tamil locale mode",
    }
    resp = test_client.post("/observations/citizen", json=payload, headers={"Accept-Language": "ta-IN"})
    assert resp.status_code == 200

    state_after = test_client.get("/state/current").json()
    # State version MUST NOT mutate upon observation submission alone
    assert state_before["state_version"] == state_after["state_version"]


# -----------------------------------------------------------------------------
# 5. Numeric & Coordinate Localization Neutrality
# -----------------------------------------------------------------------------

def test_l11_coordinate_parsing_locale_neutral(test_client):
    payload = {
        "report_type": "ROAD_BLOCKED",
        "lat": 13.025,
        "lon": 80.211,
        "confidence": 0.85,
    }
    resp = test_client.post("/observations/citizen", json=payload)
    assert resp.status_code == 200
    report = resp.json()["citizen_report"]
    assert report["report_type"] == "ROAD_BLOCKED"
    assert report["confidence"] > 0



def test_l11_nan_coordinate_rejected_regardless_of_locale(test_client):
    payload = {
        "report_type": "ROAD_FLOODED",
        "lat": "NaN",
        "lon": 80.2210,
    }
    resp = test_client.post("/observations/citizen", json=payload, headers={"Accept-Language": "ta-IN"})
    assert resp.status_code == 400


# -----------------------------------------------------------------------------
# 6. Architectural Invariant Assertion
# -----------------------------------------------------------------------------

def test_l11_architectural_invariant_forecast_obs_state_separation(test_client):
    """
    Asserts FORECAST != OBSERVATION != STATE under localized client operations.
    """
    forecast_data = test_client.get("/forecast").json()
    citizen_resp = test_client.post("/observations/citizen", json={
        "report_type": "ROAD_FLOODED",
        "lat": 13.0850,
        "lon": 80.2910,
    }).json()
    state_data = test_client.get("/state/current").json()

    # 1. Forecast horizon object
    assert "horizon_hours" in forecast_data
    # 2. Observation entity
    assert citizen_resp["citizen_report"]["provenance"]["source"] == "citizen_pgis"
    assert citizen_resp["citizen_report"]["status"] in ["SUBMITTED", "submitted", "DUPLICATE"]
    # 3. State object
    assert "state_version" in state_data
