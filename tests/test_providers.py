"""
Unit and Integration Tests for Cyclone Twin Extension Providers
Tests weather ingestion, flood model abstraction, capacity travel time, observation pipeline, and agent tools.
"""

import pytest
from cyclone_twin.providers import (
    CalibratedWeatherProvider,
    OpenMeteoWeatherProvider,
    CalibratedFloodModel,
    HANDFloodModel,
    CalibratedNetworkProvider,
    StaticTravelTimeModel,
    BPRCapacityTravelTimeModel,
    ObservationIngestionPipeline,
    AgenticToolRegistry,
)


def test_weather_providers():
    calibrated = CalibratedWeatherProvider()
    forecast = calibrated.fetch_forecast()
    assert forecast.precipitation_mm == 180.0
    assert forecast.provider == "calibrated_fallback"

    open_meteo = OpenMeteoWeatherProvider(fallback_provider=calibrated)
    om_forecast = open_meteo.fetch_forecast()
    assert om_forecast.precipitation_mm >= 0.0
    assert om_forecast.provider in ("open_meteo", "calibrated_fallback")


def test_flood_models():
    calibrated_weather = CalibratedWeatherProvider().fetch_forecast()
    calibrated_flood = CalibratedFloodModel()
    scenario = calibrated_flood.compute_inundation(calibrated_weather)
    assert scenario.scenario_id == "michaung_dec_2023"
    assert scenario.water_level_m == 1.2

    hand_model = HANDFloodModel()
    hand_scenario = hand_model.compute_inundation(calibrated_weather)
    assert hand_scenario.source == "hand_model"
    assert hand_scenario.water_level_m > 0.0


def test_travel_time_models():
    static_model = StaticTravelTimeModel()
    bpr_model = BPRCapacityTravelTimeModel(alpha=0.15, beta=4.0)

    # 1000m road at 36 km/h = 10 m/s -> 100s free flow
    t_static = static_model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0, volume=0.0)
    assert abs(t_static - 100.0) < 1e-3

    # Free flow zero volume
    t_bpr_free = bpr_model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0, capacity=1000.0, volume=0.0)
    assert abs(t_bpr_free - 100.0) < 1e-3

    # At capacity (v/c = 1.0) -> t_bpr = 100 * (1 + 0.15 * 1^4) = 115.0s
    t_bpr_cap = bpr_model.compute_travel_time(length_m=1000.0, free_flow_speed_kph=36.0, capacity=1000.0, volume=1000.0)
    assert abs(t_bpr_cap - 115.0) < 1e-3


def test_observation_pipeline():
    pipeline = ObservationIngestionPipeline()
    obs = pipeline.submit_report(
        lat=13.01,
        lon=80.22,
        observation_type="flooding",
        source="citizen_report",
        severity="critical",
        confidence=0.92,
        raw_text="Severe waterlogging on Adyar bridge",
    )
    assert obs.validated is True
    assert obs.severity == "critical"

    active = pipeline.get_active_observations()
    assert len(active) == 1
    assert active[0].observation_id == obs.observation_id


def test_agent_tool_registry():
    registry = AgenticToolRegistry()

    weather_res = registry.get_weather_forecast()
    assert "precipitation_mm" in weather_res

    flood_res = registry.get_flood_state(water_level_m=1.5)
    assert flood_res["water_level_m"] == 1.5

    obs_res = registry.submit_ground_observation(lat=13.02, lon=80.23, raw_text="Fallen tree near Saidapet")
    assert obs_res["validated"] is True
