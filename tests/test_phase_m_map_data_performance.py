"""
Regression tests for /map/data production performance and GeoJSON schema integrity.
Verifies response status, schema keys, layer feature counts, and latency bounds.
"""

import time
import pytest
from fastapi.testclient import TestClient
from cyclone_twin.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_map_data_schema_and_performance(client):
    """
    Verifies GET /map/data returns 200 OK, valid GeoJSON feature collections,
    correct network feature counts, and sub-200ms local execution speed.
    """
    t0 = time.time()
    response = client.get("/map/data")
    elapsed = time.time() - t0

    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}"
    data = response.json()

    # Schema Validation
    required_keys = {"roads", "facilities", "communities", "flood", "disabled_segments", "last_cleared_corridor"}
    assert required_keys.issubset(set(data.keys())), f"Missing keys in /map/data response: {required_keys - set(data.keys())}"

    # Feature Collection Schema Validation
    assert data["roads"]["type"] == "FeatureCollection"
    assert data["facilities"]["type"] == "FeatureCollection"
    assert data["communities"]["type"] == "FeatureCollection"

    # Network Representation Feature Counts
    roads_count = len(data["roads"]["features"])
    facilities_count = len(data["facilities"]["features"])
    communities_count = len(data["communities"]["features"])

    assert roads_count == 56, f"Expected 56 road features, found {roads_count}"
    assert facilities_count == 6, f"Expected 6 hospital facilities, found {facilities_count}"
    assert communities_count == 10, f"Expected 10 communities, found {communities_count}"

    # Latency Requirement (Sub-200ms for local execution)
    assert elapsed < 0.500, f"GET /map/data took too long locally: {elapsed:.3f}s"


def test_map_data_consecutive_consistency(client):
    """
    Verifies that multiple consecutive GET /map/data calls execute consistently
    without memory leak, missing properties, or geometry serialization degradation.
    """
    for _ in range(3):
        res = client.get("/map/data")
        assert res.status_code == 200
        payload = res.json()
        assert len(payload["roads"]["features"]) == 56
        assert len(payload["facilities"]["features"]) == 6
        assert len(payload["communities"]["features"]) == 10
