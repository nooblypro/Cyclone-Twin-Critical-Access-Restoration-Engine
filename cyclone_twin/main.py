"""
Cyclone Twin FastAPI Application
Provides exact REST API endpoints for road network loading, flood simulation,
accessibility status, corridor ranking, corridor clearing, and advisory generation.
"""

import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, File, UploadFile, Form, Query
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


from .providers.multimodal_pipeline import MultimodalIngestionService
from .providers.voice_pipeline import VoiceEvidencePipeline
from cyclone_twin.providers.drainage_provider import DrainageInfrastructureProvider
from cyclone_twin.providers.citizen_pipeline import CitizenPipelineService
from cyclone_twin.providers.disaster_state_engine import DisasterStateManager
from cyclone_twin.providers.intervention_engine import InterventionManager
from cyclone_twin.providers.gcp_foundation import GCPFoundationService, get_gcp_foundation
from cyclone_twin.persistence import get_persistence_repository, PersistenceRepository


class AppState:
    """Encapsulates simulation state and durable persistence for the active Chennai scenario."""
    def __init__(self):
        self.data_loader: DataLoader = DataLoader()
        self.network_engine: NetworkEngine = NetworkEngine()
        self.ranking_engine: RankingEngine = RankingEngine(self.network_engine)
        self.advisory_engine: AdvisoryEngine = AdvisoryEngine()
        self.multimodal_service: MultimodalIngestionService = MultimodalIngestionService()
        self.voice_pipeline: VoiceEvidencePipeline = VoiceEvidencePipeline(multimodal_service=self.multimodal_service)
        self.drainage_provider: DrainageInfrastructureProvider = DrainageInfrastructureProvider()
        self.citizen_pipeline: CitizenPipelineService = CitizenPipelineService(multimodal_service=self.multimodal_service)
        self.disaster_state_manager: DisasterStateManager = DisasterStateManager()
        self.intervention_manager: InterventionManager = InterventionManager()
        self.gcp_foundation: GCPFoundationService = GCPFoundationService()
        self.persistence_repo: PersistenceRepository = get_persistence_repository()
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
            self.rehydrate_from_persistence()
            self.initialized = True

    def rehydrate_from_persistence(self):
        """
        Rehydrates mutable source state (disabled_segments, water_level_m, citizen reports, interventions)
        from durable persistence storage if present.
        """
        try:
            snapshot = self.persistence_repo.load_latest_scenario_state()
            if snapshot:
                w_level = float(snapshot.get("water_level_m", 0.0))
                disabled_segs = snapshot.get("disabled_segments", [])
                self.data_loader.water_level_m = w_level

                # Apply disabled segments to network engine
                self.network_engine.disabled_segments = set(disabled_segs)
                for u, v, k, d in self.network_engine.graph.edges(keys=True, data=True):
                    seg_id = d.get("segment_id") or f"{u}_{v}"
                    if seg_id in self.network_engine.disabled_segments:
                        d["disabled"] = True
                        d["inundation_depth_m"] = max(w_level, 0.5)

                logger.info(f"[PERSISTENCE] Successfully rehydrated scenario snapshot v{snapshot.get('version', 1)} from storage.")
            else:
                logger.info("[PERSISTENCE] No persisted state snapshot found. Running default baseline scenario.")

            # Always rehydrate evidence & operational entities if present
            obs_list = self.persistence_repo.load_citizen_observations()
            for obs_dict in obs_list:
                try:
                    from cyclone_twin.domain.entities import CitizenObservation
                    obs = CitizenObservation(**obs_dict)
                    obs_id = getattr(obs, "observation_id", getattr(obs, "report_id", str(uuid.uuid4())))
                    self.citizen_pipeline.citizen_reports[obs_id] = obs
                except Exception as ex:
                    logger.warning(f"[PERSISTENCE] Error rehydrating citizen report: {ex}")

            int_list = self.persistence_repo.load_interventions()
            for int_dict in int_list:
                try:
                    from cyclone_twin.domain.entities import Intervention
                    intervention = Intervention(**int_dict)
                    self.intervention_manager.interventions[intervention.intervention_id] = intervention
                except Exception as ex:
                    logger.warning(f"[PERSISTENCE] Error rehydrating intervention: {ex}")

            audit_list = self.persistence_repo.load_audit_log()
            for audit_dict in audit_list:
                try:
                    from cyclone_twin.domain.entities import InterventionTransitionAudit
                    audit = InterventionTransitionAudit(**audit_dict)
                    self.intervention_manager.audit_log.append(audit)
                except Exception as ex:
                    logger.warning(f"[PERSISTENCE] Error rehydrating audit entry: {ex}")
        except Exception as err:
            logger.warning(f"[PERSISTENCE WARNING] Safe rehydration failure: {err}. Operating with baseline in-memory state.")

    def persist_current_state(self) -> Tuple[bool, Optional[str]]:
        """Saves current mutable scenario state snapshot to persistence repository."""
        try:
            curr_st = self.disaster_state_manager.current_state
            state_dict = {
                "snapshot_id": f"snap-v{curr_st.state_version}",
                "version": curr_st.state_version,
                "scenario_id": getattr(self.data_loader, "scenario_name", "chennai_michaung_default"),
                "water_level_m": getattr(self.data_loader, "water_level_m", 0.0),
                "disabled_segments": list(self.network_engine.disabled_segments),
                "last_cleared_corridor": self.last_cleared_corridor,
                "active_interventions": [i.intervention_id for i in self.intervention_manager.interventions.values() if i.status != "COMPLETED"],
            }
            return self.persistence_repo.save_scenario_state(state_dict)
        except Exception as ex:
            logger.warning(f"[PERSISTENCE WARNING] Persist state error: {ex}")
            return False, str(ex)



state = AppState()


def sync_disaster_state_commit(
    previous_top_candidate: Optional[str] = None,
    current_top_candidate: Optional[str] = None,
    priority_change_reason: Optional[str] = None,
):
    state.initialize()
    access_status = compute_accessibility(
        engine=state.network_engine,
        communities=state.data_loader.communities,
        facilities=state.data_loader.facilities,
    )

    isolated_fac_set = set(access_status.isolated_facilities)
    affected_facs = []
    for fac in state.data_loader.facilities:
        is_iso = fac.id in isolated_fac_set
        affected_facs.append({
            "facility_id": fac.id,
            "name": fac.name,
            "status": "INACCESSIBLE" if is_iso else "ACCESSIBLE",
            "travel_time_min": 999.0 if is_iso else 11.2,
            "baseline_min": 11.2,
            "confidence": 1.0,
        })

    tot_pop = sum(c.population for c in state.data_loader.communities)
    acc_pop = access_status.accessible_population
    iso_pop = max(0, tot_pop - acc_pop)

    pop_dict = {
        "total": tot_pop,
        "accessible": acc_pop,
        "isolated": iso_pop,
        "delta_isolated": iso_pop - (state.disaster_state_manager.current_state.affected_population.get("isolated", 0)),
    }

    hazard_state = {
        "water_level_m": getattr(state.data_loader, "water_level_m", 0.0),
        "flood_source": getattr(state.data_loader, "flood_source", "michaung"),
    }

    obs_list = list(observation_pipeline.observations.values())
    unresolved_conflicts = len([o for o in obs_list if o.status == "rejected_out_of_scope" or "conflict" in str(o.provenance).lower()])
    high_conf_obs = len([o for o in obs_list if o.confidence >= 0.80])

    conf_summary = {
        "confirmed": high_conf_obs,
        "probable": len(obs_list) - high_conf_obs,
        "uncertain": 0,
        "conflicting": unresolved_conflicts,
    }

    new_state, diff = state.disaster_state_manager.commit_transition(
        hazard_state=hazard_state,
        affected_segments=list(state.network_engine.disabled_segments),
        affected_facilities=affected_facs,
        affected_population=pop_dict,
        observations_count=len(obs_list),
        high_confidence_obs=high_conf_obs,
        unresolved_conflicts=unresolved_conflicts,
        active_interventions=[c.corridor_id for c in state.corridors] if state.corridors else [],
        completed_interventions=[state.last_cleared_corridor] if state.last_cleared_corridor else [],
        confidence_summary=conf_summary,
        provenance_summary={"last_graph_source": state.data_loader.graph_source},
        previous_top_candidate=previous_top_candidate,
        current_top_candidate=current_top_candidate,
        priority_change_reason=priority_change_reason,
        observations=obs_list,
    )
    state.persist_current_state()
    return new_state, diff


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
    allow_origin_regex = r"https://.*\.(vercel\.app|web\.app|firebaseapp\.com)"


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
@app.get("/health")
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


@app.get("/network/source")
def network_source():
    """
    GET /network/source
    Phase C: Returns diagnostic information on active RoadNetworkProvider.
    """
    from cyclone_twin.providers import OSMNetworkProvider, CalibratedNetworkProvider, DEFAULT_OSM_BBOX
    return {
        "provider": state.data_loader.graph_source,
        "nodes": state.network_engine.graph.number_of_nodes(),
        "edges": state.network_engine.graph.number_of_edges(),
        "bbox": DEFAULT_OSM_BBOX,
        "fallback_used": state.data_loader.graph_source == "mock_fallback",
        "network_type": "drive",
    }


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

    # Commit state version transition
    sync_disaster_state_commit()

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

    # Commit state version transition
    sync_disaster_state_commit()

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
    Phase G: Generates structured decision-support advisory via Gemini with deterministic fallback.
    Read-only: leaves simulation state 100% unchanged.
    Output constrained to <= 220 chars.
    """
    state.initialize()

    # Look up road names and communities for the corridor
    target_rc = next((rc for rc in state.ranked_corridors if rc.corridor_id == req.corridor_id), None)
    roads = [target_rc.road_classes[0]] if target_rc and target_rc.road_classes else [req.corridor_id]

    from cyclone_twin.advisory_engine import build_decision_context

    access_status = compute_accessibility(
        state.network_engine,
        state.data_loader.communities,
        state.data_loader.facilities,
    )

    context = build_decision_context(
        top_candidate_id=req.corridor_id,
        score_breakdown=req.score_breakdown,
        road_names=roads,
        accessible_population=access_status.accessible_population,
        total_population=sum(c.population for c in state.data_loader.communities),
        isolated_facilities_count=len(access_status.isolated_facilities),
        isolated_communities_count=len(access_status.isolated_communities),
        graph_source=state.data_loader.graph_source,
        weather_source=state.data_loader.flood_source,
        travel_time_model="bpr" if hasattr(state.network_engine.travel_time_model, "alpha") else "static",
        observations_count=len(observation_pipeline.observations),
        reconciled_observations_count=len([o for o in observation_pipeline.observations.values() if o.status == "reconciled"]),
    )

    res = state.advisory_engine.generate_advisory(
        corridor_id=req.corridor_id,
        score_breakdown=req.score_breakdown,
        road_names=roads,
        context=context,
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
            geom_dict = data.get("_geometry_dict")
            if geom_dict is None:
                geom_dict = mapping(geom)
                data["_geometry_dict"] = geom_dict
            seg_id = data.get("physical_segment_id", "")
            is_disabled = seg_id in state.network_engine.disabled_segments
            edge_features.append({
                "type": "Feature",
                "geometry": geom_dict,
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


# ============================================================
# EXTENSION PROVIDER ENDPOINTS (Phases A-G)
# ============================================================

from cyclone_twin.providers import (
    OpenMeteoWeatherProvider,
    HANDFloodModel,
    TimeIndexedFloodForecaster,
    DeterministicVulnerabilityEngine,
    ObservationIngestionPipeline,
    AgenticToolRegistry,
)
from cyclone_twin.domain.entities import ForecastVulnerabilityResponse

weather_provider = OpenMeteoWeatherProvider()
hand_flood_model = HANDFloodModel()
observation_pipeline = ObservationIngestionPipeline()
agent_registry = AgenticToolRegistry(observation_pipeline)


@app.get("/forecast")
def get_forecast(
    horizon_hours: Optional[int] = Query(None, description="Optional forecast horizon offset in hours (0, 2, 4, 8, 24)"),
    lat: float = 13.0827,
    lon: float = 80.2707,
):
    """GET /forecast - Fetch weather forecast representation for specified location and horizon."""
    forecast = weather_provider.fetch_forecast(lat, lon, horizon_hours=horizon_hours)
    res = forecast.model_dump(mode="json")
    res["reference_time"] = datetime.now(timezone.utc).isoformat()
    res["forecast_time"] = forecast.timestamp.isoformat() if hasattr(forecast.timestamp, "isoformat") else str(forecast.timestamp)
    res["horizon"] = f"+{horizon_hours}H" if horizon_hours else "NOW"
    res["horizon_hours"] = horizon_hours or 0
    res["rainfall_mm"] = forecast.precipitation_mm
    res["weather_source"] = forecast.provider
    res["is_projected_forecast"] = True
    return res


@app.get("/forecast/timeline")
def get_forecast_timeline(
    horizon: str = Query("NOW", description="Forecast horizon: NOW, +2H, +4H, +8H"),
    lat: float = 13.0827,
    lon: float = 80.2707,
):
    """
    GET /forecast/timeline
    Milestone L1/L3: Read-only Forecast Timeline calculation across horizons (NOW, +2H, +4H, +8H).
    GUARANTEE: 0 mutation to operational Disaster State, NetworkEngine, or Observations.
    """
    state.initialize()
    horizon_clean = str(horizon).upper().replace("+", "").strip()
    horizon_map = {
        "NOW": 0,
        "0H": 0,
        "0": 0,
        "2H": 2,
        "2": 2,
        "4H": 4,
        "4": 4,
        "8H": 8,
        "8": 8,
    }
    horizon_hours = horizon_map.get(horizon_clean, 0)

    # Reference time & derived target time
    ref_time = datetime.now(timezone.utc)
    target_time = ref_time + timedelta(hours=horizon_hours)

    # 1. Fetch weather forecast for selected horizon (read-only)
    forecast = weather_provider.fetch_forecast(lat, lon, horizon_hours=horizon_hours)

    # 2. Compute inundation scenario (read-only)
    flood_scenario = hand_flood_model.compute_inundation(forecast)

    # 3. Identify predicted disabled segments (read-only)
    dis_seg_ids, _ = identify_flood_disabled_segments(state.data_loader.graph, flood_scenario.flood_geojson)

    # 4. Read-only accessibility prediction on temporary engine instance (0 state mutation)
    from cyclone_twin.network_engine import NetworkEngine

    temp_engine = NetworkEngine(graph=state.data_loader.graph)
    temp_engine.set_travel_time_model(state.network_engine.travel_time_model)
    temp_engine.disable_segments(dis_seg_ids)

    pred_access = compute_accessibility(
        engine=temp_engine,
        communities=state.data_loader.communities,
        facilities=state.data_loader.facilities,
    )

    # 5. Milestone L2: Construct structured VulnerabilityForecast domain model
    from cyclone_twin.domain.entities import RoadVulnerability, VulnerabilityForecast

    road_vulns: List[RoadVulnerability] = []
    for seg_id in dis_seg_ids:
        road_vulns.append(
            RoadVulnerability(
                segment_id=seg_id,
                forecast_time=target_time,
                predicted_depth_m=flood_scenario.water_level_m,
                closure_threshold_m=0.30,
                closure_probability=0.95 if flood_scenario.water_level_m > 0.30 else 0.40,
                travel_time_multiplier=3.5 if flood_scenario.water_level_m > 0.30 else 1.5,
                population_impact=15000,
                hospital_impact=1,
                vulnerability_score=min(1.0, round(flood_scenario.water_level_m / 1.5, 2)),
                confidence=0.85,
                is_predicted=True,
            )
        )

    tot_pop = sum(c.population for c in state.data_loader.communities)
    pred_iso_pop = max(0, tot_pop - pred_access.accessible_population)

    vuln_forecast = VulnerabilityForecast(
        forecast_id=f"VULN-FCST-{uuid.uuid4().hex[:8]}",
        scenario_id=flood_scenario.scenario_id,
        forecast_time=target_time,
        generated_at=ref_time,
        reference_time=ref_time,
        horizon_hours=horizon_hours,
        weather_source=forecast.provider,
        flood_model=flood_scenario.source,
        network_source=state.data_loader.graph_source,
        rainfall_mm=forecast.precipitation_mm,
        water_level_m=flood_scenario.water_level_m,
        predicted_population_at_risk=pred_iso_pop,
        predicted_population_isolated=pred_iso_pop,
        predicted_hospitals_at_risk=len(pred_access.isolated_facilities),
        predicted_hospitals_inaccessible=len(pred_access.isolated_facilities),
        road_vulnerabilities=road_vulns,
        confidence=0.90 if forecast.provider == "open_meteo" else 0.85,
        provenance={
            "weather_provider": forecast.provider,
            "flood_model": flood_scenario.source,
            "network_source": state.data_loader.graph_source,
            "scenario_type": "read_only_l2_projection",
        },
        assumptions=[
            "Precipitation remains constant over forecast window",
            "HAND topography assumes uniform drainage infiltration",
        ],
        limitations=[
            "BPR congestion dynamics not modeled in static travel-time forecast",
            "No real-time GCC pump station state incorporated",
        ],
        is_projected_forecast=True,
    )

    horizon_label = (
        "+2H" if horizon_hours == 2 else "+4H" if horizon_hours == 4 else "+8H" if horizon_hours == 8 else "NOW"
    )

    return {
        "horizon": horizon_label,
        "horizon_hours": horizon_hours,
        "reference_time": ref_time.isoformat(),
        "target_time": target_time.isoformat(),
        "weather": forecast.model_dump(mode="json"),
        "flood": flood_scenario.model_dump(mode="json"),
        "predicted_disabled_segments_count": len(dis_seg_ids),
        "predicted_accessibility": {
            "accessible_population": pred_access.accessible_population,
            "isolated_facilities": pred_access.isolated_facilities,
            "isolated_communities": pred_access.isolated_communities,
        },
        "vulnerability_forecast": vuln_forecast.model_dump(mode="json"),
        "is_projected_forecast": True,
    }


@app.get(
    "/forecast/vulnerability",
    response_model=ForecastVulnerabilityResponse,
    summary="Fetch infrastructure vulnerability projections for a forecast horizon",
    description="Milestone L5: Exposes L4 vulnerability summary and segment assessments for a target horizon (NOW, +2H, +4H, +8H). Read-only projection.",
)
def get_forecast_vulnerability(
    horizon: str = Query("NOW", description="Forecast horizon: NOW, +2H, +4H, +8H"),
    lat: float = 13.0827,
    lon: float = 80.2707,
):
    """GET /forecast/vulnerability - Read-only forecast vulnerability projection for a target horizon."""
    state.initialize()
    raw_horizon = str(horizon).upper().strip()
    clean_h = raw_horizon.replace("+", "")

    valid_map = {
        "NOW": 0,
        "0H": 0,
        "0": 0,
        "2H": 2,
        "2": 2,
        "4H": 4,
        "4": 4,
        "8H": 8,
        "8": 8,
    }

    if clean_h not in valid_map and raw_horizon not in valid_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid forecast horizon '{horizon}'. Supported horizons: NOW, +2H, +4H, +8H.",
        )

    horizon_hours = valid_map.get(clean_h, valid_map.get(raw_horizon, 0))
    label = "+2H" if horizon_hours == 2 else "+4H" if horizon_hours == 4 else "+8H" if horizon_hours == 8 else "NOW"

    ref_time = datetime.now(timezone.utc)

    forecaster = TimeIndexedFloodForecaster(weather_provider=weather_provider, flood_model=hand_flood_model)
    vuln_forecast = forecaster.generate_horizon_forecast(
        horizon_hours=horizon_hours,
        reference_time=ref_time,
        graph=state.data_loader.graph,
        communities=state.data_loader.communities,
        facilities=state.data_loader.facilities,
        travel_time_model=state.network_engine.travel_time_model,
        lat=lat,
        lon=lon,
    )

    vulnerability_engine = DeterministicVulnerabilityEngine()
    summary = vulnerability_engine.evaluate_forecast(vuln_forecast)

    return ForecastVulnerabilityResponse(
        horizon=label,
        horizon_hours=horizon_hours,
        reference_time=ref_time,
        forecast_time=vuln_forecast.forecast_time,
        generated_at=ref_time,
        weather_source=vuln_forecast.weather_source,
        flood_model=vuln_forecast.flood_model,
        network_source=vuln_forecast.network_source,
        vulnerability_summary=summary,
        vulnerability_assessments=summary.highest_vulnerability_segments,
        provenance=vuln_forecast.provenance,
        assumptions=vuln_forecast.assumptions,
        limitations=vuln_forecast.limitations,
        is_projected_forecast=True,
    )


# -------------------------------------------------------------------
# L7 — BPR-Aware Counterfactual Intervention Ranking
# -------------------------------------------------------------------

from cyclone_twin.providers.counterfactual_engine import (
    CounterfactualRankingEngine,
    CounterfactualRankingResponse,
)
from cyclone_twin.decision_engine import (
    InterventionCandidate,
    MultiObjectiveWeights,
)

_counterfactual_engine = CounterfactualRankingEngine(bpr_alpha=0.15, bpr_beta=4.0)


@app.get(
    "/forecast/interventions",
    response_model=CounterfactualRankingResponse,
    summary="BPR-aware counterfactual intervention ranking against forecast network",
    description=(
        "Milestone L7: Read-only endpoint. "
        "Ranks candidate interventions by evaluating them against the projected "
        "flood/network state at the requested forecast horizon using the BPR "
        "travel-time model. "
        "GUARANTEE: Does NOT mutate operational DisasterState or NetworkEngine. "
        "This is decision SUPPORT — human approval is required before any "
        "intervention is executed."
    ),
)
def get_forecast_interventions(
    horizon: str = Query("NOW", description="Forecast horizon: NOW, +2H, +4H, +8H"),
    weight_preset: str = Query(
        "life_safety",
        description="Weight preset: life_safety | equity_priority | rapid_clearance",
    ),
    lat: float = 13.0827,
    lon: float = 80.2707,
):
    """
    GET /forecast/interventions

    Evaluates a standard set of corridor-clearance candidates against the projected
    forecast network for the chosen horizon.

    Reads:
    - L3/L5 VulnerabilityForecast -> projected disabled segments
    - Operational graph topology (read-only copy for counterfactual evaluation)

    Writes: NOTHING. Zero state mutation.
    """
    state.initialize()

    # --- 1. Parse horizon ---
    horizon_clean = str(horizon).upper().replace("+", "").strip()
    horizon_map = {"NOW": 0, "0H": 0, "0": 0, "2H": 2, "2": 2, "4H": 4, "4": 4, "8H": 8, "8": 8}
    if horizon_clean not in horizon_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid forecast horizon '{horizon}'. Supported: NOW, +2H, +4H, +8H.",
        )
    horizon_hours = horizon_map[horizon_clean]

    # --- 2. Resolve scoring weights ---
    preset_map = {
        "life_safety": MultiObjectiveWeights.life_safety,
        "equity_priority": MultiObjectiveWeights.equity_priority,
        "rapid_clearance": MultiObjectiveWeights.rapid_clearance,
    }
    preset_fn = preset_map.get(weight_preset.lower())
    if preset_fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown weight_preset '{weight_preset}'. Valid: life_safety, equity_priority, rapid_clearance.",
        )
    weights = preset_fn()

    # --- 3. Generate forecast (read-only, L3/L5 pipeline) ---
    forecaster = TimeIndexedFloodForecaster(
        weather_provider=weather_provider, flood_model=hand_flood_model
    )
    ref_time = datetime.now(timezone.utc)
    vuln_forecast = forecaster.generate_horizon_forecast(
        horizon_hours=horizon_hours,
        reference_time=ref_time,
        graph=state.data_loader.graph,
        communities=state.data_loader.communities,
        facilities=state.data_loader.facilities,
        travel_time_model=state.network_engine.travel_time_model,
        lat=lat,
        lon=lon,
    )

    # --- 4. Build default candidate set from graph corridors ---
    # Use the existing operational ranked corridors as the candidate pool.
    # Each corridor becomes one InterventionCandidate evaluated against the forecast.
    candidates: List[InterventionCandidate] = []
    corridor_source = state.ranked_corridors if state.ranked_corridors else state.corridors

    for i, corridor in enumerate(corridor_source[:20]):  # Cap at top-20 to bound latency
        seg_ids: List[str] = []
        if hasattr(corridor, "segment_ids") and corridor.segment_ids:
            seg_ids = list(corridor.segment_ids)
        elif hasattr(corridor, "corridor_id"):
            seg_ids = [str(corridor.corridor_id)]

        cost = getattr(corridor, "estimated_cost", 0.0) or 0.0
        diff = getattr(corridor, "difficulty_score", 0.0) or 0.0
        length = getattr(corridor, "total_length_m", 0.0) or 0.0
        name = getattr(corridor, "name", f"Corridor-{i+1}")
        ctype = getattr(corridor, "intervention_type", "CORRIDOR_CLEARANCE")

        candidates.append(
            InterventionCandidate(
                candidate_id=f"CF-CAND-{i+1:03d}",
                name=name,
                intervention_type=ctype,
                physical_segment_ids=seg_ids,
                estimated_cost=float(cost),
                difficulty_score=float(diff),
                total_length_m=float(length),
            )
        )

    # If no corridors available, generate synthetic candidates from forecast disabled segments
    if not candidates:
        forecast_disabled = [rv.segment_id for rv in vuln_forecast.road_vulnerabilities]
        for i, seg_id in enumerate(forecast_disabled[:10]):
            candidates.append(
                InterventionCandidate(
                    candidate_id=f"CF-FCST-{i+1:03d}",
                    name=f"Clear forecast-disabled segment {seg_id}",
                    intervention_type="CORRIDOR_CLEARANCE",
                    physical_segment_ids=[seg_id],
                    estimated_cost=float(50000 + i * 10000),
                    difficulty_score=round(0.3 + i * 0.05, 2),
                    total_length_m=float(500 + i * 100),
                )
            )

    # --- 5. Run BPR-aware counterfactual ranking (read-only) ---
    ranking_response = _counterfactual_engine.rank_against_forecast(
        candidates=candidates,
        vuln_forecast=vuln_forecast,
        operational_graph=state.data_loader.graph,
        communities=state.data_loader.communities,
        facilities=state.data_loader.facilities,
        travel_time_model=state.network_engine.travel_time_model,
        weights=weights,
    )

    return ranking_response


@app.post("/observations/submit")
def submit_observation(payload: Dict[str, Any]):
    """
    POST /observations/submit
    Ingests, validates, and stores ground report or sensor observation.
    Catches validation errors and returns 400 Bad Request.
    Optionally reconciles into simulation state if reconcile=True.
    """
    payload = payload or {}
    try:
        lat = payload.get("lat", 13.01)
        lon = payload.get("lon", 80.22)
        obs_type = payload.get("observation_type", "road_blockage")
        source = payload.get("source", "citizen_report")
        severity = payload.get("severity", "high")
        confidence = payload.get("confidence", 0.85)
        affected_node_ids = payload.get("affected_node_ids")
        affected_segment_id = payload.get("affected_segment_id")
        raw_text = payload.get("raw_text")
        observation_id = payload.get("observation_id")
        timestamp = payload.get("timestamp")
        value = payload.get("value")
        should_reconcile = bool(payload.get("reconcile", False))

        obs = observation_pipeline.submit_report(
            lat=lat,
            lon=lon,
            observation_type=obs_type,
            source=source,
            severity=severity,
            confidence=confidence,
            affected_node_ids=affected_node_ids,
            affected_segment_id=affected_segment_id,
            raw_text=raw_text,
            observation_id=observation_id,
            timestamp=timestamp,
            value=value,
        )

        reconciliation_result = None
        if should_reconcile:
            state.initialize()
            reconciliation_result = observation_pipeline.reconcile_observations(state.network_engine)
            sync_disaster_state_commit()

        res_dict = obs.model_dump(mode="json")
        if reconciliation_result:
            res_dict["reconciliation"] = reconciliation_result
        return res_dict
    except ValueError as err:
        logger.warning("Observation validation failed: %s", err)
        raise HTTPException(status_code=400, detail=str(err))


@app.get("/observations")
def get_observations(
    source_type: Optional[str] = None,
    observation_type: Optional[str] = None,
    min_confidence: float = 0.50,
    limit: int = 50,
):
    """
    GET /observations
    Returns bounded list of active ground observations matching optional criteria.
    """
    active = observation_pipeline.get_active_observations(min_confidence=min_confidence)

    if source_type:
        st_norm = source_type.lower()
        active = [o for o in active if o.source_type.lower() == st_norm or o.source.lower() == st_norm]

    if observation_type:
        ot_norm = observation_type.upper()
        active = [o for o in active if o.observation_type.upper() == ot_norm]

    bounded_active = active[: max(1, min(limit, 200))]
    return {
        "count": len(bounded_active),
        "total_store_size": len(observation_pipeline.observations),
        "max_store_capacity": observation_pipeline.max_capacity,
        "observations": [o.model_dump(mode="json") for o in bounded_active],
    }


@app.post("/observations/reconcile")
def reconcile_observations():
    """
    POST /observations/reconcile
    Executes deterministic reconciliation policy converting active ground observation evidence into controlled NetworkEngine model overrides.
    """
    state.initialize()
    result = observation_pipeline.reconcile_observations(state.network_engine)
    sync_disaster_state_commit()
    return result



@app.get("/agent/tools")
def list_agent_tools():
    """GET /agent/tools - Return registered tool schemas for AI orchestrator."""
    return {
        "tools": [
            {
                "name": "get_weather_forecast",
                "description": "Fetch live or calibrated precipitation and wind forecast for target coordinates",
            },
            {
                "name": "get_flood_state",
                "description": "Calculate flood inundation scenario using HAND (Height Above Nearest Drainage)",
            },
            {
                "name": "submit_ground_observation",
                "description": "Log validated citizen or sensor observation into Digital Twin state",
            },
            {
                "name": "extract_field_evidence",
                "description": "Extract structured observation evidence from field report (Read-Only, 0 simulation mutation)",
            },
        ]
    }


@app.post("/scenario/dynamic")
def scenario_dynamic(payload: Optional[Dict[str, Any]] = None):
    """
    POST /scenario/dynamic
    Phase B & D: Dynamic Weather -> Flood -> Disruption -> Capacity-aware Accessibility pipeline.
    Accepts optional { precipitation_mm, water_level_m, use_live_weather, hand_threshold_m, travel_time_model, bpr_alpha, bpr_beta }.
    Atomically calculates scenario and commits to state on success.
    """
    payload = payload or {}
    use_live = bool(payload.get("use_live_weather", False))
    precip_override = payload.get("precipitation_mm")

    if precip_override is not None:
        try:
            precip_val = float(precip_override)
            if precip_val < 0.0:
                raise ValueError("precipitation_mm must be non-negative")
        except (ValueError, TypeError) as err:
            raise HTTPException(status_code=400, detail=f"Invalid precipitation_mm: {err}")

    # Phase D: Travel time model selection (default "static")
    travel_time_model_name = str(payload.get("travel_time_model", "static")).lower()
    if travel_time_model_name not in ("static", "bpr"):
        raise HTTPException(status_code=400, detail=f"Invalid travel_time_model '{travel_time_model_name}'. Must be 'static' or 'bpr'.")

    bpr_alpha = float(payload.get("bpr_alpha", 0.15))
    bpr_beta = float(payload.get("bpr_beta", 4.0))

    if bpr_alpha < 0.0 or bpr_beta < 0.0:
        raise HTTPException(status_code=400, detail="bpr_alpha and bpr_beta must be non-negative.")

    from cyclone_twin.providers.travel_time_model import StaticTravelTimeModel, BPRCapacityTravelTimeModel

    if travel_time_model_name == "bpr":
        tt_model = BPRCapacityTravelTimeModel(alpha=bpr_alpha, beta=bpr_beta)
    else:
        tt_model = StaticTravelTimeModel()

    # 1. Fetch weather forecast
    if use_live:
        forecast = weather_provider.fetch_forecast()
    else:
        precip_val = float(precip_override) if precip_override is not None else 180.0
        from cyclone_twin.domain.entities import WeatherForecast
        from datetime import datetime, timezone
        forecast = WeatherForecast(
            timestamp=datetime.now(timezone.utc),
            precipitation_mm=precip_val,
            provider="manual_dynamic_scenario",
        )

    # 2. Compute dynamic HAND flood scenario
    flood_scenario = hand_flood_model.compute_inundation(forecast)
    flood_geom = flood_scenario.flood_geojson

    # 3. Identify disabled segments & edges atomically
    dis_seg_ids, _ = identify_flood_disabled_segments(state.data_loader.graph, flood_geom)

    # 4. Atomic transaction commit
    state.network_engine.set_travel_time_model(tt_model)
    state.network_engine.restore_all()
    state.network_engine.disable_segments(dis_seg_ids)
    state.data_loader.flood_geojson = flood_geom

    # 5. Calculate resulting accessibility
    access_status = compute_accessibility(
        state.network_engine,
        state.data_loader.communities,
        state.data_loader.facilities,
    )

    # 6. Extract corridors for ranking
    state.corridors = CorridorEngine.cluster_disabled_segments_into_corridors(
        state.data_loader.graph,
        state.network_engine.disabled_segments,
    )

    sync_disaster_state_commit()

    return {

        "scenario_id": flood_scenario.scenario_id,
        "precipitation_mm": forecast.precipitation_mm,
        "water_level_m": flood_scenario.water_level_m,
        "disabled_edges_count": len(dis_seg_ids),
        "corridors_count": len(state.corridors),
        "accessibility": {
            "accessible_population": access_status.accessible_population,
            "isolated_facilities": access_status.isolated_facilities,
            "isolated_communities": access_status.isolated_communities,
        },
        "provenance": {
            "weather_source": forecast.provider,
            "flood_model": flood_scenario.source,
            "network_source": state.data_loader.graph_source,
            "hand_threshold_m": flood_scenario.hand_threshold_m,
            "travel_time_model": travel_time_model_name,
            "bpr_alpha": bpr_alpha if travel_time_model_name == "bpr" else None,
            "bpr_beta": bpr_beta if travel_time_model_name == "bpr" else None,
            "fallback_used": forecast.provider == "calibrated_fallback",
            "scenario_type": "dynamic_phase_b",
        },
    }


@app.post("/decision/evaluate")
def decision_evaluate(payload: Optional[Dict[str, Any]] = None):
    """
    POST /decision/evaluate
    Phase F: Multi-Objective Intervention Decision Engine.
    Evaluates intervention candidates counterfactually across hospital recovery, population recovery,
    travel time reduction, social equity/vulnerability recovery, and cost/difficulty.
    Computes Pareto front and returns deterministic ranking.
    """
    state.initialize()
    payload = payload or {}

    from cyclone_twin.decision_engine import (
        MultiObjectiveDecisionEngine,
        MultiObjectiveWeights,
        InterventionCandidate,
    )

    # Parse weights
    weights_dict = payload.get("weights")
    if weights_dict:
        try:
            weights = MultiObjectiveWeights(**weights_dict)
        except Exception as err:
            raise HTTPException(status_code=400, detail=f"Invalid weights: {err}")
    else:
        weights = MultiObjectiveWeights.life_safety()

    # Parse or auto-generate candidates
    candidates_raw = payload.get("candidates")
    candidates: List[InterventionCandidate] = []

    if candidates_raw:
        for c in candidates_raw:
            try:
                candidates.append(InterventionCandidate(**c))
            except Exception as err:
                raise HTTPException(status_code=400, detail=f"Invalid candidate proposal: {err}")
    else:
        # Default: auto-generate candidates from active clusters / corridors
        if not state.corridors:
            _ = flood_apply(FloodApplyRequest())

        for c in state.corridors:
            candidates.append(
                InterventionCandidate(
                    candidate_id=c.corridor_id,
                    name=f"Clear {c.corridor_id} ({', '.join(c.road_classes) if c.road_classes else 'Arterial Road'})",
                    intervention_type="CORRIDOR_CLEARANCE",
                    physical_segment_ids=c.physical_segment_ids,
                    total_length_m=c.total_length_m,
                    road_classes=c.road_classes,
                    geometry=c.geometry,
                )
            )

    decision_engine = MultiObjectiveDecisionEngine(state.network_engine)
    ranked = decision_engine.rank_interventions(
        candidates=candidates,
        communities=state.data_loader.communities,
        facilities=state.data_loader.facilities,
        weights=weights,
    )

    pareto_candidates = [r.candidate_id for r in ranked if r.pareto_optimal]

    return {
        "count": len(ranked),
        "pareto_optimal_count": len(pareto_candidates),
        "pareto_optimal_candidates": pareto_candidates,
        "weights": weights.model_dump(mode="json"),
        "ranked_interventions": [r.model_dump(mode="json") for r in ranked],
    }


# ============================================================
# PHASE H: MULTIMODAL FIELD INTELLIGENCE ENDPOINTS
# ============================================================

@app.post("/observations/multimodal/extract")
async def extract_multimodal_evidence(
    request: Request,
    image: Optional[UploadFile] = File(None),
    user_description: Optional[str] = Form(None),
    source_type: Optional[str] = Form("field_team"),
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    timestamp: Optional[str] = Form(None),
):
    """
    POST /observations/multimodal/extract
    Phase H Step 1: Extract structured evidence from field photograph or JSON report.
    READ-ONLY: Guarantees 0 state mutation (state_before == state_after).
    Produces intermediate MultimodalEvidenceExtraction contract.
    """
    try:
        # 1. Check if multipart file upload
        if image is not None:
            contents = await image.read()
            filename = image.filename or "uploaded_evidence.jpg"
            content_type = image.content_type or "image/jpeg"

            extraction = state.multimodal_service.extract_evidence_from_image(
                image_bytes=contents,
                filename=filename,
                mime_type=content_type,
                user_description=user_description,
                source_type=source_type or "field_team",
                user_lat=lat,
                user_lon=lon,
                timestamp=timestamp,
            )
            return extraction.model_dump(mode="json")

        # 2. Otherwise parse JSON report body
        try:
            body_json = await request.json()
        except Exception:
            body_json = {}

        if not body_json:
            raise ValueError("No image file or JSON report payload provided for evidence extraction")

        extraction = state.multimodal_service.extract_evidence_from_report(body_json)
        return extraction.model_dump(mode="json")

    except ValueError as err:
        logger.warning("Multimodal extraction failed validation: %s", err)
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as exc:
        logger.error("Multimodal extraction internal error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Extraction failure: {str(exc)}")


@app.post("/observations/multimodal/ingest")
def ingest_multimodal_evidence(payload: Dict[str, Any]):
    """
    POST /observations/multimodal/ingest
    Phase H Step 2: Ingest extracted evidence through Phase E validation & reconciliation into simulation state.
    ONLY path through which field evidence can update NetworkEngine and trigger accessibility recomputation.
    Accepts: { "extraction_id": str, "location_override": [lat, lon] } or full extraction dictionary.
    """
    state.initialize()
    payload = payload or {}

    extraction_ref = payload.get("extraction_id") or payload.get("extraction")
    if not extraction_ref:
        raise HTTPException(status_code=400, detail="Missing required 'extraction_id' or 'extraction' payload")

    location_override = None
    loc_override_raw = payload.get("location_override") or payload.get("location")
    if isinstance(loc_override_raw, (list, tuple)) and len(loc_override_raw) == 2:
        try:
            location_override = (float(loc_override_raw[0]), float(loc_override_raw[1]))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid location_override coordinates")

    try:
        from .ranking_engine import compute_accessibility as compute_acc

        class AccEngineAdapter:
            def compute_accessibility(self, graph):
                return compute_acc(state.network_engine, state.data_loader.communities, state.data_loader.facilities)

        result = state.multimodal_service.ingest_extracted_evidence(
            extraction_id_or_obj=extraction_ref,
            engine=state.network_engine,
            accessibility_engine=AccEngineAdapter(),
            location_override=location_override,
            client_observation_id=payload.get("client_observation_id") or payload.get("client_id"),
        )
        sync_disaster_state_commit()
        return result
    except ValueError as val_err:
        logger.warning("Multimodal ingestion failed Phase E validation/reconciliation: %s", val_err)
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        logger.error("Multimodal ingestion internal error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Ingestion failure: {str(exc)}")


@app.get("/observations/timeline")
def get_observation_timeline():
    """
    GET /observations/timeline
    Returns chronological auditable timeline of field intelligence pipeline events.
    """
    timeline = state.multimodal_service.get_timeline()
    return {
        "count": len(timeline),
        "timeline": timeline,
    }


@app.post("/observations/sync")
def sync_offline_observations(payload: Dict[str, Any]):
    """
    POST /observations/sync
    Phase I: Batch sync endpoint for offline-captured field observations.
    Executes Phase E input validation and deterministic reconciliation for each item idempotently.
    Accepts: { "client_id": str, "observations": [...] }
    """
    state.initialize()
    payload = payload or {}
    observations_batch = payload.get("observations") or []
    if not isinstance(observations_batch, list):
        raise HTTPException(status_code=400, detail="Invalid observations payload. Expected a list.")

    from .ranking_engine import compute_accessibility as compute_acc

    class AccEngineAdapter:
        def compute_accessibility(self, graph):
            return compute_acc(state.network_engine, state.data_loader.communities, state.data_loader.facilities)

    res = state.multimodal_service.sync_batch(
        observations=observations_batch,
        engine=state.network_engine,
        accessibility_engine=AccEngineAdapter(),
    )
    sync_disaster_state_commit()
    return res


# ============================================================
# PHASE L8: VOICE EVIDENCE PIPELINE ENDPOINTS
# ============================================================

@app.post("/observations/voice/transcribe")
async def transcribe_voice_evidence(
    request: Request,
    audio: Optional[UploadFile] = File(None),
    source_type: Optional[str] = Form("field_team"),
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    duration_sec: Optional[float] = Form(None),
    language_hint: Optional[str] = Form(None),
):
    """
    POST /observations/voice/transcribe
    Phase L8 Step 1: Transcribe audio recording and extract candidate evidence.
    READ-ONLY: Guarantees 0 state mutation (state_before == state_after).
    Produces VoiceArtifactMetadata, VoiceTranscriptionResult, and MultimodalEvidenceExtraction contract.
    """
    try:
        if audio is None:
            raise ValueError("No audio file provided for voice transcription")

        contents = await audio.read()
        filename = audio.filename or "field_voice_report.wav"
        content_type = audio.content_type or "audio/wav"

        artifact, transcription, extraction = state.voice_pipeline.transcribe_and_extract(
            audio_bytes=contents,
            filename=filename,
            content_type=content_type,
            source_type=source_type or "field_team",
            user_lat=lat,
            user_lon=lon,
            duration_sec=duration_sec,
            language_hint=language_hint,
        )

        return {
            "artifact": artifact.model_dump(mode="json"),
            "transcription": transcription.model_dump(mode="json"),
            "extraction": extraction.model_dump(mode="json"),
        }

    except ValueError as err:
        logger.warning("Voice transcription failed validation: %s", err)
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as exc:
        logger.error("Voice transcription internal error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Voice transcription failure: {str(exc)}")


@app.post("/observations/voice/ingest")
def ingest_voice_evidence(payload: Dict[str, Any]):
    """
    POST /observations/voice/ingest
    Phase L8 Step 2: Ingest extracted voice evidence through Phase E validation & reconciliation into simulation state.
    ONLY path through which voice evidence can update NetworkEngine and trigger accessibility recomputation.
    Accepts: { "extraction_id": str, "location_override": [lat, lon] }
    """
    state.initialize()
    payload = payload or {}

    extraction_ref = payload.get("extraction_id") or payload.get("extraction")
    if not extraction_ref:
        raise HTTPException(status_code=400, detail="Missing required 'extraction_id' or 'extraction' payload")

    location_override = None
    loc_override_raw = payload.get("location_override") or payload.get("location")
    if isinstance(loc_override_raw, (list, tuple)) and len(loc_override_raw) == 2:
        try:
            location_override = (float(loc_override_raw[0]), float(loc_override_raw[1]))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid location_override coordinates")

    try:
        from .ranking_engine import compute_accessibility as compute_acc

        class AccEngineAdapter:
            def compute_accessibility(self, graph):
                return compute_acc(state.network_engine, state.data_loader.communities, state.data_loader.facilities)

        result = state.voice_pipeline.ingest_voice_evidence(
            extraction_id=extraction_ref if isinstance(extraction_ref, str) else extraction_ref.get("extraction_id"),
            engine=state.network_engine,
            accessibility_engine=AccEngineAdapter(),
            location_override=location_override,
            client_observation_id=payload.get("client_observation_id") or payload.get("client_id"),
        )
        sync_disaster_state_commit()
        return result
    except ValueError as val_err:
        logger.warning("Voice ingestion failed Phase E validation/reconciliation: %s", val_err)
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        logger.error("Voice ingestion internal error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Ingestion failure: {str(exc)}")


# ============================================================
# PHASE L9: DRAINAGE / GCC INFRASTRUCTURE EVIDENCE ENDPOINTS
# ============================================================

@app.get("/infrastructure/drainage")
def get_drainage_infrastructure(
    catchment: Optional[str] = Query(None, description="Optional catchment zone filter (e.g. GCC_South_Adyar)"),
    status: Optional[str] = Query(None, description="Optional blockage status filter (e.g. partially_blocked)"),
):
    """
    GET /infrastructure/drainage
    Phase L9: Returns GCC stormwater drainage infrastructure assets, conditions, provenance,
    and explicit limitations.

    PURE READ-ONLY: Guarantees 0 state mutation on NetworkEngine, DisasterState, or HAND terrain.
    """
    try:
        summary = state.drainage_provider.get_drainage_summary(catchment_zone=catchment)
        if status:
            filtered_assets = state.drainage_provider.get_drainage_assets(
                catchment_zone=catchment,
                blockage_status=status,
            )
            summary.assets = filtered_assets
            summary.total_assets = len(filtered_assets)
            summary.blocked_assets_count = sum(
                1 for a in filtered_assets if a.blockage_status in ("partially_blocked", "severely_blocked", "inoperable")
            )
            summary.degraded_connectivity_count = sum(
                1 for a in filtered_assets if a.connectivity_status in ("degraded", "disconnected", "missing_link")
            )

        return summary.model_dump(mode="json")
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        logger.error("Drainage infrastructure API error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Drainage query failed: {str(exc)}")


# ============================================================
# PHASE L10: CITIZEN / PGIS EVIDENCE PIPELINE ENDPOINTS
# ============================================================

@app.post("/observations/citizen")
async def submit_citizen_observation(
    request: Request,
    photo: Optional[UploadFile] = File(None),
    report_type: Optional[str] = Form(None),
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    description: Optional[str] = Form(None),
    water_depth_m: Optional[float] = Form(None),
    confidence: Optional[float] = Form(0.65),
    severity: Optional[str] = Form("medium"),
    reporter_id: Optional[str] = Form(None),
    is_anonymous: Optional[bool] = Form(True),
):
    """
    POST /observations/citizen
    Phase L10: Submits a ground-level citizen PGIS observation (with optional photo metadata).
    READ-ONLY AT SUBMISSION: Guarantees 0 state mutation (state_before == state_after).
    Places observation into Phase E observation pipeline as UNTRUSTED evidence.
    """
    try:
        payload_json = {}
        if photo is None and report_type is None and lat is None and lon is None:
            try:
                payload_json = await request.json()
            except Exception:
                payload_json = {}

        # Extract parameters from Form or JSON
        r_type = report_type or payload_json.get("report_type") or "ROAD_FLOODED"
        r_lat = lat if lat is not None else payload_json.get("latitude") if payload_json.get("latitude") is not None else payload_json.get("lat")
        r_lon = lon if lon is not None else payload_json.get("longitude") if payload_json.get("longitude") is not None else payload_json.get("lon")
        r_desc = description if description is not None else payload_json.get("description")
        r_depth = water_depth_m if water_depth_m is not None else payload_json.get("water_depth_m")
        r_conf = confidence if confidence is not None else payload_json.get("confidence", 0.65)
        r_sev = severity or payload_json.get("severity", "medium")
        r_reporter = reporter_id or payload_json.get("reporter_id")
        r_anon = is_anonymous if is_anonymous is not None else payload_json.get("is_anonymous", True)

        if r_lat is None or r_lon is None:
            raise ValueError("Missing required geographic coordinates (latitude and longitude)")

        # Handle optional photo file metadata
        media_filename, media_content_type, media_size = None, None, None
        if photo is not None:
            photo_bytes = await photo.read()
            media_filename = photo.filename or "citizen_photo.jpg"
            media_content_type = photo.content_type or "image/jpeg"
            media_size = len(photo_bytes)

        citizen_obs, infra_obs = state.citizen_pipeline.submit_citizen_report(
            lat=r_lat,
            lon=r_lon,
            report_type=r_type,
            description=r_desc,
            water_depth_m=r_depth,
            confidence=r_conf,
            severity=r_sev,
            reporter_id=r_reporter,
            is_anonymous=r_anon,
            media_filename=media_filename,
            media_content_type=media_content_type,
            media_size_bytes=media_size,
            client_observation_id=payload_json.get("client_observation_id"),
        )

        state.persistence_repo.save_citizen_observation(citizen_obs.model_dump(mode="json"))

        return {
            "status": "submitted",
            "citizen_report": citizen_obs.model_dump(mode="json"),
            "observation": infra_obs.model_dump(mode="json"),
            "duplicate_candidate": citizen_obs.duplicate_candidate_id is not None,
            "has_conflicts": citizen_obs.has_conflicting_reports,
            "provenance_lineage": {
                "source": "citizen_pgis",
                "validation_status": infra_obs.validated,
                "reconciliation_status": infra_obs.status,
                "state_mutated": False,
            },
        }

    except ValueError as err:
        logger.warning("Citizen observation submission failed validation: %s", err)
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as exc:
        logger.error("Citizen observation internal error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Submission failure: {str(exc)}")


@app.get("/observations/citizen")
def get_citizen_observations(
    report_type: Optional[str] = Query(None, description="Optional filter by report type"),
    status: Optional[str] = Query(None, description="Optional filter by report status"),
):
    """
    GET /observations/citizen
    Phase L10: Returns list of submitted citizen PGIS ground observations and aggregate statistics.
    """
    reports = state.citizen_pipeline.get_citizen_observations(report_type=report_type, status=status)
    return {
        "count": len(reports),
        "total_submitted": len(state.citizen_pipeline.citizen_reports),
        "reports": [r.model_dump(mode="json") for r in reports],
        "provenance": {
            "source": "citizen_pgis_pipeline",
            "is_authoritative_state": False,
            "note": "Citizen reports represent ground evidence. Operational state is mutated only via Phase E reconciliation.",
        },
    }


@app.get("/observations/citizen/{observation_id}")
def get_citizen_observation_by_id(observation_id: str):
    """
    GET /observations/citizen/{observation_id}
    Phase L10: Returns specific citizen report details by ID.
    """
    report = state.citizen_pipeline.get_observation_by_id(observation_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Citizen observation '{observation_id}' not found")
    return report.model_dump(mode="json")


# ============================================================
# PHASE J: REAL-TIME DISASTER INTELLIGENCE & OPERATIONAL COORDINATION
# ============================================================

from fastapi.responses import StreamingResponse
import asyncio
import json

@app.get("/state/current")
def get_current_disaster_state():
    """
    GET /state/current
    Phase J: Returns authoritative DisasterState snapshot for current version vN.
    """
    state.initialize()
    return state.disaster_state_manager.current_state.model_dump(mode="json")


@app.get("/state/diff")
def get_disaster_state_diff(from_version: int, to_version: int):
    """
    GET /state/diff
    Phase J: Computes deterministic diff between DisasterState v{from} and v{to}.
    """
    state.initialize()
    try:
        diff = state.disaster_state_manager.get_diff(from_version, to_version)
        return diff.model_dump(mode="json")
    except KeyError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.get("/alerts")
def get_operational_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
):
    """
    GET /alerts
    Phase J: Returns list of deterministic operational alerts with optional status/severity filtering.
    """
    state.initialize()
    alerts = list(state.disaster_state_manager.alert_engine.alerts.values())

    if status:
        st_upper = status.upper().strip()
        alerts = [a for a in alerts if a.status == st_upper]

    if severity:
        sev_upper = severity.upper().strip()
        alerts = [a for a in alerts if a.severity == sev_upper]

    bounded = alerts[: max(1, min(limit, 200))]
    return {
        "count": len(bounded),
        "total": len(state.disaster_state_manager.alert_engine.alerts),
        "alerts": [a.model_dump(mode="json") for a in bounded],
    }


@app.post("/alerts/{alert_id}/action")
def apply_alert_operator_action(alert_id: str, payload: Dict[str, Any]):
    """
    POST /alerts/{alert_id}/action
    Phase J: Allows human operator to ACKNOWLEDGE, RESOLVE, or DISMISS an operational alert.
    """
    state.initialize()
    action = payload.get("action", "ACKNOWLEDGE")
    operator_id = payload.get("operator_id", "Operator-01")
    comment = payload.get("comment")

    try:
        alert = state.disaster_state_manager.alert_engine.apply_operator_action(
            alert_id=alert_id,
            action=action,
            operator_id=operator_id,
            comment=comment,
        )
        return alert.model_dump(mode="json")
    except KeyError as k_err:
        raise HTTPException(status_code=404, detail=str(k_err))
    except ValueError as v_err:
        raise HTTPException(status_code=400, detail=str(v_err))


@app.get("/events/stream")
async def stream_operational_events(request: Request):
    """
    GET /events/stream
    Phase J: Real-time SSE stream for state updates, alerts, and operational events.
    """
    async def event_generator():
        last_version = state.disaster_state_manager.current_version
        last_alert_count = len(state.disaster_state_manager.alert_engine.alerts)

        init_data = json.dumps({
            "type": "CONNECTED",
            "state_version": last_version,
            "timestamp": time.time(),
        })
        yield f"data: {init_data}\n\n"

        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected from /events/stream")
                break

            curr_ver = state.disaster_state_manager.current_version
            curr_alerts = state.disaster_state_manager.alert_engine.alerts

            if curr_ver > last_version:
                diff = state.disaster_state_manager.get_diff(last_version, curr_ver)
                evt_data = json.dumps({
                    "type": "STATE_UPDATED",
                    "from_version": last_version,
                    "to_version": curr_ver,
                    "diff": diff.model_dump(mode="json"),
                })
                yield f"data: {evt_data}\n\n"
                last_version = curr_ver

            if len(curr_alerts) > last_alert_count:
                new_alerts_list = [
                    a.model_dump(mode="json")
                    for a in list(curr_alerts.values())[last_alert_count:]
                ]
                alert_evt = json.dumps({
                    "type": "ALERTS_GENERATED",
                    "alerts": new_alerts_list,
                })
                yield f"data: {alert_evt}\n\n"
                last_alert_count = len(curr_alerts)

            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/traceability/{entity_id}")
def get_entity_traceability(entity_id: str):
    """
    GET /traceability/{entity_id}
    Phase J & K: Returns provenance trace connecting current values to state version, reconciliation, ground evidence, and intervention outcome.
    """
    state.initialize()
    res = state.disaster_state_manager.get_traceability(entity_id, observation_pipeline)
    
    # Extend traceability with Phase K intervention record if matching entity or candidate ID
    matching_int = next((i for i in state.intervention_manager.interventions.values() if i.intervention_id == entity_id or i.candidate_id == entity_id or entity_id in i.physical_segment_ids), None)
    if matching_int:
        res["intervention_record"] = matching_int.model_dump(mode="json")
        res["provenance_chain"].append({
            "step": "HUMAN_AUTHORIZED_INTERVENTION",
            "status": matching_int.status,
            "operator": matching_int.operator_id,
            "detail": f"Intervention {matching_int.intervention_id} ({matching_int.status}) - Expected: +{matching_int.expected_population_recovery}, Actual: {matching_int.actual_population_recovery or 'Pending'}",
        })

    return res


# ============================================================
# PHASE K: INTERVENTION EXECUTION & OUTCOME TRACKING ENDPOINTS
# ============================================================

@app.post("/interventions/propose")
def propose_intervention(payload: Dict[str, Any]):
    """
    POST /interventions/propose
    Phase K: Creates an explicit Intervention entity from an authoritative DecisionEngine candidate.
    Freezes expected impact snapshot at approval/proposal time.
    """
    state.initialize()
    payload = payload or {}
    candidate_id = payload.get("candidate_id")
    if not candidate_id:
        raise HTTPException(status_code=400, detail="Missing required 'candidate_id'")

    # Look up candidate from ranked corridors or corridors
    target_rc = next((rc for rc in state.ranked_corridors if rc.corridor_id == candidate_id), None)
    target_c = next((c for c in state.corridors if c.corridor_id == candidate_id), None)

    if not target_rc and not target_c:
        # Default Michaung scenario candidate lookup
        if not state.corridors:
            _ = flood_apply(FloodApplyRequest())
            _ = interventions_rank(InterventionsRankRequest())
        target_rc = next((rc for rc in state.ranked_corridors if rc.corridor_id == candidate_id), None)
        target_c = next((c for c in state.corridors if c.corridor_id == candidate_id), None)

    if not target_rc and not target_c:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found in DecisionEngine evaluations.")

    target_name = target_rc.road_classes[0] if target_rc and target_rc.road_classes else (target_c.road_classes[0] if target_c and target_c.road_classes else candidate_id)
    seg_ids = target_rc.physical_segment_ids if target_rc else target_c.physical_segment_ids

    # Expected impact snapshot
    exp_pop = target_rc.score_breakdown.population_recovered if target_rc else 89000
    exp_hosp = target_rc.score_breakdown.hospitals_recovered if target_rc else 2
    exp_time = target_rc.score_breakdown.time_saved_minutes if target_rc else 22.0
    exp_score = target_rc.score if target_rc else 0.0724

    operator_id = payload.get("operator_id", "COMMANDER-01")
    notes = payload.get("notes") or payload.get("approval_notes")

    intervention = state.intervention_manager.create_intervention_from_candidate(
        candidate_id=candidate_id,
        target_name=f"Corridor Clearance ({target_name})",
        physical_segment_ids=seg_ids,
        expected_population_recovery=exp_pop,
        expected_hospital_recovery=exp_hosp,
        expected_travel_time_saved_min=exp_time,
        expected_score=exp_score,
        operator_id=operator_id,
        approval_notes=notes,
    )

    return intervention.model_dump(mode="json")


@app.post("/interventions/{intervention_id}/transition")
def transition_intervention(intervention_id: str, payload: Dict[str, Any]):
    """
    POST /interventions/{intervention_id}/transition
    Phase K: Enforces state machine transition (PROPOSED -> APPROVED -> ASSIGNED -> IN_PROGRESS -> COMPLETED / FAILED).
    On COMPLETED: performs deterministic state evaluation & expected-vs-actual outcome variance calculation.
    On FAILED: triggers deterministic replanning using DecisionEngine on current state.
    """
    state.initialize()
    payload = payload or {}
    to_status = payload.get("to_status")
    if not to_status:
        raise HTTPException(status_code=400, detail="Missing required 'to_status'")

    operator_id = payload.get("operator_id", "COMMANDER-01")
    assigned_team = payload.get("assigned_team")
    note = payload.get("note") or payload.get("reason") or payload.get("failure_reason")

    try:
        to_status_upper = to_status.upper().strip()
        curr_ver = state.disaster_state_manager.current_version

        # Handle COMPLETED transition with outcome verification
        if to_status_upper == "COMPLETED":
            intervention = state.intervention_manager.interventions.get(intervention_id)
            if not intervention:
                raise HTTPException(status_code=404, detail=f"Intervention '{intervention_id}' not found.")

            # Compute Pre-accessibility state
            pre_access = compute_accessibility(state.network_engine, state.data_loader.communities, state.data_loader.facilities)

            # Restore network segments deterministically
            restored_count = state.network_engine.restore_segments(intervention.physical_segment_ids)
            state.last_cleared_corridor = intervention.candidate_id

            # Compute Post-accessibility state
            post_access = compute_accessibility(state.network_engine, state.data_loader.communities, state.data_loader.facilities)

            # Execute completion & verification
            updated_int, outcome_summary = state.intervention_manager.complete_and_verify_outcome(
                intervention_id=intervention_id,
                pre_accessibility=pre_access,
                post_accessibility=post_access,
                restored_segments_count=restored_count,
                operator_id=operator_id,
                notes=note,
            )

            # Commit state version transition
            sync_disaster_state_commit()

            # Emit operational alert for completion
            state.disaster_state_manager.alert_engine._create_or_update_alert(
                alert_type="INTERVENTION_COMPLETED",
                severity="LOW",
                affected_entity_id=intervention_id,
                affected_entity_name=intervention.target_name,
                source_version=state.disaster_state_manager.current_version,
                evidence=[outcome_summary],
            )

            res = updated_int.model_dump(mode="json")
            res["outcome_summary"] = outcome_summary
            return res

        # Handle FAILED transition with automatic replanning
        elif to_status_upper == "FAILED":
            intervention = state.intervention_manager.transition_status(
                intervention_id=intervention_id,
                to_status="FAILED",
                operator_id=operator_id,
                note=note,
                source_state_version=curr_ver,
            )

            # Emit operational alert
            state.disaster_state_manager.alert_engine._create_or_update_alert(
                alert_type="INTERVENTION_FAILED",
                severity="HIGH",
                affected_entity_id=intervention_id,
                affected_entity_name=intervention.target_name,
                source_version=curr_ver,
                evidence=[{"failure_reason": note or "Field execution failed"}],
            )

            # Replanning: evaluate alternative candidates deterministically using DecisionEngine
            from cyclone_twin.decision_engine import MultiObjectiveDecisionEngine, MultiObjectiveWeights, InterventionCandidate
            decision_engine = MultiObjectiveDecisionEngine(state.network_engine)

            alt_candidates = []
            if state.corridors:
                for c in state.corridors:
                    if c.corridor_id != intervention.candidate_id:
                        alt_candidates.append(
                            InterventionCandidate(
                                candidate_id=c.corridor_id,
                                name=f"Clear {c.corridor_id}",
                                physical_segment_ids=c.physical_segment_ids,
                                total_length_m=c.total_length_m,
                                road_classes=c.road_classes,
                            )
                        )

            replan_results = []
            if alt_candidates:
                replan_results = decision_engine.rank_interventions(
                    candidates=alt_candidates,
                    communities=state.data_loader.communities,
                    facilities=state.data_loader.facilities,
                    weights=MultiObjectiveWeights.life_safety(),
                )

            res = intervention.model_dump(mode="json")
            if replan_results:
                new_top = replan_results[0].candidate_id
                res["replan_recommendation"] = {
                    "new_top_candidate": new_top,
                    "score": replan_results[0].score,
                    "candidates_count": len(replan_results),
                }

            return res

        else:
            # Standard state transition (APPROVED, ASSIGNED, IN_PROGRESS, CANCELLED, REJECTED)
            intervention = state.intervention_manager.transition_status(
                intervention_id=intervention_id,
                to_status=to_status_upper,
                operator_id=operator_id,
                assigned_team=assigned_team,
                note=note,
                source_state_version=curr_ver,
            )
            return intervention.model_dump(mode="json")

    except KeyError as k_err:
        raise HTTPException(status_code=404, detail=str(k_err))
    except ValueError as v_err:
        raise HTTPException(status_code=400, detail=str(v_err))


@app.post("/interventions/{intervention_id}/field-update")
def record_intervention_field_update(intervention_id: str, payload: Dict[str, Any]):
    """
    POST /interventions/{intervention_id}/field-update
    Phase K: Ingests field updates (evidence refs, water depth, execution notes) for an intervention.
    """
    state.initialize()
    payload = payload or {}
    evidence_ref = payload.get("evidence_ref") or payload.get("evidence_reference")
    notes = payload.get("notes") or payload.get("description")
    operator_id = payload.get("operator_id", "FIELD-01")

    try:
        updated_int = state.intervention_manager.record_field_update(
            intervention_id=intervention_id,
            evidence_ref=evidence_ref,
            notes=notes,
            operator_id=operator_id,
        )
        return updated_int.model_dump(mode="json")
    except KeyError as err:
        raise HTTPException(status_code=404, detail=str(err))


@app.get("/interventions")
def list_interventions(status: Optional[str] = None, limit: int = 50):
    """
    GET /interventions
    Phase K: Returns list of operational interventions with optional status filtering.
    """
    state.initialize()
    items = state.intervention_manager.get_interventions_by_status(status=status)
    bounded = items[: max(1, min(limit, 200))]
    return {
        "count": len(bounded),
        "total": len(state.intervention_manager.interventions),
        "interventions": [i.model_dump(mode="json") for i in bounded],
    }


@app.get("/interventions/{intervention_id}")
def get_intervention_detail(intervention_id: str):
    """
    GET /interventions/{intervention_id}
    Phase K: Returns detailed entity state, frozen expected impact, actual outcome, and variance.
    """
    state.initialize()
    if intervention_id not in state.intervention_manager.interventions:
        raise HTTPException(status_code=404, detail=f"Intervention '{intervention_id}' not found.")
    return state.intervention_manager.interventions[intervention_id].model_dump(mode="json")


@app.get("/interventions/{intervention_id}/audit")
def get_intervention_audit(intervention_id: str):
    """
    GET /interventions/{intervention_id}/audit
    Phase K: Returns complete transition audit log for an intervention.
    """
    state.initialize()
    logs = [a for a in state.intervention_manager.audit_log if a.intervention_id == intervention_id]
    return {
        "intervention_id": intervention_id,
        "count": len(logs),
        "audit_trail": [a.model_dump(mode="json") for a in logs],
    }


# =====================================================================
# Phase L12 — GCP Foundation Endpoints
# =====================================================================

@app.get("/gcp/status")
def get_gcp_foundation_status():
    """
    GET /gcp/status
    Phase L12: Returns GCP deployment architecture and connection manifest.
    Shows readiness of Firestore, BigQuery, and Cloud Storage.
    """
    state.initialize()
    return state.gcp_foundation.get_status_manifest()


@app.post("/gcp/snapshot")
def trigger_gcp_state_snapshot():
    """
    POST /gcp/snapshot
    Phase L12: Snapshots current disaster state to Firestore if enabled (or local buffer).
    """
    state.initialize()
    curr_state = state.disaster_state_manager.current_state
    state_dict = curr_state.model_dump(mode="json") if hasattr(curr_state, "model_dump") else {}
    return state.gcp_foundation.snapshot_state(state_dict)


@app.post("/gcp/log-event")
def log_gcp_telemetry_event(payload: Dict[str, Any]):
    """
    POST /gcp/log-event
    Phase L12: Streams telemetry event to BigQuery table if enabled (or local log).
    """
    state.initialize()
    event_type = payload.get("event_type", "GENERIC_TELEMETRY")
    return state.gcp_foundation.log_event(event_type, payload)


# =====================================================================
# Production Durable Persistence Subsystem Endpoints
# =====================================================================

@app.get("/persistence/status")
def get_persistence_status_manifest():
    """
    GET /persistence/status
    Returns health status, active engine, and storage metrics for durable persistence subsystem.
    """
    state.initialize()
    return state.persistence_repo.get_status()


@app.post("/persistence/clear")
def clear_persisted_state():
    """
    POST /persistence/clear
    Clears all persisted data tables (resets storage to clean baseline).
    """
    state.initialize()
    ok = state.persistence_repo.clear_all()
    state.last_cleared_corridor = None
    state.corridors.clear()
    state.ranked_corridors.clear()
    state.network_engine.restore_all()
    state.data_loader.water_level_m = 0.0
    sync_disaster_state_commit()
    return {"status": "cleared" if ok else "failed", "storage_cleared": ok}







