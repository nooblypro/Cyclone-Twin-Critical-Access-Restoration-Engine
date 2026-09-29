"""
Phase J — Real-Time Disaster Intelligence & Operational Coordination Tests
Covers test categories A through Z as specified in the Phase J requirement doc.
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from cyclone_twin.main import app, state, sync_disaster_state_commit, observation_pipeline
from cyclone_twin.domain.entities import DisasterState, StateDiff, OperationalAlert
from cyclone_twin.providers.disaster_state_engine import DisasterStateManager, ChangeDetector, AlertEngine

client = TestClient(app)


# --- Category A & B: Version Increment & Monotonicity ---
def test_category_a_b_state_version_increments_and_monotonicity():
    mgr = DisasterStateManager("test_scenario")
    v1 = mgr.current_version
    assert v1 == 1
    assert mgr.current_state.state_version == 1

    # Commit transition 1
    s2, diff1 = mgr.commit_transition(
        hazard_state={"water_level_m": 0.5},
        affected_segments=["seg_101"],
        affected_facilities=[{"facility_id": "FAC-01", "name": "Rajiv Gandhi Hospital", "status": "INACCESSIBLE", "travel_time_min": 999.0, "baseline_min": 11.2}],
        affected_population={"total": 477000, "accessible": 298000, "isolated": 179000},
    )

    assert s2.state_version == 2
    assert mgr.current_version == 2
    assert s2.state_version > v1

    # Commit transition 2
    s3, diff2 = mgr.commit_transition(
        hazard_state={"water_level_m": 0.3},
        affected_segments=[],
        affected_facilities=[{"facility_id": "FAC-01", "name": "Rajiv Gandhi Hospital", "status": "ACCESSIBLE", "travel_time_min": 11.2, "baseline_min": 11.2}],
        affected_population={"total": 477000, "accessible": 477000, "isolated": 0},
    )

    assert s3.state_version == 3
    assert mgr.current_version == 3
    assert s3.state_version > s2.state_version


# --- Category C, D, E, F: State Diff & Change Detection ---
def test_category_c_d_e_f_change_detection():
    before = DisasterState(
        scenario_id="scen",
        state_version=10,
        affected_segments=["seg_A"],
        affected_facilities=[
            {"facility_id": "FAC-01", "name": "Hospital A", "status": "ACCESSIBLE", "travel_time_min": 10.0},
        ],
        affected_population={"total": 100000, "accessible": 100000, "isolated": 0},
    )

    after = DisasterState(
        scenario_id="scen",
        state_version=11,
        affected_segments=["seg_A", "seg_B"],
        affected_facilities=[
            {"facility_id": "FAC-01", "name": "Hospital A", "status": "INACCESSIBLE", "travel_time_min": 999.0},
        ],
        affected_population={"total": 100000, "accessible": 75000, "isolated": 25000},
    )

    diff = ChangeDetector.detect_state_changes(before, after)

    assert diff.from_version == 10
    assert diff.to_version == 11
    assert len(diff.road_changes) == 1
    assert diff.road_changes[0]["segment_id"] == "seg_B"
    assert diff.road_changes[0]["change_type"] == "ROAD_BLOCKED"

    assert len(diff.hospital_changes) == 1
    assert diff.hospital_changes[0]["facility_id"] == "FAC-01"
    assert diff.hospital_changes[0]["before_status"] == "ACCESSIBLE"
    assert diff.hospital_changes[0]["after_status"] == "INACCESSIBLE"

    assert diff.population_change["isolated_delta"] == 25000
    assert diff.population_change["newly_isolated"] == 25000


# --- Category G, H, I, J, K: Alert Evaluation, Deduplication & Lifecycle ---
def test_category_g_h_i_j_k_alert_engine_lifecycle():
    engine = AlertEngine()

    diff = StateDiff(
        from_version=1,
        to_version=2,
        hospital_changes=[
            {"facility_id": "FAC-01", "facility_name": "Trauma Hospital", "before_status": "ACCESSIBLE", "after_status": "INACCESSIBLE", "before_travel_time_min": 11.2, "after_travel_time_min": 999.0}
        ],
        population_change={"isolated_delta": 25000, "after_isolated": 25000},
        road_changes=[{"segment_id": "seg_critical", "change_type": "ROAD_BLOCKED"}],
    )

    curr_state = DisasterState(state_version=2)
    alerts = engine.evaluate_state_diff(diff, curr_state)

    # Rule evaluation assertions
    assert len(alerts) == 3
    crit_alert = next((a for a in alerts if a.type == "CRITICAL_HOSPITAL_ACCESS_LOSS"), None)
    high_alert = next((a for a in alerts if a.type == "POPULATION_ISOLATION_INCREASE"), None)
    med_alert = next((a for a in alerts if a.type == "HIGH_CONFIDENCE_ROAD_BLOCKAGE"), None)

    assert crit_alert is not None and crit_alert.severity == "CRITICAL"
    assert high_alert is not None and high_alert.severity == "HIGH"
    assert med_alert is not None and med_alert.severity == "MEDIUM"

    # Category H: Deduplication
    alerts_pass2 = engine.evaluate_state_diff(diff, curr_state)
    assert len(engine.alerts) == 3  # No duplicates spawned in store!

    # Category I: Operator Acknowledgement
    alert_id = crit_alert.alert_id
    ack_res = engine.apply_operator_action(alert_id, "ACKNOWLEDGE", operator_id="Op-42", comment="Investigating backup route")
    assert ack_res.status == "ACKNOWLEDGED"
    assert ack_res.operator_action["operator"] == "Op-42"

    # Category J: Resolution
    res_res = engine.apply_operator_action(alert_id, "RESOLVE", operator_id="Op-42", comment="Corridor cleared")
    assert res_res.status == "RESOLVED"

    # Category K: Dismissal
    dis_res = engine.apply_operator_action(med_alert.alert_id, "DISMISS", operator_id="Op-42")
    assert dis_res.status == "DISMISSED"


# --- Category L: Operational Priority Change Detection ---
def test_category_l_priority_change_detection():
    before = DisasterState(state_version=5)
    after = DisasterState(state_version=6)

    diff = ChangeDetector.detect_state_changes(
        before,
        after,
        previous_top_candidate="CORRIDOR_B",
        current_top_candidate="CORRIDOR_A",
        priority_change_reason="New high confidence flood report blocked Corridor B",
    )

    assert diff.priority_changed is True
    assert diff.previous_top_candidate == "CORRIDOR_B"
    assert diff.current_top_candidate == "CORRIDOR_A"

    engine = AlertEngine()
    alerts = engine.evaluate_state_diff(diff, after)
    p_alert = next((a for a in alerts if a.type == "PRIORITY_CHANGED"), None)
    assert p_alert is not None
    assert p_alert.severity == "HIGH"


# --- Category M, N, O: Observation Stale & Conflict Handling ---
def test_category_m_n_o_observation_semantics():
    from cyclone_twin.domain.entities import InfrastructureObservation
    from datetime import timedelta

    engine = AlertEngine()
    diff = StateDiff(from_version=1, to_version=2)
    state_conf = DisasterState(state_version=2, unresolved_conflicts=2)

    old_dt = datetime.now(timezone.utc) - timedelta(hours=3)
    stale_obs = InfrastructureObservation(
        observation_id="OBS-STALE-99",
        timestamp=old_dt,
        source="citizen",
        observation_type="ROAD_BLOCKED",
        severity="high",
        confidence=0.85,
        lat=13.08,
        lon=80.27,
        status="reconciled",
    )

    alerts = engine.evaluate_state_diff(diff, state_conf, observations=[stale_obs])

    conf_alert = next((a for a in alerts if a.type == "OBSERVATION_CONFLICT"), None)
    stale_alert = next((a for a in alerts if a.type == "STALE_CRITICAL_OBSERVATION"), None)

    assert conf_alert is not None
    assert stale_alert is not None
    assert stale_alert.affected_entity_id == "OBS-STALE-99"


# --- Category P & Q: State Rollback & Atomic Transition ---
def test_category_p_q_atomic_transition_and_rollback():
    mgr = DisasterStateManager("test_atomic")
    v1_version = mgr.current_version

    # Invariant violation: isolated (100) + accessible (100) != total (1000)
    with pytest.raises(ValueError) as exc_info:
        mgr.commit_transition(
            hazard_state={},
            affected_segments=[],
            affected_facilities=[],
            affected_population={"total": 1000, "accessible": 100, "isolated": 100},
        )

    assert "Population invariant violation" in str(exc_info.value)
    # Rollback verification: current version and state MUST remain unchanged at v1
    assert mgr.current_version == v1_version
    assert mgr.current_state.state_version == v1_version


# --- Category R: Provenance Traceability ---
def test_category_r_observation_traceability():
    mgr = DisasterStateManager("test_prov")
    mgr.commit_transition(
        hazard_state={},
        affected_segments=["seg_001"],
        affected_facilities=[{"facility_id": "FAC-01", "name": "Rajiv Gandhi Hospital", "status": "INACCESSIBLE", "travel_time_min": 999.0, "baseline_min": 11.2}],
        affected_population={"total": 477000, "accessible": 298000, "isolated": 179000},
    )

    trace = mgr.get_traceability("seg_001")
    assert trace["entity_id"] == "seg_001"
    assert trace["status"] == "BLOCKED"
    assert len(trace["provenance_chain"]) > 0
    assert trace["current_state_version"] == 2


# --- Category S & T: Endpoints & SSE Streaming ---
def test_category_s_t_api_endpoints():
    res_curr = client.get("/state/current")
    assert res_curr.status_code == 200
    data = res_curr.json()
    assert "state_version" in data
    assert "affected_population" in data

    res_diff = client.get("/state/diff?from_version=1&to_version=1")
    assert res_diff.status_code == 200

    res_alerts = client.get("/alerts")
    assert res_alerts.status_code == 200

    res_trace = client.get("/traceability/FAC-01")
    assert res_trace.status_code == 200
    assert res_trace.json()["entity_id"] == "FAC-01"


# --- Category U, V, W, X, Y, Z: Baseline & Workflow Regressions ---
def test_category_u_z_full_system_regression():
    # 1. Baseline network state
    res_load = client.post("/network/load")
    assert res_load.status_code == 200

    # 2. Flood apply (Michaung default)
    res_flood = client.post("/flood/apply", json={})
    assert res_flood.status_code == 200

    # 3. Accessibility status check
    res_acc = client.get("/accessibility/status")
    assert res_acc.status_code == 200
    acc_data = res_acc.json()
    assert acc_data["accessible_population"] == 298000

    # 4. Intervention ranking check (+89k recovery)
    res_rank = client.post("/interventions/rank", json={})
    assert res_rank.status_code == 200
    rank_data = res_rank.json()
    top_rc = rank_data["ranked_corridors"][0]
    assert top_rc["score_breakdown"]["population_recovered"] == 89000

    # 5. Operational state version check
    res_state = client.get("/state/current")
    assert res_state.status_code == 200
    s_data = res_state.json()
    assert s_data["state_version"] >= 2

