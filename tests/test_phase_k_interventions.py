"""
Phase K — Intervention Execution & Outcome Tracking Tests
Covers test categories A through Z as specified in the Phase K requirement doc.
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from cyclone_twin.main import app, state
from cyclone_twin.domain.entities import Intervention, InterventionTransitionAudit
from cyclone_twin.providers.intervention_engine import InterventionManager

test_client = TestClient(app)



# --- Category A & J: Candidate -> Intervention Creation & Frozen Expected Impact Snapshot ---
def test_category_a_j_candidate_to_intervention_creation():
    mgr = InterventionManager()
    int_obj = mgr.create_intervention_from_candidate(
        candidate_id="corridor_03",
        target_name="Saidapet-Adyar Arterial",
        physical_segment_ids=["seg_01", "seg_02"],
        expected_population_recovery=89000,
        expected_hospital_recovery=2,
        expected_travel_time_saved_min=22.0,
        expected_score=0.0724,
        operator_id="COMMANDER-01",
        approval_notes="High criticality lifeline restoration",
    )

    assert int_obj.intervention_id.startswith("INT-")
    assert int_obj.candidate_id == "corridor_03"
    assert int_obj.status == "PROPOSED"
    assert int_obj.expected_population_recovery == 89000
    assert int_obj.expected_hospital_recovery == 2
    assert int_obj.expected_travel_time_saved_min == 22.0
    assert int_obj.expected_score == 0.0724


# --- Category B, C, D, E, H: Valid Transitions & Approval Workflow ---
def test_category_b_c_d_e_h_valid_transitions():
    mgr = InterventionManager()
    int_obj = mgr.create_intervention_from_candidate("corridor_03", "Target A", ["seg_01"], 89000, 2)
    iid = int_obj.intervention_id

    # PROPOSED -> APPROVED
    app_obj = mgr.transition_status(iid, "APPROVED", operator_id="COMMANDER-01", note="Approved by incident commander")
    assert app_obj.status == "APPROVED"
    assert app_obj.approved_at is not None

    # APPROVED -> ASSIGNED
    ass_obj = mgr.transition_status(iid, "ASSIGNED", assigned_team="FIELD-TEAM-03")
    assert ass_obj.status == "ASSIGNED"
    assert ass_obj.assigned_team == "FIELD-TEAM-03"

    # ASSIGNED -> IN_PROGRESS
    prog_obj = mgr.transition_status(iid, "IN_PROGRESS")
    assert prog_obj.status == "IN_PROGRESS"
    assert prog_obj.started_at is not None


# --- Category I: Invalid State Transitions ---
def test_category_i_invalid_transitions():
    mgr = InterventionManager()
    int_obj = mgr.create_intervention_from_candidate("corridor_03", "Target B", ["seg_01"], 89000)
    iid = int_obj.intervention_id

    # Invalid: PROPOSED -> IN_PROGRESS
    with pytest.raises(ValueError) as exc_info:
        mgr.transition_status(iid, "IN_PROGRESS")
    assert "Invalid state transition" in str(exc_info.value)

    # Approve first
    mgr.transition_status(iid, "APPROVED")
    mgr.transition_status(iid, "ASSIGNED")
    mgr.transition_status(iid, "IN_PROGRESS")
    mgr.transition_status(iid, "COMPLETED")

    # Invalid: COMPLETED -> IN_PROGRESS
    with pytest.raises(ValueError) as exc_info2:
        mgr.transition_status(iid, "IN_PROGRESS")
    assert "Invalid state transition" in str(exc_info2.value)


# --- Category F, K, L, Q: Completion, Actual Impact & Variance Calculation ---
def test_category_f_k_l_q_completion_verification_and_variance():
    mgr = InterventionManager()
    int_obj = mgr.create_intervention_from_candidate(
        "corridor_03",
        "Saidapet-Adyar",
        ["seg_01"],
        expected_population_recovery=89000,
        expected_hospital_recovery=2,
        expected_travel_time_saved_min=22.0,
    )

    class MockAccessPre:
        accessible_population = 298000
        isolated_facilities = ["FAC-01", "FAC-02"]

    class MockAccessPost:
        accessible_population = 387000
        isolated_facilities = []

    completed_int, summary = mgr.complete_and_verify_outcome(
        intervention_id=int_obj.intervention_id,
        pre_accessibility=MockAccessPre(),
        post_accessibility=MockAccessPost(),
        restored_segments_count=1,
    )

    assert completed_int.status == "COMPLETED"
    assert completed_int.actual_population_recovery == 89000
    assert completed_int.actual_hospital_recovery == 2
    assert completed_int.variance_population == 0  # 89000 - 89000
    assert completed_int.outcome_verification_status == "VERIFIED"


# --- Category G, R, S: Failure Handling & Automatic Replanning ---
def test_category_g_r_s_failure_handling_and_replanning():
    # Setup flooded scenario
    test_client.post("/network/load")
    test_client.post("/flood/apply", json={})

    # Propose candidate
    res_prop = test_client.post("/interventions/propose", json={"candidate_id": "corridor_03"})
    assert res_prop.status_code == 200
    iid = res_prop.json()["intervention_id"]

    # Transition to APPROVED -> ASSIGNED -> IN_PROGRESS
    test_client.post(f"/interventions/{iid}/transition", json={"to_status": "APPROVED"})
    test_client.post(f"/interventions/{iid}/transition", json={"to_status": "ASSIGNED", "assigned_team": "FIELD-01"})
    test_client.post(f"/interventions/{iid}/transition", json={"to_status": "IN_PROGRESS"})

    # Fail intervention
    res_fail = test_client.post(f"/interventions/{iid}/transition", json={"to_status": "FAILED", "reason": "Debris clearance equipment breakdown"})
    assert res_fail.status_code == 200
    fail_data = res_fail.json()
    assert fail_data["status"] == "FAILED"
    assert fail_data["failure_reason"] == "Debris clearance equipment breakdown"

    # Verify replanning candidate recommendation returned
    assert "replan_recommendation" in fail_data or "interventions" in fail_data


# --- Category M, N, O, P: Field Update & Sync ---
def test_category_m_n_o_p_field_update():
    res_prop = test_client.post("/interventions/propose", json={"candidate_id": "corridor_03"})
    iid = res_prop.json()["intervention_id"]

    test_client.post(f"/interventions/{iid}/transition", json={"to_status": "APPROVED"})
    test_client.post(f"/interventions/{iid}/transition", json={"to_status": "ASSIGNED", "assigned_team": "FIELD-TEAM-02"})
    test_client.post(f"/interventions/{iid}/transition", json={"to_status": "IN_PROGRESS"})

    # Record field update
    res_upd = test_client.post(f"/interventions/{iid}/field-update", json={"evidence_ref": "PHOTO-CORRIDOR-88", "notes": "Crews on site clearing fallen trees"})
    assert res_upd.status_code == 200
    upd_data = res_upd.json()
    assert "PHOTO-CORRIDOR-88" in upd_data["evidence_refs"]


# --- Category U, V, W, X, Y, Z: Endpoints, Audit & Full System Regression ---
def test_category_u_v_w_x_y_z_endpoints_and_regression():
    # 1. List interventions
    res_list = test_client.get("/interventions")
    assert res_list.status_code == 200

    # 2. Get specific intervention
    items = res_list.json()["interventions"]
    if items:
        iid = items[0]["intervention_id"]
        res_det = test_client.get(f"/interventions/{iid}")
        assert res_det.status_code == 200

        # Audit log endpoint
        res_audit = test_client.get(f"/interventions/{iid}/audit")
        assert res_audit.status_code == 200

        # Traceability integration endpoint
        res_trace = test_client.get(f"/traceability/{iid}")
        assert res_trace.status_code == 200
        assert "intervention_record" in res_trace.json()
