"""
Cyclone Twin — Milestone L7: BPR-Aware Counterfactual Intervention Ranking Engine

Connects the L3/L4/L5 forecast vulnerability layer to the existing multi-objective
decision engine so that candidates are evaluated against the *projected* (forecast)
network state rather than the current operational state.

ARCHITECTURAL INVARIANTS (must be preserved throughout L7):
1. FORECAST != OBSERVATION != STATE
   - No mutation to operational DisasterState, NetworkEngine, or observations.
   - All evaluation runs on an isolated temporary NetworkEngine cloned from the
     forecast's projected disabled-segment set.
2. RANKING is deterministic decision SUPPORT — not autonomous dispatch.
   - Humans must approve any intervention derived from this output.
3. BPR travel-time model is applied consistently on the forecast network.
   - t(v) = t0 * [1 + alpha * (v/C)^beta]
   - Restoring a segment removes it from the forecast's disabled set so BPR
     operates over the resulting (modified-forecast) topology.
4. Pareto-dominance across (ΔH, ΔP, ΔT, ΔE, 1-ΔD) is computed identically
   to the operational decision engine — no divergence in scoring logic.
"""

import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from cyclone_twin.decision_engine import (
    InterventionCandidate,
    MultiObjectiveDecisionEngine,
    MultiObjectiveWeights,
    MultiObjectiveScoreBreakdown,
    RankedIntervention,
)
from cyclone_twin.domain.entities import VulnerabilityForecast
from cyclone_twin.network_engine import NetworkEngine
from cyclone_twin.providers.travel_time_model import BPRCapacityTravelTimeModel
from cyclone_twin.ranking_engine import compute_accessibility


# ---------------------------------------------------------------------------
# Response domain model
# ---------------------------------------------------------------------------

class CounterfactualRankedIntervention(BaseModel):
    """
    A single intervention candidate evaluated against the forecast network.

    All fields are derived from the projected (forecast) state, NOT the current
    operational state. Do not use this output to directly modify DisasterState.
    """
    candidate_id: str
    rank: int
    score: float
    intervention_type: str
    score_breakdown: MultiObjectiveScoreBreakdown
    physical_segment_ids: List[str] = Field(default_factory=list)
    target_facility_ids: List[str] = Field(default_factory=list)
    estimated_cost: float = 0.0
    difficulty_score: float = 0.0
    total_length_m: float = 0.0
    pareto_optimal: bool = False
    geometry: Optional[Dict[str, Any]] = None

    # Forecast provenance — makes clear these are projections
    forecast_id: str = ""
    horizon_hours: int = 0
    evaluated_against_forecast: bool = True


class CounterfactualRankingResponse(BaseModel):
    """
    API response for GET /forecast/interventions.

    Contains ranked intervention candidates evaluated against a projected
    forecast network, not the current operational state.
    """
    ranking_id: str
    forecast_id: str
    horizon: str = "NOW"
    horizon_hours: int = Field(0, ge=0)
    reference_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Forecast network summary (projected, read-only)
    projected_disabled_segments_count: int = 0
    projected_accessible_population: int = 0
    projected_isolated_facilities: List[str] = Field(default_factory=list)
    projected_isolated_communities: List[str] = Field(default_factory=list)

    # Ranked candidates
    ranked_candidates: List[CounterfactualRankedIntervention] = Field(default_factory=list)
    pareto_front_count: int = 0

    # Provenance / audit trail
    weights_used: Dict[str, float] = Field(default_factory=dict)
    bpr_alpha: float = 0.15
    bpr_beta: float = 4.0
    provenance: Dict[str, Any] = Field(default_factory=dict)
    is_projected_forecast: bool = True
    is_read_only: bool = True


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CounterfactualRankingEngine:
    """
    Milestone L7: BPR-aware counterfactual intervention ranking over a forecast network.

    Workflow:
    1. Receive VulnerabilityForecast (projected, read-only) from L3/L5.
    2. Extract predicted disabled segment IDs from forecast.
    3. Clone graph into isolated temporary NetworkEngine with BPR travel-time model.
    4. Establish forecast baseline accessibility (projected, not operational).
    5. For each candidate: remove candidate's segments from forecast-disabled set
       (counterfactual clearance in forecast world), recompute accessibility,
       compute multi-objective delta scores.
    6. Determine Pareto-optimal front across all candidates.
    7. Return ranked list — NEVER mutate operational NetworkEngine or DisasterState.

    GUARANTEE: The operational NetworkEngine passed in is NEVER modified.
    All evaluation runs on isolated temporary engine instances.
    """

    def __init__(
        self,
        bpr_alpha: float = 0.15,
        bpr_beta: float = 4.0,
    ):
        self.bpr_alpha = bpr_alpha
        self.bpr_beta = bpr_beta
        self._bpr_model = BPRCapacityTravelTimeModel(alpha=bpr_alpha, beta=bpr_beta)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_forecast_engine(
        self,
        operational_graph,
        forecast_disabled_ids: List[str],
        travel_time_model=None,
    ) -> NetworkEngine:
        """
        Build an isolated NetworkEngine representing the *forecast* network state.

        This engine has:
        - The same graph topology as the operational graph (deep copy).
        - BPR travel-time model applied.
        - Only the forecast-predicted disabled segments deactivated.

        GUARANTEE: operational_graph is never mutated.
        """
        forecast_engine = NetworkEngine(graph=operational_graph)
        forecast_engine.set_travel_time_model(travel_time_model or self._bpr_model)
        if forecast_disabled_ids:
            # validate=False: forecast IDs are from an external projection pipeline.
            # IDs that do not exist in this graph are silently skipped (graceful degradation).
            forecast_engine.disable_segments(forecast_disabled_ids, validate=False)
        return forecast_engine

    def _evaluate_candidate_on_forecast(
        self,
        candidate: InterventionCandidate,
        forecast_engine: NetworkEngine,
        forecast_baseline,
        communities,
        facilities,
        weights: MultiObjectiveWeights,
        max_metric: float,
        threshold_seconds: float,
    ) -> MultiObjectiveScoreBreakdown:
        """
        Evaluate one candidate counterfactually against the forecast network.

        Counterfactual logic:
        - The candidate's physical_segment_ids are treated as "cleared" in the
          forecast world (i.e., removed from the disabled set).
        - This is purely hypothetical — no operational network is modified.
        - After evaluation the candidate-specific engine is discarded.

        Uses BPR formula: t(v) = t0 * [1 + alpha * (v/C)^beta]
        """
        from cyclone_twin.ranking_engine import _delta_T

        # Power counterfactual for facilities
        original_power_states: Dict[str, bool] = {}
        for fac_id in candidate.target_facility_ids:
            fac = next((f for f in facilities if f.id == fac_id), None)
            if fac:
                original_power_states[fac_id] = fac.power_status
                fac.power_status = True

        # Counterfactually restore segments on forecast engine
        segments_restored = False
        if candidate.physical_segment_ids:
            forecast_engine.restore_segments(candidate.physical_segment_ids)
            segments_restored = True

        try:
            cand_access = compute_accessibility(
                forecast_engine,
                communities,
                facilities,
                threshold_seconds=threshold_seconds,
            )
        finally:
            # Atomic rollback — restore forecast engine to its projected state
            if segments_restored:
                forecast_engine.disable_segments(
                    candidate.physical_segment_ids, validate=False
                )
            for fac_id, orig_pwr in original_power_states.items():
                fac = next((f for f in facilities if f.id == fac_id), None)
                if fac:
                    fac.power_status = orig_pwr

        # --- Metric deltas ---
        total_pop = sum(c.population for c in communities)
        baseline_iso_fac_count = len(forecast_baseline.isolated_facilities)
        baseline_acc_pop = forecast_baseline.accessible_population
        baseline_iso_pop = max(0, total_pop - baseline_acc_pop)

        cand_iso_fac_count = len(cand_access.isolated_facilities)
        cand_acc_pop = cand_access.accessible_population

        # ΔH — hospital recovery fraction
        hospitals_recovered = max(0, baseline_iso_fac_count - cand_iso_fac_count)
        delta_h = (
            min(1.0, hospitals_recovered / baseline_iso_fac_count)
            if baseline_iso_fac_count > 0 else 0.0
        )

        # ΔP — population recovery fraction
        population_recovered = max(0, cand_acc_pop - baseline_acc_pop)
        delta_p = (
            min(1.0, population_recovered / baseline_iso_pop)
            if baseline_iso_pop > 0 else 0.0
        )

        # ΔT — population-weighted travel-time reduction (BPR-based)
        delta_t, minutes_saved = _delta_T(
            forecast_baseline.community_travel_times,
            cand_access.community_travel_times,
            communities,
            threshold_seconds=threshold_seconds,
        )

        # ΔE — equity-weighted vulnerability recovery
        comm_map = {c.id: c for c in communities}
        iso_comm_set = set(forecast_baseline.isolated_communities)
        baseline_vuln_sum = sum(
            c.population * getattr(c, "vulnerability_index", 1.0)
            for c in communities if c.id in iso_comm_set
        )
        recovered_comm_ids = iso_comm_set - set(cand_access.isolated_communities)
        recovered_vuln_sum = sum(
            comm_map[cid].population * getattr(comm_map[cid], "vulnerability_index", 1.0)
            for cid in recovered_comm_ids if cid in comm_map
        )
        delta_e = (
            min(1.0, recovered_vuln_sum / baseline_vuln_sum)
            if baseline_vuln_sum > 0 else 0.0
        )

        # ΔD — difficulty / cost penalty
        penalty_metric = (
            candidate.estimated_cost if candidate.estimated_cost > 0
            else (candidate.total_length_m if candidate.total_length_m > 0
                  else candidate.difficulty_score)
        )
        delta_d = min(1.0, penalty_metric / max_metric) if max_metric > 0 else candidate.difficulty_score

        score = (
            weights.w_h * delta_h
            + weights.w_p * delta_p
            + weights.w_t * delta_t
            + weights.w_e * delta_e
            - weights.w_d * delta_d
        )

        return MultiObjectiveScoreBreakdown(
            delta_h=round(delta_h, 4),
            delta_p=round(delta_p, 4),
            delta_t=round(delta_t, 4),
            delta_e=round(delta_e, 4),
            delta_d=round(delta_d, 4),
            score=round(score, 4),
            hospitals_recovered=hospitals_recovered,
            population_recovered=population_recovered,
            equity_weighted_recovered=round(recovered_vuln_sum, 1),
            time_saved_minutes=minutes_saved,
            pareto_optimal=False,
        )

    def _identify_pareto_front(
        self,
        scored_items: List[Tuple[InterventionCandidate, MultiObjectiveScoreBreakdown]],
    ) -> Set[str]:
        """
        Identifies Pareto-optimal candidates across (ΔH, ΔP, ΔT, ΔE, 1-ΔD).
        Identical logic to operational MultiObjectiveDecisionEngine.
        """
        pareto_ids: Set[str] = set()
        for cand_a, bd_a in scored_items:
            vec_a = (bd_a.delta_h, bd_a.delta_p, bd_a.delta_t, bd_a.delta_e, 1.0 - bd_a.delta_d)
            dominated = False
            for cand_b, bd_b in scored_items:
                if cand_a.candidate_id == cand_b.candidate_id:
                    continue
                vec_b = (bd_b.delta_h, bd_b.delta_p, bd_b.delta_t, bd_b.delta_e, 1.0 - bd_b.delta_d)
                if all(b >= a for a, b in zip(vec_a, vec_b)) and any(b > a for a, b in zip(vec_a, vec_b)):
                    dominated = True
                    break
            if not dominated:
                pareto_ids.add(cand_a.candidate_id)
        return pareto_ids

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank_against_forecast(
        self,
        candidates: List[InterventionCandidate],
        vuln_forecast: VulnerabilityForecast,
        operational_graph,
        communities,
        facilities,
        travel_time_model=None,
        weights: Optional[MultiObjectiveWeights] = None,
        threshold_seconds: float = 1800.0,
    ) -> CounterfactualRankingResponse:
        """
        Rank intervention candidates against a projected forecast network state.

        Parameters
        ----------
        candidates : list of InterventionCandidate
            Intervention proposals to evaluate.
        vuln_forecast : VulnerabilityForecast
            L3/L5 read-only projected vulnerability forecast to evaluate against.
        operational_graph : networkx.DiGraph
            Operational road network graph — NEVER mutated by this method.
        communities : list of Community
            Population zones.
        facilities : list of HealthFacility
            Health facility definitions.
        travel_time_model : TravelTimeModel, optional
            Defaults to BPRCapacityTravelTimeModel(alpha, beta).
        weights : MultiObjectiveWeights, optional
            Scoring weights; defaults to life_safety preset.
        threshold_seconds : float
            Accessibility travel-time threshold in seconds.

        Returns
        -------
        CounterfactualRankingResponse
            Ranked candidates with scores, Pareto front, and full provenance.
            is_projected_forecast=True, is_read_only=True always.
        """
        ref_time = datetime.now(timezone.utc)
        w = weights or MultiObjectiveWeights.life_safety()

        # Extract projected disabled segments from forecast
        forecast_disabled_ids: List[str] = [
            rv.segment_id for rv in vuln_forecast.road_vulnerabilities
        ]

        # Build isolated forecast NetworkEngine (BPR-based, 0 operational mutation)
        forecast_engine = self._build_forecast_engine(
            operational_graph=operational_graph,
            forecast_disabled_ids=forecast_disabled_ids,
            travel_time_model=travel_time_model or self._bpr_model,
        )

        # Forecast baseline accessibility
        forecast_baseline = compute_accessibility(
            forecast_engine, communities, facilities, threshold_seconds=threshold_seconds
        )

        if not candidates:
            return CounterfactualRankingResponse(
                ranking_id=f"CF-RANK-{uuid.uuid4().hex[:8]}",
                forecast_id=vuln_forecast.forecast_id,
                horizon=self._horizon_label(vuln_forecast.horizon_hours),
                horizon_hours=vuln_forecast.horizon_hours,
                reference_time=ref_time,
                generated_at=ref_time,
                projected_disabled_segments_count=len(forecast_disabled_ids),
                projected_accessible_population=forecast_baseline.accessible_population,
                projected_isolated_facilities=forecast_baseline.isolated_facilities,
                projected_isolated_communities=forecast_baseline.isolated_communities,
                ranked_candidates=[],
                pareto_front_count=0,
                weights_used=w.model_dump(),
                bpr_alpha=self.bpr_alpha,
                bpr_beta=self.bpr_beta,
                provenance={
                    "forecast_id": vuln_forecast.forecast_id,
                    "horizon_hours": vuln_forecast.horizon_hours,
                    "candidates_evaluated": 0,
                    "method": "bpr_counterfactual_ranking_l7",
                },
            )

        # Normalisation denominator for difficulty penalty
        max_metric = max(
            (
                c.estimated_cost if c.estimated_cost > 0
                else (c.total_length_m if c.total_length_m > 0 else c.difficulty_score)
                for c in candidates
            ),
            default=1.0,
        )
        if max_metric <= 0.0:
            max_metric = 1.0

        # Score all candidates
        scored_items: List[Tuple[InterventionCandidate, MultiObjectiveScoreBreakdown]] = []
        for cand in candidates:
            bd = self._evaluate_candidate_on_forecast(
                candidate=cand,
                forecast_engine=forecast_engine,
                forecast_baseline=forecast_baseline,
                communities=communities,
                facilities=facilities,
                weights=w,
                max_metric=max_metric,
                threshold_seconds=threshold_seconds,
            )
            scored_items.append((cand, bd))

        # Pareto front
        pareto_front_ids = self._identify_pareto_front(scored_items)
        for cand, bd in scored_items:
            if cand.candidate_id in pareto_front_ids:
                bd.pareto_optimal = True

        # Deterministic sort: score DESC, penalty metric ASC, candidate_id ASC
        scored_items.sort(
            key=lambda item: (
                -item[1].score,
                item[0].estimated_cost or item[0].total_length_m or item[0].difficulty_score,
                item[0].candidate_id,
            )
        )

        # Optional tiebreaker: if top-2 scores within 0.05, prefer lower-cost
        if len(scored_items) >= 2:
            top_score = scored_items[0][1].score
            second_score = scored_items[1][1].score
            if abs(top_score - second_score) < 0.05:
                m0 = scored_items[0][0].estimated_cost or scored_items[0][0].total_length_m
                m1 = scored_items[1][0].estimated_cost or scored_items[1][0].total_length_m
                if m1 > 0 and m1 < m0:
                    scored_items[0], scored_items[1] = scored_items[1], scored_items[0]

        # Build ranked list
        horizon_label = self._horizon_label(vuln_forecast.horizon_hours)
        ranked: List[CounterfactualRankedIntervention] = []
        for idx, (cand, bd) in enumerate(scored_items):
            ranked.append(
                CounterfactualRankedIntervention(
                    candidate_id=cand.candidate_id,
                    rank=idx + 1,
                    score=bd.score,
                    intervention_type=cand.intervention_type,
                    score_breakdown=bd,
                    physical_segment_ids=cand.physical_segment_ids,
                    target_facility_ids=cand.target_facility_ids,
                    estimated_cost=cand.estimated_cost,
                    difficulty_score=cand.difficulty_score,
                    total_length_m=cand.total_length_m,
                    pareto_optimal=bd.pareto_optimal,
                    geometry=cand.geometry,
                    forecast_id=vuln_forecast.forecast_id,
                    horizon_hours=vuln_forecast.horizon_hours,
                    evaluated_against_forecast=True,
                )
            )

        return CounterfactualRankingResponse(
            ranking_id=f"CF-RANK-{uuid.uuid4().hex[:8]}",
            forecast_id=vuln_forecast.forecast_id,
            horizon=horizon_label,
            horizon_hours=vuln_forecast.horizon_hours,
            reference_time=ref_time,
            generated_at=ref_time,
            projected_disabled_segments_count=len(forecast_disabled_ids),
            projected_accessible_population=forecast_baseline.accessible_population,
            projected_isolated_facilities=forecast_baseline.isolated_facilities,
            projected_isolated_communities=forecast_baseline.isolated_communities,
            ranked_candidates=ranked,
            pareto_front_count=len(pareto_front_ids),
            weights_used=w.model_dump(),
            bpr_alpha=self.bpr_alpha,
            bpr_beta=self.bpr_beta,
            provenance={
                "forecast_id": vuln_forecast.forecast_id,
                "scenario_id": vuln_forecast.scenario_id,
                "horizon_hours": vuln_forecast.horizon_hours,
                "candidates_evaluated": len(candidates),
                "forecast_disabled_segments": len(forecast_disabled_ids),
                "method": "bpr_counterfactual_ranking_l7",
                "bpr_alpha": self.bpr_alpha,
                "bpr_beta": self.bpr_beta,
                "weights": w.model_dump(),
                "generated_at": ref_time.isoformat(),
            },
            is_projected_forecast=True,
            is_read_only=True,
        )

    @staticmethod
    def _horizon_label(horizon_hours: int) -> str:
        return {0: "NOW", 2: "+2H", 4: "+4H", 8: "+8H"}.get(horizon_hours, f"+{horizon_hours}H")
