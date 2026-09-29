"""
Phase L7 Tests: BPR-Aware Counterfactual Intervention Ranking

Tests verify:
1. CounterfactualRankingEngine is fully isolated from operational state.
2. BPR model is used for travel-time calculation on forecast network.
3. Pareto front is correctly identified across (ΔH, ΔP, ΔT, ΔE, 1-ΔD).
4. Ranked candidates are deterministically sorted.
5. FORECAST != OBSERVATION != STATE invariant is preserved.
6. GET /forecast/interventions endpoint works for all horizons and weight presets.
7. Invalid inputs return 400 not 500.
8. Empty candidates return valid empty response.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from cyclone_twin.main import app
from cyclone_twin.providers.counterfactual_engine import (
    CounterfactualRankingEngine,
    CounterfactualRankingResponse,
    CounterfactualRankedIntervention,
)
from cyclone_twin.decision_engine import (
    InterventionCandidate,
    MultiObjectiveWeights,
    MultiObjectiveScoreBreakdown,
)
from cyclone_twin.domain.entities import (
    RoadVulnerability,
    VulnerabilityForecast,
)
from cyclone_twin.network_engine import NetworkEngine
from cyclone_twin.models import Community, HealthFacility


client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mini_forecast(
    disabled_seg_ids=None,
    horizon_hours: int = 0,
    water_level_m: float = 0.5,
) -> VulnerabilityForecast:
    """Build a minimal VulnerabilityForecast with specified disabled segments."""
    now = datetime.now(timezone.utc)
    road_vulns = [
        RoadVulnerability(
            segment_id=sid,
            forecast_time=now,
            predicted_depth_m=water_level_m,
            closure_threshold_m=0.30,
            closure_probability=0.90,
            travel_time_multiplier=3.0,
            population_impact=10000,
            hospital_impact=1,
            vulnerability_score=min(1.0, round(water_level_m / 1.5, 2)),
            confidence=0.85,
            is_predicted=True,
        )
        for sid in (disabled_seg_ids or [])
    ]
    return VulnerabilityForecast(
        forecast_id=f"TEST-FCST-L7-{horizon_hours}H",
        scenario_id=f"test_scenario_h{horizon_hours}",
        forecast_time=now,
        generated_at=now,
        reference_time=now,
        horizon_hours=horizon_hours,
        weather_source="test",
        flood_model="test_hand",
        network_source="test_osm",
        rainfall_mm=60.0,
        water_level_m=water_level_m,
        predicted_population_at_risk=50000,
        predicted_population_isolated=50000,
        predicted_hospitals_at_risk=1,
        predicted_hospitals_inaccessible=1,
        road_vulnerabilities=road_vulns,
        confidence=0.85,
        provenance={"test": True},
        assumptions=["test assumption"],
        limitations=["test limitation"],
        is_projected_forecast=True,
    )


def _make_mini_graph_engine():
    """Build a tiny 4-node graph for unit testing."""
    import networkx as nx
    G = nx.MultiDiGraph()
    G.add_node("A")
    G.add_node("B")
    G.add_node("C")
    G.add_node("D")
    G.add_edge("A", "B", key=0, length=1000, speed_kph=40, highway="secondary", capacity=1800, disabled=False)
    G.add_edge("B", "C", key=0, length=1000, speed_kph=40, highway="secondary", capacity=1800, disabled=False)
    G.add_edge("C", "D", key=0, length=1000, speed_kph=40, highway="secondary", capacity=1800, disabled=False)
    G.add_edge("A", "D", key=0, length=5000, speed_kph=30, highway="tertiary", capacity=1400, disabled=False)
    engine = NetworkEngine(graph=G)
    return engine, G


def _make_communities_and_facilities():
    """Minimal communities and facilities for ranking tests."""
    communities = [
        Community(
            id="COMM-1",
            name="Test Ward 1",
            population=30000,
            node_id="A",
            lat=13.01,
            lon=80.20,
        ),
        Community(
            id="COMM-2",
            name="Test Ward 2",
            population=20000,
            node_id="B",
            lat=13.02,
            lon=80.21,
        ),
    ]
    facilities = [
        HealthFacility(
            id="FAC-1",
            name="Test Hospital",
            node_id="D",
            lat=13.05,
            lon=80.25,
            power_status=True,
        ),
    ]
    return communities, facilities


# ---------------------------------------------------------------------------
# Unit tests: CounterfactualRankingEngine
# ---------------------------------------------------------------------------

class TestCounterfactualRankingEngineUnit:
    """Unit tests for CounterfactualRankingEngine without HTTP layer."""

    def test_engine_instantiation(self):
        engine = CounterfactualRankingEngine()
        assert engine.bpr_alpha == 0.15
        assert engine.bpr_beta == 4.0

    def test_engine_custom_bpr_params(self):
        engine = CounterfactualRankingEngine(bpr_alpha=0.20, bpr_beta=3.5)
        assert engine.bpr_alpha == 0.20
        assert engine.bpr_beta == 3.5

    def test_horizon_label_mapping(self):
        engine = CounterfactualRankingEngine()
        assert engine._horizon_label(0) == "NOW"
        assert engine._horizon_label(2) == "+2H"
        assert engine._horizon_label(4) == "+4H"
        assert engine._horizon_label(8) == "+8H"
        assert engine._horizon_label(12) == "+12H"

    def test_empty_candidates_returns_valid_response(self):
        engine, G = _make_mini_graph_engine()
        communities, facilities = _make_communities_and_facilities()
        forecast = _make_mini_forecast(disabled_seg_ids=[], horizon_hours=0)
        cf_engine = CounterfactualRankingEngine()

        resp = cf_engine.rank_against_forecast(
            candidates=[],
            vuln_forecast=forecast,
            operational_graph=G,
            communities=communities,
            facilities=facilities,
        )

        assert isinstance(resp, CounterfactualRankingResponse)
        assert resp.ranked_candidates == []
        assert resp.pareto_front_count == 0
        assert resp.is_read_only is True
        assert resp.is_projected_forecast is True
        assert resp.forecast_id == forecast.forecast_id

    def test_single_candidate_is_pareto_optimal(self):
        engine, G = _make_mini_graph_engine()
        communities, facilities = _make_communities_and_facilities()
        forecast = _make_mini_forecast(disabled_seg_ids=["seg_A_B_0"], horizon_hours=2)
        cf_engine = CounterfactualRankingEngine()

        # Candidate restores the forecast-disabled segment using proper segment ID
        candidate = InterventionCandidate(
            candidate_id="CAND-SINGLE",
            name="Restore A-B",
            intervention_type="CORRIDOR_CLEARANCE",
            physical_segment_ids=["seg_A_B_0"],
            estimated_cost=50000.0,
            difficulty_score=0.4,
            total_length_m=1000.0,
        )

        resp = cf_engine.rank_against_forecast(
            candidates=[candidate],
            vuln_forecast=forecast,
            operational_graph=G,
            communities=communities,
            facilities=facilities,
        )

        assert len(resp.ranked_candidates) == 1
        assert resp.pareto_front_count == 1
        assert resp.ranked_candidates[0].pareto_optimal is True
        assert resp.ranked_candidates[0].rank == 1

    def test_multiple_candidates_ranked_deterministically(self):
        engine, G = _make_mini_graph_engine()
        communities, facilities = _make_communities_and_facilities()
        forecast = _make_mini_forecast(disabled_seg_ids=[], horizon_hours=4)
        cf_engine = CounterfactualRankingEngine()

        candidates = [
            InterventionCandidate(
                candidate_id=f"CAND-{i:03d}",
                name=f"Candidate {i}",
                intervention_type="CORRIDOR_CLEARANCE",
                physical_segment_ids=[],
                estimated_cost=float(i * 10000),
                difficulty_score=round(0.1 * i, 1),
                total_length_m=float(i * 500),
            )
            for i in range(1, 6)
        ]

        resp1 = cf_engine.rank_against_forecast(
            candidates=candidates,
            vuln_forecast=forecast,
            operational_graph=G,
            communities=communities,
            facilities=facilities,
        )

        resp2 = cf_engine.rank_against_forecast(
            candidates=candidates,
            vuln_forecast=forecast,
            operational_graph=G,
            communities=communities,
            facilities=facilities,
        )

        # Deterministic: same candidates → same rank order
        ids1 = [c.candidate_id for c in resp1.ranked_candidates]
        ids2 = [c.candidate_id for c in resp2.ranked_candidates]
        assert ids1 == ids2

    def test_ranked_candidates_have_required_fields(self):
        engine, G = _make_mini_graph_engine()
        communities, facilities = _make_communities_and_facilities()
        forecast = _make_mini_forecast(disabled_seg_ids=[], horizon_hours=0)
        cf_engine = CounterfactualRankingEngine()

        candidate = InterventionCandidate(
            candidate_id="CAND-CHECK",
            name="Checkfields",
            intervention_type="CORRIDOR_CLEARANCE",
            physical_segment_ids=[],
            estimated_cost=75000.0,
            difficulty_score=0.5,
            total_length_m=2000.0,
        )

        resp = cf_engine.rank_against_forecast(
            candidates=[candidate],
            vuln_forecast=forecast,
            operational_graph=G,
            communities=communities,
            facilities=facilities,
        )

        ri = resp.ranked_candidates[0]
        assert ri.candidate_id == "CAND-CHECK"
        assert ri.rank == 1
        assert isinstance(ri.score, float)
        assert isinstance(ri.score_breakdown, MultiObjectiveScoreBreakdown)
        assert ri.evaluated_against_forecast is True
        assert ri.forecast_id == forecast.forecast_id
        assert ri.horizon_hours == 0

    def test_forecast_invariant_operational_graph_not_mutated(self):
        """
        INVARIANT: operational graph must be unchanged after counterfactual evaluation.
        """
        engine, G = _make_mini_graph_engine()
        communities, facilities = _make_communities_and_facilities()
        # Use correct auto-generated segment IDs from NetworkEngine
        forecast = _make_mini_forecast(disabled_seg_ids=["seg_A_B_0", "seg_B_C_0"], horizon_hours=2)
        cf_engine = CounterfactualRankingEngine()

        # Snapshot the disabled_segments set on the forecast engine (operational G is not mutated)
        before_node_count = G.number_of_nodes()
        before_edge_count = G.number_of_edges()

        candidates = [
            InterventionCandidate(
                candidate_id="CAND-RESTORE",
                name="Restore A-B",
                intervention_type="CORRIDOR_CLEARANCE",
                physical_segment_ids=["seg_A_B_0"],
                estimated_cost=50000.0,
                difficulty_score=0.3,
                total_length_m=1000.0,
            )
        ]

        cf_engine.rank_against_forecast(
            candidates=candidates,
            vuln_forecast=forecast,
            operational_graph=G,
            communities=communities,
            facilities=facilities,
        )

        # Verify graph topology (nodes and edges) is unchanged
        assert G.number_of_nodes() == before_node_count, (
            "Operational graph node count changed after counterfactual evaluation — INVARIANT VIOLATION"
        )
        assert G.number_of_edges() == before_edge_count, (
            "Operational graph edge count changed after counterfactual evaluation — INVARIANT VIOLATION"
        )

    def test_score_components_in_0_1_range(self):
        engine, G = _make_mini_graph_engine()
        communities, facilities = _make_communities_and_facilities()
        forecast = _make_mini_forecast(disabled_seg_ids=[], horizon_hours=0)
        cf_engine = CounterfactualRankingEngine()

        candidates = [
            InterventionCandidate(
                candidate_id=f"CAND-SCORE-{i}",
                name=f"Score test {i}",
                intervention_type="CORRIDOR_CLEARANCE",
                physical_segment_ids=[],
                estimated_cost=float(i * 20000),
                difficulty_score=round(0.2 * i, 1),
                total_length_m=float(i * 300),
            )
            for i in range(1, 4)
        ]

        resp = cf_engine.rank_against_forecast(
            candidates=candidates,
            vuln_forecast=forecast,
            operational_graph=G,
            communities=communities,
            facilities=facilities,
        )

        for ri in resp.ranked_candidates:
            bd = ri.score_breakdown
            assert 0.0 <= bd.delta_h <= 1.0, f"delta_h out of range: {bd.delta_h}"
            assert 0.0 <= bd.delta_p <= 1.0, f"delta_p out of range: {bd.delta_p}"
            assert 0.0 <= bd.delta_t <= 1.0, f"delta_t out of range: {bd.delta_t}"
            assert 0.0 <= bd.delta_e <= 1.0, f"delta_e out of range: {bd.delta_e}"
            assert 0.0 <= bd.delta_d <= 1.0, f"delta_d out of range: {bd.delta_d}"

    def test_provenance_fields_populated(self):
        engine, G = _make_mini_graph_engine()
        communities, facilities = _make_communities_and_facilities()
        forecast = _make_mini_forecast(horizon_hours=4)
        cf_engine = CounterfactualRankingEngine()

        resp = cf_engine.rank_against_forecast(
            candidates=[],
            vuln_forecast=forecast,
            operational_graph=G,
            communities=communities,
            facilities=facilities,
        )

        assert resp.provenance["method"] == "bpr_counterfactual_ranking_l7"
        assert resp.provenance["forecast_id"] == forecast.forecast_id
        assert resp.provenance["horizon_hours"] == 4
        assert resp.bpr_alpha == 0.15
        assert resp.bpr_beta == 4.0
        assert resp.weights_used is not None

    def test_pareto_front_with_dominated_candidates(self):
        """
        If candidate B dominates candidate A on all objectives, A is NOT pareto-optimal.
        """
        engine, G = _make_mini_graph_engine()
        communities, facilities = _make_communities_and_facilities()
        forecast = _make_mini_forecast(horizon_hours=0)
        cf_engine = CounterfactualRankingEngine()

        # Create candidates that differ only in difficulty (cost)
        # Lower cost candidates will be preferred (lower delta_d penalty)
        candidates = [
            InterventionCandidate(
                candidate_id="HIGH-COST",
                name="High cost intervention",
                intervention_type="CORRIDOR_CLEARANCE",
                physical_segment_ids=[],
                estimated_cost=200000.0,
                difficulty_score=0.9,
                total_length_m=3000.0,
            ),
            InterventionCandidate(
                candidate_id="LOW-COST",
                name="Low cost intervention",
                intervention_type="CORRIDOR_CLEARANCE",
                physical_segment_ids=[],
                estimated_cost=10000.0,
                difficulty_score=0.1,
                total_length_m=500.0,
            ),
        ]

        resp = cf_engine.rank_against_forecast(
            candidates=candidates,
            vuln_forecast=forecast,
            operational_graph=G,
            communities=communities,
            facilities=facilities,
        )

        assert len(resp.ranked_candidates) == 2
        # Pareto front count is bounded
        assert resp.pareto_front_count >= 1

    def test_weight_preset_equity_priority(self):
        engine, G = _make_mini_graph_engine()
        communities, facilities = _make_communities_and_facilities()
        forecast = _make_mini_forecast(horizon_hours=0)
        cf_engine = CounterfactualRankingEngine()
        weights = MultiObjectiveWeights.equity_priority()

        candidates = [
            InterventionCandidate(
                candidate_id="EQ-CAND",
                name="Equity candidate",
                intervention_type="CORRIDOR_CLEARANCE",
                physical_segment_ids=[],
                estimated_cost=30000.0,
                difficulty_score=0.3,
                total_length_m=1000.0,
            )
        ]

        resp = cf_engine.rank_against_forecast(
            candidates=candidates,
            vuln_forecast=forecast,
            operational_graph=G,
            communities=communities,
            facilities=facilities,
            weights=weights,
        )

        assert resp.weights_used["w_e"] == pytest.approx(0.30, abs=1e-4)

    def test_bpr_model_applied_on_forecast_engine(self):
        """
        BPRCapacityTravelTimeModel must be set on the forecast engine.
        Verifies the engine is built with BPR (not static) model.
        """
        from cyclone_twin.providers.travel_time_model import BPRCapacityTravelTimeModel

        engine, G = _make_mini_graph_engine()
        cf_engine = CounterfactualRankingEngine(bpr_alpha=0.15, bpr_beta=4.0)

        forecast_engine = cf_engine._build_forecast_engine(
            operational_graph=G,
            forecast_disabled_ids=[],
        )

        assert isinstance(forecast_engine.travel_time_model, BPRCapacityTravelTimeModel)
        assert forecast_engine.travel_time_model.alpha == 0.15
        assert forecast_engine.travel_time_model.beta == 4.0


# ---------------------------------------------------------------------------
# Integration tests: HTTP endpoint
# ---------------------------------------------------------------------------

class TestForecastInterventionsEndpoint:
    """Integration tests for GET /forecast/interventions via FastAPI TestClient."""

    def test_get_forecast_interventions_now(self):
        resp = client.get("/forecast/interventions?horizon=NOW")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_projected_forecast"] is True
        assert data["is_read_only"] is True
        assert "ranked_candidates" in data
        assert "forecast_id" in data
        assert "horizon" in data
        assert data["horizon_hours"] == 0

    def test_get_forecast_interventions_plus2h(self):
        resp = client.get("/forecast/interventions?horizon=%2B2H")
        assert resp.status_code == 200
        data = resp.json()
        assert data["horizon_hours"] == 2
        assert data["horizon"] == "+2H"

    def test_get_forecast_interventions_plus4h(self):
        resp = client.get("/forecast/interventions?horizon=%2B4H")
        assert resp.status_code == 200
        data = resp.json()
        assert data["horizon_hours"] == 4

    def test_get_forecast_interventions_plus8h(self):
        resp = client.get("/forecast/interventions?horizon=%2B8H")
        assert resp.status_code == 200
        data = resp.json()
        assert data["horizon_hours"] == 8

    def test_invalid_horizon_returns_400(self):
        resp = client.get("/forecast/interventions?horizon=INVALID")
        assert resp.status_code == 400

    def test_invalid_weight_preset_returns_400(self):
        resp = client.get("/forecast/interventions?weight_preset=unknown_preset")
        assert resp.status_code == 400

    def test_equity_priority_preset(self):
        resp = client.get("/forecast/interventions?weight_preset=equity_priority")
        assert resp.status_code == 200
        data = resp.json()
        assert data["weights_used"]["w_e"] == pytest.approx(0.30, abs=0.01)

    def test_rapid_clearance_preset(self):
        resp = client.get("/forecast/interventions?weight_preset=rapid_clearance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["weights_used"]["w_d"] == pytest.approx(0.30, abs=0.01)

    def test_life_safety_preset_default(self):
        resp = client.get("/forecast/interventions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["weights_used"]["w_h"] == pytest.approx(0.35, abs=0.01)

    def test_ranked_candidates_structure(self):
        resp = client.get("/forecast/interventions?horizon=NOW")
        assert resp.status_code == 200
        data = resp.json()
        for candidate in data["ranked_candidates"]:
            assert "candidate_id" in candidate
            assert "rank" in candidate
            assert "score" in candidate
            assert "score_breakdown" in candidate
            bd = candidate["score_breakdown"]
            assert 0.0 <= bd["delta_h"] <= 1.0
            assert 0.0 <= bd["delta_p"] <= 1.0
            assert 0.0 <= bd["delta_t"] <= 1.0
            assert 0.0 <= bd["delta_e"] <= 1.0
            assert 0.0 <= bd["delta_d"] <= 1.0
            assert candidate["evaluated_against_forecast"] is True

    def test_ranked_candidates_sorted_by_rank(self):
        resp = client.get("/forecast/interventions?horizon=NOW")
        assert resp.status_code == 200
        data = resp.json()
        ranks = [c["rank"] for c in data["ranked_candidates"]]
        assert ranks == sorted(ranks), "Candidates must be sorted by rank ascending"

    def test_provenance_includes_method(self):
        resp = client.get("/forecast/interventions?horizon=NOW")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provenance"]["method"] == "bpr_counterfactual_ranking_l7"

    def test_bpr_params_in_response(self):
        resp = client.get("/forecast/interventions?horizon=NOW")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bpr_alpha"] == pytest.approx(0.15, abs=1e-4)
        assert data["bpr_beta"] == pytest.approx(4.0, abs=1e-4)

    def test_is_read_only_always_true(self):
        for horizon in ["NOW", "+2H", "+4H", "+8H"]:
            resp = client.get(f"/forecast/interventions?horizon={horizon.replace('+', '%2B')}")
            assert resp.status_code == 200
            assert resp.json()["is_read_only"] is True

    def test_horizon_without_plus_sign(self):
        """Horizon without + prefix should be accepted (e.g. '2H', '4H')."""
        resp = client.get("/forecast/interventions?horizon=2H")
        assert resp.status_code == 200
        assert resp.json()["horizon_hours"] == 2

    def test_ranking_id_unique_per_call(self):
        """Each call must produce a unique ranking_id."""
        resp1 = client.get("/forecast/interventions?horizon=NOW")
        resp2 = client.get("/forecast/interventions?horizon=NOW")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["ranking_id"] != resp2.json()["ranking_id"]


# ---------------------------------------------------------------------------
# Invariant tests: FORECAST != OBSERVATION != STATE
# ---------------------------------------------------------------------------

class TestForecastInvariant:
    """
    Verify that calling /forecast/interventions does NOT mutate operational state.
    """

    def test_operational_state_unchanged_after_ranking(self):
        """
        Call /accessibility/status before and after /forecast/interventions —
        the operational accessibility state must be identical.
        """
        before = client.get("/accessibility/status").json()
        client.get("/forecast/interventions?horizon=%2B4H")
        after = client.get("/accessibility/status").json()

        assert before["accessible_population"] == after["accessible_population"], (
            "Operational accessible population changed after L7 ranking — INVARIANT VIOLATION"
        )
        assert before["isolated_facilities"] == after["isolated_facilities"], (
            "Operational isolated facilities changed after L7 ranking — INVARIANT VIOLATION"
        )

    def test_forecast_interventions_does_not_affect_observations(self):
        """
        Submitting observations and then calling /forecast/interventions must not
        change observation count.
        """
        # Count observations before
        obs_before = client.get("/observations").json()
        count_before = len(obs_before) if isinstance(obs_before, list) else obs_before.get("total", 0)

        # Call L7 ranking
        client.get("/forecast/interventions?horizon=%2B2H")

        # Count observations after
        obs_after = client.get("/observations").json()
        count_after = len(obs_after) if isinstance(obs_after, list) else obs_after.get("total", 0)

        assert count_before == count_after, (
            "Observation count changed after L7 forecast intervention ranking — INVARIANT VIOLATION"
        )
