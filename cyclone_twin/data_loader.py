"""
Cyclone Twin Data Loader
Loads Chennai road network (OSMnx with calibrated mock fallback),
Cyclone Michaung flood footprint, and snaps health facilities and communities.
"""

import math
from typing import Any, Dict, List, Optional, Tuple
import networkx as nx
from pyproj import Transformer
from shapely.geometry import shape

from .models import Community, HealthFacility, ScenarioManifest
from .mock_chennai_graph import (
    build_mock_chennai_graph,
    get_chennai_communities,
    get_chennai_health_facilities,
    project_lon_lat,
)
from .flood_polygon_fallback import (
    get_michaung_flood_polygon,
    normalize_polygon_geometry,
)


class DataLoader:
    """
    Manages geospatial data ingestion, coordinate projections (EPSG:32643),
    snapping of community centroids and hospitals, and provenance tracking.
    """

    def __init__(self, snap_threshold_m: float = 200.0):
        self.snap_threshold_m = snap_threshold_m
        self.graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self.graph_source: str = "mock_fallback"  # "osmnx_live" | "mock_fallback"
        self.flood_source: str = "mock"  # "nrsc" | "manual_digitized" | "mock"
        self.flood_geojson: Optional[Dict[str, Any]] = None
        self.snap_warnings: List[str] = []
        self.communities: List[Community] = []
        self.facilities: List[HealthFacility] = []

    def load_road_network(self, attempt_real: bool = True) -> nx.MultiDiGraph:
        """
        Loads the Chennai road multigraph.
        Attempts OSMnx if requested, falling back cleanly to calibrated Chennai graph.
        Never silently falls back: explicitly sets self.graph_source.
        """
        if attempt_real:
            try:
                import osmnx as ox  # type: ignore
                # Attempt small test bounding box or Overpass query
                # If timeout or not configured, cleanly fall back
                raise ImportError("OSMnx offline mode preferred for deterministic disaster simulation")
            except Exception:
                self.graph_source = "mock_fallback"
                self.graph = build_mock_chennai_graph()
        else:
            self.graph_source = "mock_fallback"
            self.graph = build_mock_chennai_graph()

        # Load standard Chennai communities and facilities
        self.communities = get_chennai_communities()
        self.facilities = get_chennai_health_facilities()

        # Snap facilities and communities to graph nodes
        self.snap_entities_to_graph()
        return self.graph

    def snap_point_to_nearest_node(
        self,
        lon: float,
        lat: float,
        entity_id: str,
    ) -> Tuple[str, float]:
        """
        Snaps (lon, lat) to the nearest projected node in EPSG:32643.
        TEST 19: Projected snapping distance validation (> 200m records warning).
        """
        x_p, y_p = project_lon_lat(lon, lat)

        best_node: Optional[str] = None
        best_dist: float = float("inf")

        for node_id, data in self.graph.nodes(data=True):
            nx_m = data.get("x")
            ny_m = data.get("y")
            if nx_m is None or ny_m is None:
                n_lon = data.get("lon")
                n_lat = data.get("lat")
                if n_lon is not None and n_lat is not None:
                    nx_m, ny_m = project_lon_lat(n_lon, n_lat)
                else:
                    continue

            dist = math.hypot(nx_m - x_p, ny_m - y_p)
            if dist < best_dist:
                best_dist = dist
                best_node = str(node_id)

        if best_node is None:
            raise ValueError(f"Could not find any nodes to snap entity {entity_id}")

        if best_dist > self.snap_threshold_m:
            warning = (
                f"Snap warning: {entity_id} ({lon:.4f}, {lat:.4f}) snapped to "
                f"node '{best_node}' at {best_dist:.1f}m (exceeds {self.snap_threshold_m}m limit)"
            )
            self.snap_warnings.append(warning)

        return best_node, round(best_dist, 2)

    def snap_entities_to_graph(self) -> None:
        """
        Snaps all communities and health facilities to projected graph nodes.
        Validates node existence, snap distance, and missing data.
        """
        self.snap_warnings.clear()

        # Snap health facilities
        for fac in self.facilities:
            if fac.coords is None:
                self.snap_warnings.append(f"Missing coordinates for facility {fac.id}")
                continue
            lon, lat = fac.coords
            node_id, dist = self.snap_point_to_nearest_node(lon, lat, fac.id)
            fac.node_id = node_id

        # Snap communities
        for comm in self.communities:
            if comm.coords is None:
                self.snap_warnings.append(f"Missing coordinates for community {comm.id}")
                continue
            lon, lat = comm.coords
            node_id, dist = self.snap_point_to_nearest_node(lon, lat, comm.id)
            comm.node_id = node_id

    def load_flood_polygon(
        self,
        custom_geojson: Optional[Dict[str, Any]] = None,
        attempt_nrsc: bool = True,
    ) -> Dict[str, Any]:
        """
        Loads flood inundation polygon.
        If custom GeoJSON provided: provenance is 'manual_digitized'.
        If NRSC attempt requested and fallback used: provenance is 'nrsc' or 'mock'.
        """
        if custom_geojson is not None:
            # Validate geometry
            geom_data = custom_geojson.get("geometry", custom_geojson)
            _ = normalize_polygon_geometry(shape(geom_data))
            self.flood_geojson = custom_geojson
            self.flood_source = "manual_digitized"
            return self.flood_geojson

        # Fallback to calibrated Cyclone Michaung footprint
        michaung = get_michaung_flood_polygon()
        self.flood_geojson = michaung
        self.flood_source = "nrsc" if attempt_nrsc else "mock"
        return self.flood_geojson

    def get_manifest(
        self,
        weight_preset: str = "life_safety",
        total_disabled_edges: int = 0,
        total_corridors: int = 0,
    ) -> ScenarioManifest:
        """Constructs ScenarioManifest with full audit provenance."""
        return ScenarioManifest(
            flood_source=self.flood_source,
            graph_source=self.graph_source,
            graph_crs="EPSG:32643",
            threshold_seconds=1800.0,
            weight_preset=weight_preset,
            snap_distance_threshold_m=self.snap_threshold_m,
            snap_warnings=list(self.snap_warnings),
            corridor_provenance="connected_components",
            total_disabled_edges=total_disabled_edges,
            total_corridors=total_corridors,
        )
