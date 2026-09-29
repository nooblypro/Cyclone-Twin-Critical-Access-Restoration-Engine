"""
SQLite Storage Implementation for Cyclone Twin Persistence Subsystem
Provides durable single-file database storage using Python's built-in sqlite3.
Enables optimistic version locking, atomic transactions, WAL concurrency mode,
and zero-downtime fallback degradation.
"""

import json
import os
import sqlite3
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .repository import PersistenceRepository

logger = logging.getLogger("cyclone_twin.persistence.sqlite")


class SQLitePersistenceRepository(PersistenceRepository):
    """
    SQLite-backed durable state repository.
    Persists source state across application restarts on Render or local execution.
    """

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_path = os.getenv("CYCLONE_TWIN_DB_PATH", "cache/cyclone_twin_state.db")
        
        self.db_path = db_path
        self.active = False
        self.last_error: Optional[str] = None
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a configured SQLite connection with WAL mode and row factory."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _initialize_database(self):
        """Creates required database directory and schema tables if not present."""
        try:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scenario_snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        version INTEGER NOT NULL,
                        scenario_id TEXT NOT NULL,
                        water_level_m REAL NOT NULL,
                        disabled_segments_json TEXT NOT NULL,
                        state_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS citizen_observations (
                        observation_id TEXT PRIMARY KEY,
                        report_type TEXT NOT NULL,
                        lat REAL NOT NULL,
                        lon REAL NOT NULL,
                        data_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS interventions (
                        intervention_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        corridor_id TEXT,
                        data_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        audit_id TEXT PRIMARY KEY,
                        intervention_id TEXT NOT NULL,
                        from_status TEXT,
                        to_status TEXT,
                        data_json TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    );
                """)
                conn.commit()
            self.active = True
            self.last_error = None
            logger.info(f"[PERSISTENCE] SQLite database initialized at '{self.db_path}'")
        except Exception as err:
            self.active = False
            self.last_error = str(err)
            logger.warning(f"[PERSISTENCE WARNING] SQLite initialization fallback: {err}")

    def get_status(self) -> Dict[str, Any]:
        """Returns structured persistence health status manifest."""
        if not self.active:
            return {
                "backend_type": "sqlite",
                "status": "FALLBACK_IN_MEMORY",
                "storage_location": self.db_path,
                "is_active": False,
                "error": self.last_error,
            }

        try:
            with self._get_connection() as conn:
                c_snap = conn.execute("SELECT COUNT(*), MAX(version) FROM scenario_snapshots").fetchone()
                c_obs = conn.execute("SELECT COUNT(*) FROM citizen_observations").fetchone()
                c_int = conn.execute("SELECT COUNT(*) FROM interventions").fetchone()
                c_aud = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()

                return {
                    "backend_type": "sqlite",
                    "status": "DURABLE_PERSISTENCE_ACTIVE",
                    "storage_location": self.db_path,
                    "is_active": True,
                    "snapshots_count": c_snap[0] if c_snap else 0,
                    "latest_version": c_snap[1] if c_snap and c_snap[1] else 1,
                    "observations_count": c_obs[0] if c_obs else 0,
                    "interventions_count": c_int[0] if c_int else 0,
                    "audit_events_count": c_aud[0] if c_aud else 0,
                }
        except Exception as err:
            return {
                "backend_type": "sqlite",
                "status": "FALLBACK_IN_MEMORY",
                "storage_location": self.db_path,
                "is_active": False,
                "error": str(err),
            }

    def save_scenario_state(
        self,
        snapshot_data: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Saves scenario state snapshot with optimistic version check."""
        if not self.active:
            return False, "PERSISTENCE_INACTIVE_FALLBACK"

        try:
            snapshot_id = snapshot_data.get("snapshot_id") or f"snap-{uuid.uuid4().hex[:8]}"
            version = snapshot_data.get("version", 1)
            scenario_id = snapshot_data.get("scenario_id", "chennai_michaung_default")
            water_level_m = float(snapshot_data.get("water_level_m", 0.0))
            disabled_segs = snapshot_data.get("disabled_segments", [])
            created_at = datetime.now(timezone.utc).isoformat()

            with self._get_connection() as conn:
                # Concurrency check: if expected_version is specified, ensure latest DB version matches
                if expected_version is not None:
                    row = conn.execute("SELECT MAX(version) FROM scenario_snapshots").fetchone()
                    curr_max_v = row[0] if row and row[0] is not None else 0
                    if curr_max_v > expected_version:
                        logger.warning(
                            f"[PERSISTENCE CONFLICT] State save rejected. Current max version {curr_max_v} > expected {expected_version}"
                        )
                        return False, f"CONCURRENCY_CONFLICT: Current version {curr_max_v} exceeds expected {expected_version}"

                conn.execute(
                    """
                    INSERT OR REPLACE INTO scenario_snapshots (
                        snapshot_id, version, scenario_id, water_level_m, disabled_segments_json, state_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        version,
                        scenario_id,
                        water_level_m,
                        json.dumps(disabled_segs),
                        json.dumps(snapshot_data),
                        created_at,
                    ),
                )
                conn.commit()
            logger.info(f"[PERSISTENCE] Saved scenario snapshot '{snapshot_id}' v{version}")
            return True, None
        except Exception as err:
            logger.warning(f"[PERSISTENCE WARNING] Save scenario state error: {err}")
            return False, str(err)

    def load_latest_scenario_state(self) -> Optional[Dict[str, Any]]:
        """Loads latest scenario snapshot from database."""
        if not self.active:
            return None

        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT state_json FROM scenario_snapshots ORDER BY version DESC, created_at DESC LIMIT 1"
                ).fetchone()
                if row and row["state_json"]:
                    return json.loads(row["state_json"])
        except Exception as err:
            logger.warning(f"[PERSISTENCE WARNING] Load latest state error: {err}")
        return None

    def save_citizen_observation(self, obs_data: Dict[str, Any]) -> bool:
        """Persists or updates citizen observation."""
        if not self.active:
            return False

        try:
            obs_id = obs_data.get("report_id") or obs_data.get("observation_id") or f"obs-{uuid.uuid4().hex[:8]}"
            report_type = obs_data.get("report_type", "UNKNOWN")
            lat = float(obs_data.get("lat", 0.0))
            lon = float(obs_data.get("lon", 0.0))
            created_at = obs_data.get("submitted_at") or datetime.now(timezone.utc).isoformat()

            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO citizen_observations (
                        observation_id, report_type, lat, lon, data_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (obs_id, report_type, lat, lon, json.dumps(obs_data), created_at),
                )
                conn.commit()
            logger.info(f"[PERSISTENCE] Saved citizen observation '{obs_id}'")
            return True
        except Exception as err:
            logger.warning(f"[PERSISTENCE WARNING] Save citizen observation error: {err}")
            return False

    def load_citizen_observations(self) -> List[Dict[str, Any]]:
        """Loads all persisted citizen observations."""
        if not self.active:
            return []

        try:
            with self._get_connection() as conn:
                rows = conn.execute("SELECT data_json FROM citizen_observations ORDER BY created_at ASC").fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]
        except Exception as err:
            logger.warning(f"[PERSISTENCE WARNING] Load citizen observations error: {err}")
            return []

    def save_intervention(self, intervention_data: Dict[str, Any]) -> bool:
        """Persists or updates operational intervention state."""
        if not self.active:
            return False

        try:
            int_id = intervention_data.get("intervention_id") or f"int-{uuid.uuid4().hex[:8]}"
            status = intervention_data.get("status", "PROPOSED")
            corridor_id = intervention_data.get("corridor_id")
            updated_at = datetime.now(timezone.utc).isoformat()

            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO interventions (
                        intervention_id, status, corridor_id, data_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (int_id, status, corridor_id, json.dumps(intervention_data), updated_at),
                )
                conn.commit()
            logger.info(f"[PERSISTENCE] Saved intervention '{int_id}' ({status})")
            return True
        except Exception as err:
            logger.warning(f"[PERSISTENCE WARNING] Save intervention error: {err}")
            return False

    def load_interventions(self) -> List[Dict[str, Any]]:
        """Loads all persisted interventions."""
        if not self.active:
            return []

        try:
            with self._get_connection() as conn:
                rows = conn.execute("SELECT data_json FROM interventions ORDER BY updated_at ASC").fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]
        except Exception as err:
            logger.warning(f"[PERSISTENCE WARNING] Load interventions error: {err}")
            return []

    def save_audit_log_entry(self, audit_data: Dict[str, Any]) -> bool:
        """Persists transition audit entry."""
        if not self.active:
            return False

        try:
            audit_id = audit_data.get("audit_id") or f"aud-{uuid.uuid4().hex[:8]}"
            int_id = audit_data.get("intervention_id", "UNKNOWN")
            from_status = audit_data.get("from_status")
            to_status = audit_data.get("to_status")
            ts = audit_data.get("timestamp") or datetime.now(timezone.utc).isoformat()

            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO audit_log (
                        audit_id, intervention_id, from_status, to_status, data_json, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (audit_id, int_id, from_status, to_status, json.dumps(audit_data), ts),
                )
                conn.commit()
            return True
        except Exception as err:
            logger.warning(f"[PERSISTENCE WARNING] Save audit log entry error: {err}")
            return False

    def load_audit_log(self) -> List[Dict[str, Any]]:
        """Loads transition audit log."""
        if not self.active:
            return []

        try:
            with self._get_connection() as conn:
                rows = conn.execute("SELECT data_json FROM audit_log ORDER BY timestamp ASC").fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]
        except Exception as err:
            logger.warning(f"[PERSISTENCE WARNING] Load audit log error: {err}")
            return []

    def clear_all(self) -> bool:
        """Clears all persisted data."""
        if not self.active:
            return False

        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM scenario_snapshots;")
                conn.execute("DELETE FROM citizen_observations;")
                conn.execute("DELETE FROM interventions;")
                conn.execute("DELETE FROM audit_log;")
                conn.commit()
            logger.info("[PERSISTENCE] Cleared all sqlite persisted state tables.")
            return True
        except Exception as err:
            logger.warning(f"[PERSISTENCE WARNING] Clear all error: {err}")
            return False
