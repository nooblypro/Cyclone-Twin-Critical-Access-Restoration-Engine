"""
Phase L10 — Citizen / Participatory GIS (PGIS) Evidence Pipeline
Cyclone Twin — Critical Access Restoration Engine

Provides validated ingestion, provenance tracking, duplicate candidate detection,
conflicting report preservation, media metadata validation, and privacy-preserving
anonymous reporting for ground-level citizen observations.

STRICT ARCHITECTURAL PRINCIPLE:
CITIZEN REPORT → EVIDENCE → VALIDATION → RECONCILIATION → NETWORK / INFRASTRUCTURE STATE
Citizen reports enter at OBSERVATION, never directly at STATE.
A citizen report does NOT automatically close roads, change flood depths, alter HAND,
or re-rank interventions until Phase E reconciliation criteria are satisfied.
"""

import math
import uuid
import re
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone

from cyclone_twin.domain.entities import (
    CitizenObservation,
    CitizenMediaMetadata,
    InfrastructureObservation,
)
from cyclone_twin.providers.observation_pipeline import (
    CHENNAI_BBOX,
    ObservationIngestionPipeline,
    normalize_observation_type,
    normalize_source_type,
)
from cyclone_twin.providers.multimodal_pipeline import (
    sanitize_untrusted_text,
    MultimodalIngestionService,
)

logger = logging.getLogger("cyclone_twin.citizen_pipeline")

# Controlled Report Types vocabulary
CONTROLLED_REPORT_TYPES: Set[str] = {
    "ROAD_FLOODED",
    "ROAD_BLOCKED",
    "ROAD_PASSABLE",
    "WATER_LEVEL",
    "DRAIN_OVERFLOW",
    "HOSPITAL_ACCESS_BLOCKED",
    "DEBRIS",
    "FALLEN_TREE",
    "BRIDGE_BLOCKED",
    "POWER_OUTAGE",
    "OTHER",
}

# Map citizen report types to Phase E observation types
REPORT_TYPE_TO_OBS_TYPE: Dict[str, str] = {
    "ROAD_FLOODED": "ROAD_BLOCKED",
    "ROAD_BLOCKED": "ROAD_BLOCKED",
    "DEBRIS": "ROAD_BLOCKED",
    "FALLEN_TREE": "ROAD_BLOCKED",
    "BRIDGE_BLOCKED": "ROAD_BLOCKED",
    "ROAD_PASSABLE": "ROAD_OPEN",
    "WATER_LEVEL": "FLOOD_DEPTH",
    "DRAIN_OVERFLOW": "DRAIN_OVERFLOW",
    "HOSPITAL_ACCESS_BLOCKED": "HOSPITAL_ACCESS",
    "POWER_OUTAGE": "TRAFFIC_CONDITION",
    "OTHER": "TRAFFIC_CONDITION",
}

ALLOWED_PHOTO_MIME_TYPES: Set[str] = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
MAX_PHOTO_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB


class CitizenPipelineService:
    """
    Phase L10: Citizen / PGIS Evidence Pipeline Service.
    Manages citizen report submission, validation, media metadata validation,
    duplicate candidate tagging, conflict preservation, and Phase E pipeline submission.

    READ-ONLY AT SUBMISSION: Does NOT mutate NetworkEngine or DisasterState directly.
    """

    def __init__(self, multimodal_service: Optional[MultimodalIngestionService] = None):
        self._multimodal_service = multimodal_service or MultimodalIngestionService()
        self.citizen_reports: Dict[str, CitizenObservation] = {}

    def validate_citizen_input(
        self,
        lat: Any,
        lon: Any,
        report_type: str,
        confidence: Any = 0.65,
        water_depth_m: Optional[Any] = None,
    ) -> Tuple[float, float, float, str, Optional[float]]:
        """
        Validates citizen report numeric parameters, bounds, and controlled report type.
        Raises ValueError for NaN, Infinity, out-of-bounds coords, or unsupported types.
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

        # Chennai BBox check
        if not (
            CHENNAI_BBOX["min_lon"] <= f_lon <= CHENNAI_BBOX["max_lon"]
            and CHENNAI_BBOX["min_lat"] <= f_lat <= CHENNAI_BBOX["max_lat"]
        ):
            raise ValueError(
                f"Coordinates ({f_lat:.4f}, {f_lon:.4f}) lie outside Chennai study region "
                f"[{CHENNAI_BBOX['min_lon']}-{CHENNAI_BBOX['max_lon']} E, {CHENNAI_BBOX['min_lat']}-{CHENNAI_BBOX['max_lat']} N]"
            )

        # Validate Confidence
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError(f"Confidence must be a numeric float, got {type(confidence).__name__}")
        f_conf = float(confidence)
        if math.isnan(f_conf) or math.isinf(f_conf):
            raise ValueError("Confidence cannot be NaN or Infinity")
        if not (0.0 <= f_conf <= 1.0):
            raise ValueError(f"Confidence must be within range [0.0, 1.0], got {f_conf}")

        # Validate Report Type
        norm_type = str(report_type).strip().upper()
        if norm_type not in CONTROLLED_REPORT_TYPES:
            raise ValueError(f"Unsupported report type '{report_type}'. Allowed: {sorted(list(CONTROLLED_REPORT_TYPES))}")

        # Validate depth if provided
        f_depth = None
        if water_depth_m is not None:
            if isinstance(water_depth_m, bool) or not isinstance(water_depth_m, (int, float)):
                raise ValueError("Water depth must be a valid non-negative float")
            f_depth = float(water_depth_m)
            if math.isnan(f_depth) or math.isinf(f_depth) or f_depth < 0.0:
                raise ValueError("Water depth must be a finite non-negative float")

        return f_lat, f_lon, f_conf, norm_type, f_depth

    def validate_media_metadata(
        self,
        filename: str,
        content_type: str,
        size_bytes: int,
    ) -> CitizenMediaMetadata:
        """
        Validates photo/media attachment metadata.
        Rejects executables, path traversal, oversized files, and unsupported MIME types.
        """
        if not filename:
            raise ValueError("Media filename cannot be empty")

        if ".." in filename or "/" in filename or "\\" in filename:
            raise ValueError("Filename contains disallowed path traversal sequences")

        norm_mime = content_type.lower().strip().split(";")[0].strip()
        if norm_mime not in ALLOWED_PHOTO_MIME_TYPES:
            raise ValueError(f"Unsupported media MIME type '{content_type}'. Allowed: {sorted(list(ALLOWED_PHOTO_MIME_TYPES))}")

        if size_bytes < 0:
            raise ValueError("Media size cannot be negative")

        if size_bytes > MAX_PHOTO_SIZE_BYTES:
            raise ValueError(f"Media file size ({size_bytes:,} bytes) exceeds maximum limit of 10 MB")

        safe_filename = sanitize_untrusted_text(filename)
        media_id = f"med_{uuid.uuid4().hex[:8]}"

        return CitizenMediaMetadata(
            media_id=media_id,
            filename_sanitized=safe_filename,
            mime_type=norm_mime,
            size_bytes=size_bytes,
            captured_at=datetime.now(timezone.utc),
            storage_ref=f"LOCAL_METADATA_{media_id}",
        )

    def _detect_duplicates_and_conflicts(
        self,
        lat: float,
        lon: float,
        report_type: str,
        now: datetime,
    ) -> Tuple[Optional[str], bool]:
        """
        Deterministic spatial-temporal duplicate candidate & conflicting report detector.
        Distance threshold: 0.1 km (100m). Time threshold: 30 minutes.

        Returns: (duplicate_candidate_id, has_conflicts)
        """
        dup_id: Optional[str] = None
        has_conflicts = False

        for existing in self.citizen_reports.values():
            # Distance in km
            d_lat = (existing.latitude - lat) * 111.0
            d_lon = (existing.longitude - lon) * 111.0 * math.cos(math.radians(lat))
            dist_km = math.sqrt(d_lat * d_lat + d_lon * d_lon)

            if dist_km <= 0.10:
                # Time difference in minutes
                ex_time = existing.created_at if existing.created_at.tzinfo else existing.created_at.replace(tzinfo=timezone.utc)
                age_min = abs((now - ex_time).total_seconds()) / 60.0

                if age_min <= 30.0:
                    if existing.report_type == report_type:
                        dup_id = existing.observation_id
                    elif (
                        (report_type in ("ROAD_FLOODED", "ROAD_BLOCKED") and existing.report_type == "ROAD_PASSABLE")
                        or (report_type == "ROAD_PASSABLE" and existing.report_type in ("ROAD_FLOODED", "ROAD_BLOCKED"))
                    ):
                        has_conflicts = True
                        existing.has_conflicting_reports = True

        return dup_id, has_conflicts

    def submit_citizen_report(
        self,
        lat: float,
        lon: float,
        report_type: str = "ROAD_FLOODED",
        description: Optional[str] = None,
        water_depth_m: Optional[float] = None,
        confidence: float = 0.65,
        severity: str = "medium",
        reporter_id: Optional[str] = None,
        is_anonymous: bool = True,
        media_filename: Optional[str] = None,
        media_content_type: Optional[str] = None,
        media_size_bytes: Optional[int] = None,
        timestamp: Optional[Any] = None,
        client_observation_id: Optional[str] = None,
    ) -> Tuple[CitizenObservation, InfrastructureObservation]:
        """
        Submits a ground-level citizen PGIS observation.

        READ-ONLY AT SUBMISSION:
        Inserts citizen observation into Phase E observation pipeline with source='citizen'.
        Does NOT directly mutate NetworkEngine or DisasterState.

        Returns: (CitizenObservation, InfrastructureObservation)
        """
        now = datetime.now(timezone.utc)

        # 1. Validate inputs
        f_lat, f_lon, f_conf, norm_report_type, f_depth = self.validate_citizen_input(
            lat=lat,
            lon=lon,
            report_type=report_type,
            confidence=confidence,
            water_depth_m=water_depth_m,
        )

        # 2. Sanitize user text description
        safe_desc = sanitize_untrusted_text(description or "")

        # 3. Process optional media metadata
        media_meta: Optional[CitizenMediaMetadata] = None
        if media_filename and media_content_type and media_size_bytes is not None:
            media_meta = self.validate_media_metadata(
                filename=media_filename,
                content_type=media_content_type,
                size_bytes=media_size_bytes,
            )

        # 4. Privacy: pseudonymous/anonymous reporter ID
        anon_reporter = (
            reporter_id if reporter_id and not is_anonymous
            else f"citizen_anon_{uuid.uuid4().hex[:6]}"
        )

        # 5. Duplicate and Conflict Detection
        obs_id = client_observation_id or f"cit_{uuid.uuid4().hex[:8]}"
        dup_candidate_id, has_conflicts = self._detect_duplicates_and_conflicts(
            lat=f_lat,
            lon=f_lon,
            report_type=norm_report_type,
            now=now,
        )

        initial_status = "DUPLICATE" if dup_candidate_id else "CONFLICTING" if has_conflicts else "SUBMITTED"

        # 6. Create CitizenObservation domain entity
        citizen_obs = CitizenObservation(
            observation_id=obs_id,
            report_type=norm_report_type,
            latitude=f_lat,
            longitude=f_lon,
            description=safe_desc,
            reporter_id=anon_reporter,
            is_anonymous=is_anonymous,
            water_depth_m=f_depth,
            severity=severity if severity in ("low", "medium", "high", "critical") else "medium",
            confidence=f_conf,
            status=initial_status,
            source="citizen",
            created_at=now,
            received_at=now,
            sync_status="SYNCED",
            media_metadata=media_meta,
            duplicate_candidate_id=dup_candidate_id,
            has_conflicting_reports=has_conflicts,
            provenance={
                "source": "citizen_pgis",
                "reporter_id": anon_reporter,
                "is_anonymous": is_anonymous,
                "has_media": media_meta is not None,
                "duplicate_candidate": dup_candidate_id,
                "conflicts_flagged": has_conflicts,
            },
        )
        self.citizen_reports[obs_id] = citizen_obs

        # 7. Map report_type to Phase E InfrastructureObservation type
        phase_e_obs_type = REPORT_TYPE_TO_OBS_TYPE.get(norm_report_type, "ROAD_BLOCKED")

        # 8. Submit report to Phase E Observation Pipeline (read-only observation store)
        infra_obs = self._multimodal_service.pipeline.submit_report(
            lat=f_lat,
            lon=f_lon,
            observation_type=phase_e_obs_type,
            source="citizen",
            severity=citizen_obs.severity,
            confidence=f_conf,
            raw_text=safe_desc or f"Citizen PGIS report ({norm_report_type})",
            observation_id=obs_id,
            timestamp=timestamp or now,
            value=f_depth,
        )

        return citizen_obs, infra_obs

    def get_citizen_observations(
        self,
        report_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[CitizenObservation]:
        """Returns list of active citizen PGIS observations matching optional filters."""
        results = list(self.citizen_reports.values())
        if report_type:
            rt_norm = str(report_type).strip().upper()
            results = [r for r in results if r.report_type == rt_norm]
        if status:
            st_norm = str(status).strip().upper()
            results = [r for r in results if r.status == st_norm]
        return results

    def get_observation_by_id(self, obs_id: str) -> Optional[CitizenObservation]:
        """Returns citizen observation by ID."""
        return self.citizen_reports.get(str(obs_id).strip())
