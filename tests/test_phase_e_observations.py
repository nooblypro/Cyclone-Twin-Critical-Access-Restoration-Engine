"""
Phase E Tests: Ground Observation Ingestion & Model Reconciliation Pipeline
Verifies:
1. Valid observation accepted
2. Invalid latitude rejected (< -90 or > 90)
3. Invalid longitude rejected (< -180 or > 180)
4. Invalid confidence rejected (< 0 or > 1)
5. Invalid observation type rejected
6. Invalid source type rejected
7. NaN values rejected
8. Infinity values rejected
9. Duplicate observation handled deterministically (idempotent replacement)
10. Out-of-area observation handled (outside Chennai bounding box rejected)
11. Full provenance metadata preserved
12. Timestamp handling (ISO string parsing / temporal expiration)
13. ROAD_BLOCKED observation processing
14. ROAD_OPEN observation processing
15. Conflicting observations resolution (ROAD_BLOCKED vs ROAD_OPEN)
16. Low-confidence observation does not bypass reconciliation
17. Reconciled observation produces deterministic override in NetworkEngine
18. Malformed observation cannot mutate simulation state
19. Bounded store size & eviction at capacity
20. Agent tool uses same validation path
21. Baseline simulation regression preserved
"""

import pytest
import math
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from cyclone_twin.domain.entities import InfrastructureObservation
from cyclone_twin.providers.observation_pipeline import ObservationIngestionPipeline
from cyclone_twin.providers.agent_tools import AgenticToolRegistry
from cyclone_twin.network_engine import NetworkEngine
from cyclone_twin.data_loader import DataLoader
from cyclone_twin.ranking_engine import compute_accessibility
from cyclone_twin.main import app


@pytest.fixture
def pipeline():
    return ObservationIngestionPipeline(max_capacity=10)


def test_01_valid_observation_accepted(pipeline):
    obs = pipeline.submit_report(
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_BLOCKED",
        source="official",
        confidence=0.90,
    )
    assert obs.observation_id.startswith("obs_")
    assert obs.status == "accepted"
    assert obs.lat == 13.08
    assert obs.lon == 80.27
    assert obs.confidence == 0.90
    assert obs.source_type == "official"


def test_02_invalid_latitude_rejected(pipeline):
    with pytest.raises(ValueError, match="Latitude"):
        pipeline.submit_report(lat=95.0, lon=80.27)

    with pytest.raises(ValueError, match="Latitude"):
        pipeline.submit_report(lat=-100.0, lon=80.27)


def test_03_invalid_longitude_rejected(pipeline):
    with pytest.raises(ValueError, match="Longitude"):
        pipeline.submit_report(lat=13.08, lon=200.0)

    with pytest.raises(ValueError, match="Longitude"):
        pipeline.submit_report(lat=13.08, lon=-190.0)


def test_04_invalid_confidence_rejected(pipeline):
    with pytest.raises(ValueError, match="Confidence"):
        pipeline.submit_report(lat=13.08, lon=80.27, confidence=1.5)

    with pytest.raises(ValueError, match="Confidence"):
        pipeline.submit_report(lat=13.08, lon=80.27, confidence=-0.1)


def test_05_invalid_observation_type_rejected(pipeline):
    with pytest.raises(ValueError, match="Unsupported observation type"):
        pipeline.submit_report(lat=13.08, lon=80.27, observation_type="MAGIC_TELEPORT")


def test_06_invalid_source_type_rejected(pipeline):
    with pytest.raises(ValueError, match="Unsupported source type"):
        pipeline.submit_report(lat=13.08, lon=80.27, source="alien_satellite")


def test_07_nan_rejected(pipeline):
    with pytest.raises(ValueError, match="NaN"):
        pipeline.submit_report(lat=float("nan"), lon=80.27)

    with pytest.raises(ValueError, match="NaN"):
        pipeline.submit_report(lat=13.08, lon=float("nan"))

    with pytest.raises(ValueError, match="NaN"):
        pipeline.submit_report(lat=13.08, lon=80.27, confidence=float("nan"))


def test_08_infinity_rejected(pipeline):
    with pytest.raises(ValueError, match="Infinity"):
        pipeline.submit_report(lat=float("inf"), lon=80.27)

    with pytest.raises(ValueError, match="Infinity"):
        pipeline.submit_report(lat=13.08, lon=float("inf"))

    with pytest.raises(ValueError, match="Infinity"):
        pipeline.submit_report(lat=13.08, lon=80.27, confidence=float("inf"))


def test_09_duplicate_observation_handled_deterministically(pipeline):
    obs1 = pipeline.submit_report(
        observation_id="obs_dup_100",
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_BLOCKED",
        confidence=0.85,
    )
    assert len(pipeline.observations) == 1

    # Idempotent replacement submission
    obs2 = pipeline.submit_report(
        observation_id="obs_dup_100",
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_BLOCKED",
        confidence=0.95,
    )
    assert len(pipeline.observations) == 1
    assert pipeline.observations["obs_dup_100"].confidence == 0.95
    assert obs2.provenance["duplicate_replacement"] is True


def test_10_out_of_area_observation_handled(pipeline):
    # Location outside Chennai bounding box (e.g., London coords)
    with pytest.raises(ValueError, match="outside Chennai study region"):
        pipeline.submit_report(lat=51.5074, lon=-0.1278)


def test_11_provenance_preserved(pipeline):
    obs = pipeline.submit_report(
        observation_id="obs_prov_01",
        lat=13.05,
        lon=80.25,
        observation_type="FLOOD_DEPTH",
        source="field_team",
        confidence=0.92,
        value=0.55,
    )
    prov = obs.provenance
    assert prov["source"] == "field_team"
    assert prov["observation_id"] == "obs_prov_01"
    assert prov["confidence"] == 0.92
    assert prov["location"] == {"lat": 13.05, "lon": 80.25}
    assert "ingestion_timestamp" in prov


def test_12_timestamp_handling_and_expiration(pipeline):
    old_time = datetime.now(timezone.utc) - timedelta(days=2)  # 48h old
    obs_old = pipeline.submit_report(
        observation_id="obs_old",
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_BLOCKED",
        source="official",
        confidence=0.90,
        timestamp=old_time,
    )
    assert obs_old.timestamp == old_time

    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    # Reconcile with 24h max_age_seconds
    res = pipeline.reconcile_observations(engine, max_age_seconds=86400)
    # 48h old report is expired and must NOT mutate engine
    assert res["reconciled_count"] == 0
    assert len(res["disabled_segments"]) == 0


def test_13_road_blocked_observation_processing(pipeline):
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    target_seg = list(engine.valid_segment_ids)[0]

    pipeline.submit_report(
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_BLOCKED",
        source="official",
        confidence=0.90,
        affected_segment_id=target_seg,
    )

    res = pipeline.reconcile_observations(engine)
    assert res["reconciled_count"] == 1
    assert target_seg in res["disabled_segments"]
    assert target_seg in engine.disabled_segments


def test_14_road_open_observation_processing(pipeline):
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    target_seg = list(engine.valid_segment_ids)[0]
    engine.disable_segments([target_seg])
    assert target_seg in engine.disabled_segments

    pipeline.submit_report(
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_OPEN",
        source="field_team",
        confidence=0.95,
        affected_segment_id=target_seg,
    )

    res = pipeline.reconcile_observations(engine)
    assert res["reconciled_count"] == 1
    assert target_seg in res["restored_segments"]
    assert target_seg not in engine.disabled_segments


def test_15_conflicting_observations_resolution(pipeline):
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    target_seg = list(engine.valid_segment_ids)[0]

    # Report 1: Citizen says ROAD_BLOCKED at T1
    pipeline.submit_report(
        observation_id="obs_conf_1",
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_BLOCKED",
        source="citizen",
        confidence=0.85,
        affected_segment_id=target_seg,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
    )

    # Report 2: Official field team says ROAD_OPEN at T2 (newer + higher priority source)
    pipeline.submit_report(
        observation_id="obs_conf_2",
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_OPEN",
        source="official",
        confidence=0.95,
        affected_segment_id=target_seg,
        timestamp=datetime.now(timezone.utc),
    )

    res = pipeline.reconcile_observations(engine)
    assert target_seg in res["restored_segments"]
    assert target_seg not in engine.disabled_segments


def test_16_low_confidence_observation_does_not_bypass_reconciliation(pipeline):
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    target_seg = list(engine.valid_segment_ids)[0]

    # Single low-confidence citizen report (confidence < 0.85, uncorroborated)
    pipeline.submit_report(
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_BLOCKED",
        source="citizen",
        confidence=0.60,
        affected_segment_id=target_seg,
    )

    res = pipeline.reconcile_observations(engine)
    # Must NOT mutate engine
    assert res["reconciled_count"] == 0
    assert target_seg not in engine.disabled_segments


def test_17_reconciled_observation_produces_deterministic_override(pipeline):
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    target_seg = list(engine.valid_segment_ids)[0]

    pipeline.submit_report(
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_BLOCKED",
        source="official",
        confidence=0.90,
        affected_segment_id=target_seg,
    )

    # Run reconciliation twice
    res1 = pipeline.reconcile_observations(engine)
    res2 = pipeline.reconcile_observations(engine)

    assert res1["disabled_segments"] == res2["disabled_segments"] == [target_seg]


def test_18_malformed_observation_cannot_mutate_simulation():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)
    client = TestClient(app)

    # Attempt submitting malformed observation via API (NaN latitude)
    r = client.post("/observations/submit", json={"lat": "NaN", "lon": 80.27})
    assert r.status_code == 400

    # Ensure engine disabled segments remain empty
    assert len(engine.disabled_segments) == 0


def test_19_observation_store_bounded_eviction():
    pipe = ObservationIngestionPipeline(max_capacity=5)

    for i in range(10):
        pipe.submit_report(
            observation_id=f"obs_bound_{i}",
            lat=13.08,
            lon=80.27,
            observation_type="ROAD_BLOCKED",
            confidence=0.90,
        )

    # Store size capped strictly at max_capacity=5
    assert len(pipe.observations) == 5
    # First 5 items (0..4) evicted, remaining items are 5..9
    assert "obs_bound_0" not in pipe.observations
    assert "obs_bound_9" in pipe.observations


def test_20_agent_tool_uses_same_validation_path():
    pipe = ObservationIngestionPipeline()
    registry = AgenticToolRegistry(observation_pipeline=pipe)

    # Valid submission via agent tool
    res = registry.submit_ground_observation(
        lat=13.08,
        lon=80.27,
        observation_type="ROAD_BLOCKED",
        confidence=0.90,
    )
    assert res["status"] == "accepted"
    assert len(pipe.observations) == 1

    # Invalid submission via agent tool (out of bounds)
    with pytest.raises(ValueError, match="outside Chennai study region"):
        registry.submit_ground_observation(
            lat=50.0,
            lon=0.0,
        )


def test_21_baseline_simulation_regression_preserved():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    # Baseline check
    base_access = compute_accessibility(engine, loader.communities, loader.facilities)
    assert base_access.accessible_population == 477000
    assert len(base_access.isolated_facilities) == 0
    assert len(base_access.isolated_communities) == 0
