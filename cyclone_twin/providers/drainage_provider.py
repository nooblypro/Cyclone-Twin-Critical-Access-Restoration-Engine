"""
Phase L9 — GCC Drainage & Stormwater Infrastructure Evidence Provider
Cyclone Twin — Critical Access Restoration Engine

Provides a deterministic, provenance-aware infrastructure evidence layer representing
Greater Chennai Corporation (GCC) style stormwater drainage assets, conditions,
blockage status, and connectivity anomalies.

IMPORTANT PHYSICAL MODEL GUARANTEES:
1. HAND / terrain topography is NEVER modified by drainage infrastructure conditions.
   HAND represents baseline elevation/terrain susceptibility.
   Drainage condition represents infrastructure capacity/maintenance state.
2. Drainage provider is READ-ONLY. It does NOT mutate NetworkEngine, DisasterState,
   or operational state directly.
3. Does NOT claim to be a hydrodynamic solver (SWMM / Navier-Stokes).
4. Data provenance is explicitly labeled as `gcc_calibrated` (simulated scenario data)
   when live GCC IoT API telemetry is unavailable.
"""

import math
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from cyclone_twin.domain.entities import (
    DrainageInfrastructureAsset,
    DrainageInfrastructureSummary,
    DrainSegment,
)
from cyclone_twin.providers.observation_pipeline import CHENNAI_BBOX

logger = logging.getLogger("cyclone_twin.drainage_provider")


# Default calibrated GCC stormwater drainage infrastructure scenario assets
DEFAULT_GCC_DRAINAGE_ASSETS: List[Dict[str, Any]] = [
    {
        "asset_id": "drain_gcc_01",
        "asset_name": "Arterial Stormwater Drain — Grand Southern Trunk Rd",
        "asset_type": "stormwater_drain",
        "catchment_zone": "GCC_South_Adyar",
        "latitude": 13.0100,
        "longitude": 80.2100,
        "connected_network_node": "node_01",
        "condition_score": 0.40,
        "capacity_cumecs": 12.5,
        "capacity_factor": 0.35,
        "blockage_status": "partially_blocked",
        "blockage_probability": 0.65,
        "connectivity_status": "degraded",
        "observed_issue": "Heavy siltation and debris accumulation reducing effective flow section",
        "source": "gcc_calibrated",
        "confidence": 0.85,
        "is_simulated": True,
    },
    {
        "asset_id": "drain_gcc_02",
        "asset_name": "Box Culvert — Saidapet Junction",
        "asset_type": "culvert",
        "catchment_zone": "GCC_South_Adyar",
        "latitude": 13.0250,
        "longitude": 80.2230,
        "connected_network_node": "node_02",
        "condition_score": 0.20,
        "capacity_cumecs": 25.0,
        "capacity_factor": 0.15,
        "blockage_status": "severely_blocked",
        "blockage_probability": 0.90,
        "connectivity_status": "degraded",
        "observed_issue": "Structural blockage at inflow throat near metro bridge pillar",
        "source": "gcc_calibrated",
        "confidence": 0.90,
        "is_simulated": True,
    },
    {
        "asset_id": "drain_gcc_03",
        "asset_name": "Outfall Channel — Cooum River Discharge #4",
        "asset_type": "outfall",
        "catchment_zone": "GCC_Central_Cooum",
        "latitude": 13.0750,
        "longitude": 80.2600,
        "connected_network_node": "node_03",
        "condition_score": 0.85,
        "capacity_cumecs": 30.0,
        "capacity_factor": 0.85,
        "blockage_status": "open",
        "blockage_probability": 0.10,
        "connectivity_status": "connected",
        "observed_issue": None,
        "source": "gcc_calibrated",
        "confidence": 0.90,
        "is_simulated": True,
    },
    {
        "asset_id": "drain_gcc_04",
        "asset_name": "Stormwater Pumping Station — Velachery South",
        "asset_type": "pumping_station",
        "catchment_zone": "GCC_South_Velachery",
        "latitude": 12.9800,
        "longitude": 80.2200,
        "connected_network_node": "node_04",
        "condition_score": 0.50,
        "capacity_cumecs": 18.0,
        "capacity_factor": 0.50,
        "blockage_status": "partially_blocked",
        "blockage_probability": 0.50,
        "connectivity_status": "degraded",
        "observed_issue": "Auxiliary pump #2 tripping under high trash rack head loss",
        "source": "gcc_calibrated",
        "confidence": 0.80,
        "is_simulated": True,
    },
    {
        "asset_id": "drain_gcc_05",
        "asset_name": "Micro-Drain Link — Kodambakkam High Rd",
        "asset_type": "drain_link",
        "catchment_zone": "GCC_Central",
        "latitude": 13.0500,
        "longitude": 80.2300,
        "connected_network_node": "node_05",
        "condition_score": 0.10,
        "capacity_cumecs": 5.0,
        "capacity_factor": 0.05,
        "blockage_status": "inoperable",
        "blockage_probability": 0.95,
        "connectivity_status": "missing_link",
        "observed_issue": "Unlinked construction gap between primary collector and roadside conduit",
        "source": "gcc_calibrated",
        "confidence": 0.95,
        "is_simulated": True,
    },
    {
        "asset_id": "drain_gcc_06",
        "asset_name": "Drainage Junction Vault — Guindy Industrial Estate",
        "asset_type": "junction",
        "catchment_zone": "GCC_South_Adyar",
        "latitude": 13.0080,
        "longitude": 80.2120,
        "connected_network_node": "node_06",
        "condition_score": 0.90,
        "capacity_cumecs": 15.0,
        "capacity_factor": 0.90,
        "blockage_status": "open",
        "blockage_probability": 0.05,
        "connectivity_status": "connected",
        "observed_issue": None,
        "source": "gcc_calibrated",
        "confidence": 0.85,
        "is_simulated": True,
    },
]


class DrainageInfrastructureProvider:
    """
    Phase L9: Drainage Infrastructure Evidence Provider.
    Manages loading, validation, spatial indexing, and provenance tracking for
    Greater Chennai Corporation (GCC) stormwater drainage assets and condition reports.

    READ-ONLY: Does NOT mutate NetworkEngine, DisasterState, or HAND terrain topography.
    """

    def __init__(
        self,
        assets: Optional[List[DrainageInfrastructureAsset]] = None,
        source_name: str = "gcc_calibrated",
        is_simulated: bool = True,
    ):
        self.source_name = source_name
        self.is_simulated = is_simulated
        self._assets: Dict[str, DrainageInfrastructureAsset] = {}

        if assets is not None:
            for asset in assets:
                self._add_asset(asset)
        else:
            self._load_default_calibrated_assets()

    def _load_default_calibrated_assets(self) -> None:
        """Loads default calibrated GCC stormwater drainage scenario dataset."""
        now = datetime.now(timezone.utc)
        for item in DEFAULT_GCC_DRAINAGE_ASSETS:
            asset = DrainageInfrastructureAsset(
                asset_id=item["asset_id"],
                asset_name=item["asset_name"],
                asset_type=item["asset_type"],
                catchment_zone=item["catchment_zone"],
                latitude=item["latitude"],
                longitude=item["longitude"],
                connected_network_node=item.get("connected_network_node"),
                condition_score=item["condition_score"],
                capacity_cumecs=item["capacity_cumecs"],
                capacity_factor=item["capacity_factor"],
                blockage_status=item["blockage_status"],
                blockage_probability=item["blockage_probability"],
                connectivity_status=item["connectivity_status"],
                observed_issue=item.get("observed_issue"),
                source=self.source_name,
                confidence=item["confidence"],
                provenance={
                    "dataset": "GCC Calibrated Stormwater Drainage Infrastructure Scenario",
                    "source_type": self.source_name,
                    "is_simulated": self.is_simulated,
                    "zone": item["catchment_zone"],
                },
                is_simulated=self.is_simulated,
                last_inspected_at=now,
            )
            self._assets[asset.asset_id] = asset

    def _add_asset(self, asset: DrainageInfrastructureAsset) -> None:
        """Validates and registers an asset into the provider index."""
        if not asset.asset_id:
            raise ValueError("DrainageInfrastructureAsset missing required asset_id")
        self._assets[asset.asset_id] = asset

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_drainage_assets(
        self,
        catchment_zone: Optional[str] = None,
        blockage_status: Optional[str] = None,
    ) -> List[DrainageInfrastructureAsset]:
        """
        Returns list of drainage infrastructure assets matching optional filters.
        Pure read-only operation.
        """
        results = list(self._assets.values())
        if catchment_zone:
            cz_norm = str(catchment_zone).strip().lower()
            results = [a for a in results if a.catchment_zone.lower() == cz_norm]
        if blockage_status:
            bs_norm = str(blockage_status).strip().lower()
            results = [a for a in results if a.blockage_status.lower() == bs_norm]
        return results

    def get_asset_by_id(self, asset_id: str) -> Optional[DrainageInfrastructureAsset]:
        """Returns asset by ID or None if not found."""
        return self._assets.get(str(asset_id).strip())

    def get_drainage_summary(
        self,
        catchment_zone: Optional[str] = None,
    ) -> DrainageInfrastructureSummary:
        """
        Produces a complete DrainageInfrastructureSummary for the public API.
        Includes full provenance metadata, explicit status, assumptions, and limitations.
        """
        assets = self.get_drainage_assets(catchment_zone=catchment_zone)
        now = datetime.now(timezone.utc)

        blocked_count = sum(
            1 for a in assets if a.blockage_status in ("partially_blocked", "severely_blocked", "inoperable")
        )
        degraded_conn_count = sum(
            1 for a in assets if a.connectivity_status in ("degraded", "disconnected", "missing_link")
        )

        lats = [a.latitude for a in assets] if assets else [CHENNAI_BBOX["min_lat"]]
        lons = [a.longitude for a in assets] if assets else [CHENNAI_BBOX["min_lon"]]

        coverage = {
            "min_lat": min(lats),
            "max_lat": max(lats),
            "min_lon": min(lons),
            "max_lon": max(lons),
        }

        assumptions = [
            "Representative GCC stormwater drainage infrastructure scenario calibrated for Greater Chennai Corporation.",
            "HAND topography represents baseline terrain susceptibility; drainage condition provides complementary infrastructure capacity/vulnerability evidence.",
            "Drainage infrastructure observations do NOT alter HAND elevation values or hydraulic slope topography.",
        ]

        limitations = [
            "No real-time GCC IoT sensor telemetry stream connected; uses calibrated infrastructure scenario fixture.",
            "Static drainage network topology without hydrodynamic SWMM pipe flow solver.",
            "Field evidence reports require Phase E validation and reconciliation before state ingestion.",
        ]

        return DrainageInfrastructureSummary(
            retrieved_at=now,
            dataset_name="GCC Calibrated Stormwater Drainage Infrastructure Scenario",
            dataset_version="v1.0",
            source=self.source_name,
            is_simulated=self.is_simulated,
            total_assets=len(assets),
            blocked_assets_count=blocked_count,
            degraded_connectivity_count=degraded_conn_count,
            geographic_coverage=coverage,
            assets=assets,
            provenance={
                "provider": "DrainageInfrastructureProvider",
                "source_type": self.source_name,
                "is_simulated": self.is_simulated,
                "catchment_filter": catchment_zone,
                "asset_count": len(assets),
            },
            assumptions=assumptions,
            limitations=limitations,
        )

    # ------------------------------------------------------------------
    # Spatial Drainage Vulnerability Evidence Evaluation
    # ------------------------------------------------------------------

    def evaluate_drainage_vulnerability_factor(
        self,
        lat: float,
        lon: float,
        radius_km: float = 1.5,
    ) -> float:
        """
        Evaluates a spatial drainage vulnerability factor [0.0, 1.0] for a coordinate.
        Calculates impact of nearby degraded/blocked drainage assets within radius_km.

        PURE READ-ONLY: Does NOT mutate HAND terrain, flood model, or NetworkEngine state.

        Returns:
            0.0 -> Drainage fully operational, no nearby blockages
            1.0 -> High localized drainage failure/blockage risk
        """
        if isinstance(lat, bool) or isinstance(lon, bool) or not (
            isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        ):
            raise ValueError("Coordinates must be valid numeric floats")

        f_lat, f_lon = float(lat), float(lon)
        if math.isnan(f_lat) or math.isnan(f_lon) or math.isinf(f_lat) or math.isinf(f_lon):
            raise ValueError("Coordinates cannot be NaN or Infinity")

        if not (-90.0 <= f_lat <= 90.0 and -180.0 <= f_lon <= 180.0):
            raise ValueError("Coordinates out of geographic range")

        max_vuln = 0.0

        for asset in self._assets.values():
            # Haversine distance in km
            d_lat = math.radians(asset.latitude - f_lat)
            d_lon = math.radians(asset.longitude - f_lon)
            a = (
                math.sin(d_lat / 2.0) ** 2
                + math.cos(math.radians(f_lat))
                * math.cos(math.radians(asset.latitude))
                * math.sin(d_lon / 2.0) ** 2
            )
            c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
            dist_km = 6371.0 * c

            if dist_km <= radius_km:
                # Drainage asset severity factor based on blockage and condition loss
                blockage_factor = (
                    0.90 if asset.blockage_status == "inoperable"
                    else 0.75 if asset.blockage_status == "severely_blocked"
                    else 0.50 if asset.blockage_status == "partially_blocked"
                    else 0.10
                )
                capacity_loss = 1.0 - max(0.0, min(1.0, asset.capacity_factor))
                asset_vuln = (0.60 * blockage_factor + 0.40 * capacity_loss) * asset.confidence

                # Distance decay
                distance_weight = max(0.0, 1.0 - (dist_km / radius_km))
                local_impact = asset_vuln * distance_weight
                if local_impact > max_vuln:
                    max_vuln = local_impact

        return round(min(1.0, max(0.0, max_vuln)), 4)
