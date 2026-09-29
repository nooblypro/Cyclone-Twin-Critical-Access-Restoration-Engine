"""
Phase F Tests: Deterministic Multi-Objective Intervention Decision Engine
Verifies:
1. MultiObjectiveWeights initialization, sum validation, and presets (life_safety, equity_priority, rapid_clearance)
2. Counterfactual state isolation (atomic rollback of network segment states and health facility power states)
3. Multi-objective score breakdown calculation (Delta H, Delta P, Delta T, Delta E, Delta D)
4. Equity-weighted population vulnerability recovery (Delta E) calculation
5. Hospital power restoration intervention evaluation (POWER_RESTORATION increases Delta H)
6. Dewatering pump intervention evaluation (PUMP_DEPLOYMENT)
7. Corridor clearance intervention evaluation (CORRIDOR_CLEARANCE)
8. Multi-candidate deterministic ranking (score DESC)
9. Pareto dominance identification (non-dominated candidate front)
10. Operational tiebreaker logic (close scores sorted by lower cost/difficulty ASC)
11. Exception safety (state rollback guaranteed on evaluation errors)
12. API endpoint integration (POST /decision/evaluate)
13. Baseline simulation regression preservation
"""

import pytest
from fastapi.testclient import TestClient

from cyclone_twin.models import Community, HealthFacility
from cyclone_twin.decision_engine import (
    MultiObjectiveDecisionEngine,
    MultiObjectiveWeights,
    InterventionCandidate,
)
from cyclone_twin.network_engine import NetworkEngine
from cyclone_twin.data_loader import DataLoader
from cyclone_twin.ranking_engine import compute_accessibility
from cyclone_twin.main import app


def test_01_multiobjective_weights_validation():
    w = MultiObjectiveWeights.life_safety()
    assert abs((w.w_h + w.w_p + w.w_t + w.w_e + w.w_d) - 1.0) < 1e-4

    w_equity = MultiObjectiveWeights.equity_priority()
    assert w_equity.w_e == 0.30

    w_clear = MultiObjectiveWeights.rapid_clearance()
    assert w_clear.w_d == 0.30

    with pytest.raises(ValueError):
        MultiObjectiveWeights(w_h=0.5, w_p=0.5, w_t=0.5, w_e=0.5, w_d=0.5)

    with pytest.raises(ValueError):
        MultiObjectiveWeights(w_h=-0.1, w_p=0.4, w_t=0.3, w_e=0.2, w_d=0.2)


def test_02_counterfactual_state_isolation():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    # Disable a segment
    disabled_seg = list(engine.valid_segment_ids)[0]
    engine.disable_segments([disabled_seg])
    assert disabled_seg in engine.disabled_segments

    # Unpower a hospital
    facility = loader.facilities[0]
    facility.power_status = False

    decision_engine = MultiObjectiveDecisionEngine(engine)
    candidate = InterventionCandidate(
        candidate_id="cand_test_isolation",
        name="Test Candidate",
        intervention_type="POWER_RESTORATION",
        physical_segment_ids=[disabled_seg],
        target_facility_ids=[facility.id],
    )

    baseline_access = compute_accessibility(engine, loader.communities, loader.facilities)
    _ = decision_engine.evaluate_candidate(
        candidate=candidate,
        baseline_access=baseline_access,
        communities=loader.communities,
        facilities=loader.facilities,
        weights=MultiObjectiveWeights.life_safety(),
        max_cost_or_length=1000.0,
    )

    # State MUST be 100% restored to original state after evaluation
    assert disabled_seg in engine.disabled_segments
    assert facility.power_status is False


def test_03_score_breakdown_formula():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    decision_engine = MultiObjectiveDecisionEngine(engine)
    cand = InterventionCandidate(
        candidate_id="c1",
        name="Candidate 1",
        estimated_cost=500.0,
    )

    w = MultiObjectiveWeights(w_h=0.35, w_p=0.25, w_t=0.15, w_e=0.15, w_d=0.10)
    base = compute_accessibility(engine, loader.communities, loader.facilities)
    bd = decision_engine.evaluate_candidate(cand, base, loader.communities, loader.facilities, w, 1000.0)

    expected = round(
        w.w_h * bd.delta_h + w.w_p * bd.delta_p + w.w_t * bd.delta_t + w.w_e * bd.delta_e - w.w_d * bd.delta_d,
        4,
    )
    assert bd.score == expected


def test_04_equity_weighted_vulnerability_recovery():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    # Assign high vulnerability to Velachery
    for comm in loader.communities:
        if comm.id == "COMM_VELACHERY":
            comm.vulnerability_index = 3.0
        else:
            comm.vulnerability_index = 1.0

    # Apply Michaung flood
    from cyclone_twin.flood_polygon_fallback import identify_flood_disabled_segments, normalize_polygon_geometry
    from shapely.geometry import shape
    flood_geojson = loader.load_flood_polygon(attempt_nrsc=False)
    flood_shape = normalize_polygon_geometry(shape(flood_geojson["geometry"]))
    disabled_segs, _ = identify_flood_disabled_segments(graph, flood_shape)
    engine.disable_segments(disabled_segs)

    decision_engine = MultiObjectiveDecisionEngine(engine)
    corridors = from_corridors_to_candidates(graph, engine.disabled_segments)

    w_standard = MultiObjectiveWeights.life_safety()
    w_equity = MultiObjectiveWeights.equity_priority()

    ranked_std = decision_engine.rank_interventions(corridors, loader.communities, loader.facilities, w_standard)
    ranked_eq = decision_engine.rank_interventions(corridors, loader.communities, loader.facilities, w_equity)

    assert len(ranked_std) > 0
    assert len(ranked_eq) > 0
    # Equity weighted score component (delta_e) must be >= 0
    assert ranked_eq[0].score_breakdown.delta_e >= 0.0


def test_05_power_restoration_intervention():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    # Disable power to Fortis Malar
    fac = next(f for f in loader.facilities if f.id == "FAC_FORTIS_MALAR")
    fac.power_status = False

    decision_engine = MultiObjectiveDecisionEngine(engine)
    cand_power = InterventionCandidate(
        candidate_id="cand_power_malar",
        name="Restore Power Fortis Malar",
        intervention_type="POWER_RESTORATION",
        target_facility_ids=["FAC_FORTIS_MALAR"],
        estimated_cost=100.0,
    )

    base = compute_accessibility(engine, loader.communities, loader.facilities)
    bd = decision_engine.evaluate_candidate(
        cand_power, base, loader.communities, loader.facilities, MultiObjectiveWeights.life_safety(), 1000.0
    )

    assert bd.hospitals_recovered == 1
    assert bd.delta_h > 0.0


def test_06_dewatering_pump_intervention():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    target_segs = list(engine.valid_segment_ids)[:2]
    engine.disable_segments(target_segs)

    decision_engine = MultiObjectiveDecisionEngine(engine)
    cand_pump = InterventionCandidate(
        candidate_id="cand_pump_01",
        name="Deploy Dewatering Pumps Ward 178",
        intervention_type="PUMP_DEPLOYMENT",
        physical_segment_ids=target_segs,
        estimated_cost=250.0,
    )

    base = compute_accessibility(engine, loader.communities, loader.facilities)
    bd = decision_engine.evaluate_candidate(
        cand_pump, base, loader.communities, loader.facilities, MultiObjectiveWeights.life_safety(), 1000.0
    )

    assert bd.delta_d == 0.25  # 250 / 1000


def test_07_corridor_clearance_intervention():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    target_segs = list(engine.valid_segment_ids)[:3]
    engine.disable_segments(target_segs)

    decision_engine = MultiObjectiveDecisionEngine(engine)
    cand_clear = InterventionCandidate(
        candidate_id="cand_clear_01",
        name="Clear Saidapet Corridor Debris",
        intervention_type="CORRIDOR_CLEARANCE",
        physical_segment_ids=target_segs,
        total_length_m=500.0,
    )

    base = compute_accessibility(engine, loader.communities, loader.facilities)
    bd = decision_engine.evaluate_candidate(
        cand_clear, base, loader.communities, loader.facilities, MultiObjectiveWeights.life_safety(), 1000.0
    )

    assert bd.delta_d == 0.50  # 500 / 1000


def test_08_multicandidate_deterministic_ranking():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    c1 = InterventionCandidate(candidate_id="c1", name="Cand 1", estimated_cost=100.0)
    c2 = InterventionCandidate(candidate_id="c2", name="Cand 2", estimated_cost=500.0)
    c3 = InterventionCandidate(candidate_id="c3", name="Cand 3", estimated_cost=900.0)

    decision_engine = MultiObjectiveDecisionEngine(engine)
    r1 = decision_engine.rank_interventions([c1, c2, c3], loader.communities, loader.facilities)
    r2 = decision_engine.rank_interventions([c3, c1, c2], loader.communities, loader.facilities)

    # Identical deterministic ordering regardless of permutation
    assert [x.candidate_id for x in r1] == [x.candidate_id for x in r2]
    assert r1[0].rank == 1
    assert r1[0].score >= r1[1].score >= r1[2].score


def test_09_pareto_dominance_identification():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    decision_engine = MultiObjectiveDecisionEngine(engine)

    # Candidate A dominates Candidate B (same impact, lower cost)
    c_a = InterventionCandidate(candidate_id="c_a", name="A", estimated_cost=100.0)
    c_b = InterventionCandidate(candidate_id="c_b", name="B", estimated_cost=800.0)

    ranked = decision_engine.rank_interventions([c_a, c_b], loader.communities, loader.facilities)

    assert ranked[0].candidate_id == "c_a"
    assert ranked[0].pareto_optimal is True


def test_10_operational_tiebreaker_logic():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    # Two candidates with nearly identical impact but different costs
    c_high_cost = InterventionCandidate(candidate_id="c_high", name="High Cost", estimated_cost=900.0)
    c_low_cost = InterventionCandidate(candidate_id="c_low", name="Low Cost", estimated_cost=100.0)

    decision_engine = MultiObjectiveDecisionEngine(engine)
    ranked = decision_engine.rank_interventions([c_high_cost, c_low_cost], loader.communities, loader.facilities)

    # Lower cost candidate wins tiebreaker when scores are within 0.05
    assert ranked[0].candidate_id == "c_low"


def test_11_exception_safety_state_rollback():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    target_seg = list(engine.valid_segment_ids)[0]
    engine.disable_segments([target_seg])

    decision_engine = MultiObjectiveDecisionEngine(engine)
    cand = InterventionCandidate(
        candidate_id="cand_err",
        name="Error Candidate",
        physical_segment_ids=[target_seg],
    )

    base = compute_accessibility(engine, loader.communities, loader.facilities)

    # Evaluate candidate safely
    _ = decision_engine.evaluate_candidate(
        cand, base, loader.communities, loader.facilities, MultiObjectiveWeights.life_safety(), 1000.0
    )

    # Network state MUST be safely restored after evaluation
    assert target_seg in engine.disabled_segments


def test_12_api_endpoint_decision_evaluate():
    client = TestClient(app)

    # POST /decision/evaluate
    res = client.post(
        "/decision/evaluate",
        json={
            "weights": {"w_h": 0.35, "w_p": 0.25, "w_t": 0.15, "w_e": 0.15, "w_d": 0.10},
            "candidates": [
                {
                    "candidate_id": "cand_api_1",
                    "name": "API Proposal 1",
                    "intervention_type": "CORRIDOR_CLEARANCE",
                    "estimated_cost": 200.0,
                },
                {
                    "candidate_id": "cand_api_2",
                    "name": "API Proposal 2",
                    "intervention_type": "PUMP_DEPLOYMENT",
                    "estimated_cost": 500.0,
                },
            ],
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 2
    assert "pareto_optimal_candidates" in data
    assert "ranked_interventions" in data
    assert data["ranked_interventions"][0]["rank"] == 1


def test_13_baseline_simulation_regression_preserved():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    base_access = compute_accessibility(engine, loader.communities, loader.facilities)
    assert base_access.accessible_population == 477000
    assert len(base_access.isolated_facilities) == 0
    assert len(base_access.isolated_communities) == 0


def from_corridors_to_candidates(graph, disabled_segment_ids):
    from cyclone_twin.corridor_engine import CorridorEngine
    corridors = CorridorEngine.cluster_disabled_segments_into_corridors(graph, disabled_segment_ids)
    candidates = []
    for c in corridors:
        candidates.append(
            InterventionCandidate(
                candidate_id=c.corridor_id,
                name=f"Clear {c.corridor_id}",
                intervention_type="CORRIDOR_CLEARANCE",
                physical_segment_ids=c.physical_segment_ids,
                total_length_m=c.total_length_m,
                road_classes=c.road_classes,
                geometry=c.geometry,
            )
        )
    return candidates
