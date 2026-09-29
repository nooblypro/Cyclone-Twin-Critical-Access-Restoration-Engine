"""
Road Network Provider Implementations for Cyclone Twin
Includes Calibrated Chennai Multigraph Provider, OSMnx Ingestion/Normalization Provider,
Graph Quality Validation, and Coordinate-to-Node Spatial Mapping.
"""

import math
import logging
from typing import Any, Dict, List, Optional, Tuple, Set
import networkx as nx
from shapely.geometry import LineString, Point

from cyclone_twin.mock_chennai_graph import build_mock_chennai_graph
from cyclone_twin.providers.base import RoadNetworkProvider

logger = logging.getLogger(__name__)

# Default bounded Bounding Box for Chennai arterial corridor simulation area
# Tuple order for OSMnx 2.0+: (left, bottom, right, top) = (min_lon, min_lat, max_lon, max_lat)
DEFAULT_OSM_BBOX = (80.15, 12.89, 80.29, 13.09)


def parse_speed_kph(maxspeed_attr: Any, highway_attr: Any) -> float:
    """Parses maxspeed attribute from OSM data or applies default highway speed classification."""
    if maxspeed_attr is not None:
        if isinstance(maxspeed_attr, list) and maxspeed_attr:
            maxspeed_attr = maxspeed_attr[0]
        try:
            val_str = str(maxspeed_attr).split()[0]
            val = float(val_str)
            if val > 0:
                return val
        except (ValueError, IndexError, TypeError):
            pass

    # Centralized highway speed classification defaults (km/h)
    h_str = str(highway_attr[0] if isinstance(highway_attr, list) and highway_attr else highway_attr).lower()
    if "motorway" in h_str or "trunk" in h_str:
        return 60.0
    if "primary" in h_str:
        return 50.0
    if "secondary" in h_str:
        return 40.0
    if "tertiary" in h_str:
        return 35.0
    return 30.0


def normalize_osm_graph(raw_graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Normalizes a raw OSMnx graph or synthetic MultiDiGraph into Cyclone Twin's
    internal graph schema required by NetworkEngine.
    Preserves directed edge topology, road metadata, and calculates travel times.
    """
    if raw_graph is None or raw_graph.number_of_nodes() == 0 or raw_graph.number_of_edges() == 0:
        raise ValueError("Invalid graph: raw graph is empty or None")

    norm_graph = nx.MultiDiGraph()
    norm_graph.graph.update(raw_graph.graph)

    # 1. Normalize Nodes
    for node, data in raw_graph.nodes(data=True):
        node_str = str(node)
        lon = float(data.get("x", data.get("lon", 80.22)))
        lat = float(data.get("y", data.get("lat", 13.00)))

        if math.isnan(lon) or math.isnan(lat):
            raise ValueError(f"Invalid node coordinates: NaN detected for node {node_str}")

        norm_graph.add_node(
            node_str,
            x=lon,
            y=lat,
            lon=lon,
            lat=lat,
            elevation=float(data.get("elevation", 2.0)),
        )

    # 2. Normalize Edges
    for u, v, key, data in raw_graph.edges(keys=True, data=True):
        u_str, v_str = str(u), str(v)

        length_m = float(data.get("length", 100.0))
        if length_m <= 0:
            length_m = 10.0

        highway_type = data.get("highway", "unclassified")
        if isinstance(highway_type, list):
            highway_type = highway_type[0]

        speed_kph = parse_speed_kph(data.get("maxspeed"), highway_type)
        speed_mps = speed_kph * (1000.0 / 3600.0)
        travel_time_sec = float(data.get("travel_time", length_m / speed_mps))

        # Preserve Bridge / Tunnel attributes
        bridge_raw = data.get("bridge")
        is_bridge = str(bridge_raw).lower() in ("yes", "true", "1") if bridge_raw is not None else False

        tunnel_raw = data.get("tunnel")
        is_tunnel = str(tunnel_raw).lower() in ("yes", "true", "1") if tunnel_raw is not None else False

        # Segment ID attribution
        osmid = data.get("osmid")
        if isinstance(osmid, list):
            osmid = osmid[0]
        seg_id = str(data.get("physical_segment_id") or (f"way_{osmid}" if osmid else f"seg_{u_str}_{v_str}_{key}"))

        # Geometry preservation
        geom = data.get("geometry")
        if geom is None:
            u_node = norm_graph.nodes[u_str]
            v_node = norm_graph.nodes[v_str]
            geom = LineString([(u_node["lon"], u_node["lat"]), (v_node["lon"], v_node["lat"])])

        edge_attrs = {
            "length": length_m,
            "speed_kph": speed_kph,
            "travel_time": travel_time_sec,
            "physical_segment_id": seg_id,
            "highway": str(highway_type),
            "bridge": "yes" if is_bridge else "no",
            "tunnel": "yes" if is_tunnel else "no",
            "layer": int(data.get("layer", 1 if is_bridge else (-1 if is_tunnel else 0))),
            "name": str(data.get("name", "Arterial Road")),
            "geometry": geom,
        }

        norm_graph.add_edge(u_str, v_str, key=key, **edge_attrs)

    return norm_graph


def map_entity_to_nearest_node(graph: nx.MultiDiGraph, lat: float, lon: float) -> Tuple[str, float]:
    """
    Computes spatial distance from coordinate (lat, lon) to all graph nodes
    and returns (nearest_node_id, min_distance_meters).
    """
    if graph is None or graph.number_of_nodes() == 0:
        raise ValueError("Cannot map coordinate to empty graph")

    min_dist_sq = float("inf")
    nearest_node: Optional[str] = None

    # Earth radius ~ 6,371,000m; 1 deg lat ~ 111,000m
    lat_rad = math.radians(lat)
    cos_lat = math.cos(lat_rad)

    for node_id, data in graph.nodes(data=True):
        n_lat = float(data.get("lat", data.get("y", 0.0)))
        n_lon = float(data.get("lon", data.get("x", 0.0)))

        d_lat = (lat - n_lat) * 111000.0
        d_lon = (lon - n_lon) * 111000.0 * cos_lat
        dist_sq = d_lat * d_lat + d_lon * d_lon

        if dist_sq < min_dist_sq:
            min_dist_sq = dist_sq
            nearest_node = str(node_id)

    return nearest_node or list(graph.nodes)[0], math.sqrt(min_dist_sq)


class CalibratedNetworkProvider(RoadNetworkProvider):
    """Calibrated Chennai Metropolitan arterial network provider (25 nodes, 56 edges)."""

    def load_network(self) -> nx.MultiDiGraph:
        return build_mock_chennai_graph()


class OSMNetworkProvider(RoadNetworkProvider):
    """
    OSMnx dynamic road network provider.
    Acquires drivable road multigraph from Overpass, validates quality, normalizes geometry/attributes,
    and caches network in memory. Falls back to CalibratedNetworkProvider on timeout or failure.
    """

    def __init__(
        self,
        fallback_provider: Optional[RoadNetworkProvider] = None,
        bbox: Tuple[float, float, float, float] = DEFAULT_OSM_BBOX,
        request_timeout: float = 4.0,
    ):
        self.fallback = fallback_provider or CalibratedNetworkProvider()
        self.bbox = bbox
        self.request_timeout = request_timeout
        self._cached_graph: Optional[nx.MultiDiGraph] = None

    def load_network(self) -> nx.MultiDiGraph:
        if self._cached_graph is not None:
            return self._cached_graph

        try:
            import osmnx as ox  # type: ignore
            ox.settings.request_timeout = self.request_timeout

            # Query drivable road network within bounded Chennai bbox (left, bottom, right, top)
            raw_g = ox.graph_from_bbox(bbox=self.bbox, network_type="drive")
            norm_g = normalize_osm_graph(raw_g)

            if norm_g.number_of_nodes() > 0 and norm_g.number_of_edges() > 0:
                self._cached_graph = norm_g
                logger.info(
                    "Successfully loaded and normalized OSMnx network: %d nodes, %d edges",
                    norm_g.number_of_nodes(),
                    norm_g.number_of_edges(),
                )
                return norm_g
        except Exception as err:
            logger.warning("OSMnx network ingestion unavailable or failed: %s. Using calibrated fallback.", err)

        fallback_g = self.fallback.load_network()
        self._cached_graph = fallback_g
        return fallback_g
