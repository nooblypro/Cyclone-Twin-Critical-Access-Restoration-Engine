"""
Cyclone Twin Multi-Objective Intervention Decision Engine
Evaluates counterfactual intervention proposals (corridor clearance, pump deployment, power restoration, embankment stabilization)
across multi-objective metrics: hospital recovery, population recovery, travel time reduction, equity-weighted vulnerability recovery, and cost/difficulty.
Computes Pareto optimality and ranks proposals deterministically with strict state isolation.
"""

import math
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field, model_validator

from cyclone_twin.models import Community, HealthFacility, Corridor, AccessibilityResult
from cyclone_twin.network_engine import NetworkEngine
from cyclone_twin.ranking_engine import compute_accessibility, _delta_T


class MultiObjectiveWeights(BaseModel):
    """
    Multi-objective scoring weights for intervention decision engine.
    w_h: hospital recovery weight
    w_p: population recovery weight
    w_t: travel time improvement weight
    w_e: social equity / vulnerability recovery weight
    w_d: cost / difficulty penalty weight
    Must be non-negative and sum to 1.0 within float tolerance.
    """
    w_h: float = Field(0.35, ge=0.0, le=1.0, description="Weight for hospital accessibility recovery")
    w_p: float = Field(0.25, ge=0.0, le=1.0, description="Weight for population accessibility recovery")
    w_t: float = Field(0.15, ge=0.0, le=1.0, description="Weight for travel time reduction")
    w_e: float = Field(0.15, ge=0.0, le=1.0, description="Weight for equity / vulnerability recovery")
    w_d: float = Field(0.10, ge=0.0, le=1.0, description="Weight for cost / difficulty / length penalty")

    @model_validator(mode="after")
    def validate_sum(self) -> "MultiObjectiveWeights":
        total = self.w_h + self.w_p + self.w_t + self.w_e + self.w_d
        if abs(total - 1.0) > 1e-4:
            raise ValueError(f"MultiObjectiveWeights must sum to 1.0, got sum = {total:.4f}")
        return self

    @classmethod
    def equity_priority(cls) -> "MultiObjectiveWeights":
        """Equity-focused preset prioritizing vulnerable population zones."""
        return cls(w_h=0.25, w_p=0.20, w_t=0.15, w_e=0.30, w_d=0.10)

    @classmethod
    def life_safety(cls) -> "MultiObjectiveWeights":
        """Pre-configured life-safety preset prioritizing hospital access and population."""
        return cls(w_h=0.35, w_p=0.25, w_t=0.15, w_e=0.15, w_d=0.10)

    @classmethod
    def rapid_clearance(cls) -> "MultiObjectiveWeights":
        """Clearance-focused preset prioritizing rapid low-difficulty interventions."""
        return cls(w_h=0.20, w_p=0.20, w_t=0.15, w_e=0.15, w_d=0.30)


class InterventionCandidate(BaseModel):
    """
    Candidate infrastructure intervention proposal for counterfactual evaluation.
    Supports corridor clearance, pump deployment, hospital power restoration, embankment stabilization, and bridge prioritization.
    """
    candidate_id: str
    name: str
    intervention_type: str = "CORRIDOR_CLEARANCE"  # "CORRIDOR_CLEARANCE" | "PUMP_DEPLOYMENT" | "POWER_RESTORATION" | "EMBANKMENT_STABILIZATION" | "BRIDGE_PRIORITIZATION"
    physical_segment_ids: List[str] = Field(default_factory=list)
    target_facility_ids: List[str] = Field(default_factory=list)
    estimated_cost: float = Field(0.0, ge=0.0)
    difficulty_score: float = Field(0.0, ge=0.0, le=1.0)
    total_length_m: float = Field(0.0, ge=0.0)
    road_classes: List[str] = Field(default_factory=list)
    geometry: Optional[Dict[str, Any]] = None


class MultiObjectiveScoreBreakdown(BaseModel):
    """Normalized multi-objective deltas, Pareto status, and summary metrics."""
    delta_h: float = Field(..., ge=0.0, le=1.0, description="Normalized hospital recovery delta")
    delta_p: float = Field(..., ge=0.0, le=1.0, description="Normalized population recovery delta")
    delta_t: float = Field(..., ge=0.0, le=1.0, description="Normalized travel time improvement delta")
    delta_e: float = Field(..., ge=0.0, le=1.0, description="Normalized equity vulnerability recovery delta")
    delta_d: float = Field(..., ge=0.0, le=1.0, description="Normalized difficulty/cost penalty delta")
    score: float
    hospitals_recovered: int = 0
    population_recovered: int = 0
    equity_weighted_recovered: float = 0.0
    time_saved_minutes: float = 0.0
    pareto_optimal: bool = False


class RankedIntervention(BaseModel):
    """Ranked intervention candidate with multi-objective breakdown and Pareto status."""
    candidate_id: str
    rank: int
    score: float
    intervention_type: str
    score_breakdown: MultiObjectiveScoreBreakdown
    physical_segment_ids: List[str]
    target_facility_ids: List[str]
    estimated_cost: float
    difficulty_score: float
    total_length_m: float
    pareto_optimal: bool = False
    geometry: Optional[Dict[str, Any]] = None


class MultiObjectiveDecisionEngine:
    """
    Deterministic Multi-Objective Intervention Decision Engine.
    Evaluates candidate interventions counterfactually against network graph.
    Formula:
    S(c) = w_h * ΔH + w_p * ΔP + w_t * ΔT + w_e * ΔE - w_d * ΔD
    Identifies Pareto-optimal front and ranks proposals deterministically with state isolation.
    """

    def __init__(self, network_engine: NetworkEngine):
        self.network_engine = network_engine

    def evaluate_candidate(
        self,
        candidate: InterventionCandidate,
        baseline_access: AccessibilityResult,
        communities: List[Community],
        facilities: List[HealthFacility],
        weights: MultiObjectiveWeights,
        max_cost_or_length: float,
        threshold_seconds: float = 1800.0,
    ) -> MultiObjectiveScoreBreakdown:
        """
        Counterfactually evaluates a single intervention proposal.
        Guarantees 100% atomic state isolation via try ... finally rollback.
        """
        original_power_states: Dict[str, bool] = {}
        for fac_id in candidate.target_facility_ids:
            fac = next((f for f in facilities if f.id == fac_id), None)
            if fac:
                original_power_states[fac_id] = fac.power_status
                fac.power_status = True  # Counterfactually power health facility

        segments_restored = False
        if candidate.physical_segment_ids:
            self.network_engine.restore_segments(candidate.physical_segment_ids)
            segments_restored = True

        try:
            cand_access = compute_accessibility(
                self.network_engine,
                communities,
                facilities,
                threshold_seconds=threshold_seconds,
            )
        finally:
            # Atomic state rollback
            if segments_restored:
                self.network_engine.disable_segments(candidate.physical_segment_ids, validate=False)
            for fac_id, orig_pwr in original_power_states.items():
                fac = next((f for f in facilities if f.id == fac_id), None)
                if fac:
                    fac.power_status = orig_pwr

        # Metrics calculation
        total_pop = sum(c.population for c in communities)
        baseline_isolated_fac_count = len(baseline_access.isolated_facilities)
        baseline_isolated_pop = total_pop - baseline_access.accessible_population

        cand_isolated_fac_count = len(cand_access.isolated_facilities)
        cand_accessible_pop = cand_access.accessible_population

        # 1. Delta H (Hospital Recovery)
        hospitals_recovered = max(0, baseline_isolated_fac_count - cand_isolated_fac_count)
        delta_h = min(1.0, max(0.0, hospitals_recovered / baseline_isolated_fac_count)) if baseline_isolated_fac_count > 0 else 0.0

        # 2. Delta P (Population Recovery)
        population_recovered = max(0, cand_accessible_pop - baseline_access.accessible_population)
        delta_p = min(1.0, max(0.0, population_recovered / baseline_isolated_pop)) if baseline_isolated_pop > 0 else 0.0

        # 3. Delta T (Population-Weighted Travel Time Reduction)
        delta_t, minutes_saved = _delta_T(
            baseline_access.community_travel_times,
            cand_access.community_travel_times,
            communities,
            threshold_seconds=threshold_seconds,
        )

        # 4. Delta E (Equity-Weighted Vulnerability Recovery)
        comm_map = {c.id: c for c in communities}
        isolated_comm_set = set(baseline_access.isolated_communities)

        baseline_isolated_vuln_sum = sum(
            c.population * getattr(c, "vulnerability_index", 1.0)
            for c in communities if c.id in isolated_comm_set
        )

        cand_isolated_comm_set = set(cand_access.isolated_communities)
        recovered_comm_ids = isolated_comm_set - cand_isolated_comm_set

        recovered_vuln_sum = sum(
            comm_map[cid].population * getattr(comm_map[cid], "vulnerability_index", 1.0)
            for cid in recovered_comm_ids if cid in comm_map
        )

        if baseline_isolated_vuln_sum > 0:
            delta_e = min(1.0, max(0.0, recovered_vuln_sum / baseline_isolated_vuln_sum))
        else:
            delta_e = 0.0

        # 5. Delta D (Difficulty / Cost / Length Penalty)
        penalty_metric = candidate.estimated_cost if candidate.estimated_cost > 0 else (
            candidate.total_length_m if candidate.total_length_m > 0 else candidate.difficulty_score
        )
        if max_cost_or_length > 0:
            delta_d = min(1.0, max(0.0, penalty_metric / max_cost_or_length))
        else:
            delta_d = candidate.difficulty_score

        # Multi-Objective Score Formula
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

    def identify_pareto_front(
        self,
        scored_items: List[Tuple[InterventionCandidate, MultiObjectiveScoreBreakdown]],
    ) -> Set[str]:
        """
        Identifies non-dominated candidate proposals across objective vectors:
        (delta_h, delta_p, delta_t, delta_e, 1 - delta_d).
        Returns set of candidate_ids on the Pareto front.
        """
        pareto_ids: Set[str] = set()

        for cand_a, bd_a in scored_items:
            vec_a = (bd_a.delta_h, bd_a.delta_p, bd_a.delta_t, bd_a.delta_e, 1.0 - bd_a.delta_d)
            dominated = False

            for cand_b, bd_b in scored_items:
                if cand_a.candidate_id == cand_b.candidate_id:
                    continue
                vec_b = (bd_b.delta_h, bd_b.delta_p, bd_b.delta_t, bd_b.delta_e, 1.0 - bd_b.delta_d)

                if all(b_val >= a_val for a_val, b_val in zip(vec_a, vec_b)) and any(b_val > a_val for a_val, b_val in zip(vec_a, vec_b)):
                    dominated = True
                    break

            if not dominated:
                pareto_ids.add(cand_a.candidate_id)

        return pareto_ids

    def rank_interventions(
        self,
        candidates: List[InterventionCandidate],
        communities: List[Community],
        facilities: List[HealthFacility],
        weights: Optional[MultiObjectiveWeights] = None,
        threshold_seconds: float = 1800.0,
    ) -> List[RankedIntervention]:
        """
        Counterfactually evaluates and ranks intervention proposals deterministically.
        Computes Pareto optimality and applies operational tiebreakers.
        """
        if not candidates:
            return []

        w = weights or MultiObjectiveWeights.life_safety()
        baseline_access = compute_accessibility(
            self.network_engine,
            communities,
            facilities,
            threshold_seconds=threshold_seconds,
        )

        max_metric = max(
            (c.estimated_cost if c.estimated_cost > 0 else (c.total_length_m if c.total_length_m > 0 else c.difficulty_score) for c in candidates),
            default=1.0,
        )
        if max_metric <= 0.0:
            max_metric = 1.0

        scored_items: List[Tuple[InterventionCandidate, MultiObjectiveScoreBreakdown]] = []
        for cand in candidates:
            bd = self.evaluate_candidate(
                candidate=cand,
                baseline_access=baseline_access,
                communities=communities,
                facilities=facilities,
                weights=w,
                max_cost_or_length=max_metric,
                threshold_seconds=threshold_seconds,
            )
            scored_items.append((cand, bd))

        # Determine Pareto optimal front
        pareto_front_ids = self.identify_pareto_front(scored_items)
        for cand, bd in scored_items:
            if cand.candidate_id in pareto_front_ids:
                bd.pareto_optimal = True

        # Sort candidates deterministically: score DESC, penalty metric ASC, candidate_id ASC
        scored_items.sort(
            key=lambda item: (-item[1].score, item[0].estimated_cost or item[0].total_length_m or item[0].difficulty_score, item[0].candidate_id)
        )

        if len(scored_items) >= 2:
            top_score = scored_items[0][1].score
            second_score = scored_items[1][1].score
            if abs(top_score - second_score) < 0.05:
                metric_0 = scored_items[0][0].estimated_cost or scored_items[0][0].total_length_m
                metric_1 = scored_items[1][0].estimated_cost or scored_items[1][0].total_length_m
                if metric_1 > 0 and metric_1 < metric_0:
                    scored_items[0], scored_items[1] = scored_items[1], scored_items[0]

        ranked: List[RankedIntervention] = []
        for idx, (cand, bd) in enumerate(scored_items):
            ranked.append(
                RankedIntervention(
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
                )
            )

        return ranked
