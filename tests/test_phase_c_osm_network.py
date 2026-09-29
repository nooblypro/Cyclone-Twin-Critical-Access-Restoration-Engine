"""
Phase C Test Suite — OSMnx Dynamic Road Network Ingestion & Graph Normalization
Validates OSMNetworkProvider construction, synthetic/raw graph normalization, directed topology,
attribute preservation, coordinate-to-node mapping, failure fallback, and baseline regression.
"""

import pytest
import networkx as nx
from shapely.geometry import LineString
from fastapi.testclient import TestClient

from cyclone_twin.main import app
from cyclone_twin.providers import (
    OSMNetworkProvider,
    CalibratedNetworkProvider,
    DEFAULT_OSM_BBOX,
)
from cyclone_twin.providers.network_provider import (
    normalize_osm_graph,
    map_entity_to_nearest_node,
    parse_speed_kph,
)
from cyclone_twin.network_engine import NetworkEngine
from cyclone_twin.flood_polygon_fallback import identify_flood_disabled_segments
from shapely.geometry import Polygon

client = TestClient(app)


def test_osm_provider_construction():
    """TEST A: OSMNetworkProvider instantiates with custom and default bounding boxes."""
    provider_default = OSMNetworkProvider()
    assert provider_default.bbox == DEFAULT_OSM_BBOX
    assert provider_default.request_timeout == 4.0

    custom_bbox = (80.20, 13.00, 80.25, 13.05)
    provider_custom = OSMNetworkProvider(bbox=custom_bbox, request_timeout=2.0)
    assert provider_custom.bbox == custom_bbox
    assert provider_custom.request_timeout == 2.0


def test_synthetic_graph_normalization():
    """TEST B & D: Synthetic MultiDiGraph normalizes attributes (length, speed, travel_time, bridge, tunnel)."""
    raw_g = nx.MultiDiGraph()
    raw_g.add_node(101, x=80.21, y=13.01, elevation=3.5)
    raw_g.add_node(102, x=80.23, y=13.02, elevation=2.0)

    raw_g.add_edge(
        101, 102, key=0,
        length=1000.0,
        highway="primary",
        maxspeed="50",
        bridge="yes",
        name="Mount Road",
    )

    norm_g = normalize_osm_graph(raw_g)
    assert norm_g.number_of_nodes() == 2
    assert norm_g.number_of_edges() == 1

    # Check node normalization
    assert "101" in norm_g.nodes
    assert norm_g.nodes["101"]["lon"] == 80.21

    # Check edge normalization
    edge = norm_g["101"]["102"][0]
    assert edge["length"] == 1000.0
    assert edge["speed_kph"] == 50.0
    assert abs(edge["travel_time"] - (1000.0 / (50.0 * 1000 / 3600))) < 1e-3
    assert edge["bridge"] == "yes"
    assert edge["tunnel"] == "no"
    assert edge["name"] == "Mount Road"
    assert isinstance(edge["geometry"], LineString)


def test_directionality_preservation():
    """TEST C: One-way directed edges remain single directed edges in normalized graph."""
    raw_g = nx.MultiDiGraph()
    raw_g.add_node("A", x=80.20, y=13.00)
    raw_g.add_node("B", x=80.21, y=13.00)

    # One-way edge from A to B
    raw_g.add_edge("A", "B", key=0, length=500.0, highway="secondary", oneway=True)

    norm_g = normalize_osm_graph(raw_g)
    assert norm_g.has_edge("A", "B")
    assert not norm_g.has_edge("B", "A")


def test_missing_attributes_handled_with_defaults():
    """TEST E: Missing maxspeed, lanes, geometry do not crash normalization."""
    raw_g = nx.MultiDiGraph()
    raw_g.add_node(1, x=80.20, y=13.00)
    raw_g.add_node(2, x=80.21, y=13.00)

    # Edge with minimal attributes
    raw_g.add_edge(1, 2, key=0)

    norm_g = normalize_osm_graph(raw_g)
    edge = norm_g["1"]["2"][0]
    assert edge["length"] == 100.0
    assert edge["speed_kph"] == 30.0  # Default unclassified speed
    assert edge["bridge"] == "no"
    assert edge["tunnel"] == "no"
    assert isinstance(edge["geometry"], LineString)


def test_invalid_graph_triggers_rejection():
    """TEST F: Empty or NaN-coordinate graphs raise ValueError."""
    with pytest.raises(ValueError, match="empty or None"):
        normalize_osm_graph(nx.MultiDiGraph())

    nan_g = nx.MultiDiGraph()
    nan_g.add_node(1, x=float("nan"), y=13.00)
    nan_g.add_node(2, x=80.21, y=13.00)
    nan_g.add_edge(1, 2, key=0)

    with pytest.raises(ValueError, match="NaN detected"):
        normalize_osm_graph(nan_g)


def test_osm_provider_fallback_behavior():
    """TEST G: Invalid OSM query parameters safely fall back to CalibratedNetworkProvider."""
    calibrated = CalibratedNetworkProvider()
    # Provide invalid bbox coordinates to trigger provider fallback
    osm_provider = OSMNetworkProvider(fallback_provider=calibrated, bbox=(-999.0, -999.0, -999.0, -999.0))
    g = osm_provider.load_network()

    assert g.number_of_nodes() == 25
    assert g.number_of_edges() == 56


def test_coordinate_to_nearest_node_mapping():
    """TEST H: Coordinate-to-node spatial mapping calculates nearest graph node."""
    calibrated = CalibratedNetworkProvider().load_network()

    # Saidapet ward coordinate (80.22, 13.02)
    node_id, dist = map_entity_to_nearest_node(calibrated, lat=13.02, lon=80.22)
    assert isinstance(node_id, str)
    assert dist >= 0.0
    assert node_id in calibrated.nodes


def test_flood_compatibility_with_normalized_graph():
    """TEST J: Normalized graph exposes enough metadata for flood disruption logic."""
    raw_g = nx.MultiDiGraph()
    raw_g.add_node("1", x=80.21, y=13.02)
    raw_g.add_node("2", x=80.22, y=13.02)
    raw_g.add_edge("1", "2", key=0, length=500.0, highway="primary", bridge="yes", physical_segment_id="bridge_seg_1")
    raw_g.add_edge("2", "1", key=0, length=500.0, highway="primary", tunnel="yes", physical_segment_id="tunnel_seg_1")

    norm_g = normalize_osm_graph(raw_g)

    # Overlapping flood footprint
    flood_poly = Polygon([(80.20, 13.01), (80.23, 13.01), (80.23, 13.03), (80.20, 13.03)])
    disabled_segs, _ = identify_flood_disabled_segments(norm_g, flood_poly)

    # Elevated bridge must be preserved
    assert "bridge_seg_1" not in disabled_segs
    # Submerged tunnel must be disabled
    assert "tunnel_seg_1" in disabled_segs


def test_network_source_diagnostic_api():
    """TEST K: GET /network/source returns diagnostic information on active provider."""
    res = client.get("/network/source")
    assert res.status_code == 200
    data = res.json()
    assert "provider" in data
    assert data["nodes"] == 25
    assert data["edges"] == 56
    assert data["fallback_used"] is True
