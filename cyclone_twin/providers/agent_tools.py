"""
Agentic AI Tool Interface for Cyclone Twin
Provides structured, validated tools for AI agents to query state and trigger deterministic simulation actions.
"""

from typing import Any, Dict, List, Optional
from cyclone_twin.providers.weather_provider import OpenMeteoWeatherProvider
from cyclone_twin.providers.flood_model import HANDFloodModel
from cyclone_twin.providers.observation_pipeline import ObservationIngestionPipeline


class AgenticToolRegistry:
    """Tool execution harness for AI agents operating on Cyclone Twin."""

    def __init__(self, observation_pipeline: Optional[ObservationIngestionPipeline] = None):
        self.weather_provider = OpenMeteoWeatherProvider()
        self.flood_model = HANDFloodModel()
        self.obs_pipeline = observation_pipeline or ObservationIngestionPipeline()

    def get_weather_forecast(self, lat: float = 13.0827, lon: float = 80.2707) -> Dict[str, Any]:
        """Tool: Retrieve weather forecast for target coordinates."""
        forecast = self.weather_provider.fetch_forecast(lat, lon)
        return forecast.model_dump(mode="json")

    def get_flood_state(self, water_level_m: Optional[float] = None) -> Dict[str, Any]:
        """Tool: Calculate flood inundation scenario."""
        forecast = self.weather_provider.fetch_forecast()
        scenario = self.flood_model.compute_inundation(forecast)
        if water_level_m is not None:
            scenario.water_level_m = water_level_m
        return scenario.model_dump(mode="json")

    def submit_ground_observation(
        self,
        lat: float,
        lon: float,
        observation_type: str = "road_blockage",
        source: str = "agent_ingested",
        severity: str = "high",
        confidence: float = 0.90,
        raw_text: Optional[str] = None,
        observation_id: Optional[str] = None,
        value: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Tool: Submit validated ground report through the observation pipeline validation path."""
        obs = self.obs_pipeline.submit_report(
            lat=lat,
            lon=lon,
            observation_type=observation_type,
            source=source,
            severity=severity,
            confidence=confidence,
            raw_text=raw_text,
            observation_id=observation_id,
            value=value,
        )
        return obs.model_dump(mode="json")

    def get_recent_observations(
        self,
        min_confidence: float = 0.50,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Tool: Query active validated ground observations."""
        active = self.obs_pipeline.get_active_observations(min_confidence=min_confidence)
        return [obs.model_dump(mode="json") for obs in active[:limit]]

    def extract_field_evidence(
        self,
        report_dict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Tool: Extract structured evidence from field report (Read-Only).
        Strict Rule: DOES NOT MUTATE NetworkEngine, graph, or accessibility state.
        Extracted evidence must be separately ingested through Phase E validation and reconciliation.
        """
        from cyclone_twin.providers.multimodal_pipeline import MultimodalExtractor
        extractor = MultimodalExtractor()
        extraction = extractor.extract_from_field_report(report_dict)
        return extraction.model_dump(mode="json")

