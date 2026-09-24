"""
Cyclone Twin Ranking & Accessibility Engine
Implements deterministic corridor scoring, population-weighted travel time deltas,
and Section 11/18 tiebreaker and dead-end rules.
"""

from typing import Dict, List, Optional, Set, Tuple
from .models import (
    Weights,
    Community,
    HealthFacility,
    Corridor,
    ScoreBreakdown,
    RankedCorridor,
    AccessibilityResult,
)
from .network_engine import NetworkEngine


def compute_accessibility(
    engine: NetworkEngine,
    communities: List[Community],
    facilities: List[HealthFacility],
    threshold_seconds: float = 1800.0,
) -> AccessibilityResult:
    """
    Computes deterministic accessibility status across all communities and health facilities.
    Section 16: Only powered hospitals participate as active destinations.
    If no active hospitals, return all-isolated accessibility state.
    Section 10: Multi-source Dijkstra on reversed graph.
    """
    total_population = sum(c.population for c in communities)

    # Filter active (powered) health facilities
    active_facilities = [f for f in facilities if f.power_status and f.node_id is not None]
    active_facility_nodes = [str(f.node_id) for f in active_facilities if str(f.node_id) in engine.graph]

    # If no powered/active hospitals in the graph, all facilities and communities are isolated
    if not active_facility_nodes:
        return AccessibilityResult(
            accessible_population=0,
            isolated_facilities=[f.id for f in facilities],
            isolated_communities=[c.id for c in communities],
            facility_travel_times={},
            community_travel_times={},
            active_hospital_count=0,
        )

    # Collect community nodes
    community_nodes = [str(c.node_id) for c in communities if c.node_id is not None]

    # Run multi-source Dijkstra on reversed graph
    node_travel_times = engine.community_to_hospital_times(
        community_nodes=community_nodes,
        active_hospital_nodes=active_facility_nodes,
        cutoff=threshold_seconds,
    )

    # Classify communities
    accessible_pop = 0
    isolated_comm_ids: List[str] = []
    comm_times: Dict[str, float] = {}

    for comm in communities:
        if comm.node_id is None:
            isolated_comm_ids.append(comm.id)
            continue

        c_node = str(comm.node_id)
        t = node_travel_times.get(c_node)

        if t is not None and t <= threshold_seconds:
            accessible_pop += comm.population
            comm_times[comm.id] = round(t, 2)
        else:
            isolated_comm_ids.append(comm.id)

    # Determine isolated health facilities:
    # A facility is isolated if its node has no active incoming/outgoing edges or
    # cannot reach/be reached by any community
    isolated_fac_ids: List[str] = []
    facility_times: Dict[str, float] = {}

    for fac in facilities:
        if not fac.power_status or fac.node_id is None:
            isolated_fac_ids.append(fac.id)
            continue

        f_node = str(fac.node_id)
        if f_node not in engine.graph:
            isolated_fac_ids.append(fac.id)
            continue

        # Check if any community reached this facility or if it has any active adjacent edge
        has_active_edges = False
        for succ in engine.graph.successors(f_node):
            if engine._active_weight(f_node, succ) is not None:
                has_active_edges = True
                break
        if not has_active_edges:
            for pred in engine.graph.predecessors(f_node):
                if engine._active_weight(pred, f_node) is not None:
                    has_active_edges = True
                    break

        if not has_active_edges:
            isolated_fac_ids.append(fac.id)
        else:
            facility_times[fac.id] = 0.0

    return AccessibilityResult(
        accessible_population=accessible_pop,
        isolated_facilities=sorted(isolated_fac_ids),
        isolated_communities=sorted(isolated_comm_ids),
        facility_travel_times=facility_times,
        community_travel_times=comm_times,
        active_hospital_count=len(active_facility_nodes),
    )


def _delta_T(
    baseline_times: Dict[str, float],
    candidate_times: Dict[str, float],
    communities: List[Community],
    threshold_seconds: float = 1800.0,
) -> Tuple[float, float]:
    """
    Calculates population-weighted travel-time improvement (Section 11).
    Considers ONLY communities reachable both before and after corridor restoration.
    Clamped to [0, 1].
    Returns (delta_t, total_minutes_saved).
    """
    comm_map = {c.id: c for c in communities}
    sum_pop_reduction = 0.0
    sum_pop_baseline = 0.0
    total_time_saved_sec = 0.0

    for c_id, t_before in baseline_times.items():
        if t_before > threshold_seconds:
            continue

        t_after = candidate_times.get(c_id)
        if t_after is None or t_after > threshold_seconds:
            continue

        c = comm_map.get(c_id)
        if not c:
            continue

        diff_sec = max(0.0, t_before - t_after)
        if diff_sec > 0:
            sum_pop_reduction += c.population * (diff_sec / t_before)
            total_time_saved_sec += diff_sec
        sum_pop_baseline += c.population

    if sum_pop_baseline <= 0.0:
        return 0.0, 0.0

    delta_t = min(1.0, max(0.0, sum_pop_reduction / sum_pop_baseline))
    minutes_saved = round(total_time_saved_sec / 60.0, 1)
    return delta_t, minutes_saved


class RankingEngine:
    """
    Deterministic scoring and ranking engine for infrastructure restoration corridors.
    Locked formula:
    S(c) = w_h * ΔH + w_p * ΔP + w_t * ΔT - w_d * ΔD
    """

    def __init__(self, engine: NetworkEngine):
        self.engine = engine

    def score_corridor(
        self,
        corridor: Corridor,
        baseline_access: AccessibilityResult,
        communities: List[Community],
        facilities: List[HealthFacility],
        weights: Weights,
        max_corridor_length: float,
        threshold_seconds: float = 1800.0,
    ) -> ScoreBreakdown:
        """
        Calculates normalized deltas and score for a single corridor.
        """
        # Temporarily restore candidate corridor's physical segments
        self.engine.restore_segments(corridor.physical_segment_ids)

        try:
            cand_access = compute_accessibility(
                self.engine,
                communities,
                facilities,
                threshold_seconds=threshold_seconds,
            )
        finally:
            # Re-disable segments immediately to preserve network state
            self.engine.disable_segments(corridor.physical_segment_ids, validate=False)

        # Baseline metrics
        total_pop = sum(c.population for c in communities)
        baseline_isolated_fac_count = len(baseline_access.isolated_facilities)
        baseline_isolated_pop = total_pop - baseline_access.accessible_population

        cand_isolated_fac_count = len(cand_access.isolated_facilities)
        cand_accessible_pop = cand_access.accessible_population

        # 1. Delta H (Hospitals recovered)
        hospitals_recovered = max(0, baseline_isolated_fac_count - cand_isolated_fac_count)
        if baseline_isolated_fac_count > 0:
            delta_h = min(1.0, max(0.0, hospitals_recovered / baseline_isolated_fac_count))
        else:
            delta_h = 0.0

        # 2. Delta P (Population recovered)
        population_recovered = max(0, cand_accessible_pop - baseline_access.accessible_population)
        if baseline_isolated_pop > 0:
            delta_p = min(1.0, max(0.0, population_recovered / baseline_isolated_pop))
        else:
            delta_p = 0.0

        # 3. Delta T (Population-weighted travel-time improvement)
        delta_t, minutes_saved = _delta_T(
            baseline_access.community_travel_times,
            cand_access.community_travel_times,
            communities,
            threshold_seconds=threshold_seconds,
        )

        # 4. Delta D (Corridor length / difficulty penalty)
        if max_corridor_length > 0:
            delta_d = min(1.0, max(0.0, corridor.total_length_m / max_corridor_length))
        else:
            delta_d = 0.0

        # Dead-end & combined intervention check (Section 11 & Section 18)
        # If all positive deltas are zero, restoring this corridor does not improve connectivity on its own
        combined_req = (delta_h == 0.0 and delta_p == 0.0 and delta_t == 0.0)

        # Locked formula
        score = (
            weights.w_h * delta_h
            + weights.w_p * delta_p
            + weights.w_t * delta_t
            - weights.w_d * delta_d
        )

        return ScoreBreakdown(
            delta_h=round(delta_h, 4),
            delta_p=round(delta_p, 4),
            delta_t=round(delta_t, 4),
            delta_d=round(delta_d, 4),
            score=round(score, 4),
            combined_intervention_required=combined_req,
            hospitals_recovered=hospitals_recovered,
            population_recovered=population_recovered,
            time_saved_minutes=minutes_saved,
        )

    def rank_corridors(
        self,
        corridors: List[Corridor],
        communities: List[Community],
        facilities: List[HealthFacility],
        weights: Optional[Weights] = None,
        threshold_seconds: float = 1800.0,
    ) -> List[RankedCorridor]:
        """
        Ranks all candidate restoration corridors deterministically.
        Applies length tiebreaker when top scores differ by < 0.05 (Section 18).
        """
        if not corridors:
            return []

        w = weights or Weights.life_safety()
        baseline_access = compute_accessibility(
            self.engine,
            communities,
            facilities,
            threshold_seconds=threshold_seconds,
        )

        max_len = max((c.total_length_m for c in corridors), default=1.0)
        if max_len <= 0.0:
            max_len = 1.0

        scored_candidates: List[Tuple[Corridor, ScoreBreakdown]] = []
        for corr in corridors:
            breakdown = self.score_corridor(
                corr,
                baseline_access=baseline_access,
                communities=communities,
                facilities=facilities,
                weights=w,
                max_corridor_length=max_len,
                threshold_seconds=threshold_seconds,
            )
            scored_candidates.append((corr, breakdown))

        # Deterministic primary sort: score descending, then corridor_id ascending
        scored_candidates.sort(
            key=lambda item: (-item[1].score, item[0].corridor_id)
        )

        # Operational Realism Tiebreaker (Section 18):
        # If abs(top_score - second_score) < 0.05, sort by total_length_m ascending
        if len(scored_candidates) >= 2:
            top_score = scored_candidates[0][1].score
            second_score = scored_candidates[1][1].score
            if abs(top_score - second_score) < 0.05:
                # Re-sort the close candidates by total_length_m ascending
                if scored_candidates[1][0].total_length_m < scored_candidates[0][0].total_length_m:
                    scored_candidates[0], scored_candidates[1] = (
                        scored_candidates[1],
                        scored_candidates[0],
                    )

        # Build final ranked list
        ranked: List[RankedCorridor] = []
        for idx, (corr, bd) in enumerate(scored_candidates):
            ranked.append(
                RankedCorridor(
                    corridor_id=corr.corridor_id,
                    rank=idx + 1,
                    score=bd.score,
                    score_breakdown=bd,
                    total_length_m=corr.total_length_m,
                    road_classes=corr.road_classes,
                    physical_segment_ids=corr.physical_segment_ids,
                    geometry=corr.geometry,
                )
            )

        return ranked
