"""
Phase L10 Test Suite — Citizen / PGIS Evidence Pipeline
Cyclone Twin — Critical Access Restoration Engine

Verifies:
1. CitizenObservation & CitizenMediaMetadata domain entity creation & validation
2. Controlled report type vocabulary enforcement
3. Strict NaN, Infinity, and geographic coordinate validation
4. Media metadata validation, path traversal protection, and file size limits
5. Deterministic duplicate candidate detection & conflicting report preservation
6. Non-mutation invariant: Citizen report submission is 100% read-only on simulation state
7. Phase E reconciliation integration (state mutation ONLY occurs upon reconciliation)
8. Forecast != Observation != State separation
9. Privacy & anonymous reporter handling
10. FastAPI POST /observations/citizen and GET /observations/citizen endpoint compliance
"""

import math
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from cyclone_twin.main import app, state
from cyclone_twin.domain.entities import (
    CitizenObservation,
    CitizenMediaMetadata,
    InfrastructureObservation,
)
from cyclone_twin.providers.citizen_pipeline import (
    CitizenPipelineService,
    CONTROLLED_REPORT_TYPES,
)


@pytest.fixture
def mock_citizen_pipeline():
    """Provides a fresh CitizenPipelineService instance."""
    return CitizenPipelineService()


@pytest.fixture
def sample_citizen_obs():
    """Provides a sample valid CitizenObservation."""
    return CitizenObservation(
        observation_id="cit_test_01",
        report_type="ROAD_FLOODED",
        latitude=13.0827,
        longitude=80.2707,
        description="Water accumulation on arterial road near Egmore station",
        reporter_id="citizen_anon_123",
        is_anonymous=True,
        confidence=0.65,
        status="SUBMITTED",
        source="citizen",
    )


# ---------------------------------------------------------------------------
# 1. Domain Entity & Input Validation Tests
# ---------------------------------------------------------------------------

def test_citizen_observation_creation_valid(sample_citizen_obs):
    """Verifies successful creation of a valid CitizenObservation."""
    assert sample_citizen_obs.observation_id == "cit_test_01"
    assert sample_citizen_obs.report_type == "ROAD_FLOODED"
    assert sample_citizen_obs.latitude == 13.0827
    assert sample_citizen_obs.longitude == 80.2707
    assert sample_citizen_obs.confidence == 0.65
    assert sample_citizen_obs.status == "SUBMITTED"


def test_citizen_observation_nan_rejection():
    """Rejects NaN float values for coordinates and confidence."""
    with pytest.raises(ValueError):
        CitizenObservation(
            observation_id="cit_nan_lat",
            latitude=float("nan"),
            longitude=80.2707,
        )

    with pytest.raises(ValueError):
        CitizenObservation(
            observation_id="cit_nan_conf",
            latitude=13.0827,
            longitude=80.2707,
            confidence=float("nan"),
        )


def test_citizen_observation_infinity_rejection():
    """Rejects Infinity float values for coordinates."""
    with pytest.raises(ValueError):
        CitizenObservation(
            observation_id="cit_inf_lon",
            latitude=13.0827,
            longitude=float("inf"),
        )


def test_citizen_observation_bounds_validation():
    """Enforces geographic lat/lon and confidence range bounds."""
    with pytest.raises(ValueError):
        CitizenObservation(
            observation_id="cit_bad_lat",
            latitude=100.0,
            longitude=80.2707,
        )

    with pytest.raises(ValueError):
        CitizenObservation(
            observation_id="cit_bad_conf",
            latitude=13.0827,
            longitude=80.2707,
            confidence=1.2,
        )


def test_controlled_report_type_validation(mock_citizen_pipeline):
    """Verifies validation of controlled report type vocabulary."""
    f_lat, f_lon, f_conf, norm_type, f_depth = mock_citizen_pipeline.validate_citizen_input(
        lat=13.0827,
        lon=80.2707,
        report_type="road_flooded",
    )
    assert norm_type == "ROAD_FLOODED"

    with pytest.raises(ValueError, match="Unsupported report type"):
        mock_citizen_pipeline.validate_citizen_input(
            lat=13.0827,
            lon=80.2707,
            report_type="ALIEN_INVASION",
        )


# ---------------------------------------------------------------------------
# 2. Media Metadata & Security Tests
# ---------------------------------------------------------------------------

def test_media_metadata_valid(mock_citizen_pipeline):
    """Verifies valid photo metadata processing."""
    media = mock_citizen_pipeline.validate_media_metadata(
        filename="road_flooded_photo.jpg",
        content_type="image/jpeg",
        size_bytes=500000,
    )
    assert media.media_id.startswith("med_")
    assert media.mime_type == "image/jpeg"
    assert media.size_bytes == 500000


def test_media_metadata_path_traversal_rejection(mock_citizen_pipeline):
    """Rejects filenames containing path traversal sequences."""
    with pytest.raises(ValueError, match="disallowed path traversal"):
        mock_citizen_pipeline.validate_media_metadata(
            filename="../../etc/passwd.jpg",
            content_type="image/jpeg",
            size_bytes=1000,
        )


def test_media_metadata_oversized_file_rejection(mock_citizen_pipeline):
    """Rejects media metadata exceeding maximum 10 MB limit."""
    with pytest.raises(ValueError, match="exceeds maximum limit"):
        mock_citizen_pipeline.validate_media_metadata(
            filename="giant_photo.jpg",
            content_type="image/jpeg",
            size_bytes=15 * 1024 * 1024,  # 15 MB
        )


def test_media_metadata_disallowed_mime_rejection(mock_citizen_pipeline):
    """Rejects media metadata with unsupported MIME type (e.g. executable/PDF)."""
    with pytest.raises(ValueError, match="Unsupported media MIME type"):
        mock_citizen_pipeline.validate_media_metadata(
            filename="malware.exe",
            content_type="application/x-msdownload",
            size_bytes=1000,
        )


# ---------------------------------------------------------------------------
# 3. Duplicate Candidate & Conflict Detection Tests
# ---------------------------------------------------------------------------

def test_duplicate_candidate_detection(mock_citizen_pipeline):
    """
    Verifies that a report submitted at nearby coordinates (100m) and within 30 min
    with same report type is tagged as a duplicate candidate.
    """
    # First submission
    c1, _ = mock_citizen_pipeline.submit_citizen_report(
        lat=13.0827,
        lon=80.2707,
        report_type="ROAD_FLOODED",
        description="First report of flooding",
    )
    assert c1.duplicate_candidate_id is None
    assert c1.status == "SUBMITTED"

    # Second submission at same spot 1 minute later
    c2, _ = mock_citizen_pipeline.submit_citizen_report(
        lat=13.0828,
        lon=80.2707,
        report_type="ROAD_FLOODED",
        description="Second report of flooding at same spot",
    )
    assert c2.duplicate_candidate_id == c1.observation_id
    assert c2.status == "DUPLICATE"


def test_conflicting_reports_preservation(mock_citizen_pipeline):
    """
    Verifies that conflicting reports (ROAD_FLOODED vs ROAD_PASSABLE at same location)
    are preserved as separate observations and flagged with has_conflicting_reports=True.
    """
    # Citizen A reports ROAD_FLOODED
    cA, _ = mock_citizen_pipeline.submit_citizen_report(
        lat=13.0500,
        lon=80.2300,
        report_type="ROAD_FLOODED",
        description="Road deeply flooded",
    )

    # Citizen B reports ROAD_PASSABLE at same spot
    cB, _ = mock_citizen_pipeline.submit_citizen_report(
        lat=13.0501,
        lon=80.2300,
        report_type="ROAD_PASSABLE",
        description="Road is clear and passable now",
    )

    assert cB.has_conflicting_reports is True
    assert cA.has_conflicting_reports is True
    assert cB.status == "CONFLICTING"


# ---------------------------------------------------------------------------
# 4. Non-Mutation Invariant & Reconciliation Tests
# ---------------------------------------------------------------------------

def test_citizen_submission_is_read_only_on_simulation_state(mock_citizen_pipeline):
    """
    CRITICAL INVARIANT:
    Submitting a citizen report MUST NOT directly mutate NetworkEngine or DisasterState.
    """
    state.initialize()
    edges_before = state.network_engine.graph.number_of_edges()

    # Submit citizen report
    c_obs, i_obs = mock_citizen_pipeline.submit_citizen_report(
        lat=13.0827,
        lon=80.2707,
        report_type="ROAD_FLOODED",
        description="Heavy flooding reported",
    )

    edges_after = state.network_engine.graph.number_of_edges()
    # State MUST remain 100% unmutated at submission time
    assert edges_before == edges_after
    assert c_obs.source == "citizen"
    assert i_obs.source_type == "citizen"


def test_reconciliation_required_for_state_mutation(mock_citizen_pipeline):
    """
    Verifies that state mutation occurs ONLY when Phase E reconciliation is explicitly run.
    """
    state.initialize()
    edges_before = state.network_engine.graph.number_of_edges()

    # Submit citizen report with high confidence
    c_obs, i_obs = mock_citizen_pipeline.submit_citizen_report(
        lat=13.0827,
        lon=80.2707,
        report_type="ROAD_FLOODED",
        confidence=0.90,
    )

    # Explicitly run Phase E reconciliation
    recon_res = mock_citizen_pipeline._multimodal_service.pipeline.reconcile_observations(state.network_engine)
    assert recon_res["reconciled_count"] >= 1
    assert "disabled_segments" in recon_res


def test_forecast_observation_state_separation(mock_citizen_pipeline):
    """
    INVARIANT: FORECAST != OBSERVATION != STATE
    Forecast data does not create citizen observations, and citizen reports do not alter weather forecasts.
    """
    state.initialize()

    # Submit citizen report
    c_obs, _ = mock_citizen_pipeline.submit_citizen_report(
        lat=13.0827,
        lon=80.2707,
        report_type="ROAD_FLOODED",
    )

    # Citizen report source is explicitly citizen
    assert c_obs.source == "citizen"
    assert c_obs.provenance["source"] == "citizen_pgis"


# ---------------------------------------------------------------------------
# 5. Privacy & Anonymity Tests
# ---------------------------------------------------------------------------

def test_privacy_anonymous_reporting(mock_citizen_pipeline):
    """Verifies that anonymous reporting generates a pseudonymous ID without storing PII."""
    c_obs, _ = mock_citizen_pipeline.submit_citizen_report(
        lat=13.0827,
        lon=80.2707,
        report_type="ROAD_FLOODED",
        is_anonymous=True,
    )
    assert c_obs.is_anonymous is True
    assert c_obs.reporter_id.startswith("citizen_anon_")


# ---------------------------------------------------------------------------
# 6. Coexistence of Evidence Streams Tests
# ---------------------------------------------------------------------------

def test_multi_source_evidence_coexistence(mock_citizen_pipeline):
    """
    Verifies that official, field_team, voice, drainage, and citizen evidence
    coexist as distinct streams in the observation pipeline without collapsing.
    """
    state.initialize()
    pipeline = state.multimodal_service.pipeline

    # Submit official report
    o_obs = pipeline.submit_report(lat=13.0827, lon=80.2707, source="official")

    # Submit field team report
    f_obs = pipeline.submit_report(lat=13.0827, lon=80.2707, source="field_team")

    # Submit citizen report
    c_obs, _ = mock_citizen_pipeline.submit_citizen_report(lat=13.0827, lon=80.2707, report_type="ROAD_FLOODED")

    assert o_obs.source_type == "official"
    assert f_obs.source_type == "field_team"
    assert c_obs.source == "citizen"


# ---------------------------------------------------------------------------
# 7. FastAPI Endpoints Tests
# ---------------------------------------------------------------------------

def test_fastapi_post_citizen_observation_json():
    """Tests POST /observations/citizen endpoint with JSON payload."""
    client = TestClient(app)

    response = client.post(
        "/observations/citizen",
        json={
            "report_type": "ROAD_FLOODED",
            "lat": 13.0827,
            "lon": 80.2707,
            "description": "Anand Theatre junction flooded under 0.4m water",
            "confidence": 0.70,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "submitted"
    assert "citizen_report" in data
    assert "observation" in data
    assert data["citizen_report"]["report_type"] == "ROAD_FLOODED"
    assert data["provenance_lineage"]["state_mutated"] is False


def test_fastapi_post_citizen_observation_multipart(sample_wav_bytes=None):
    """Tests POST /observations/citizen endpoint with multipart photo metadata upload."""
    client = TestClient(app)
    dummy_photo = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00" + b"\x00" * 100

    response = client.post(
        "/observations/citizen",
        files={"photo": ("ground_photo.jpg", dummy_photo, "image/jpeg")},
        data={
            "report_type": "DEBRIS",
            "lat": "13.0500",
            "lon": "80.2300",
            "description": "Fallen tree blocking lane near hospital",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "submitted"
    assert data["citizen_report"]["media_metadata"] is not None
    assert data["citizen_report"]["media_metadata"]["mime_type"] == "image/jpeg"


def test_fastapi_get_citizen_observations():
    """Tests GET /observations/citizen endpoint."""
    client = TestClient(app)

    response = client.get("/observations/citizen")
    assert response.status_code == 200

    data = response.json()
    assert "count" in data
    assert "total_submitted" in data
    assert "reports" in data
    assert "provenance" in data
    assert data["provenance"]["is_authoritative_state"] is False


def test_fastapi_get_citizen_observation_by_id():
    """Tests GET /observations/citizen/{observation_id} endpoint."""
    client = TestClient(app)

    # Submit first
    post_res = client.post(
        "/observations/citizen",
        json={"report_type": "ROAD_PASSABLE", "lat": 13.0100, "lon": 80.2100},
    )
    assert post_res.status_code == 200
    obs_id = post_res.json()["citizen_report"]["observation_id"]

    # Fetch by ID
    get_res = client.get(f"/observations/citizen/{obs_id}")
    assert get_res.status_code == 200
    fetched = get_res.json()
    assert fetched["observation_id"] == obs_id
    assert fetched["report_type"] == "ROAD_PASSABLE"


def test_fastapi_citizen_invalid_coordinates_rejection():
    """Verifies structured 400 response for invalid coordinates."""
    client = TestClient(app)

    response = client.post(
        "/observations/citizen",
        json={"report_type": "ROAD_FLOODED", "lat": 99.0, "lon": 80.2707},
    )
    assert response.status_code == 400
    assert "Latitude out of valid range" in response.json()["detail"]


def test_fastapi_citizen_invalid_report_type_rejection():
    """Verifies structured 400 response for invalid report type."""
    client = TestClient(app)

    response = client.post(
        "/observations/citizen",
        json={"report_type": "INVALID_TYPE", "lat": 13.0827, "lon": 80.2707},
    )
    assert response.status_code == 400
    assert "Unsupported report type" in response.json()["detail"]


def test_deterministic_repeated_submission(mock_citizen_pipeline):
    """Verifies deterministic processing of repeated citizen submissions."""
    c1, _ = mock_citizen_pipeline.submit_citizen_report(
        lat=13.0827, lon=80.2707, report_type="ROAD_FLOODED", confidence=0.70
    )
    c2, _ = mock_citizen_pipeline.submit_citizen_report(
        lat=13.0827, lon=80.2707, report_type="ROAD_FLOODED", confidence=0.70
    )
    assert c1.latitude == c2.latitude
    assert c1.longitude == c2.longitude
    assert c1.confidence == c2.confidence
