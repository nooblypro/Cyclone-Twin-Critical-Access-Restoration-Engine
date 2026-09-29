"""
Phase D Tests: Capacity-Aware Travel Time & Congestion Modeling (BPR Model)
Verifies:
1. BPR construction & parameter validation
2. v=0 -> t=t0
3. v=C -> t=t0 * (1 + alpha)
4. v>C -> t > t0 * (1 + alpha)
5. Mathematical monotonicity (v1 < v2 => t(v1) <= t(v2))
6. Custom alpha / beta configuration
7. Missing capacity handling & hierarchy fallback
8. Missing volume handling
9. Deterministic output
10. Static model compatibility & zero regression on baseline metrics
11. Routing with BPR on synthetic multi-path graph
12. Flood-disabled edge remains unavailable under BPR
13. OSM-normalized graph compatibility
14. Full simulation regression (Baseline 477k, Michaung 298k/179k, Criticality +0.0724, Recovery +89k)
"""

import pytest
import networkx as nx
from cyclone_twin.providers.travel_time_model import (
    StaticTravelTimeModel,
    BPRCapacityTravelTimeModel,
    derive_capacity,
)
from cyclone_twin.network_engine import NetworkEngine
from cyclone_twin.ranking_engine import RankingEngine, compute_accessibility
from cyclone_twin.data_loader import DataLoader
from cyclone_twin.corridor_engine import CorridorEngine
from cyclone_twin.models import Weights


def test_bpr_construction_and_validation():
    model = BPRCapacityTravelTimeModel(alpha=0.15, beta=4.0)
    assert model.alpha == 0.15
    assert model.beta == 4.0

    with pytest.raises(ValueError):
        BPRCapacityTravelTimeModel(alpha=-0.1, beta=4.0)

    with pytest.raises(ValueError):
        BPRCapacityTravelTimeModel(alpha=0.15, beta=-1.0)


def test_bpr_volume_zero():
    model = BPRCapacityTravelTimeModel(alpha=0.15, beta=4.0)
    # length=1000m, free_flow=36km/h (10m/s) -> t0 = 100s
    t = model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0, capacity=2000.0, volume=0.0)
    assert pytest.approx(t, rel=1e-5) == 100.0


def test_bpr_volume_equals_capacity():
    model = BPRCapacityTravelTimeModel(alpha=0.15, beta=4.0)
    # length=1000m, free_flow=36km/h -> t0 = 100s
    # v = C = 2000 -> v/C = 1.0 -> 1 + 0.15*(1.0^4) = 1.15 -> t = 115.0s
    t = model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0, capacity=2000.0, volume=2000.0)
    assert pytest.approx(t, rel=1e-5) == 115.0


def test_bpr_volume_exceeds_capacity():
    model = BPRCapacityTravelTimeModel(alpha=0.15, beta=4.0)
    # v = 2 * C -> v/C = 2.0 -> 1 + 0.15*(16.0) = 3.4 -> t = 340.0s
    t = model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0, capacity=2000.0, volume=4000.0)
    assert pytest.approx(t, rel=1e-5) == 340.0


def test_bpr_monotonicity():
    model = BPRCapacityTravelTimeModel(alpha=0.15, beta=4.0)
    v_previous = 0.0
    t_previous = model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0, capacity=2000.0, volume=v_previous)

    for v in [500.0, 1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 5000.0]:
        t_current = model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0, capacity=2000.0, volume=v)
        assert t_current >= t_previous, f"Monotonicity violated: t({v})={t_current} < t({v_previous})={t_previous}"
        t_previous = t_current
        v_previous = v


def test_custom_alpha_beta():
    model = BPRCapacityTravelTimeModel(alpha=0.20, beta=2.0)
    # v = C -> 1 + 0.20*(1.0^2) = 1.20 -> t = 120.0s
    t = model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0, capacity=1000.0, volume=1000.0)
    assert pytest.approx(t, rel=1e-5) == 120.0


def test_missing_capacity_hierarchy():
    # Explicit capacity
    assert derive_capacity(capacity_attr=3500.0, highway_attr="primary") == 3500.0
    # Highway classification fallback
    assert derive_capacity(capacity_attr=None, highway_attr="motorway") == 4000.0
    assert derive_capacity(capacity_attr=None, highway_attr="primary") == 2500.0
    assert derive_capacity(capacity_attr=None, highway_attr="secondary") == 1800.0
    assert derive_capacity(capacity_attr=None, highway_attr="tertiary") == 1400.0
    # Default fallback
    assert derive_capacity(capacity_attr=None, highway_attr="residential") == 2000.0
    assert derive_capacity(capacity_attr=None, highway_attr=None) == 2000.0


def test_missing_volume():
    model = BPRCapacityTravelTimeModel()
    t = model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0)
    assert pytest.approx(t, rel=1e-5) == 100.0


def test_deterministic_output():
    model = BPRCapacityTravelTimeModel()
    results = [
        model.compute_travel_time(length_m=1500.0, free_flow_speed_kph=50.0, capacity=2500.0, volume=1200.0)
        for _ in range(10)
    ]
    assert all(r == results[0] for r in results)


def test_static_model_compatibility():
    static_model = StaticTravelTimeModel()
    bpr_model = BPRCapacityTravelTimeModel()

    t_static = static_model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0)
    t_bpr_zero = bpr_model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0, volume=0.0)

    assert t_static == t_bpr_zero == 100.0


def test_routing_with_bpr_synthetic_graph():
    """
    Synthetic graph:
    A -> B -> C (direct route, 1000m)
    A -> D -> C (alternative route, 1200m)
    Low volume: Direct route A->B->C is faster.
    High volume on A->B->C: Alternative route A->D->C becomes faster!
    """
    g = nx.MultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")
    g.add_node("D")

    g.add_edge("A", "B", key=0, length=500.0, speed_kph=36.0, capacity=1000.0, current_volume=0.0, physical_segment_id="seg_ab")
    g.add_edge("B", "C", key=0, length=500.0, speed_kph=36.0, capacity=1000.0, current_volume=0.0, physical_segment_id="seg_bc")

    g.add_edge("A", "D", key=0, length=600.0, speed_kph=36.0, capacity=1000.0, current_volume=0.0, physical_segment_id="seg_ad")
    g.add_edge("D", "C", key=0, length=600.0, speed_kph=36.0, capacity=1000.0, current_volume=0.0, physical_segment_id="seg_dc")

    engine = NetworkEngine(graph=g)
    
    # 1. Static model routing
    engine.set_travel_time_model(StaticTravelTimeModel())
    times_static = engine.community_to_hospital_times(community_nodes=["A"], active_hospital_nodes=["C"])
    assert times_static["A"] == 100.0  # 1000m at 10m/s

    # 2. BPR model with zero volume
    engine.set_travel_time_model(BPRCapacityTravelTimeModel(alpha=0.15, beta=4.0))
    times_bpr_low = engine.community_to_hospital_times(community_nodes=["A"], active_hospital_nodes=["C"])
    assert times_bpr_low["A"] == 100.0

    # 3. BPR model with high volume on direct route (seg_ab & seg_bc volume = 3000, 3x capacity)
    # v/C = 3 -> 1 + 0.15*(81) = 13.15 -> segment time = 50s * 13.15 = 657.5s -> total direct = 1315s
    # Alternative route A->D->C volume = 0 -> time = 60s + 60s = 120s
    g["A"]["B"][0]["current_volume"] = 3000.0
    g["B"]["C"][0]["current_volume"] = 3000.0
    engine.set_graph(g)
    engine.set_travel_time_model(BPRCapacityTravelTimeModel(alpha=0.15, beta=4.0))

    times_bpr_high = engine.community_to_hospital_times(community_nodes=["A"], active_hospital_nodes=["C"])
    assert times_bpr_high["A"] == 120.0  # Routed via A -> D -> C because direct route is heavily congested!


def test_flooded_edge_remains_unavailable_under_bpr():
    g = nx.MultiDiGraph()
    g.add_edge("A", "B", key=0, length=100.0, speed_kph=36.0, capacity=1000.0, current_volume=0.0, physical_segment_id="seg_ab")

    engine = NetworkEngine(graph=g)
    engine.set_travel_time_model(BPRCapacityTravelTimeModel(alpha=0.15, beta=4.0))

    # Before flood: active
    assert engine._active_weight("A", "B") == 10.0

    # Disable segment (flooded)
    engine.disable_segments(["seg_ab"])

    # Under BPR, flooded edge MUST remain disabled (returns None)
    assert engine._active_weight("A", "B") is None
    times = engine.community_to_hospital_times(community_nodes=["A"], active_hospital_nodes=["B"])
    assert "A" not in times


def test_osm_graph_compatibility():
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)

    engine = NetworkEngine(graph=graph)
    engine.set_travel_time_model(BPRCapacityTravelTimeModel(alpha=0.15, beta=4.0))

    access = compute_accessibility(engine, loader.communities, loader.facilities)

    # Baseline network access with BPR at v=0 must match Static (477,000)
    assert access.accessible_population == 477000
    assert len(access.isolated_facilities) == 0


def test_existing_simulation_regression():
    """
    Guarantees strict Phase C baseline & Michaung regression numbers:
    - Baseline: 477,000 accessible
    - Michaung: 298,000 accessible / 179,000 isolated
    - Criticality: +89,000 recovered population (delta_p = 89000 / 179000 = 0.4972)
    - Recovery: +89,000 recovered
    """
    loader = DataLoader()
    graph = loader.load_road_network(attempt_real=False)
    engine = NetworkEngine(graph=graph)

    # Baseline check
    base_access = compute_accessibility(engine, loader.communities, loader.facilities)
    assert base_access.accessible_population == 477000
    assert len(base_access.isolated_facilities) == 0
    assert len(base_access.isolated_communities) == 0

    # Michaung flood check
    flood_geojson = loader.load_flood_polygon(attempt_nrsc=False)
    from cyclone_twin.flood_polygon_fallback import identify_flood_disabled_segments, normalize_polygon_geometry
    from shapely.geometry import shape

    flood_shape = normalize_polygon_geometry(shape(flood_geojson["geometry"]))
    disabled_segs, _ = identify_flood_disabled_segments(graph, flood_shape)
    engine.disable_segments(disabled_segs)

    michaung_access = compute_accessibility(engine, loader.communities, loader.facilities)
    assert michaung_access.accessible_population == 298000
    isolated_pop = 477000 - 298000
    assert isolated_pop == 179000

    # Ranking & restoration check
    corridors = CorridorEngine.cluster_disabled_segments_into_corridors(graph, engine.disabled_segments)
    ranking_engine = RankingEngine(engine)
    ranked = ranking_engine.rank_corridors(corridors, loader.communities, loader.facilities, Weights.life_safety())

    top_corridor = ranked[0]
    assert top_corridor.score_breakdown.population_recovered == 89000
    assert pytest.approx(top_corridor.score_breakdown.delta_p, abs=1e-4) == 89000 / 179000

    # Clear top corridor & check population recovery
    engine.restore_segments(top_corridor.physical_segment_ids)
    restored_access = compute_accessibility(engine, loader.communities, loader.facilities)
    recovered_pop = restored_access.accessible_population - michaung_access.accessible_population
    assert recovered_pop == 89000
