"""
Cyclone Twin Comprehensive Test Suite
Covers the 14 core graph/ranking tests, required tests 15-20,
plus tests for weights, bridge/tunnel rules, API contracts, and Killer Demo comparison.
"""

import pytest
import networkx as nx
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection, LineString, Point
from fastapi.testclient import TestClient

from cyclone_twin.models import (
    Weights,
    Community,
    HealthFacility,
    Corridor,
    ScoreBreakdown,
    RankedCorridor,
    ScenarioManifest,
)
from cyclone_twin.network_engine import NetworkEngine
from cyclone_twin.ranking_engine import RankingEngine, compute_accessibility, _delta_T
from cyclone_twin.corridor_engine import CorridorEngine
from cyclone_twin.flood_polygon_fallback import (
    normalize_polygon_geometry,
    identify_flood_disabled_segments,
    get_michaung_flood_polygon,
)
from cyclone_twin.data_loader import DataLoader
from cyclone_twin.advisory_engine import AdvisoryEngine
from cyclone_twin.main import app


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def toy_graph() -> nx.MultiDiGraph:
    """
    Creates a deterministic toy network:
    Node 1 (Community A, pop 10,000)
    Node 2 (Community B, pop 20,000)
    Node 3 (Junction)
    Node 4 (Hospital H1)
    Node 5 (Hospital H2)
    """
    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:32643"

    nodes = {
        "1": (100.0, 100.0),
        "2": (200.0, 100.0),
        "3": (150.0, 200.0),
        "4": (100.0, 300.0),
        "5": (200.0, 300.0),
    }
    for n, (x, y) in nodes.items():
        G.add_node(n, x=x, y=y, lon=80.20 + x * 0.001, lat=13.00 + y * 0.001)

    edges = [
        # Community 1 -> Junction 3 (two-way)
        ("1", "3", 0, "seg_1_3", 500.0, 50.0),
        ("3", "1", 0, "seg_1_3", 500.0, 50.0),
        # Community 2 -> Junction 3 (two-way)
        ("2", "3", 0, "seg_2_3", 600.0, 60.0),
        ("3", "2", 0, "seg_2_3", 600.0, 60.0),
        # Junction 3 -> Hospital 4 (two-way)
        ("3", "4", 0, "seg_3_4", 400.0, 40.0),
        ("4", "3", 0, "seg_3_4", 400.0, 40.0),
        # Junction 3 -> Hospital 5 (two-way)
        ("3", "5", 0, "seg_3_5", 800.0, 80.0),
        ("5", "3", 0, "seg_3_5", 800.0, 80.0),
    ]

    for u, v, k, seg_id, length, speed in edges:
        travel_time = length / (speed * 1000.0 / 3600.0)
        u_node = G.nodes[u]
        v_node = G.nodes[v]
        geom = LineString([(u_node["x"], u_node["y"]), (v_node["x"], v_node["y"])])
        G.add_edge(
            u, v, key=k,
            physical_segment_id=seg_id,
            length=length,
            speed_kph=speed,
            travel_time=travel_time,
            bridge="no",
            tunnel="no",
            layer=0,
            geometry=geom,
        )

    return G


@pytest.fixture
def toy_entities():
    communities = [
        Community(id="COMM_A", name="Community A", population=10000, node_id="1"),
        Community(id="COMM_B", name="Community B", population=20000, node_id="2"),
    ]
    facilities = [
        HealthFacility(id="HOSP_1", name="Hospital 1", beds=100, node_id="4", power_status=True),
        HealthFacility(id="HOSP_2", name="Hospital 2", beds=50, node_id="5", power_status=True),
    ]
    return communities, facilities


# -----------------------------------------------------------------------------
# Core 14 Toy-Graph Tests
# -----------------------------------------------------------------------------

def test_01_baseline_accessibility(toy_graph, toy_entities):
    """TEST 01: All communities reach hospitals on intact baseline graph."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    res = compute_accessibility(engine, comms, facs)
    assert res.accessible_population == 30000
    assert len(res.isolated_communities) == 0
    assert len(res.isolated_facilities) == 0


def test_02_network_disruption_single_edge(toy_graph, toy_entities):
    """TEST 02: Disabling an edge to Community A isolates Community A."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    engine.disable_segments(["seg_1_3"])
    res = compute_accessibility(engine, comms, facs)
    assert res.accessible_population == 20000
    assert "COMM_A" in res.isolated_communities
    assert "COMM_B" not in res.isolated_communities


def test_03_multiple_edge_failures_isolate_both(toy_graph, toy_entities):
    """TEST 03: Disabling access to all hospitals isolates all communities."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    engine.disable_segments(["seg_3_4", "seg_3_5"])
    res = compute_accessibility(engine, comms, facs)
    assert res.accessible_population == 0
    assert len(res.isolated_communities) == 2


def test_04_hospital_isolation_detection(toy_graph, toy_entities):
    """TEST 04: Hospital with all adjacent segments disabled is marked isolated."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    engine.disable_segments(["seg_3_4"])
    res = compute_accessibility(engine, comms, facs)
    assert "HOSP_1" in res.isolated_facilities
    assert "HOSP_2" not in res.isolated_facilities


def test_05_recompute_times_after_restoration(toy_graph, toy_entities):
    """TEST 05: Re-enabling segments restores travel times deterministically."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    engine.disable_segments(["seg_1_3"])
    assert compute_accessibility(engine, comms, facs).accessible_population == 20000

    engine.restore_segments(["seg_1_3"])
    assert compute_accessibility(engine, comms, facs).accessible_population == 30000


def test_06_delta_h_calculation(toy_graph, toy_entities):
    """TEST 06: Recovering an isolated hospital yields positive Delta H."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    engine.disable_segments(["seg_3_4"])  # HOSP_1 isolated

    ranking = RankingEngine(engine)
    corr = Corridor(
        corridor_id="corr_h1",
        physical_segment_ids=["seg_3_4"],
        total_length_m=400.0,
    )
    breakdown = ranking.score_corridor(
        corridor=corr,
        baseline_access=compute_accessibility(engine, comms, facs),
        communities=comms,
        facilities=facs,
        weights=Weights.life_safety(),
        max_corridor_length=400.0,
    )
    assert breakdown.hospitals_recovered == 1
    assert breakdown.delta_h == 1.0


def test_07_delta_p_calculation(toy_graph, toy_entities):
    """TEST 07: Recovering an isolated community yields positive Delta P."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    engine.disable_segments(["seg_1_3"])  # COMM_A (10,000) isolated

    ranking = RankingEngine(engine)
    corr = Corridor(
        corridor_id="corr_c1",
        physical_segment_ids=["seg_1_3"],
        total_length_m=500.0,
    )
    breakdown = ranking.score_corridor(
        corridor=corr,
        baseline_access=compute_accessibility(engine, comms, facs),
        communities=comms,
        facilities=facs,
        weights=Weights.life_safety(),
        max_corridor_length=500.0,
    )
    assert breakdown.population_recovered == 10000
    assert breakdown.delta_p == 1.0


def test_08_delta_t_calculation(toy_graph, toy_entities):
    """TEST 08: Population-weighted travel time improvement (Delta T) is calculated and bounded."""
    comms, _ = toy_entities
    baseline_times = {"COMM_A": 200.0, "COMM_B": 300.0}
    candidate_times = {"COMM_A": 100.0, "COMM_B": 150.0}
    delta_t, min_saved = _delta_T(baseline_times, candidate_times, comms)
    assert 0.0 < delta_t <= 1.0
    assert min_saved > 0.0


def test_09_delta_d_penalty(toy_graph, toy_entities):
    """TEST 09: Longer corridor incurs higher Delta D penalty."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    ranking = RankingEngine(engine)

    corr_short = Corridor(corridor_id="c_short", physical_segment_ids=["seg_1_3"], total_length_m=100.0)
    corr_long = Corridor(corridor_id="c_long", physical_segment_ids=["seg_2_3"], total_length_m=1000.0)

    base = compute_accessibility(engine, comms, facs)
    b_short = ranking.score_corridor(corr_short, base, comms, facs, Weights.life_safety(), 1000.0)
    b_long = ranking.score_corridor(corr_long, base, comms, facs, Weights.life_safety(), 1000.0)

    assert b_short.delta_d < b_long.delta_d
    assert b_long.delta_d == 1.0


def test_10_score_corridor_formula(toy_graph, toy_entities):
    """TEST 10: S(c) matches w_h*ΔH + w_p*ΔP + w_t*ΔT - w_d*ΔD."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    engine.disable_segments(["seg_1_3", "seg_3_4"])
    ranking = RankingEngine(engine)

    w = Weights(w_h=0.40, w_p=0.30, w_t=0.20, w_d=0.10)
    corr = Corridor(corridor_id="corr_test", physical_segment_ids=["seg_1_3"], total_length_m=500.0)
    base = compute_accessibility(engine, comms, facs)
    bd = ranking.score_corridor(corr, base, comms, facs, w, 1000.0)

    expected = round(w.w_h * bd.delta_h + w.w_p * bd.delta_p + w.w_t * bd.delta_t - w.w_d * bd.delta_d, 4)
    assert bd.score == expected


def test_11_deterministic_ranking(toy_graph, toy_entities):
    """TEST 11: Corridors are ranked score descending, with deterministic output."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    engine.disable_segments(["seg_1_3", "seg_2_3", "seg_3_4"])
    ranking = RankingEngine(engine)

    c1 = Corridor(corridor_id="c1", physical_segment_ids=["seg_1_3"], total_length_m=500.0)
    c2 = Corridor(corridor_id="c2", physical_segment_ids=["seg_2_3"], total_length_m=600.0)
    c3 = Corridor(corridor_id="c3", physical_segment_ids=["seg_3_4"], total_length_m=400.0)

    r1 = ranking.rank_corridors([c1, c2, c3], comms, facs)
    r2 = ranking.rank_corridors([c3, c1, c2], comms, facs)

    # Identical deterministic ordering regardless of input list permutation
    assert [rc.corridor_id for rc in r1] == [rc.corridor_id for rc in r2]
    assert r1[0].rank == 1
    assert r1[0].score >= r1[1].score >= r1[2].score


def test_12_weights_validation():
    """TEST 12: Weights must sum to 1.0 and be non-negative."""
    w = Weights.life_safety()
    assert abs((w.w_h + w.w_p + w.w_t + w.w_d) - 1.0) < 1e-4

    with pytest.raises(ValueError):
        Weights(w_h=0.5, w_p=0.5, w_t=0.5, w_d=0.5)

    with pytest.raises(ValueError):
        Weights(w_h=-0.1, w_p=0.5, w_t=0.3, w_d=0.3)


def test_13_power_status_filtering(toy_graph, toy_entities):
    """TEST 13: Hospitals without power are excluded as destinations."""
    comms, facs = toy_entities
    facs[0].power_status = False
    facs[1].power_status = False

    engine = NetworkEngine(toy_graph)
    res = compute_accessibility(engine, comms, facs)
    # With no powered hospitals, all communities are isolated
    assert res.accessible_population == 0
    assert len(res.isolated_facilities) == 2


def test_14_dead_end_detection(toy_graph, toy_entities):
    """TEST 14: Restoring a disconnected dead-end flags combined_intervention_required."""
    comms, facs = toy_entities
    # Disconnect junction from hospitals completely
    engine = NetworkEngine(toy_graph)
    engine.disable_segments(["seg_3_4", "seg_3_5", "seg_1_3"])

    ranking = RankingEngine(engine)
    # Restoring seg_1_3 only leads to junction 3 which still cannot reach any hospital
    corr = Corridor(corridor_id="corr_deadend", physical_segment_ids=["seg_1_3"], total_length_m=500.0)
    base = compute_accessibility(engine, comms, facs)
    bd = ranking.score_corridor(corr, base, comms, facs, Weights.life_safety(), 500.0)

    assert bd.combined_intervention_required is True
    assert bd.delta_h == 0.0
    assert bd.delta_p == 0.0


# -----------------------------------------------------------------------------
# Explicitly Mandated Tests 15 - 20
# -----------------------------------------------------------------------------

def test_15_invalid_segment_id_raises_assertion_error(toy_graph):
    """TEST 15: Invalid segment ID raises AssertionError."""
    engine = NetworkEngine(toy_graph)
    with pytest.raises(AssertionError) as exc_info:
        engine.disable_segments(["non_existent_segment_xyz"], validate=True)
    assert "Invalid segment ID" in str(exc_info.value)


def test_16_parallel_multidigraph_edges_select_fastest_active(toy_graph):
    """TEST 16: Parallel MultiDiGraph edges select fastest active edge."""
    # Add parallel edge between 1 and 3 with different speeds/travel times
    toy_graph.add_edge(
        "1", "3", key=1,
        physical_segment_id="seg_1_3_express",
        length=500.0,
        travel_time=15.0,  # 15s express vs 36s normal
    )
    engine = NetworkEngine(toy_graph)

    # Both active: selects express (15.0)
    w_both = engine._active_weight("1", "3")
    assert w_both == 15.0

    # Disable express: selects normal
    engine.disable_segments(["seg_1_3_express"])
    w_normal = engine._active_weight("1", "3")
    assert w_normal == pytest.approx(36.0, 0.5)

    # Disable both: returns None
    engine.disable_segments(["seg_1_3"])
    w_none = engine._active_weight("1", "3")
    assert w_none is None


def test_17_make_valid_geometrycollection_retains_polygons():
    """TEST 17: make_valid() GeometryCollection normalization retains polygonal components."""
    # Create a GeometryCollection containing a Polygon, LineString, and Point
    p1 = Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)])
    line = LineString([(3, 3), (4, 4)])
    pt = Point(5, 5)
    gc = GeometryCollection([p1, line, pt])

    normalized = normalize_polygon_geometry(gc)
    assert isinstance(normalized, (Polygon, MultiPolygon))
    assert normalized.area == pytest.approx(4.0, 1e-4)


def test_18_empty_hospital_sources_returns_empty_dict(toy_graph):
    """TEST 18: Empty hospital sources return {}."""
    engine = NetworkEngine(toy_graph)
    # Empty hospital nodes list
    res = engine.community_to_hospital_times(community_nodes=["1", "2"], active_hospital_nodes=[])
    assert res == {}

    # Empty community nodes list
    res2 = engine.community_to_hospital_times(community_nodes=[], active_hospital_nodes=["4"])
    assert res2 == {}


def test_19_projected_snapping_distance_validation():
    """TEST 19: Projected snapping distance validation (> 200m records warning)."""
    loader = DataLoader(snap_threshold_m=200.0)
    loader.load_road_network(attempt_real=False)

    # Point far outside Chennai (e.g., Delhi coordinates)
    far_lon, far_lat = 77.2090, 28.6139
    node_id, dist = loader.snap_point_to_nearest_node(far_lon, far_lat, "FAR_AWAY_ENTITY")

    assert dist > 200.0
    assert any("FAR_AWAY_ENTITY" in w and "exceeds 200.0m limit" in w for w in loader.snap_warnings)


def test_20_missing_edge_geometry_reconstructed_from_nodes():
    """TEST 20: Missing edge geometry is reconstructed from node coordinates."""
    G = nx.MultiDiGraph()
    G.add_node("A", x=100.0, y=200.0)
    G.add_node("B", x=300.0, y=400.0)
    # Add edge WITHOUT geometry
    G.add_edge("A", "B", key=0, length=282.8, travel_time=20.0, physical_segment_id="seg_ab")

    engine = NetworkEngine()
    engine.set_graph(G)

    edge_data = engine.graph["A"]["B"][0]
    assert "geometry" in edge_data
    assert isinstance(edge_data["geometry"], LineString)
    coords = list(edge_data["geometry"].coords)
    assert coords == [(100.0, 200.0), (300.0, 400.0)]


# -----------------------------------------------------------------------------
# Additional Required Architecture Tests
# -----------------------------------------------------------------------------

def test_21_bridge_and_tunnel_preservation(toy_graph):
    """TEST 21: Bridges preserved, tunnels disabled under flood intersection."""
    # Create flood polygon overlapping all nodes in toy_graph
    flood_poly = Polygon([(0, 0), (500, 0), (500, 500), (0, 500), (0, 0)])

    # Mark seg_1_3 as elevated bridge (both directions)
    toy_graph["1"]["3"][0]["bridge"] = "yes"
    toy_graph["1"]["3"][0]["layer"] = 1
    toy_graph["3"]["1"][0]["bridge"] = "yes"
    toy_graph["3"]["1"][0]["layer"] = 1

    # Mark seg_2_3 as tunnel (both directions)
    toy_graph["2"]["3"][0]["tunnel"] = "yes"
    toy_graph["2"]["3"][0]["layer"] = -1
    toy_graph["3"]["2"][0]["tunnel"] = "yes"
    toy_graph["3"]["2"][0]["layer"] = -1

    disabled_segs, _ = identify_flood_disabled_segments(toy_graph, flood_poly)

    # Bridge seg_1_3 must NOT be disabled
    assert "seg_1_3" not in disabled_segs
    # Tunnel seg_2_3 MUST be disabled
    assert "seg_2_3" in disabled_segs


def test_22_corridor_clustering():
    """TEST 22: Contiguous disabled segments cluster into connected components."""
    G = nx.MultiDiGraph()
    # Path: A - B - C (connected), and isolated segment D - E
    G.add_node("A", x=0, y=0)
    G.add_node("B", x=1, y=0)
    G.add_node("C", x=2, y=0)
    G.add_node("D", x=10, y=10)
    G.add_node("E", x=11, y=10)

    G.add_edge("A", "B", key=0, physical_segment_id="seg_ab", length=100.0, highway="primary")
    G.add_edge("B", "C", key=0, physical_segment_id="seg_bc", length=100.0, highway="primary")
    G.add_edge("D", "E", key=0, physical_segment_id="seg_de", length=150.0, highway="secondary")

    engine = NetworkEngine(G)
    engine.disable_segments(["seg_ab", "seg_bc", "seg_de"])

    corridors = CorridorEngine.cluster_disabled_segments_into_corridors(
        engine.graph, engine.disabled_segments
    )

    assert len(corridors) == 2
    # One corridor has 2 segments (ab + bc), other has 1 segment (de)
    lengths = {len(c.physical_segment_ids) for c in corridors}
    assert lengths == {1, 2}


def test_23_tiebreaker_close_scores(toy_graph, toy_entities):
    """TEST 23: Section 18 length tiebreaker when top scores differ by < 0.05."""
    comms, facs = toy_entities
    engine = NetworkEngine(toy_graph)
    ranking = RankingEngine(engine)

    # Two corridors with identical recovery impact but different lengths
    c_long = Corridor(corridor_id="c_long", physical_segment_ids=["seg_1_3"], total_length_m=500.0)
    c_short = Corridor(corridor_id="c_short", physical_segment_ids=["seg_2_3"], total_length_m=100.0)

    # Rank with low w_d so scores are very close (< 0.05)
    w = Weights(w_h=0.45, w_p=0.35, w_t=0.19, w_d=0.01)
    ranked = ranking.rank_corridors([c_long, c_short], comms, facs, weights=w)

    assert len(ranked) == 2
    # Shorter corridor wins tiebreaker
    assert ranked[0].corridor_id == "c_short"
    assert ranked[0].rank == 1


def test_24_advisory_deterministic_fallback():
    """TEST 24: Advisory text <= 220 chars and validates fallback."""
    advisor = AdvisoryEngine(api_key=None)  # Forces fallback
    bd = ScoreBreakdown(
        delta_h=0.5,
        delta_p=0.8,
        delta_t=0.2,
        delta_d=0.1,
        score=0.45,
        hospitals_recovered=1,
        population_recovered=18000,
        time_saved_minutes=22.0,
    )
    res = advisor.generate_advisory("corridor_test", bd)
    assert res.validated is True
    assert res.fallback is True
    assert len(res.advisory_text) <= 220
    assert "corridor_test" in res.source_corridor_id


def test_25_scenario_manifest():
    """TEST 25: ScenarioManifest exports complete provenance and CRS."""
    loader = DataLoader()
    loader.load_road_network(attempt_real=False)
    loader.load_flood_polygon()
    manifest = loader.get_manifest(total_disabled_edges=12, total_corridors=3)

    assert manifest.graph_crs == "EPSG:32643"
    assert manifest.graph_source == "mock_fallback"
    assert manifest.flood_source in ("nrsc", "mock")
    assert manifest.threshold_seconds == 1800.0
    assert manifest.total_corridors == 3


def test_26_api_contracts():
    """TEST 26: Full REST API contracts comply exactly with Section 19."""
    client = TestClient(app)

    # 1. POST /network/load
    r_load = client.post("/network/load", json={})
    assert r_load.status_code == 200
    d_load = r_load.json()
    assert "nodes" in d_load and "edges" in d_load
    assert d_load["graph_source"] in ("osmnx_live", "mock_fallback")

    # 2. POST /flood/apply
    r_flood = client.post("/flood/apply", json={})
    assert r_flood.status_code == 200
    d_flood = r_flood.json()
    assert "disabled_edges" in d_flood
    assert "corridors" in d_flood
    assert d_flood["flood_source"] in ("nrsc", "manual_digitized", "mock")

    # 3. GET /accessibility/status
    r_access = client.get("/accessibility/status")
    assert r_access.status_code == 200
    d_access = r_access.json()
    assert "accessible_population" in d_access
    assert "isolated_facilities" in d_access
    assert "isolated_communities" in d_access

    # 4. POST /interventions/rank
    r_rank = client.post("/interventions/rank", json={"weights": {"w_h": 0.4, "w_p": 0.3, "w_t": 0.2, "w_d": 0.1}})
    assert r_rank.status_code == 200
    d_rank = r_rank.json()
    assert "ranked_corridors" in d_rank
    assert "manifest" in d_rank

    # 5. POST /interventions/clear
    top_corr = d_rank["ranked_corridors"][0]["corridor_id"]
    r_clear = client.post("/interventions/clear", json={"corridor_id": top_corr})
    assert r_clear.status_code == 200
    d_clear = r_clear.json()
    assert d_clear["corridor_id"] == top_corr
    assert "new_graph_state" in d_clear

    # 6. POST /advisory/generate
    bd = d_rank["ranked_corridors"][0]["score_breakdown"]
    r_adv = client.post("/advisory/generate", json={"corridor_id": top_corr, "score_breakdown": bd})
    assert r_adv.status_code == 200
    d_adv = r_adv.json()
    assert len(d_adv["advisory_text"]) <= 220
    assert d_adv["validated"] is True


def test_27_killer_demo_comparison():
    """
    TEST 27: Killer Demo Comparison.
    Demonstrates that two flooded corridors can produce radically different network consequences.
    Calculated strictly from graph engine, never hardcoded.
    """
    client = TestClient(app)
    client.post("/network/load", json={})
    client.post("/flood/apply", json={})
    r_rank = client.post("/interventions/rank", json={})
    ranked = r_rank.json()["ranked_corridors"]

    assert len(ranked) >= 2
    top = ranked[0]
    bottom = ranked[-1]

    # Top corridor has significantly higher network criticality than bottom
    assert top["score"] > bottom["score"]
    # The top corridor recovers more population or hospitals than bottom
    top_bd = top["score_breakdown"]
    bottom_bd = bottom["score_breakdown"]

    assert (top_bd["population_recovered"] > bottom_bd["population_recovered"]) or \
           (top_bd["hospitals_recovered"] > bottom_bd["hospitals_recovered"]) or \
           (top_bd["delta_t"] >= bottom_bd["delta_t"])
