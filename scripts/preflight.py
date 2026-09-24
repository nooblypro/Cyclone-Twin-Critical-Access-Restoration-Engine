#!/usr/bin/env python3
"""
Cyclone Twin Preflight Validation Script (Section 34)
Validates runtime environment, coordinate reference systems, spatial joins,
flood intersection, corridor connectivity, and data integrity.
Exits with code 0 on success, code 1 on critical failure.
"""

import os
import sys
import logging

# Ensure root workspace directory is in python path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from shapely.geometry import Polygon, LineString, Point, GeometryCollection
from pyproj import CRS, Transformer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("preflight")


def run_preflight() -> bool:
    all_passed = True
    print("=" * 65)
    print("CYCLONE TWIN — SYSTEM PREFLIGHT SANITY CHECK")
    print("=" * 65)

    # 1. Dependency Verification
    required_modules = [
        "networkx",
        "shapely",
        "geopandas",
        "pydantic",
        "fastapi",
        "uvicorn",
        "pyproj",
        "pytest",
    ]
    print("\n[1/8] Verifying Required Packages...")
    for mod in required_modules:
        try:
            __import__(mod)
            print(f"  ✓ {mod:<15} OK")
        except ImportError as e:
            print(f"  ✗ {mod:<15} FAILED ({e})")
            all_passed = False

    # 2. CRS & Projections (EPSG:32643)
    print("\n[2/8] Validating Coordinate Systems & Projections (EPSG:32643)...")
    try:
        crs_utm = CRS.from_epsg(32643)
        assert crs_utm.is_projected, "EPSG:32643 must be a projected CRS (UTM Zone 43N)"
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
        x, y = transformer.transform(80.27, 13.08)
        assert 900000 < x < 1200000, f"Unexpected projected easting: {x}"
        assert 1400000 < y < 1600000, f"Unexpected projected northing: {y}"
        print(f"  ✓ CRS projection verified: (80.27, 13.08) -> ({x:.1f}m, {y:.1f}m)")
    except Exception as e:
        print(f"  ✗ CRS validation failed: {e}")
        all_passed = False

    # 3. Bounding Box Ordering
    print("\n[3/8] Validating Bounding Box Conventions...")
    try:
        # Standard bounding box format: (minx, miny, maxx, maxy) -> (west, south, east, north)
        bbox = (80.15, 12.90, 80.30, 13.15)
        minx, miny, maxx, maxy = bbox
        assert minx < maxx and miny < maxy, "Invalid bbox coordinate bounds"
        print(f"  ✓ Bounding box verified: {bbox}")
    except Exception as e:
        print(f"  ✗ BBox ordering failed: {e}")
        all_passed = False

    # 4. Geometry Normalization (make_valid & GeometryCollection)
    print("\n[4/8] Validating Geometry Validity & Polygon Extraction (TEST 17)...")
    try:
        from cyclone_twin.flood_polygon_fallback import normalize_polygon_geometry
        gc = GeometryCollection([
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]),
            LineString([(2, 2), (3, 3)]),
            Point(4, 4),
        ])
        norm = normalize_polygon_geometry(gc)
        assert norm.geom_type in ("Polygon", "MultiPolygon"), f"Unexpected type: {norm.geom_type}"
        print("  ✓ make_valid() GeometryCollection normalization verified")
    except Exception as e:
        print(f"  ✗ Geometry normalization failed: {e}")
        all_passed = False

    # 5. Flood Intersection & Bridge/Tunnel Rules
    print("\n[5/8] Validating Flood Intersection & Bridge/Tunnel Invariance...")
    try:
        from cyclone_twin.mock_chennai_graph import build_mock_chennai_graph
        from cyclone_twin.flood_polygon_fallback import get_michaung_flood_polygon, identify_flood_disabled_segments
        from shapely.geometry import shape

        G = build_mock_chennai_graph()
        poly = shape(get_michaung_flood_polygon()["geometry"])
        disabled_segs, disabled_edges = identify_flood_disabled_segments(G, poly)

        assert len(disabled_segs) > 0, "No segments disabled under flood"
        # Verify bridge seg_saidapet_elevated is NOT disabled
        assert "seg_saidapet_elevated" not in disabled_segs, "Elevated bridge was improperly disabled!"
        print(f"  ✓ Flood intersection verified ({len(disabled_segs)} segments disabled, bridges preserved)")
    except Exception as e:
        print(f"  ✗ Flood intersection validation failed: {e}")
        all_passed = False

    # 6. Node Snapping & 200m Distance Threshold (TEST 19)
    print("\n[6/8] Validating Node Snapping & Distance Threshold...")
    try:
        from cyclone_twin.data_loader import DataLoader
        loader = DataLoader(snap_threshold_m=200.0)
        loader.load_road_network(attempt_real=False)
        assert len(loader.facilities) > 0, "No health facilities loaded"
        assert len(loader.communities) > 0, "No communities loaded"
        # Check all facilities snapped to existing nodes
        for f in loader.facilities:
            assert f.node_id in loader.graph, f"Facility {f.id} snapped to invalid node"
        print(f"  ✓ Snapping verified ({len(loader.facilities)} facilities, {len(loader.communities)} communities)")
    except Exception as e:
        print(f"  ✗ Snapping validation failed: {e}")
        all_passed = False

    # 7. Corridor Clustering & Connectivity
    print("\n[7/8] Validating Connected Component Corridor Generation...")
    try:
        from cyclone_twin.corridor_engine import CorridorEngine
        corridors = CorridorEngine.cluster_disabled_segments_into_corridors(G, set(disabled_segs))
        assert len(corridors) >= 2, f"Expected multiple corridors, got {len(corridors)}"
        print(f"  ✓ Connected corridor clustering verified ({len(corridors)} distinct corridors)")
    except Exception as e:
        print(f"  ✗ Corridor clustering failed: {e}")
        all_passed = False

    # 8. Deterministic Ranking & Manifest
    print("\n[8/8] Validating Deterministic Ranking Engine & Manifest...")
    try:
        from cyclone_twin.network_engine import NetworkEngine
        from cyclone_twin.ranking_engine import RankingEngine
        from cyclone_twin.models import Weights

        engine = NetworkEngine(G)
        engine.disable_segments(disabled_segs)
        ranking = RankingEngine(engine)
        ranked = ranking.rank_corridors(corridors, loader.communities, loader.facilities, Weights.life_safety())
        assert len(ranked) == len(corridors), "Corridor ranking count mismatch"
        assert ranked[0].score >= ranked[-1].score, "Ranking order not descending"
        manifest = loader.get_manifest(total_disabled_edges=len(disabled_edges), total_corridors=len(ranked))
        assert manifest.graph_crs == "EPSG:32643"
        print(f"  ✓ Deterministic ranking & manifest verified (Top rank: {ranked[0].corridor_id} with score {ranked[0].score:.4f})")
    except Exception as e:
        print(f"  ✗ Ranking validation failed: {e}")
        all_passed = False

    print("\n" + "=" * 65)
    if all_passed:
        print("PREFLIGHT STATUS: ALL CHECKS PASSED [READY FOR OPERATION]")
        print("=" * 65)
        return True
    else:
        print("PREFLIGHT STATUS: ONE OR MORE CHECKS FAILED")
        print("=" * 65)
        return False


if __name__ == "__main__":
    success = run_preflight()
    sys.exit(0 if success else 1)
