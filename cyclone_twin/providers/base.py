"""
Abstract Provider Base Interfaces for Cyclone Twin
Defines strict abstract contracts for external weather, flood, network, travel-time, and predictive providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import networkx as nx

from cyclone_twin.domain.entities import (
    WeatherForecast,
    FloodScenario,
    InfrastructureObservation,
)


class WeatherProvider(ABC):
    """Abstract interface for weather forecast ingestion."""

    @abstractmethod
    def fetch_forecast(
        self, lat: float = 13.0827, lon: float = 80.2707, horizon_hours: Optional[int] = None
    ) -> WeatherForecast:
        """Fetch precipitation and wind forecast for a target location."""
        pass


class FloodModel(ABC):
    """Abstract interface for flood inundation calculation."""

    @abstractmethod
    def compute_inundation(self, forecast: WeatherForecast) -> FloodScenario:
        """Calculate inundation footprint and water level from forecast or scenario."""
        pass


class RoadNetworkProvider(ABC):
    """Abstract interface for road network graph ingestion."""

    @abstractmethod
    def load_network(self) -> nx.MultiDiGraph:
        """Load and return the spatial road multigraph."""
        pass


class TravelTimeModel(ABC):
    """Abstract interface for edge travel time calculation."""

    @abstractmethod
    def compute_travel_time(
        self,
        length_m: float,
        free_flow_speed_kph: float,
        capacity: float = 2000.0,
        volume: float = 0.0,
        is_disabled: bool = False,
    ) -> float:
        """Calculate travel time in seconds given edge attributes and current traffic volume."""
        pass


class VulnerabilityModel(ABC):
    """Abstract interface for predictive infrastructure vulnerability estimation."""

    @abstractmethod
    def predict_vulnerability_score(self, edge_features: Dict[str, Any]) -> float:
        """Return a vulnerability probability score in range [0.0, 1.0]."""
        pass
