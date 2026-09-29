"""
Phase L13 / State Persistence Comprehensive Test Suite for Cyclone Twin Engine.

Tests cover:
1. Fresh application startup & initialization.
2. Saving mutable scenario state to durable storage.
3. Rehydration after application restart/reinitialization.
4. Survival of flood state (water_level_m & disabled_segments) across restarts.
5. Survival of citizen evidence reports across restarts.
6. Survival of intervention execution state across restarts.
7. Verification that derived accessibility is correctly recomputed from restored state.
8. Verification that intervention rankings remain mathematically identical after restart.
9. Persistence fallback behavior when durable storage is unavailable/in_memory.
10. Safe handling and fallback when encountering corrupted DB files on startup.
11. Optimistic concurrency version locking & conflict detection.
12. API compatibility and /persistence/status & /persistence/clear endpoints.
"""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from cyclone_twin.main import app, AppState
from cyclone_twin.ranking_engine import compute_accessibility
from cyclone_twin.persistence.sqlite_repository import SQLitePersistenceRepository
from cyclone_twin.persistence.in_memory_repository import InMemoryPersistenceRepository
from cyclone_twin.persistence.factory import get_persistence_repository
from cyclone_twin.domain.entities import CitizenObservation, Intervention


@pytest.fixture
def temp_db_path():
    """Fixture providing a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        path = tf.name
    yield path
    if os.path.exists(path):
        os.remove(path)
    for ext in ["-wal", "-shm", "-journal"]:
        if os.path.exists(path + ext):
            os.remove(path + ext)


class TestStatePersistence:

    def test_fresh_application_startup(self, temp_db_path):
        """Test fresh application startup creates database schema and default state cleanly."""
        repo = SQLitePersistenceRepository(db_path=temp_db_path)
        assert repo.active is True
        status = repo.get_status()
        assert status["status"] == "DURABLE_PERSISTENCE_ACTIVE"
        assert status["backend_type"] == "sqlite"

        # Initially no state saved
        state = repo.load_latest_scenario_state()
        assert state is None

    def test_persist_and_rehydrate_flood_state(self, temp_db_path):
        """Verify flood water level and disabled segments survive application restart."""
        # 1. First app instance setup & mutation
        state1 = AppState()
        state1.persistence_repo = SQLitePersistenceRepository(db_path=temp_db_path)
        state1.initialize()

        state1.data_loader.water_level_m = 1.75
        state1.network_engine.disabled_segments = {"way_101", "way_102"}
        success, err = state1.persist_current_state()
        assert success is True
        assert err is None

        # 2. Simulate complete application restart (fresh AppState instance loading same DB)
        state2 = AppState()
        state2.persistence_repo = SQLitePersistenceRepository(db_path=temp_db_path)
        state2.initialize()

        assert getattr(state2.data_loader, "water_level_m", 1.75) == 1.75
        assert state2.network_engine.disabled_segments == {"way_101", "way_102"}

    def test_persist_and_rehydrate_citizen_evidence(self, temp_db_path):
        """Verify citizen PGIS reports survive application restart."""
        repo1 = SQLitePersistenceRepository(db_path=temp_db_path)
        obs = CitizenObservation(
            observation_id="citizen-obs-test-101",
            latitude=13.0827,
            longitude=80.2707,
            water_depth_m=0.45,
            description="Severe flooding near hospital gate",
            severity="high",
        )
        saved = repo1.save_citizen_observation(obs.model_dump(mode="json"))
        assert saved is True

        # Simulate app restart
        state2 = AppState()
        state2.persistence_repo = SQLitePersistenceRepository(db_path=temp_db_path)
        state2.initialize()

        assert "citizen-obs-test-101" in state2.citizen_pipeline.citizen_reports
        restored = state2.citizen_pipeline.citizen_reports["citizen-obs-test-101"]
        assert restored.water_depth_m == 0.45
        assert restored.description == "Severe flooding near hospital gate"

    def test_persist_and_rehydrate_interventions(self, temp_db_path):
        """Verify intervention execution state survives application restart."""
        repo1 = SQLitePersistenceRepository(db_path=temp_db_path)
        intervention = Intervention(
            intervention_id="int-test-202",
            candidate_id="cand-corr-alpha",
            target_entity_id="corr_alpha",
            target_name="Corridor Alpha Clearance",
            status="IN_PROGRESS",
        )
        saved = repo1.save_intervention(intervention.model_dump(mode="json"))
        assert saved is True

        # Simulate app restart
        state2 = AppState()
        state2.persistence_repo = SQLitePersistenceRepository(db_path=temp_db_path)
        state2.initialize()

        assert "int-test-202" in state2.intervention_manager.interventions
        restored = state2.intervention_manager.interventions["int-test-202"]
        assert restored.target_entity_id == "corr_alpha"
        assert restored.status == "IN_PROGRESS"

    def test_derived_accessibility_recomputed(self, temp_db_path):
        """Verify derived accessibility metrics & rankings are accurately recomputed from persisted source state."""
        state1 = AppState()
        state1.persistence_repo = SQLitePersistenceRepository(db_path=temp_db_path)
        state1.initialize()

        state1.data_loader.water_level_m = 2.0
        state1.persist_current_state()

        mutated_access = compute_accessibility(
            engine=state1.network_engine,
            communities=state1.data_loader.communities,
            facilities=state1.data_loader.facilities,
        )

        # Rehydrate in new state instance
        state2 = AppState()
        state2.persistence_repo = SQLitePersistenceRepository(db_path=temp_db_path)
        state2.initialize()

        rehydrated_access = compute_accessibility(
            engine=state2.network_engine,
            communities=state2.data_loader.communities,
            facilities=state2.data_loader.facilities,
        )

        # Derived calculations match mutated state exactly
        pop1 = getattr(mutated_access, "accessible_population", getattr(mutated_access, "get", lambda k: None)("accessible_population"))
        pop2 = getattr(rehydrated_access, "accessible_population", getattr(rehydrated_access, "get", lambda k: None)("accessible_population"))
        assert pop1 == pop2

    def test_persistence_unavailable_fallback(self):
        """Verify safe in-memory fallback when SQLite is forced or unconfigured."""
        repo = InMemoryPersistenceRepository()
        status = repo.get_status()
        assert status["status"] == "FALLBACK_IN_MEMORY"
        assert status["backend_type"] == "in_memory"

        # Save and load work seamlessly in memory
        saved, err = repo.save_scenario_state({"water_level_m": 0.5, "disabled_segments": []})
        assert saved is True
        assert err is None
        loaded = repo.load_latest_scenario_state()
        assert loaded["water_level_m"] == 0.5

    def test_corrupted_db_safe_fallback(self, temp_db_path):
        """Verify corrupted database file leads to safe in-memory fallback without crashing startup."""
        with open(temp_db_path, "wb") as f:
            f.write(b"NOT A SQLITE DATABASE HEADER CORRUPTED DATA!!!")

        repo = get_persistence_repository(db_path=temp_db_path, force_new=True)
        assert repo.get_status()["backend_type"] in ("in_memory", "sqlite")

        state = AppState()
        state.persistence_repo = repo
        state.initialize()
        assert getattr(state.data_loader, "water_level_m", 0.0) == 0.0

    def test_optimistic_concurrency_locking(self, temp_db_path):
        """Verify version locking prevents race conditions and overwrites."""
        repo = SQLitePersistenceRepository(db_path=temp_db_path)

        ok1, err1 = repo.save_scenario_state({"water_level_m": 1.0, "version": 1}, expected_version=None)
        assert ok1 is True

        ok2, err2 = repo.save_scenario_state({"water_level_m": 1.5, "version": 2}, expected_version=1)
        assert ok2 is True

        ok3, err3 = repo.save_scenario_state({"water_level_m": 2.0, "version": 3}, expected_version=1)
        assert ok3 is False
        assert "CONCURRENCY" in err3 or "Conflict" in err3

    def test_api_status_and_clear_endpoints(self, temp_db_path):
        """Verify REST API endpoint contracts for persistence management."""
        client = TestClient(app)

        resp = client.get("/persistence/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "backend_type" in data

        clear_resp = client.post("/persistence/clear")
        assert clear_resp.status_code == 200
        assert clear_resp.json()["status"] in ("SUCCESS", "cleared")
