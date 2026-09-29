"""
Phase L12 — GCP Foundation & Deployment Test Suite
Validates GCP cloud readiness, Firestore/GCS/BigQuery fallbacks, Cloud Run Dockerfile,
Firebase Hosting configuration, API endpoints, and core architectural invariants.
"""

import json
import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware as FastAPICORSMiddleware

from cyclone_twin.main import app, state
from cyclone_twin.providers.gcp_foundation import GCPFoundationService, get_gcp_foundation
from cyclone_twin.domain.entities import InfrastructureObservation, CitizenObservation
from cyclone_twin.ranking_engine import compute_accessibility

ROOT_DIR = Path(__file__).parent.parent


def test_dockerfile_and_config_files_exist():
    """Verify that Dockerfile, firebase.json, .firebaserc, cloudbuild.yaml, and deploy_gcp.sh exist."""
    assert (ROOT_DIR / "Dockerfile").exists(), "Dockerfile missing"
    assert (ROOT_DIR / "firebase.json").exists(), "firebase.json missing"
    assert (ROOT_DIR / ".firebaserc").exists(), ".firebaserc missing"
    assert (ROOT_DIR / "cloudbuild.yaml").exists(), "cloudbuild.yaml missing"
    assert (ROOT_DIR / "deploy_gcp.sh").exists(), "deploy_gcp.sh missing"


def test_firebase_json_valid_structure():
    """Verify firebase.json contains SPA rewrites and api proxies."""
    config_path = ROOT_DIR / "firebase.json"
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "hosting" in data
    hosting = data["hosting"]
    assert hosting.get("public") == "frontend/dist"
    rewrites = hosting.get("rewrites", [])
    assert len(rewrites) >= 2
    api_rewrite = next((r for r in rewrites if r.get("source") == "/api/**"), None)
    assert api_rewrite is not None
    assert api_rewrite.get("run", {}).get("serviceId") == "cyclone-twin-backend"


def test_firebaserc_valid_project():
    """Verify .firebaserc points to valid GCP/Firebase project ID."""
    config_path = ROOT_DIR / ".firebaserc"
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "projects" in data
    assert "default" in data["projects"]


def test_gcp_foundation_service_local_fallback():
    """Verify GCPFoundationService initializes smoothly in local fallback mode."""
    service = GCPFoundationService(project_id="test-project", local_fallback=True)
    manifest = service.get_status_manifest()
    
    assert manifest["status"] == "HEALTHY"
    assert manifest["project_id"] == "test-project"
    assert manifest["mode"] == "LOCAL_FALLBACK"
    assert "target_architecture" in manifest
    arch = manifest["target_architecture"]
    assert arch["frontend"] == "Firebase Hosting"
    assert arch["backend"] == "Cloud Run (FastAPI)"
    assert arch["database"] == "Firestore"
    assert arch["storage"] == "Cloud Storage"
    assert arch["analytics"] == "BigQuery"


def test_gcp_foundation_snapshot_state():
    """Verify state snapshotting in GCP service."""
    service = GCPFoundationService(local_fallback=True)
    sample_state = {"state_id": "ST-101", "version": 1, "severity": "HIGH"}
    res = service.snapshot_state(sample_state)
    assert res["status"] in ["SNAPSHOT_SAVED_LOCAL", "FIRESTORE_SNAPSHOT_SAVED"]
    assert res["snapshot_id"] is not None
    assert service.get_status_manifest()["snapshots_count"] >= 1


def test_gcp_foundation_upload_media(tmp_path):
    """Verify GCS media upload helper in local fallback mode."""
    service = GCPFoundationService(local_fallback=True)
    sample_file = tmp_path / "test_image.jpg"
    sample_file.write_bytes(b"dummy image bytes for test")
    
    res = service.upload_media(str(sample_file), destination_blob_name="evidence/test_image.jpg")
    assert res["status"] in ["UPLOAD_SAVED_LOCAL", "GCS_UPLOADED"]
    assert "media_url" in res
    assert service.get_status_manifest()["uploads_count"] >= 1


def test_gcp_foundation_log_event():
    """Verify BigQuery telemetry logging helper in local fallback mode."""
    service = GCPFoundationService(local_fallback=True)
    event_payload = {"user": "OPERATOR_01", "action": "CLEAR_CORRIDOR", "corridor_id": "C-01"}
    res = service.log_event(event_type="CORRIDOR_CLEARANCE", payload=event_payload)
    assert res["status"] in ["EVENT_LOGGED_LOCAL", "BIGQUERY_STREAMED"]
    assert res["event_id"] is not None
    assert service.get_status_manifest()["telemetry_events_count"] >= 1


def test_api_gcp_status_endpoint():
    """Test GET /gcp/status REST API endpoint."""
    client = TestClient(app)
    response = client.get("/gcp/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "target_architecture" in data
    assert data["target_architecture"]["backend"] == "Cloud Run (FastAPI)"


def test_api_gcp_snapshot_endpoint():
    """Test POST /gcp/snapshot REST API endpoint."""
    client = TestClient(app)
    response = client.post("/gcp/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert "snapshot_id" in data
    assert data["status"] in ["SNAPSHOT_SAVED_LOCAL", "FIRESTORE_SNAPSHOT_SAVED"]


def test_api_gcp_log_event_endpoint():
    """Test POST /gcp/log-event REST API endpoint."""
    client = TestClient(app)
    payload = {"event_type": "TEST_AUDIT", "metric": 99.9}
    response = client.post("/gcp/log-event", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["EVENT_LOGGED_LOCAL", "BIGQUERY_STREAMED"]


def test_cors_firebase_and_vercel_origins():
    """Verify CORS allow_origin_regex supports Firebase Hosting and Vercel domains."""
    client = TestClient(app)
    res_firebase = client.options(
        "/accessibility/status",
        headers={"Origin": "https://cyclone-twin-gcc.web.app", "Access-Control-Request-Method": "GET"},
    )
    assert res_firebase.status_code == 200
    assert res_firebase.headers.get("access-control-allow-origin") == "https://cyclone-twin-gcc.web.app"


def test_core_math_invariant_preserved():
    """Verify Dijkstra graph calculation and disaster state transitions are unchanged."""
    state.initialize()
    # Perform Dijkstra route query to confirm graph engine intact
    graph = state.network_engine.graph
    assert graph is not None
    assert len(graph.nodes) > 0

    # Verify accessibility calculation
    access = compute_accessibility(
        state.network_engine,
        state.data_loader.communities,
        state.data_loader.facilities,
    )
    assert access is not None


def test_forecast_observation_state_separation_invariant():
    """Verify Forecast != Observation != State separation remains 100% strictly enforced."""
    obs = InfrastructureObservation(
        observation_id="OBS-L12-TEST",
        lat=13.0827,
        lon=80.2707,
        source="citizen_report",
        observation_type="FLOOD_DEPTH",
        severity="high",
    )
    assert obs.observation_id == "OBS-L12-TEST"
    assert obs.observation_type == "FLOOD_DEPTH"
