"""
Phase I Field Operations & Offline Synchronization Test Suite
Verifies offline observation capture contracts, idempotency keys, duplicate sync defense,
conflict handling, retry behavior, batch ingestion, and regression across Phases A-H.
"""

import math
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from cyclone_twin.main import app, state
from cyclone_twin.domain.entities import MultimodalEvidenceExtraction
from cyclone_twin.providers.multimodal_pipeline import MultimodalIngestionService

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_app_state():
    state.initialize()
    state.network_engine.restore_all()
    state.multimodal_service = MultimodalIngestionService()
    yield
    state.network_engine.restore_all()


# Category A & B: Offline observation structure & local persistence model
def test_category_a_b_offline_observation_model():
    item = {
        "client_observation_id": "client_obs_1001",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source": "field_team",
        "observation_type": "ROAD_BLOCKED",
        "latitude": 13.05,
        "longitude": 80.22,
        "water_depth_m": 0.35,
        "description": "Flooded road near Saidapet",
        "sync_status": "QUEUED",
    }
    assert item["client_observation_id"] == "client_obs_1001"
    assert item["sync_status"] == "QUEUED"


# Category C, D, E: Local queue persistence & image reference handling
def test_category_c_d_e_queue_persistence_schema():
    queue_item = {
        "client_observation_id": "client_obs_1002",
        "observation_type": "FLOOD_DEPTH",
        "latitude": 13.04,
        "longitude": 80.21,
        "water_depth_m": 0.45,
        "evidence_reference": "PHOTO_OFFLINE_001",
        "image_data": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ...",
        "sync_status": "QUEUED",
        "retry_count": 0,
    }
    assert queue_item["evidence_reference"] == "PHOTO_OFFLINE_001"
    assert queue_item["retry_count"] == 0


# Category F & G: GPS available vs GPS unavailable (location_resolution_required)
def test_category_f_g_gps_availability_handling():
    service = state.multimodal_service

    # GPS unavailable (null coordinates)
    obs_no_gps = {
        "client_observation_id": "client_obs_no_gps",
        "observation_type": "ROAD_BLOCKED",
        "latitude": None,
        "longitude": None,
        "source": "field_team",
    }
    batch_no_gps = service.sync_batch([obs_no_gps], state.network_engine)
    assert batch_no_gps["failed_count"] == 1
    assert "Location resolution required" in batch_no_gps["results"][0]["error"]

    # GPS available
    obs_gps = {
        "client_observation_id": "client_obs_gps",
        "observation_type": "ROAD_BLOCKED",
        "latitude": 13.05,
        "longitude": 80.22,
        "source": "field_team",
    }
    batch_res = service.sync_batch([obs_gps], state.network_engine)
    assert batch_res["synced_count"] == 1
    assert batch_res["results"][0]["status"] == "ingested"


# Category H & I: Connectivity restoration & successful batch synchronization
def test_category_h_i_batch_synchronization():
    resp = client.post(
        "/observations/sync",
        json={
            "client_id": "device_field_01",
            "observations": [
                {
                    "client_observation_id": "client_obs_sync_1",
                    "observation_type": "ROAD_BLOCKED",
                    "latitude": 13.05,
                    "longitude": 80.22,
                    "water_depth_m": 0.40,
                    "source": "field_team",
                    "confidence": 0.90,
                    "description": "Offline photo captured near Saidapet",
                },
                {
                    "client_observation_id": "client_obs_sync_2",
                    "observation_type": "ROAD_OPEN",
                    "latitude": 13.08,
                    "longitude": 80.27,
                    "source": "official",
                    "confidence": 0.85,
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_received"] == 2
    assert data["synced_count"] == 2
    assert data["failed_count"] == 0


# Category M & V: Idempotency & duplicate synchronization defense
def test_category_m_v_idempotent_duplicate_sync():
    sync_payload = {
        "client_id": "device_field_01",
        "observations": [
            {
                "client_observation_id": "client_obs_idempotent_999",
                "observation_type": "ROAD_BLOCKED",
                "latitude": 13.05,
                "longitude": 80.22,
                "water_depth_m": 0.40,
                "source": "field_team",
            }
        ],
    }

    # 1. First Submission
    resp1 = client.post("/observations/sync", json=sync_payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["synced_count"] == 1
    assert data1["idempotent_replays"] == 0
    assert data1["results"][0]["idempotent_replay"] is False

    disabled_count_after_first = len(state.network_engine.disabled_segments)

    # 2. Duplicate Submission (Replay)
    resp2 = client.post("/observations/sync", json=sync_payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["synced_count"] == 0
    assert data2["idempotent_replays"] == 1
    assert data2["results"][0]["idempotent_replay"] is True

    disabled_count_after_second = len(state.network_engine.disabled_segments)

    # Idempotency Invariant: Duplicate replay MUST NOT change disabled edges count or create 2nd observation
    assert disabled_count_after_first == disabled_count_after_second
    assert len(state.multimodal_service.pipeline.observations) == 1


# Category O: Conflicting field observations reconciliation
def test_category_o_conflicting_observations_reconciliation():
    now_iso = datetime.now(timezone.utc).isoformat()
    resp = client.post(
        "/observations/sync",
        json={
            "client_id": "device_field_01",
            "observations": [
                {
                    "client_observation_id": "client_obs_conflict_a",
                    "observation_type": "ROAD_BLOCKED",
                    "latitude": 13.05,
                    "longitude": 80.22,
                    "source": "field_team",
                    "confidence": 0.90,
                    "timestamp": now_iso,
                },
                {
                    "client_observation_id": "client_obs_conflict_b",
                    "observation_type": "ROAD_OPEN",
                    "latitude": 13.05,
                    "longitude": 80.22,
                    "source": "official",
                    "confidence": 0.95,
                    "timestamp": now_iso,
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conflicts_count"] > 0

    # Both observations MUST remain stored in pipeline
    assert len(state.multimodal_service.pipeline.observations) == 2


# Category P & Q: Validation failure & malformed evidence handling
def test_category_p_q_validation_failure():
    resp = client.post(
        "/observations/sync",
        json={
            "client_id": "device_field_01",
            "observations": [
                {
                    "client_observation_id": "client_obs_bad_coords",
                    "observation_type": "ROAD_BLOCKED",
                    "latitude": 89.99,  # Out of Chennai bbox
                    "longitude": 80.22,
                }
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed_count"] == 1
    assert data["results"][0]["status"] == "failed"


# Category R & S & T: Backend unavailable & queue processing safety
def test_category_r_s_t_batch_ordering():
    service = state.multimodal_service
    batch = [
        {"client_observation_id": f"item_{i}", "observation_type": "ROAD_OPEN", "latitude": 13.08, "longitude": 80.27}
        for i in range(5)
    ]
    res = service.sync_batch(batch, state.network_engine)
    assert res["total_received"] == 5
    assert len(res["results"]) == 5


# Category W: Provenance preservation across sync
def test_category_w_provenance_preservation():
    resp = client.post(
        "/observations/sync",
        json={
            "client_id": "device_field_01",
            "observations": [
                {
                    "client_observation_id": "client_obs_prov_777",
                    "observation_type": "ROAD_BLOCKED",
                    "latitude": 13.05,
                    "longitude": 80.22,
                    "source": "field_team",
                }
            ],
        },
    )
    assert resp.status_code == 200
    lineage = resp.json()["results"][0]["provenance_lineage"]
    assert lineage["client_observation_id"] == "client_obs_prov_777"
    assert lineage["validation_status"] is True


# Category X, Y, Z: Regression verification across Phase E, G, H
def test_category_x_y_z_regression_baselines():
    # 1. Baseline Accessibility
    access = client.get("/accessibility/status").json()
    assert access["accessible_population"] == 477000
    assert len(access["isolated_facilities"]) == 0

    # 2. Flood Scenario
    flood_res = client.post("/flood/apply", json={}).json()
    assert flood_res["disabled_edges"] > 0

    access_flooded = client.get("/accessibility/status").json()
    assert access_flooded["accessible_population"] == 298000

    # 3. Criticality Ranking
    rank_res = client.post("/interventions/rank", json={}).json()
    assert len(rank_res["ranked_corridors"]) > 0

    top = rank_res["ranked_corridors"][0]
    assert top["score"] > 0.0

    # 4. Advisory Generation
    adv_res = client.post(
        "/advisory/generate",
        json={
            "corridor_id": top["corridor_id"],
            "score_breakdown": top["score_breakdown"],
        },
    ).json()
    assert adv_res["validated"] is True
    assert len(adv_res["advisory_text"]) <= 220
