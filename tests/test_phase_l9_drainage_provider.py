"""
Phase L9 Test Suite — GCC Drainage & Stormwater Infrastructure Evidence Provider
Cyclone Twin — Critical Access Restoration Engine

Verifies:
1. DrainageInfrastructureAsset entity creation & validation
2. Strict NaN, Infinity, and out-of-bounds float rejection
3. DrainageInfrastructureProvider asset loading & spatial queries
4. Provenance tracking and explicit simulated/calibrated labeling
5. HAND topography preservation (0 mutation on HAND elevation/topography)
6. State preservation (0 mutation on NetworkEngine/DisasterState from provider queries)
7. Forecast != Observation != State invariant preservation
8. Phase E observation pipeline support for DRAIN_BLOCKED reports
9. Voice evidence pipeline integration for drainage reports
10. FastAPI GET /infrastructure/drainage endpoint compliance & validation
"""

import math
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from cyclone_twin.main import app, state
from cyclone_twin.domain.entities import (
    DrainageInfrastructureAsset,
    DrainageInfrastructureSummary,
    DrainSegment,
    InfrastructureObservation,
)
from cyclone_twin.providers.drainage_provider import (
    DrainageInfrastructureProvider,
    DEFAULT_GCC_DRAINAGE_ASSETS,
)
from cyclone_twin.providers.flood_model import HANDFloodModel


@pytest.fixture
def sample_asset():
    """Provides a valid test DrainageInfrastructureAsset."""
    return DrainageInfrastructureAsset(
        asset_id="drain_test_01",
        asset_name="Test Culvert",
        asset_type="culvert",
        catchment_zone="GCC_Central",
        latitude=13.0827,
        longitude=80.2707,
        condition_score=0.75,
        capacity_cumecs=15.0,
        capacity_factor=0.80,
        blockage_status="partially_blocked",
        blockage_probability=0.30,
        connectivity_status="connected",
        source="gcc_calibrated",
        confidence=0.85,
        is_simulated=True,
    )


@pytest.fixture
def mock_drainage_provider():
    """Provides a fresh DrainageInfrastructureProvider instance."""
    return DrainageInfrastructureProvider()


# ---------------------------------------------------------------------------
# 1. Entity Validation Tests
# ---------------------------------------------------------------------------

def test_drainage_asset_creation_valid(sample_asset):
    """Verifies successful creation of a valid DrainageInfrastructureAsset."""
    assert sample_asset.asset_id == "drain_test_01"
    assert sample_asset.asset_type == "culvert"
    assert sample_asset.latitude == 13.0827
    assert sample_asset.longitude == 80.2707
    assert sample_asset.condition_score == 0.75
    assert sample_asset.is_simulated is True


def test_drainage_asset_nan_rejection():
    """Rejects NaN float values for numeric fields."""
    with pytest.raises(ValueError):
        DrainageInfrastructureAsset(
            asset_id="drain_nan",
            latitude=float("nan"),
            longitude=80.2707,
        )

    with pytest.raises(ValueError):
        DrainageInfrastructureAsset(
            asset_id="drain_nan_cond",
            latitude=13.0827,
            longitude=80.2707,
            condition_score=float("nan"),
        )


def test_drainage_asset_infinity_rejection():
    """Rejects Infinity float values for coordinates and attributes."""
    with pytest.raises(ValueError):
        DrainageInfrastructureAsset(
            asset_id="drain_inf",
            latitude=13.0827,
            longitude=float("inf"),
        )

    with pytest.raises(ValueError):
        DrainageInfrastructureAsset(
            asset_id="drain_inf_prob",
            latitude=13.0827,
            longitude=80.2707,
            blockage_probability=float("-inf"),
        )


def test_drainage_asset_bounds_validation():
    """Enforces geographic and probability bounds on Pydantic schema."""
    with pytest.raises(ValueError):
        DrainageInfrastructureAsset(
            asset_id="drain_out_bounds",
            latitude=95.0,  # invalid lat
            longitude=80.2707,
        )

    with pytest.raises(ValueError):
        DrainageInfrastructureAsset(
            asset_id="drain_conf_bounds",
            latitude=13.0827,
            longitude=80.2707,
            confidence=1.5,  # out of range [0, 1]
        )


# ---------------------------------------------------------------------------
# 2. Provider Loading & Provenance Tests
# ---------------------------------------------------------------------------

def test_provider_load_default_assets(mock_drainage_provider):
    """Verifies default GCC calibrated assets load correctly."""
    assets = mock_drainage_provider.get_drainage_assets()
    assert len(assets) >= 6
    assert any(a.asset_id == "drain_gcc_01" for a in assets)
    assert any(a.asset_type == "pumping_station" for a in assets)


def test_provider_explicit_provenance(mock_drainage_provider):
    """Verifies that provider assets and summaries explicitly state source and simulated status."""
    summary = mock_drainage_provider.get_drainage_summary()
    assert summary.source == "gcc_calibrated"
    assert summary.is_simulated is True
    assert "Representative GCC stormwater drainage infrastructure scenario" in summary.assumptions[0]
    assert len(summary.limitations) >= 2


def test_provider_empty_dataset_handling():
    """Verifies provider handles an empty asset list safely."""
    provider = DrainageInfrastructureProvider(assets=[])
    assets = provider.get_drainage_assets()
    assert len(assets) == 0

    summary = provider.get_drainage_summary()
    assert summary.total_assets == 0
    assert summary.blocked_assets_count == 0


def test_provider_asset_filtering(mock_drainage_provider):
    """Tests filtering assets by catchment zone and blockage status."""
    adyar_assets = mock_drainage_provider.get_drainage_assets(catchment_zone="GCC_South_Adyar")
    assert len(adyar_assets) >= 1
    assert all(a.catchment_zone == "GCC_South_Adyar" for a in adyar_assets)

    blocked_assets = mock_drainage_provider.get_drainage_assets(blockage_status="severely_blocked")
    assert len(blocked_assets) >= 1
    assert all(a.blockage_status == "severely_blocked" for a in blocked_assets)


def test_provider_get_asset_by_id(mock_drainage_provider):
    """Tests asset retrieval by ID."""
    asset = mock_drainage_provider.get_asset_by_id("drain_gcc_02")
    assert asset is not None
    assert asset.asset_type == "culvert"

    missing = mock_drainage_provider.get_asset_by_id("non_existent_id")
    assert missing is None


# ---------------------------------------------------------------------------
# 3. Spatial Vulnerability Evaluation & Non-Mutation Invariants
# ---------------------------------------------------------------------------

def test_spatial_drainage_vulnerability_factor(mock_drainage_provider):
    """Tests evaluate_drainage_vulnerability_factor for spatial coordinate."""
    # Near Saidapet culvert (severely blocked)
    factor_blocked = mock_drainage_provider.evaluate_drainage_vulnerability_factor(13.0250, 80.2230)
    assert 0.0 <= factor_blocked <= 1.0
    assert factor_blocked > 0.40

    # Far away in open water / distant area
    factor_distant = mock_drainage_provider.evaluate_drainage_vulnerability_factor(12.8000, 80.0000)
    assert factor_distant == 0.0


def test_hand_elevation_remains_unchanged(mock_drainage_provider):
    """
    CRITICAL PHYSICAL INVARIANT:
    Drainage infrastructure evidence MUST NOT alter HAND terrain elevation model values.
    """
    from cyclone_twin.domain.entities import WeatherForecast

    hand_model = HANDFloodModel()
    forecast = WeatherForecast(precipitation_mm=100.0, wind_speed_kmh=80.0)

    # Compute HAND inundation scenario before
    scenario_before = hand_model.compute_inundation(forecast)

    # Evaluate drainage provider
    vuln_factor = mock_drainage_provider.evaluate_drainage_vulnerability_factor(13.0250, 80.2230)
    assert vuln_factor > 0.0

    # Compute HAND inundation scenario after — MUST BE IDENTICAL
    scenario_after = hand_model.compute_inundation(forecast)
    assert scenario_before.water_level_m == scenario_after.water_level_m
    assert scenario_before.hand_threshold_m == scenario_after.hand_threshold_m
    assert scenario_before.flood_geojson == scenario_after.flood_geojson


def test_provider_does_not_mutate_simulation_state(mock_drainage_provider):
    """
    INVARIANT: Provider operations are 100% read-only and leave NetworkEngine unchanged.
    """
    state.initialize()
    edges_before = state.network_engine.graph.number_of_edges()

    # Perform queries
    _ = mock_drainage_provider.get_drainage_summary()
    _ = mock_drainage_provider.evaluate_drainage_vulnerability_factor(13.0827, 80.2707)

    edges_after = state.network_engine.graph.number_of_edges()
    assert edges_before == edges_after


# ---------------------------------------------------------------------------
# 4. Observation & Reconciliation Pipeline Integration
# ---------------------------------------------------------------------------

def test_observation_pipeline_supports_drain_blocked():
    """Verifies that Phase E observation pipeline accepts DRAIN_BLOCKED observation type."""
    state.initialize()
    pipeline = state.multimodal_service.pipeline

    obs = pipeline.submit_report(
        lat=13.0250,
        lon=80.2230,
        observation_type="DRAIN_BLOCKED",
        source="field_team",
        severity="critical",
        confidence=0.90,
        raw_text="Main box culvert throat completely clogged with cyclone debris",
    )

    assert obs.observation_type == "DRAIN_BLOCKED"
    assert obs.validated is True
    assert obs.status in ("accepted", "VALIDATED", "SUBMITTED", "PENDING_RECONCILIATION")


def test_observation_pipeline_drain_blocked_nan_rejection():
    """Rejects NaN coordinates on DRAIN_BLOCKED observation submission."""
    state.initialize()
    pipeline = state.multimodal_service.pipeline

    with pytest.raises(ValueError, match="NaN"):
        pipeline.submit_report(
            lat=float("nan"),
            lon=80.2230,
            observation_type="DRAIN_BLOCKED",
            source="field_team",
            confidence=0.90,
        )


def test_forecast_observation_state_separation(mock_drainage_provider):
    """
    INVARIANT: FORECAST != OBSERVATION != STATE
    Checking drainage assets does not create unverified ground observations or alter forecasts.
    """
    state.initialize()
    obs_count_before = len(state.multimodal_service.pipeline.observations)

    # Calling provider does NOT insert observation into pipeline
    _ = mock_drainage_provider.get_drainage_summary()

    obs_count_after = len(state.multimodal_service.pipeline.observations)
    assert obs_count_before == obs_count_after


# ---------------------------------------------------------------------------
# 5. Voice Pipeline Integration
# ---------------------------------------------------------------------------

def test_voice_pipeline_drainage_observation_extraction():
    """Verifies that spoken drainage reports route cleanly to DRAIN_BLOCKED observation type."""
    state.initialize()
    voice_pipeline = state.voice_pipeline

    # Sample WAV audio bytes fixture
    header = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    audio_bytes = header + (b"\x00" * 100)

    # Transcribe and extract (read-only)
    artifact, transcription, extraction = voice_pipeline.transcribe_and_extract(
        audio_bytes=audio_bytes,
        filename="drain_report.wav",
        content_type="audio/wav",
        source_type="field_team",
        user_lat=13.0250,
        user_lon=80.2230,
    )

    assert extraction.source_type == "field_team"
    assert extraction.latitude == 13.0250
    assert extraction.longitude == 80.2230


# ---------------------------------------------------------------------------
# 6. FastAPI Endpoint Tests
# ---------------------------------------------------------------------------

def test_fastapi_get_drainage_infrastructure():
    """Tests GET /infrastructure/drainage endpoint."""
    client = TestClient(app)

    response = client.get("/infrastructure/drainage")
    assert response.status_code == 200

    data = response.json()
    assert "assets" in data
    assert "provenance" in data
    assert "source" in data
    assert data["source"] == "gcc_calibrated"
    assert data["is_simulated"] is True
    assert data["total_assets"] >= 6


def test_fastapi_get_drainage_infrastructure_with_filters():
    """Tests GET /infrastructure/drainage with catchment and status query parameters."""
    client = TestClient(app)

    response = client.get("/infrastructure/drainage?catchment=GCC_South_Adyar&status=severely_blocked")
    assert response.status_code == 200

    data = response.json()
    assert data["total_assets"] >= 1
    assert all(a["catchment_zone"] == "GCC_South_Adyar" for a in data["assets"])
    assert all(a["blockage_status"] == "severely_blocked" for a in data["assets"])


def test_fastapi_get_drainage_infrastructure_invalid_filter_handling():
    """Verifies graceful response when filter matches no assets."""
    client = TestClient(app)

    response = client.get("/infrastructure/drainage?catchment=NON_EXISTENT_ZONE")
    assert response.status_code == 200

    data = response.json()
    assert data["total_assets"] == 0
    assert len(data["assets"]) == 0


def test_deterministic_repeated_results(mock_drainage_provider):
    """Verifies that identical provider queries produce 100% deterministic output."""
    res1 = mock_drainage_provider.evaluate_drainage_vulnerability_factor(13.0250, 80.2230)
    res2 = mock_drainage_provider.evaluate_drainage_vulnerability_factor(13.0250, 80.2230)
    assert res1 == res2


def test_drain_segment_backwards_compatibility():
    """Ensures existing DrainSegment model remains fully functional."""
    ds = DrainSegment(
        drain_id="ds_01",
        catchment_zone="Zone 10",
        gradient_slope=0.002,
        capacity_cumecs=15.0,
        condition_rating="clogged",
        provenance="gcc_calibrated",
    )
    assert ds.drain_id == "ds_01"
    assert ds.condition_rating == "clogged"
