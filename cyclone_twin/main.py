"""
Cyclone Twin FastAPI Application
Provides exact REST API endpoints for road network loading, flood simulation,
accessibility status, corridor ranking, corridor clearing, and advisory generation.
"""

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import shape, mapping

from .models import (
    NetworkLoadRequest,
    NetworkLoadResponse,
    FloodApplyRequest,
    FloodApplyResponse,
    AccessibilityStatusResponse,
    InterventionsRankRequest,
    InterventionsRankResponse,
    InterventionsClearRequest,
    InterventionsClearResponse,
    ClearStateResult,
    AdvisoryGenerateRequest,
    AdvisoryGenerateResponse,
    ScoreBreakdown,
    RankedCorridor,
    Weights,
)
from .network_engine import NetworkEngine
from .ranking_engine import RankingEngine, compute_accessibility
from .corridor_engine import CorridorEngine
from .data_loader import DataLoader
from .flood_polygon_fallback import identify_flood_disabled_segments, normalize_polygon_geometry
from .advisory_engine import AdvisoryEngine

# Setup structured logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("cyclone_twin")


class AppState:
    """Encapsulates in-memory simulation state for the active Chennai scenario."""
    def __init__(self):
        self.data_loader: DataLoader = DataLoader()
        self.network_engine: NetworkEngine = NetworkEngine()
        self.ranking_engine: RankingEngine = RankingEngine(self.network_engine)
        self.advisory_engine: AdvisoryEngine = AdvisoryEngine()
        self.corridors: List[Any] = []
        self.ranked_corridors: List[RankedCorridor] = []
        self.current_weights: Weights = Weights.life_safety()
        self.last_cleared_corridor: Optional[str] = None
        self.initialized: bool = False

    def initialize(self):
        if not self.initialized:
            logger.info("Initializing Cyclone Twin default scenario...")
            self.data_loader.load_road_network(attempt_real=False)
            self.network_engine.set_graph(self.data_loader.graph)
            self.initialized = True


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Eagerly initialize on startup
    state.initialize()
    logger.info("Cyclone Twin application started and ready.")
    yield
    logger.info("Cyclone Twin application shutting down.")


app = FastAPI(
    title="Cyclone Twin API",
    description="Network-Aware Infrastructure Vulnerability Forecaster for Greater Chennai Corporation",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware supporting production Vercel origins and local dev
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
if allowed_origins_raw == "*":
    origins = ["*"]
    allow_origin_regex = None
else:
    origins = [orig.strip() for orig in allowed_origins_raw.split(",") if orig.strip()]
    allow_origin_regex = r"https://.*\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """
    Section 33: Observability logging for request, execution duration,
    and scenario status without exposing credentials.
    """
    req_id = str(uuid.uuid4())[:8]
    start_time = time.perf_counter()

    logger.info(
        f"[REQ-{req_id}] {request.method} {request.url.path} "
        f"graph_source={state.data_loader.graph_source} "
        f"disabled_segs={len(state.network_engine.disabled_segments)}"
    )

    try:
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(f"[REQ-{req_id}] status={response.status_code} duration={duration_ms:.2f}ms")
        response.headers["X-Request-ID"] = req_id
        return response
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error(f"[REQ-{req_id}] ERROR: {str(exc)} after {duration_ms:.2f}ms")
        raise


@app.get("/")
def health():
    return {
        "status": "online",
        "system": "Cyclone Twin",
        "version": "1.0.0",
        "target": "Greater Chennai Corporation (GCC)",
    }


# ============================================================
# API CONTRACT ENDPOINTS (Section 19)
# ============================================================

@app.post("/network/load", response_model=NetworkLoadResponse)
def network_load(req: Optional[NetworkLoadRequest] = None):
    """
    POST /network/load
    Reloads Chennai road network.
    Response: { "nodes": int, "edges": int, "graph_source": str }
    """
    start = time.perf_counter()
    graph = state.data_loader.load_road_network(attempt_real=False)
    state.network_engine.set_graph(graph)
    state.corridors.clear()
    state.ranked_corridors.clear()
    state.last_cleared_corridor = None

    elapsed = (time.perf_counter() - start) * 1000.0
    logger.info(
        f"Loaded network: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges, "
        f"source={state.data_loader.graph_source} in {elapsed:.1f}ms"
    )

    return NetworkLoadResponse(
        nodes=graph.number_of_nodes(),
        edges=graph.number_of_edges(),
        graph_source=state.data_loader.graph_source,
    )


@app.post("/flood/apply", response_model=FloodApplyResponse)
def flood_apply(req: FloodApplyRequest):
    """
    POST /flood/apply
    Applies flood footprint, disables intersecting roads (obeying bridges/tunnels),
    and clusters disabled segments into connected restoration corridors.
    Response: { "disabled_edges": int, "flood_source": str, "corridors": int }
    """
    state.initialize()
    # Reset any previous disabled segments
    state.network_engine.restore_all()

    # Load flood polygon (custom or fallback)
    try:
        flood_geojson = state.data_loader.load_flood_polygon(
            custom_geojson=req.flood_geojson,
            attempt_nrsc=True,
        )
        geom_dict = flood_geojson.get("geometry", flood_geojson)
        flood_shape = normalize_polygon_geometry(shape(geom_dict))
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"Invalid flood GeoJSON geometry provided: {exc}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid flood GeoJSON geometry: {str(exc)}",
        )

    # Identify disabled segments enforcing bridge/tunnel/layer rules (Section 15)
    disabled_segs, disabled_edges = identify_flood_disabled_segments(
        state.network_engine.graph,
        flood_shape,
    )

    # Disable segments in network engine
    state.network_engine.disable_segments(disabled_segs, validate=True)

    # Cluster into connected restoration corridors (Section 17)
    corridors = CorridorEngine.cluster_disabled_segments_into_corridors(
        state.network_engine.graph,
        state.network_engine.disabled_segments,
    )
    state.corridors = corridors
    state.ranked_corridors.clear()

    logger.info(
        f"Applied flood: {len(disabled_edges)} disabled edges, {len(corridors)} corridors, "
        f"source={state.data_loader.flood_source}"
    )

    return FloodApplyResponse(
        disabled_edges=len(disabled_edges),
        flood_source=state.data_loader.flood_source,
        corridors=len(corridors),
    )


@app.get("/accessibility/status", response_model=AccessibilityStatusResponse)
def accessibility_status():
    """
    GET /accessibility/status
    Calculates current accessibility given active disabled roads.
    Response: { "accessible_population": int, "isolated_facilities": [str], "isolated_communities": [str] }
    """
    state.initialize()
    res = compute_accessibility(
        engine=state.network_engine,
        communities=state.data_loader.communities,
        facilities=state.data_loader.facilities,
    )

    return AccessibilityStatusResponse(
        accessible_population=res.accessible_population,
        isolated_facilities=res.isolated_facilities,
        isolated_communities=res.isolated_communities,
    )


@app.post("/interventions/rank", response_model=InterventionsRankResponse)
def interventions_rank(req: InterventionsRankRequest):
    """
    POST /interventions/rank
    Ranks corridors using the locked deterministic formula.
    Returns ranked corridors and full ScenarioManifest.
    """
    state.initialize()

    # If corridors have not been generated yet, apply default Michaung flood scenario
    if not state.corridors:
        _ = flood_apply(FloodApplyRequest())

    weights = req.weights or Weights.life_safety()
    state.current_weights = weights

    ranked = state.ranking_engine.rank_corridors(
        corridors=state.corridors,
        communities=state.data_loader.communities,
        facilities=state.data_loader.facilities,
        weights=weights,
    )
    state.ranked_corridors = ranked

    total_disabled_edges = sum(len(c.edge_keys) for c in state.corridors)
    manifest = state.data_loader.get_manifest(
        weight_preset="life_safety" if weights == Weights.life_safety() else "custom",
        total_disabled_edges=total_disabled_edges,
        total_corridors=len(ranked),
    )

    logger.info(
        f"Ranked {len(ranked)} corridors with weights w_h={weights.w_h}, w_p={weights.w_p}, "
        f"w_t={weights.w_t}, w_d={weights.w_d}"
    )

    return InterventionsRankResponse(
        ranked_corridors=ranked,
        manifest=manifest,
    )


@app.post("/interventions/clear", response_model=InterventionsClearResponse)
def interventions_clear(req: InterventionsClearRequest):
    """
    POST /interventions/clear
    Simulates clearing a specific corridor.
    Response: { "corridor_id": str, "new_graph_state": { "accessible_population": int, "isolated_count": int } }
    """
    state.initialize()

    # Find the target corridor
    target_corridor = next((c for c in state.corridors if c.corridor_id == req.corridor_id), None)
    if not target_corridor:
        # Check in ranked corridors as well
        target_rc = next((rc for rc in state.ranked_corridors if rc.corridor_id == req.corridor_id), None)
        if target_rc:
            seg_ids = target_rc.physical_segment_ids
        else:
            raise HTTPException(status_code=404, detail=f"Corridor '{req.corridor_id}' not found.")
    else:
        seg_ids = target_corridor.physical_segment_ids

    # Restore the corridor segments
    restored_count = state.network_engine.restore_segments(seg_ids)
    state.last_cleared_corridor = req.corridor_id

    # Re-evaluate accessibility
    new_access = compute_accessibility(
        engine=state.network_engine,
        communities=state.data_loader.communities,
        facilities=state.data_loader.facilities,
    )

    isolated_total = len(new_access.isolated_facilities) + len(new_access.isolated_communities)

    logger.info(
        f"Cleared corridor {req.corridor_id} ({restored_count} segments restored). "
        f"New accessible population={new_access.accessible_population}, isolated_count={isolated_total}"
    )

    return InterventionsClearResponse(
        corridor_id=req.corridor_id,
        new_graph_state=ClearStateResult(
            accessible_population=new_access.accessible_population,
            isolated_count=isolated_total,
        ),
    )


@app.post("/advisory/generate", response_model=AdvisoryGenerateResponse)
def advisory_generate(req: AdvisoryGenerateRequest):
    """
    POST /advisory/generate
    Generates dispatch advisory via Gemini with deterministic fallback.
    Output constrained to <= 220 chars.
    """
    state.initialize()

    # Look up road names and communities for the corridor
    target_rc = next((rc for rc in state.ranked_corridors if rc.corridor_id == req.corridor_id), None)
    roads = [target_rc.road_classes[0]] if target_rc and target_rc.road_classes else [req.corridor_id]

    res = state.advisory_engine.generate_advisory(
        corridor_id=req.corridor_id,
        score_breakdown=req.score_breakdown,
        road_names=roads,
    )

    return res


# ============================================================
# OPERATIONAL MAP DATA ENDPOINT (for Frontend Cartography)
# ============================================================

@app.get("/map/data")
def get_map_data():
    """
    Returns full GeoJSON layers for Chennai roads, hospitals, communities,
    and flood footprint for direct rendering in the frontend map.
    """
    state.initialize()

    # Road edges GeoJSON
    edge_features = []
    for u, v, key, data in state.network_engine.graph.edges(keys=True, data=True):
        geom = data.get("geometry")
        if geom is not None:
            seg_id = data.get("physical_segment_id", "")
            is_disabled = seg_id in state.network_engine.disabled_segments
            edge_features.append({
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {
                    "u": str(u),
                    "v": str(v),
                    "key": key,
                    "name": data.get("name", "Arterial Road"),
                    "length": data.get("length", 100),
                    "speed_kph": data.get("speed_kph", 40),
                    "highway": data.get("highway", "primary"),
                    "bridge": data.get("bridge", "no"),
                    "layer": data.get("layer", 0),
                    "disabled": is_disabled,
                    "segment_id": seg_id,
                },
            })

    # Facilities GeoJSON
    facility_features = []
    access_status = compute_accessibility(
        state.network_engine,
        state.data_loader.communities,
        state.data_loader.facilities,
    )
    isolated_fac_set = set(access_status.isolated_facilities)

    for fac in state.data_loader.facilities:
        if fac.coords:
            facility_features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [fac.coords[0], fac.coords[1]],
                },
                "properties": {
                    "id": fac.id,
                    "name": fac.name,
                    "beds": fac.beds,
                    "power_status": fac.power_status,
                    "isolated": fac.id in isolated_fac_set,
                    "node_id": fac.node_id,
                },
            })

    # Communities GeoJSON
    community_features = []
    isolated_comm_set = set(access_status.isolated_communities)

    for comm in state.data_loader.communities:
        if comm.coords:
            community_features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [comm.coords[0], comm.coords[1]],
                },
                "properties": {
                    "id": comm.id,
                    "name": comm.name,
                    "population": comm.population,
                    "isolated": comm.id in isolated_comm_set,
                    "travel_time_sec": access_status.community_travel_times.get(comm.id),
                    "node_id": comm.node_id,
                },
            })

    return {
        "roads": {"type": "FeatureCollection", "features": edge_features},
        "facilities": {"type": "FeatureCollection", "features": facility_features},
        "communities": {"type": "FeatureCollection", "features": community_features},
        "flood": state.data_loader.flood_geojson,
        "disabled_segments": list(state.network_engine.disabled_segments),
        "last_cleared_corridor": state.last_cleared_corridor,
    }
