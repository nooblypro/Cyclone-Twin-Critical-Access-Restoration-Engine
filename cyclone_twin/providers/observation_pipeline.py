"""
Multimodal Observation Ingestion & Reconciliation Pipeline for Cyclone Twin
Provides validated ingestion, full provenance tracking, bounded in-memory storage,
duplicate handling, geographic bounding, and deterministic model reconciliation.
"""

import math
import uuid
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone

from cyclone_twin.domain.entities import InfrastructureObservation

logger = logging.getLogger("cyclone_twin.observation_pipeline")

# Bounded study operating area (Greater Chennai Corporation metropolitan area)
CHENNAI_BBOX = {"min_lon": 80.00, "min_lat": 12.80, "max_lon": 80.35, "max_lat": 13.25}

SUPPORTED_SOURCES: Set[str] = {"citizen", "sensor", "field_team", "drone", "official"}
SOURCE_ALIASES: Dict[str, str] = {
    "citizen_report": "citizen",
    "agency": "official",
    "agent_ingested": "official",
    "field_agent": "field_team",
}

SUPPORTED_OBS_TYPES: Set[str] = {
    "ROAD_BLOCKED",
    "ROAD_OPEN",
    "FLOOD_DEPTH",
    "FLOOD_PRESENT",
    "BRIDGE_STATUS",
    "HOSPITAL_ACCESS",
    "TRAFFIC_CONDITION",
    "DRAIN_BLOCKED",
    "DRAIN_CAPACITY_LOSS",
    "DRAIN_OVERFLOW",
}
TYPE_ALIASES: Dict[str, str] = {
    "road_blockage": "ROAD_BLOCKED",
    "flooding": "FLOOD_PRESENT",
    "power_outage": "TRAFFIC_CONDITION",
    "drain_blockage": "DRAIN_BLOCKED",
    "blocked_drain": "DRAIN_BLOCKED",
    "drain_clogged": "DRAIN_BLOCKED",
    "drain_overflow": "DRAIN_OVERFLOW",
}

SOURCE_PRIORITY: Dict[str, int] = {
    "official": 5,
    "field_team": 4,
    "sensor": 3,
    "drone": 2,
    "citizen": 1,
}


def normalize_source_type(source: str) -> str:
    s_lower = str(source).lower().strip()
    return SOURCE_ALIASES.get(s_lower, s_lower)


def normalize_observation_type(obs_type: str) -> str:
    t_str = str(obs_type).strip()
    if t_str in TYPE_ALIASES:
        return TYPE_ALIASES[t_str]
    t_upper = t_str.upper()
    return TYPE_ALIASES.get(t_str.lower(), t_upper)


class ObservationIngestionPipeline:
    """
    Ingestion, validation, provenance, bounded storage, and reconciliation pipeline
    for ground observations. Strictly separates observation storage from simulation state.
    """

    def __init__(self, max_capacity: int = 500):
        self.max_capacity = max_capacity
        self.observations: Dict[str, InfrastructureObservation] = {}

    def validate_observation_input(
        self,
        lat: Any,
        lon: Any,
        confidence: Any,
        observation_type: str,
        source: str,
        timestamp: Optional[Any] = None,
        value: Optional[Any] = None,
    ) -> Tuple[float, float, float, str, str, datetime]:
        """
        Validates observation parameters.
        Raises ValueError for invalid lat/lon, NaN/Inf, out-of-bounds coords,
        out-of-range confidence, unsupported observation/source types, or malformed depth values.
        """
        # Validate Lat
        if isinstance(lat, bool) or not isinstance(lat, (int, float)):
            raise ValueError(f"Latitude must be a valid numeric float, got {type(lat).__name__}")
        f_lat = float(lat)
        if math.isnan(f_lat) or math.isinf(f_lat):
            raise ValueError("Latitude cannot be NaN or Infinity")
        if not (-90.0 <= f_lat <= 90.0):
            raise ValueError(f"Latitude out of valid range [-90, 90]: {f_lat}")

        # Validate Lon
        if isinstance(lon, bool) or not isinstance(lon, (int, float)):
            raise ValueError(f"Longitude must be a valid numeric float, got {type(lon).__name__}")
        f_lon = float(lon)
        if math.isnan(f_lon) or math.isinf(f_lon):
            raise ValueError("Longitude cannot be NaN or Infinity")
        if not (-180.0 <= f_lon <= 180.0):
            raise ValueError(f"Longitude out of valid range [-180, 180]: {f_lon}")

        # Geographic Bounding Box Validation (Chennai Region)
        if not (CHENNAI_BBOX["min_lon"] <= f_lon <= CHENNAI_BBOX["max_lon"] and CHENNAI_BBOX["min_lat"] <= f_lat <= CHENNAI_BBOX["max_lat"]):
            raise ValueError(
                f"Observation coordinates ({f_lat:.4f}, {f_lon:.4f}) lie outside Chennai study region "
                f"[{CHENNAI_BBOX['min_lon']}-{CHENNAI_BBOX['max_lon']} E, {CHENNAI_BBOX['min_lat']}-{CHENNAI_BBOX['max_lat']} N]"
            )

        # Validate Confidence
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError(f"Confidence must be a valid numeric float, got {type(confidence).__name__}")
        f_conf = float(confidence)
        if math.isnan(f_conf) or math.isinf(f_conf):
            raise ValueError("Confidence cannot be NaN or Infinity")
        if not (0.0 <= f_conf <= 1.0):
            raise ValueError(f"Confidence must be within range [0.0, 1.0], got {f_conf}")

        # Validate Source Type
        norm_source = normalize_source_type(source)
        if norm_source not in SUPPORTED_SOURCES:
            raise ValueError(f"Unsupported source type '{source}'. Allowed: {sorted(list(SUPPORTED_SOURCES))}")

        # Validate Observation Type
        norm_type = normalize_observation_type(observation_type)
        if norm_type not in SUPPORTED_OBS_TYPES:
            raise ValueError(f"Unsupported observation type '{observation_type}'. Allowed: {sorted(list(SUPPORTED_OBS_TYPES))}")

        # Validate Value requirements for specific types
        if norm_type == "FLOOD_DEPTH":
            if value is None:
                raise ValueError("FLOOD_DEPTH observation requires a numeric value (depth_m)")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"FLOOD_DEPTH value must be a valid non-negative float, got {type(value).__name__}")
            f_val = float(value)
            if math.isnan(f_val) or math.isinf(f_val) or f_val < 0.0:
                raise ValueError(f"FLOOD_DEPTH value must be a finite non-negative number, got {f_val}")

        # Validate Timestamp
        obs_time: datetime
        if timestamp is None:
            obs_time = datetime.now(timezone.utc)
        elif isinstance(timestamp, datetime):
            obs_time = timestamp
        elif isinstance(timestamp, str):
            try:
                obs_time = datetime.fromisoformat(timestamp)
            except ValueError:
                raise ValueError(f"Invalid ISO timestamp string: '{timestamp}'")
        else:
            raise ValueError(f"Timestamp must be a datetime or ISO string, got {type(timestamp).__name__}")

        return f_lat, f_lon, f_conf, norm_type, norm_source, obs_time

    def submit_report(
        self,
        lat: float,
        lon: float,
        observation_type: str = "road_blockage",
        source: str = "citizen_report",
        severity: str = "high",
        confidence: float = 0.85,
        affected_node_ids: Optional[List[str]] = None,
        affected_segment_id: Optional[str] = None,
        raw_text: Optional[str] = None,
        observation_id: Optional[str] = None,
        timestamp: Optional[Any] = None,
        value: Optional[Any] = None,
    ) -> InfrastructureObservation:
        """
        Validates, normalizes, and ingests a ground report into bounded store with provenance tracking.
        Handles duplicate observation_id via idempotent replacement.
        """
        f_lat, f_lon, f_conf, norm_type, norm_source, obs_time = self.validate_observation_input(
            lat=lat,
            lon=lon,
            confidence=confidence,
            observation_type=observation_type,
            source=source,
            timestamp=timestamp,
            value=value,
        )

        ingestion_time = datetime.now(timezone.utc)
        obs_id = str(observation_id) if observation_id else f"obs_{uuid.uuid4().hex[:8]}"

        # Idempotent replacement check vs Bounded Store capacity
        is_duplicate = obs_id in self.observations
        if not is_duplicate and len(self.observations) >= self.max_capacity:
            # Evict oldest entry (FIFO)
            oldest_key = next(iter(self.observations))
            del self.observations[oldest_key]
            logger.info("Bounded store capacity (%d) reached. Evicted oldest observation: %s", self.max_capacity, oldest_key)

        validated_status = (norm_source in ("sensor", "official", "field_team", "drone")) or (f_conf >= 0.80)

        provenance_meta = {
            "source": norm_source,
            "raw_source": source,
            "observation_id": obs_id,
            "timestamp": obs_time.isoformat(),
            "ingestion_timestamp": ingestion_time.isoformat(),
            "location": {"lat": f_lat, "lon": f_lon},
            "confidence": f_conf,
            "duplicate_replacement": is_duplicate,
            "processing_status": "accepted",
        }

        obs = InfrastructureObservation(
            observation_id=obs_id,
            timestamp=obs_time,
            ingestion_timestamp=ingestion_time,
            source=source,
            source_type=norm_source,
            observation_type=norm_type,
            severity=severity,
            confidence=f_conf,
            lat=f_lat,
            lon=f_lon,
            value=value,
            affected_segment_id=affected_segment_id,
            affected_node_ids=affected_node_ids or [],
            raw_text=raw_text,
            validated=validated_status,
            status="accepted",
            provenance=provenance_meta,
        )

        self.observations[obs_id] = obs
        return obs

    def get_active_observations(self, min_confidence: float = 0.50) -> List[InfrastructureObservation]:
        """Return validated active observations meeting confidence threshold."""
        return [
            obs for obs in self.observations.values()
            if obs.validated and obs.confidence >= min_confidence and obs.status == "accepted"
        ]

    def map_observation_to_segment(self, obs: InfrastructureObservation, graph: Any) -> Optional[str]:
        """Maps an observation coordinate to nearest graph segment ID if not explicitly provided."""
        if obs.affected_segment_id:
            return obs.affected_segment_id

        if graph is None or not hasattr(graph, "edges") or graph.number_of_edges() == 0:
            return None

        # Spatial distance search to find nearest physical segment
        min_dist_sq = float("inf")
        nearest_seg: Optional[str] = None
        lat_rad = math.radians(obs.lat)
        cos_lat = math.cos(lat_rad)

        for u, v, key, data in graph.edges(keys=True, data=True):
            seg_id = data.get("physical_segment_id") or f"seg_{u}_{v}_{key}"
            # Check geometry or node coords
            u_node = graph.nodes.get(u) if u in graph.nodes else graph.nodes.get(str(u), {})
            v_node = graph.nodes.get(v) if v in graph.nodes else graph.nodes.get(str(v), {})
            u_lat = float(u_node.get("lat", u_node.get("y", obs.lat)))
            u_lon = float(u_node.get("lon", u_node.get("x", obs.lon)))
            v_lat = float(v_node.get("lat", v_node.get("y", obs.lat)))
            v_lon = float(v_node.get("lon", v_node.get("x", obs.lon)))

            mid_lat = (u_lat + v_lat) / 2.0
            mid_lon = (u_lon + v_lon) / 2.0

            d_lat = (obs.lat - mid_lat) * 111000.0
            d_lon = (obs.lon - mid_lon) * 111000.0 * cos_lat
            dist_sq = d_lat * d_lat + d_lon * d_lon

            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                nearest_seg = seg_id

        return nearest_seg

    def reconcile_observations(
        self,
        engine: Any,
        max_age_seconds: float = 86400.0,
    ) -> Dict[str, Any]:
        """
        Deterministic reconciliation policy:
        Converts validated ground observation evidence into controlled simulation model overrides in NetworkEngine.
        Core Rule: OBSERVATION != TRUTH.
        Criteria:
        1. Exclude expired observations (> max_age_seconds).
        2. Single low-confidence citizen report (<0.85) without corroboration is stored as evidence, but DOES NOT mutate engine.
        3. Trusted sources (official, field_team, sensor >= 0.70) or high-confidence citizen (>=0.85) / corroborated reports are eligible.
        4. Conflicting reports for the same segment are resolved by source priority (official > field_team > sensor > drone > citizen), timestamp (newer wins), and confidence.
        """
        now = datetime.now(timezone.utc)
        segment_reports: Dict[str, List[InfrastructureObservation]] = {}

        # 1. Collect and filter active valid observations
        for obs in self.observations.values():
            if not obs.validated or obs.status not in ("accepted", "reconciled"):
                continue

            # Check temporal validity
            obs_dt = obs.timestamp if obs.timestamp.tzinfo else obs.timestamp.replace(tzinfo=timezone.utc)
            age_sec = (now - obs_dt).total_seconds()
            if age_sec > max_age_seconds:
                continue

            seg_id = self.map_observation_to_segment(obs, engine.graph if engine else None)
            if seg_id:
                segment_reports.setdefault(seg_id, []).append(obs)

        disabled_to_commit: Set[str] = set()
        restored_to_commit: Set[str] = set()
        reconciled_count = 0
        conflicts_detected: List[Dict[str, Any]] = []

        # 2. Reconcile reports per physical segment
        for seg_id, reports in segment_reports.items():
            # Check eligibility
            eligible_reports = []
            for r in reports:
                is_trusted = r.source_type in ("official", "field_team", "sensor") and r.confidence >= 0.70
                is_high_conf = r.confidence >= 0.85
                is_corroborated = len(reports) >= 2

                if is_trusted or is_high_conf or is_corroborated:
                    eligible_reports.append(r)

            if not eligible_reports:
                continue  # Single low-confidence report does NOT mutate engine

            # Conflict Resolution: Sort eligible reports by (Source Priority DESC, Timestamp DESC, Confidence DESC)
            def report_sort_key(rep: InfrastructureObservation):
                prio = SOURCE_PRIORITY.get(rep.source_type, 1)
                t_val = rep.timestamp.timestamp() if rep.timestamp else 0.0
                return (prio, t_val, rep.confidence)

            best_report = max(eligible_reports, key=report_sort_key)

            # Check for conflicting evidence (e.g. ROAD_BLOCKED vs ROAD_OPEN)
            obs_types = {r.observation_type for r in eligible_reports}
            if len(obs_types) > 1:
                conflicts_detected.append({
                    "segment_id": seg_id,
                    "competing_reports": [
                        {
                            "observation_id": r.observation_id,
                            "source": r.source_type,
                            "observation_type": r.observation_type,
                            "confidence": r.confidence,
                            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                        }
                        for r in eligible_reports
                    ],
                    "winning_observation_id": best_report.observation_id,
                    "winning_type": best_report.observation_type,
                    "resolution_policy": "source_priority_and_recency",
                })

            if best_report.observation_type in ("ROAD_BLOCKED", "FLOOD_PRESENT"):
                disabled_to_commit.add(seg_id)
                best_report.status = "reconciled"
                reconciled_count += 1
            elif best_report.observation_type == "ROAD_OPEN":
                restored_to_commit.add(seg_id)
                best_report.status = "reconciled"
                reconciled_count += 1

        # 3. Apply overrides to NetworkEngine atomically if engine provided
        if engine and hasattr(engine, "disable_segments") and hasattr(engine, "restore_segments"):
            if disabled_to_commit:
                engine.disable_segments(disabled_to_commit, validate=False)
            if restored_to_commit:
                engine.restore_segments(restored_to_commit)

        return {
            "reconciled_count": reconciled_count,
            "disabled_segments": sorted(list(disabled_to_commit)),
            "restored_segments": sorted(list(restored_to_commit)),
            "conflicts_detected": conflicts_detected,
            "has_conflicts": len(conflicts_detected) > 0,
            "provenance": {
                "policy": "deterministic_evidence_threshold",
                "max_age_seconds": max_age_seconds,
                "timestamp": now.isoformat(),
            },
        }

