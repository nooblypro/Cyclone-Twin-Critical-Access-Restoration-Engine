"""
Cyclone Twin Flood Polygon Fallback & Geometry Processing
Handles flood polygon normalization, Cyclone Michaung flood footprint, and bridge/tunnel filtering.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection, shape, mapping
from shapely.validation import make_valid
from shapely.ops import unary_union
import networkx as nx


def normalize_polygon_geometry(geom: Any) -> Polygon | MultiPolygon:
    """
    Normalizes and repairs arbitrary or invalid geometries.
    TEST 17: make_valid() GeometryCollection normalization retains polygonal components only.
    """
    if not geom.is_valid:
        geom = make_valid(geom)

    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom

    if isinstance(geom, GeometryCollection):
        polygons = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
        if not polygons:
            raise ValueError("No polygonal components found in GeometryCollection")
        return unary_union(polygons)

    raise ValueError(f"Geometry must be polygonal, got {geom.geom_type}")


def get_michaung_flood_polygon() -> Dict[str, Any]:
    """
    Returns GeoJSON Feature representing the major Cyclone Michaung (2023)
    inundation footprint across Greater Chennai Corporation.
    Includes 3 distinct hydrographic inundation pockets:
    1. Saidapet & Jafferkhanpet Adyar River basin lowlands (Arterial Lifeline)
    2. Velachery & Madipakkam lake overflow basin (Dense Community Lifeline)
    3. Santhome coastal surge pocket (Peripheral Low-Criticality Corridor)
    Enables realistic Killer Demo comparison of disparate network criticality.
    """
    poly_saidapet = [
        [80.202, 13.015],
        [80.228, 13.015],
        [80.228, 13.030],
        [80.202, 13.030],
        [80.202, 13.015],
    ]

    poly_velachery = [
        [80.208, 12.955],
        [80.225, 12.955],
        [80.225, 12.985],
        [80.208, 12.985],
        [80.208, 12.955],
    ]

    poly_santhome = [
        [80.268, 13.025],
        [80.282, 13.025],
        [80.282, 13.042],
        [80.268, 13.042],
        [80.268, 13.025],
    ]

    return {
        "type": "Feature",
        "properties": {
            "source": "nrsc_michaung_inundation_model",
            "event": "Cyclone Michaung December 2023",
            "region": "Greater Chennai Corporation (GCC) Disaster Assessment",
        },
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [
                [poly_saidapet],
                [poly_velachery],
                [poly_santhome],
            ],
        },
    }


def identify_flood_disabled_segments(
    graph: nx.MultiDiGraph,
    flood_geom: Any,
) -> Tuple[List[str], List[Tuple[str, str, int]]]:
    """
    Identifies edges and physical segments that must be disabled due to flood intersection.
    Enforces Section 15 rules:
    - bridge == 'yes' OR layer > 0 -> PRESERVE
    - tunnel == 'yes' OR layer < 0 -> DISABLE (if intersecting)
    """
    norm_flood = normalize_polygon_geometry(flood_geom)
    disabled_segments: Set[str] = set()
    disabled_edges: List[Tuple[str, str, int]] = []

    # Map physical segments to check if any edge in the segment is explicitly a bridge
    bridge_segments: Set[str] = set()
    for _, _, _, data in graph.edges(keys=True, data=True):
        bridge = str(data.get("bridge", "")).lower() == "yes"
        try:
            layer = int(data.get("layer", 0))
        except (ValueError, TypeError):
            layer = 0
        if bridge or layer > 0:
            seg_id = data.get("physical_segment_id")
            if seg_id:
                bridge_segments.add(str(seg_id))

    for u, v, key, data in graph.edges(keys=True, data=True):
        edge_geom = data.get("geometry")
        if edge_geom is None:
            continue

        # Check intersection with flood footprint
        if not norm_flood.intersects(edge_geom):
            continue

        seg_id = str(data.get("physical_segment_id") or f"seg_{u}_{v}_{key}")

        # Rule: bridge == "yes" OR layer > 0 -> PRESERVE
        if seg_id in bridge_segments:
            continue

        bridge = str(data.get("bridge", "")).lower() == "yes"
        try:
            layer = int(data.get("layer", 0))
        except (ValueError, TypeError):
            layer = 0

        if bridge or layer > 0:
            continue

        # Rule: tunnel == "yes" OR layer < 0 -> DISABLE
        # Standard surface road -> DISABLE
        disabled_segments.add(seg_id)
        disabled_edges.append((str(u), str(v), key))

    return sorted(list(disabled_segments)), disabled_edges
