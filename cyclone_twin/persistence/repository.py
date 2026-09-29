"""
Persistence Repository Abstract Interface for Cyclone Twin
Defines the clean persistence boundary for mutable scenario state, observations,
interventions, and operational audit events.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class PersistenceRepository(ABC):
    """
    Abstract Storage Interface.
    Decouples deterministic engines and application domain from storage engines.
    """

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns structured health status of the persistence layer."""
        pass

    @abstractmethod
    def save_scenario_state(
        self,
        snapshot_data: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Saves mutable scenario state snapshot.
        Supports optimistic concurrency version checking.
        """
        pass

    @abstractmethod
    def load_latest_scenario_state(self) -> Optional[Dict[str, Any]]:
        """Loads latest valid scenario state snapshot for rehydration."""
        pass

    @abstractmethod
    def save_citizen_observation(self, obs_data: Dict[str, Any]) -> bool:
        """Persists ground-level citizen PGIS observation record."""
        pass

    @abstractmethod
    def load_citizen_observations(self) -> List[Dict[str, Any]]:
        """Loads all persisted citizen PGIS observations."""
        pass

    @abstractmethod
    def save_intervention(self, intervention_data: Dict[str, Any]) -> bool:
        """Persists operational intervention entity state."""
        pass

    @abstractmethod
    def load_interventions(self) -> List[Dict[str, Any]]:
        """Loads all operational interventions."""
        pass

    @abstractmethod
    def save_audit_log_entry(self, audit_data: Dict[str, Any]) -> bool:
        """Persists an operational transition audit entry."""
        pass

    @abstractmethod
    def load_audit_log(self) -> List[Dict[str, Any]]:
        """Loads complete transition audit log."""
        pass

    @abstractmethod
    def clear_all(self) -> bool:
        """Clears all persisted data (used for scenario resets and testing)."""
        pass
