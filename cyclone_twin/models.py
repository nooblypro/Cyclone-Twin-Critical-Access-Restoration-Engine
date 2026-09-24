"""
Cyclone Twin Data Models
Defines core domain entities, input/output schemas, and scenario manifests.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, model_validator


class ActionVerb(str, Enum):
    DEPLOY_PUMPS = "DEPLOY_PUMPS"
    CLEAR_DEBRIS = "CLEAR_DEBRIS"
    STABILIZE_EMBANKMENT = "STABILIZE_EMBANKMENT"
    RESTORE_POWER = "RESTORE_POWER"
    PRIORITIZE_ACCESS = "PRIORITIZE_ACCESS"


class Weights(BaseModel):
    """
    Scoring weights for corridor ranking.
    Must be non-negative and sum to 1.0 within float tolerance.
    """
    w_h: float = Field(0.40, ge=0.0, le=1.0, description="Weight for hospital accessibility recovery")
    w_p: float = Field(0.30, ge=0.0, le=1.0, description="Weight for population accessibility recovery")
    w_t: float = Field(0.20, ge=0.0, le=1.0, description="Weight for travel time reduction")
    w_d: float = Field(0.10, ge=0.0, le=1.0, description="Weight for corridor clearance difficulty / length penalty")

    @model_validator(mode="after")
    def validate_sum(self) -> "Weights":
        total = self.w_h + self.w_p + self.w_t + self.w_d
        if abs(total - 1.0) > 1e-4:
            raise ValueError(f"Weights must sum to 1.0, got sum = {total:.4f}")
        return self

    @classmethod
    def life_safety(cls) -> "Weights":
        """Pre-configured life-safety preset prioritizing hospital access and population."""
        return cls(w_h=0.40, w_p=0.30, w_t=0.20, w_d=0.10)

    @classmethod
    def hospital_priority(cls) -> "Weights":
        return cls(w_h=0.60, w_p=0.20, w_t=0.15, w_d=0.05)

    @classmethod
    def rapid_clearance(cls) -> "Weights":
        return cls(w_h=0.25, w_p=0.25, w_t=0.20, w_d=0.30)


class Community(BaseModel):
    """Represents a residential or administrative community zone."""
    id: str
    name: str
    population: int = Field(..., ge=0)
    node_id: Optional[str] = None
    coords: Optional[Tuple[float, float]] = None  # (lon, lat) in WGS84
    accessible: bool = True
    travel_time_sec: Optional[float] = None
    nearest_facility_id: Optional[str] = None


class HealthFacility(BaseModel):
    """Represents an emergency hospital or medical center."""
    id: str
    name: str
    node_id: Optional[str] = None
    coords: Optional[Tuple[float, float]] = None  # (lon, lat) in WGS84
    beds: int = Field(100, ge=0)
    power_status: bool = True  # Only powered hospitals participate as active destinations
    accessible: bool = True


class Corridor(BaseModel):
    """A contiguous cluster of disabled road segments forming a restoration candidate."""
    corridor_id: str
    edge_keys: List[Tuple[str, str, int]] = Field(default_factory=list)  # (u, v, key)
    physical_segment_ids: List[str] = Field(default_factory=list)
    total_length_m: float = Field(0.0, ge=0.0)
    road_classes: List[str] = Field(default_factory=list)
    geometry: Optional[Dict[str, Any]] = None  # GeoJSON LineString / MultiLineString


class ScoreBreakdown(BaseModel):
    """Normalized deltas and calculated score components for a corridor."""
    delta_h: float = Field(..., ge=0.0, le=1.0, description="Normalized hospital recovery delta")
    delta_p: float = Field(..., ge=0.0, le=1.0, description="Normalized population recovery delta")
    delta_t: float = Field(..., ge=0.0, le=1.0, description="Normalized travel time improvement delta")
    delta_d: float = Field(..., ge=0.0, le=1.0, description="Normalized length / difficulty delta")
    score: float
    combined_intervention_required: bool = False
    hospitals_recovered: int = 0
    population_recovered: int = 0
    time_saved_minutes: float = 0.0


class RankedCorridor(BaseModel):
    """Ranked restoration corridor with score breakdown and geographical metadata."""
    corridor_id: str
    rank: int
    score: float
    score_breakdown: ScoreBreakdown
    total_length_m: float
    road_classes: List[str]
    physical_segment_ids: List[str]
    geometry: Optional[Dict[str, Any]] = None


class AccessibilityResult(BaseModel):
    """Summary of emergency network accessibility at a given graph state."""
    accessible_population: int = 0
    isolated_facilities: List[str] = Field(default_factory=list)
    isolated_communities: List[str] = Field(default_factory=list)
    facility_travel_times: Dict[str, float] = Field(default_factory=dict)
    community_travel_times: Dict[str, float] = Field(default_factory=dict)
    active_hospital_count: int = 0


class ScenarioManifest(BaseModel):
    """Audit trail and metadata provenance for the evaluated scenario."""
    flood_source: str = "mock"  # "nrsc" | "manual_digitized" | "mock"
    graph_source: str = "mock_fallback"  # "osmnx_live" | "mock_fallback"
    graph_crs: str = "EPSG:32643"
    threshold_seconds: float = 1800.0  # 30-minute critical access threshold
    weight_preset: str = "life_safety"
    snap_distance_threshold_m: float = 200.0
    snap_warnings: List[str] = Field(default_factory=list)
    corridor_provenance: str = "connected_components"
    total_disabled_edges: int = 0
    total_corridors: int = 0


# API Request / Response schemas

class NetworkLoadRequest(BaseModel):
    pass


class NetworkLoadResponse(BaseModel):
    nodes: int
    edges: int
    graph_source: str  # "osmnx_live" | "mock_fallback"


class FloodApplyRequest(BaseModel):
    flood_geojson: Optional[Dict[str, Any]] = None


class FloodApplyResponse(BaseModel):
    disabled_edges: int
    flood_source: str  # "nrsc" | "manual_digitized" | "mock"
    corridors: int


class AccessibilityStatusResponse(BaseModel):
    accessible_population: int
    isolated_facilities: List[str]
    isolated_communities: List[str]


class InterventionsRankRequest(BaseModel):
    weights: Optional[Weights] = None


class InterventionsRankResponse(BaseModel):
    ranked_corridors: List[RankedCorridor]
    manifest: ScenarioManifest


class InterventionsClearRequest(BaseModel):
    corridor_id: str


class ClearStateResult(BaseModel):
    accessible_population: int
    isolated_count: int


class InterventionsClearResponse(BaseModel):
    corridor_id: str
    new_graph_state: ClearStateResult


class AdvisoryGenerateRequest(BaseModel):
    corridor_id: str
    score_breakdown: ScoreBreakdown


class AdvisoryGenerateResponse(BaseModel):
    advisory_text: str = Field(..., max_length=220)
    language: str = "en"
    source_corridor_id: str
    validated: bool = True
    fallback: bool = False
    road_names: List[str] = Field(default_factory=list)
    communities_affected: List[str] = Field(default_factory=list)
    action_verb: ActionVerb = ActionVerb.PRIORITIZE_ACCESS
