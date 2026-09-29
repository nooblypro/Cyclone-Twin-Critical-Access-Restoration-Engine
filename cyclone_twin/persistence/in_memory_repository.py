"""
In-Memory Storage Implementation for Cyclone Twin Persistence Subsystem
Provides zero-downtime, volatile fallback storage when durable file storage
is unconfigured or disabled.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .repository import PersistenceRepository

logger = logging.getLogger("cyclone_twin.persistence.in_memory")


class InMemoryPersistenceRepository(PersistenceRepository):
    """
    Volatile in-memory state repository fallback.
    Maintains transient state buffers without file/DB dependencies.
    """

    def __init__(self):
        self.snapshots: List[Dict[str, Any]] = []
        self.citizen_observations: Dict[str, Dict[str, Any]] = {}
        self.interventions: Dict[str, Dict[str, Any]] = {}
        self.audit_log: List[Dict[str, Any]] = []

    def get_status(self) -> Dict[str, Any]:
        """Returns in-memory fallback status manifest."""
        latest_ver = self.snapshots[-1].get("version", 1) if self.snapshots else 1
        return {
            "backend_type": "in_memory",
            "status": "FALLBACK_IN_MEMORY",
            "storage_location": "RAM (Volatile)",
            "is_active": True,
            "snapshots_count": len(self.snapshots),
            "latest_version": latest_ver,
            "observations_count": len(self.citizen_observations),
            "interventions_count": len(self.interventions),
            "audit_events_count": len(self.audit_log),
        }

    def save_scenario_state(
        self,
        snapshot_data: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Saves snapshot to in-memory list with version check."""
        if expected_version is not None and self.snapshots:
            latest_v = self.snapshots[-1].get("version", 0)
            if latest_v > expected_version:
                return False, f"CONCURRENCY_CONFLICT: Current version {latest_v} > expected {expected_version}"

        snapshot_id = snapshot_data.get("snapshot_id") or f"snap-{uuid.uuid4().hex[:8]}"
        record = {**snapshot_data, "snapshot_id": snapshot_id}
        self.snapshots.append(record)
        return True, None

    def load_latest_scenario_state(self) -> Optional[Dict[str, Any]]:
        """Returns latest snapshot from in-memory list."""
        return self.snapshots[-1] if self.snapshots else None

    def save_citizen_observation(self, obs_data: Dict[str, Any]) -> bool:
        """Saves citizen observation to in-memory dict."""
        obs_id = obs_data.get("report_id") or obs_data.get("observation_id") or f"obs-{uuid.uuid4().hex[:8]}"
        self.citizen_observations[obs_id] = dict(obs_data)
        return True

    def load_citizen_observations(self) -> List[Dict[str, Any]]:
        """Loads all citizen observations from memory."""
        return list(self.citizen_observations.values())

    def save_intervention(self, intervention_data: Dict[str, Any]) -> bool:
        """Saves intervention to in-memory dict."""
        int_id = intervention_data.get("intervention_id") or f"int-{uuid.uuid4().hex[:8]}"
        self.interventions[int_id] = dict(intervention_data)
        return True

    def load_interventions(self) -> List[Dict[str, Any]]:
        """Loads all interventions from memory."""
        return list(self.interventions.values())

    def save_audit_log_entry(self, audit_data: Dict[str, Any]) -> bool:
        """Appends audit entry to memory list."""
        self.audit_log.append(dict(audit_data))
        return True

    def load_audit_log(self) -> List[Dict[str, Any]]:
        """Loads audit log from memory."""
        return list(self.audit_log)

    def clear_all(self) -> bool:
        """Clears all in-memory buffers."""
        self.snapshots.clear()
        self.citizen_observations.clear()
        self.interventions.clear()
        self.audit_log.clear()
        return True
