"""
Cyclone Twin Domain Entities
Core data models representing physical, environmental, and operational domain concepts.
"""

import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class WeatherForecast(BaseModel):
    """Weather forecast snapshot for a geographic location."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    precipitation_mm: float = Field(0.0, ge=0.0)
    precipitation_probability: float = Field(0.0, ge=0.0, le=100.0)
    wind_speed_kmh: float = Field(0.0, ge=0.0)
    forecast_horizon_hours: int = Field(24, ge=0)
    location_name: str = "Chennai"
    lat: float = 13.0827
    lon: float = 80.2707
    provider: str = "calibrated_fallback"  # "open_meteo" | "calibrated_fallback"


class FloodScenario(BaseModel):
    """Modeled flood scenario driven by forecast or digitized footprint."""
    scenario_id: str
    water_level_m: float = Field(0.0, ge=0.0)
    hand_threshold_m: float = Field(0.30, ge=0.0)
    flood_geojson: Optional[Dict[str, Any]] = None
    source: str = "calibrated_michaung"  # "hand_model" | "open_meteo_driven" | "calibrated_michaung"


class RoadSegment(BaseModel):
    """Extensible road network segment."""
    segment_id: str
    u_node: str
    v_node: str
    length_m: float = Field(..., ge=0.0)
    free_flow_speed_kph: float = Field(40.0, gt=0.0)
    capacity_vehicles_per_hour: float = Field(2000.0, gt=0.0)
    current_volume: float = Field(0.0, ge=0.0)
    elevation_m: float = 2.0
    hand_height_m: float = 1.0
    is_bridge: bool = False
    disabled: bool = False
    inundation_depth_m: float = 0.0


class PopulationZone(BaseModel):
    """Socioeconomic population zone or ward."""
    zone_id: str
    name: str
    population: int = Field(..., ge=0)
    vulnerability_index: float = Field(1.0, ge=0.1, le=5.0)  # Equity weighting factor
    centroid_lat: float
    centroid_lon: float
    nearest_node_id: str


class CriticalFacility(BaseModel):
    """Critical destination infrastructure (hospitals, emergency centers)."""
    facility_id: str
    name: str
    facility_type: str = "trauma_center"  # "trauma_center" | "shelter" | "fire_station"
    bed_capacity: int = Field(100, ge=0)
    has_backup_power: bool = True
    lat: float
    lon: float
    nearest_node_id: str


class DrainSegment(BaseModel):
    """Stormwater drain network segment (GCC municipal infrastructure)."""
    drain_id: str
    catchment_zone: str
    gradient_slope: float = 0.001
    capacity_cumecs: float = 10.0
    condition_rating: str = "good"  # "good" | "clogged" | "damaged"
    geometry: Optional[Dict[str, Any]] = None
    provenance: str = "gcc_calibrated"  # "gcc_official" | "gcc_calibrated"


class DrainageInfrastructureAsset(BaseModel):
    """
    Phase L9: Domain representation for GCC-style stormwater drainage infrastructure assets.
    Represents physical/network infrastructure conditions (condition, capacity factor, blockage status, connectivity).
    IMPORTANT: Does NOT mutate HAND elevation values or hydraulic topography.
    """
    asset_id: str
    asset_name: str = ""
    asset_type: str = "stormwater_drain"  # "stormwater_drain" | "culvert" | "outfall" | "pumping_station" | "drain_link" | "junction"
    catchment_zone: str = "GCC_Central"
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    connected_network_node: Optional[str] = None
    condition_score: float = Field(1.0, ge=0.0, le=1.0)  # 0.0=failed/clogged, 1.0=fully operational
    capacity_cumecs: float = Field(10.0, ge=0.0)
    capacity_factor: float = Field(1.0, ge=0.0, le=1.0)  # 0.0=no effective capacity, 1.0=nominal capacity
    blockage_status: str = "open"  # "open" | "partially_blocked" | "severely_blocked" | "inoperable"
    blockage_probability: float = Field(0.0, ge=0.0, le=1.0)
    connectivity_status: str = "connected"  # "connected" | "degraded" | "disconnected" | "missing_link"
    observed_issue: Optional[str] = None
    source: str = "gcc_calibrated"  # "gcc_official" | "gcc_calibrated" | "field_team" | "sensor"
    confidence: float = Field(0.85, ge=0.0, le=1.0)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    is_simulated: bool = True
    last_inspected_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("latitude", "longitude", "condition_score", "capacity_cumecs", "capacity_factor", "blockage_probability", "confidence")
    @classmethod
    def check_finite_floats(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Float value must be finite (NaN and Infinity rejected)")
        return v


class DrainageInfrastructureSummary(BaseModel):
    """
    Phase L9: Public API summary response model for GET /infrastructure/drainage.
    Exposes drainage infrastructure assets, provenance, source status, and explicit limitations.
    """
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    dataset_name: str = "GCC Calibrated Stormwater Drainage Infrastructure Scenario"
    dataset_version: str = "v1.0"
    source: str = "gcc_calibrated"
    is_simulated: bool = True
    total_assets: int = Field(0, ge=0)
    blocked_assets_count: int = Field(0, ge=0)
    degraded_connectivity_count: int = Field(0, ge=0)
    geographic_coverage: Dict[str, float] = Field(default_factory=dict)
    assets: List[DrainageInfrastructureAsset] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class CitizenMediaMetadata(BaseModel):
    """
    Phase L10: Photo/Media evidence metadata attached to a citizen PGIS report.
    Binary contents are NOT stored inside this domain entity.
    """
    media_id: str
    filename_sanitized: str
    mime_type: str = "image/jpeg"  # "image/jpeg" | "image/png" | "image/webp"
    size_bytes: int = Field(..., ge=0)
    captured_at: Optional[datetime] = None
    storage_ref: str = ""

    @field_validator("size_bytes")
    @classmethod
    def check_size(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Media size cannot be negative")
        if v > 10 * 1024 * 1024:
            raise ValueError("Media file size exceeds maximum limit of 10 MB")
        return v


class CitizenObservation(BaseModel):
    """
    Phase L10: Ground observation submitted by a member of the public (PGIS).
    Serves as UNTRUSTED evidence until validated and reconciled via Phase E pipeline.
    Does NOT mutate NetworkEngine, DisasterState, HAND, or priorities directly.
    """
    observation_id: str
    report_type: str = "ROAD_FLOODED"  # "ROAD_FLOODED" | "ROAD_BLOCKED" | "ROAD_PASSABLE" | "WATER_LEVEL" | "DRAIN_OVERFLOW" | "HOSPITAL_ACCESS_BLOCKED" | "DEBRIS" | "FALLEN_TREE" | "BRIDGE_BLOCKED" | "POWER_OUTAGE" | "OTHER"
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    description: str = ""
    reporter_id: str = "citizen_anonymous"
    is_anonymous: bool = True
    water_depth_m: Optional[float] = Field(None, ge=0.0)
    severity: str = "medium"  # "low" | "medium" | "high" | "critical"
    confidence: float = Field(0.65, ge=0.0, le=1.0)
    status: str = "SUBMITTED"  # "SUBMITTED" | "VALIDATING" | "VALIDATED" | "RECONCILED" | "REJECTED" | "DUPLICATE" | "CONFLICTING" | "EXPIRED"
    source: str = "citizen"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    received_at: datetime = Field(default_factory=datetime.utcnow)
    sync_status: str = "SYNCED"  # "QUEUED" | "SYNCED" | "FAILED"
    media_metadata: Optional[CitizenMediaMetadata] = None
    duplicate_candidate_id: Optional[str] = None
    has_conflicting_reports: bool = False
    provenance: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("latitude", "longitude", "confidence")
    @classmethod
    def check_finite_floats(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Float value must be finite (NaN and Infinity rejected)")
        return v


class InfrastructureObservation(BaseModel):
    """Multimodal ground report or sensor observation with full provenance and validation metadata."""
    observation_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ingestion_timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = "citizen_report"  # "citizen_report" | "sensor" | "drone" | "agency" | "citizen" | "field_team" | "official"
    source_type: str = "citizen"    # Normalized source type: "citizen" | "sensor" | "field_team" | "drone" | "official"
    observation_type: str = "ROAD_BLOCKED"  # "ROAD_BLOCKED" | "ROAD_OPEN" | "FLOOD_DEPTH" | "FLOOD_PRESENT" | "BRIDGE_STATUS" | "HOSPITAL_ACCESS" | "TRAFFIC_CONDITION"
    severity: str = "high"  # "low" | "medium" | "high" | "critical"
    confidence: float = Field(0.85, ge=0.0, le=1.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    value: Optional[Any] = None
    affected_segment_id: Optional[str] = None
    affected_node_ids: List[str] = Field(default_factory=list)
    raw_text: Optional[str] = None
    validated: bool = False
    status: str = "received"  # "received" | "accepted" | "reconciled" | "rejected_out_of_scope" | "rejected_invalid"
    provenance: Dict[str, Any] = Field(default_factory=dict)


class MultimodalEvidenceExtraction(BaseModel):
    """
    Intermediate representation of extracted field evidence before Phase E validation and reconciliation.
    AI/Vision extraction produces this contract; it NEVER directly mutates simulation graph or accessibility state.
    """
    extraction_id: str
    observation_type: str = "ROAD_BLOCKED"  # "ROAD_BLOCKED" | "ROAD_OPEN" | "FLOOD_DEPTH" | "FLOOD_PRESENT" | "BRIDGE_STATUS" | "HOSPITAL_ACCESS" | "TRAFFIC_CONDITION"
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    timestamp: Optional[str] = None
    estimated_water_depth_m: Optional[float] = Field(None, ge=0.0)
    depth_source: str = "unknown"  # "field_measurement" | "visual_estimate" | "unknown"
    depth_confidence: float = Field(0.50, ge=0.0, le=1.0)
    road_condition: str = "unknown"  # "passable" | "flooded" | "debris_blocked" | "damaged" | "unknown"
    infrastructure_condition: str = "unknown"
    confidence: float = Field(0.70, ge=0.0, le=1.0)
    evidence_description: str = ""
    detected_features: List[str] = Field(default_factory=list)
    source_type: str = "field_team"  # "citizen" | "sensor" | "field_team" | "drone" | "official"
    model_name: str = "gemini-2.5-flash-vision"
    model_version: str = "v1"
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw_evidence_reference: str = ""
    uncertainty: Dict[str, Any] = Field(default_factory=dict)
    extraction_status: str = "extracted"  # "extracted" | "location_unresolved" | "low_confidence" | "invalid_evidence" | "extraction_failed"
    location_resolution_required: bool = False


class OperationalAlert(BaseModel):
    """
    Deterministic operational alert generated by system rules.
    Never created or modified by AI.
    """
    alert_id: str
    type: str  # "CRITICAL_HOSPITAL_ACCESS_LOSS" | "POPULATION_ISOLATION_INCREASE" | "HIGH_CONFIDENCE_ROAD_BLOCKAGE" | "CORRIDOR_RESTORED" | "OBSERVATION_CONFLICT" | "STALE_CRITICAL_OBSERVATION" | "INTERVENTION_FAILED" | "PRIORITY_CHANGED"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    severity: str = "MEDIUM"  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    source_state_version: int = 1
    affected_entity_id: str
    affected_entity_name: Optional[str] = None
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    status: str = "NEW"  # "NEW" | "ACKNOWLEDGED" | "RESOLVED" | "DISMISSED"
    operator_action: Optional[Dict[str, Any]] = None


class OperationalEvent(BaseModel):
    """
    Explicit internal event representing an actual system state transition.
    """
    event_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    state_version: int = 1
    details: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)


class DisasterState(BaseModel):
    """
    Authoritative snapshot of the current disaster state at state_version N.
    """
    scenario_id: str = "chennai_michaung_default"
    state_version: int = 1
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    valid_from: datetime = Field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = None
    hazard_state: Dict[str, Any] = Field(default_factory=dict)
    affected_segments: List[str] = Field(default_factory=list)
    affected_facilities: List[Dict[str, Any]] = Field(default_factory=list)
    affected_population: Dict[str, Any] = Field(default_factory=dict)
    observations_count: int = 0
    high_confidence_observations: int = 0
    unresolved_conflicts: int = 0
    active_interventions: List[str] = Field(default_factory=list)
    completed_interventions: List[str] = Field(default_factory=list)
    confidence_summary: Dict[str, int] = Field(default_factory=lambda: {"confirmed": 0, "probable": 0, "uncertain": 0, "conflicting": 0})
    provenance_summary: Dict[str, Any] = Field(default_factory=dict)


class StateDiff(BaseModel):
    """
    Deterministic diff between two DisasterState versions.
    """
    from_version: int
    to_version: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    road_changes: List[Dict[str, Any]] = Field(default_factory=list)
    hospital_changes: List[Dict[str, Any]] = Field(default_factory=list)
    population_change: Dict[str, Any] = Field(default_factory=dict)
    priority_changed: bool = False
    previous_top_candidate: Optional[str] = None
    current_top_candidate: Optional[str] = None
    priority_change_reason: Optional[str] = None
    new_alerts: List[str] = Field(default_factory=list)
    resolved_alerts: List[str] = Field(default_factory=list)



class InterventionTransitionAudit(BaseModel):
    """
    Audit record logging a state transition in an intervention lifecycle.
    """
    audit_id: str
    intervention_id: str
    from_status: str
    to_status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    operator_id: str = "COMMANDER-01"
    note: Optional[str] = None
    source_state_version: int = 1


class Intervention(BaseModel):
    """
    Operational intervention entity created when a human operator approves a candidate.
    Tracks state machine lifecycle: PROPOSED -> APPROVED -> ASSIGNED -> IN_PROGRESS -> COMPLETED / FAILED (or CANCELLED / REJECTED).
    Separates frozen expected impact (captured at approval) from measured actual impact (computed upon completion).
    """
    intervention_id: str
    candidate_id: str
    intervention_type: str = "CORRIDOR_CLEARANCE"
    target_entity_id: str
    target_name: str
    proposed_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    status: str = "PROPOSED"  # "PROPOSED" | "APPROVED" | "REJECTED" | "ASSIGNED" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | "CANCELLED"
    operator_id: str = "COMMANDER-01"
    assigned_team: Optional[str] = None
    physical_segment_ids: List[str] = Field(default_factory=list)

    # Expected Impact Snapshot (Frozen at approval time, immutable thereafter)
    expected_population_recovery: int = 0
    expected_hospital_recovery: int = 0
    expected_travel_time_saved_min: float = 0.0
    expected_score: float = 0.0

    # Measured Actual Impact (Computed deterministically from post-intervention graph state)
    actual_population_recovery: Optional[int] = None
    actual_hospital_recovery: Optional[int] = None
    actual_travel_time_saved_min: Optional[float] = None

    # Calculated Variance (Actual - Expected)
    variance_population: Optional[int] = None
    variance_hospital: Optional[int] = None
    variance_travel_time_min: Optional[float] = None

    outcome_verification_status: str = "UNVERIFIED"  # "UNVERIFIED" | "CLAIM_RECEIVED" | "VERIFIED" | "FAILED"
    evidence_refs: List[str] = Field(default_factory=list)
    approval_notes: Optional[str] = None
    execution_notes: Optional[str] = None
    outcome_notes: Optional[str] = None
    failure_reason: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)


class RoadVulnerability(BaseModel):
    """
    Milestone L2: Predicted infrastructure vulnerability for a specific road network segment.
    PREDICTED ONLY — Strictly read-only representation. Does NOT mutate operational road status.
    """
    segment_id: str
    forecast_time: datetime = Field(default_factory=datetime.utcnow)
    predicted_depth_m: float = Field(0.0, ge=0.0)
    closure_threshold_m: float = Field(0.30, ge=0.0)
    closure_probability: float = Field(0.0, ge=0.0, le=1.0)
    travel_time_multiplier: float = Field(1.0, gt=0.0)
    population_impact: int = Field(0, ge=0)
    hospital_impact: int = Field(0, ge=0)
    vulnerability_score: float = Field(0.0, ge=0.0, le=1.0)
    confidence: float = Field(0.85, ge=0.0, le=1.0)
    is_predicted: bool = True

    @field_validator("predicted_depth_m", "closure_threshold_m", "closure_probability", "travel_time_multiplier", "vulnerability_score", "confidence")
    @classmethod
    def check_finite_floats(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Float value must be finite (NaN and Infinity rejected)")
        return v


class VulnerabilityForecast(BaseModel):
    """
    Milestone L2: Structured representation of forecasted vulnerability state for one forecast horizon.
    Read-only projection — strictly independent from operational DisasterState.
    """
    forecast_id: str
    scenario_id: str = "michaung_dec_2023"
    forecast_time: datetime = Field(default_factory=datetime.utcnow)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    reference_time: datetime = Field(default_factory=datetime.utcnow)
    horizon_hours: int = Field(0, ge=0)

    weather_source: str = "calibrated_fallback"
    flood_model: str = "hand_model"
    network_source: str = "osm_chennai"

    rainfall_mm: float = Field(0.0, ge=0.0)
    water_level_m: float = Field(0.0, ge=0.0)

    predicted_population_at_risk: int = Field(0, ge=0)
    predicted_population_isolated: int = Field(0, ge=0)

    predicted_hospitals_at_risk: int = Field(0, ge=0)
    predicted_hospitals_inaccessible: int = Field(0, ge=0)

    road_vulnerabilities: List[RoadVulnerability] = Field(default_factory=list)

    confidence: float = Field(0.85, ge=0.0, le=1.0)

    provenance: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)

    is_projected_forecast: bool = True

    @field_validator("rainfall_mm", "water_level_m", "confidence")
    @classmethod
    def check_finite_floats(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Float value must be finite (NaN and Infinity rejected)")
        return v


class VulnerabilityAssessment(BaseModel):
    """
    Milestone L4: Deterministic vulnerability projection assessment for a single road segment.
    Calculated from L3 forecast output. Pure/read-only assessment.
    """
    segment_id: str
    forecast_time: datetime = Field(default_factory=datetime.utcnow)
    vulnerability_score: float = Field(0.0, ge=0.0, le=1.0)

    # Component normalized scores [0.0, 1.0]
    flood_exposure: float = Field(0.0, ge=0.0, le=1.0)
    population_impact: float = Field(0.0, ge=0.0, le=1.0)
    hospital_impact: float = Field(0.0, ge=0.0, le=1.0)
    travel_time_impact: float = Field(0.0, ge=0.0, le=1.0)

    # Raw metrics for transparency and auditability
    raw_excess_depth_m: float = Field(0.0, ge=0.0)
    raw_population_impact: int = Field(0, ge=0)
    raw_hospital_impact: int = Field(0, ge=0)
    raw_travel_time_multiplier: float = Field(1.0, ge=0.0)

    weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "flood_exposure": 0.30,
            "population_impact": 0.25,
            "hospital_impact": 0.25,
            "travel_time_impact": 0.20,
        }
    )
    components: Dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(0.85, ge=0.0, le=1.0)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""

    @field_validator(
        "vulnerability_score",
        "flood_exposure",
        "population_impact",
        "hospital_impact",
        "travel_time_impact",
        "confidence",
    )
    @classmethod
    def check_finite_floats(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Float value must be finite (NaN and Infinity rejected)")
        return v


class VulnerabilitySummary(BaseModel):
    """
    Milestone L4: Forecast-level summary of projected infrastructure vulnerability assessments.
    VULNERABILITY ASSESSMENT ONLY — Does NOT produce intervention/restoration priorities.
    """
    forecast_id: str
    scenario_id: str
    horizon_hours: int = Field(0, ge=0)
    forecast_time: datetime = Field(default_factory=datetime.utcnow)
    reference_time: datetime = Field(default_factory=datetime.utcnow)
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    total_assessed_segments: int = Field(0, ge=0)
    segments_above_threshold: int = Field(0, ge=0)
    vulnerability_threshold: float = Field(0.50, ge=0.0, le=1.0)

    max_vulnerability_score: float = Field(0.0, ge=0.0, le=1.0)
    mean_vulnerability_score: float = Field(0.0, ge=0.0, le=1.0)

    highest_vulnerability_segments: List[VulnerabilityAssessment] = Field(default_factory=list)
    component_summaries: Dict[str, float] = Field(default_factory=dict)
    weights_used: Dict[str, float] = Field(default_factory=dict)

    provenance: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    is_projected_forecast: bool = True

    @field_validator("max_vulnerability_score", "mean_vulnerability_score", "vulnerability_threshold")
    @classmethod
    def check_finite_floats(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Float value must be finite (NaN and Infinity rejected)")
        return v


class ForecastVulnerabilityResponse(BaseModel):
    """
    Milestone L5: Public API response model for GET /forecast/vulnerability.
    Presents structured vulnerability summary and segment assessments for a specific forecast horizon.
    Read-only projection — does NOT produce intervention/restoration priorities.
    """
    horizon: str = "NOW"
    horizon_hours: int = Field(0, ge=0)
    reference_time: datetime = Field(default_factory=datetime.utcnow)
    forecast_time: datetime = Field(default_factory=datetime.utcnow)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    weather_source: str = "calibrated_fallback"
    flood_model: str = "hand_model"
    network_source: str = "osm_chennai"
    vulnerability_summary: VulnerabilitySummary
    vulnerability_assessments: List[VulnerabilityAssessment] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    is_projected_forecast: bool = True


class VoiceArtifactMetadata(BaseModel):
    """
    Metadata describing an uploaded voice recording (Phase L8).
    Binary audio contents are NOT stored inside this domain entity.
    """
    artifact_id: str
    filename_sanitized: str
    mime_type: str
    size_bytes: int = Field(..., ge=0)
    duration_sec: Optional[float] = Field(None, ge=0.0)
    source: str = "field_team"
    language_hint: Optional[str] = None
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    received_at: datetime = Field(default_factory=datetime.utcnow)
    transcription_id: Optional[str] = None
    extraction_status: str = "pending"  # "pending" | "transcribed" | "transcription_unavailable" | "failed"
    provenance: Dict[str, Any] = Field(default_factory=dict)


class VoiceTranscriptionResult(BaseModel):
    """
    Result of transcribing audio and extracting evidence metadata (Phase L8).
    Maintains clean separation between transcription confidence and extraction confidence.
    """
    transcription_id: Optional[str] = None
    artifact_id: Optional[str] = None
    transcript: str = ""
    transcription_confidence: float = Field(0.70, ge=0.0, le=1.0)
    language_detected: Optional[str] = None
    observation_type: Optional[str] = None
    estimated_water_depth_m: Optional[float] = Field(None, ge=0.0)
    depth_source: str = "unknown"
    extraction_confidence: float = Field(0.65, ge=0.0, le=1.0)
    evidence_description: str = ""
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    transcribed_at: datetime = Field(default_factory=datetime.utcnow)
    provider: str = "gemini-2.5-flash"
    fallback_used: bool = False
    transcription_status: str = "SUCCESS"  # "SUCCESS" | "PARTIAL" | "TRANSCRIPTION_UNAVAILABLE" | "FAILED"






