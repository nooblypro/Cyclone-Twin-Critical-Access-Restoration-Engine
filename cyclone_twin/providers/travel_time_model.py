"""
Travel Time Model Implementations for Cyclone Twin
Includes Static travel time and BPR (Bureau of Public Roads) capacity-aware congestion pricing model.
"""

from typing import Any, Optional
from cyclone_twin.providers.base import TravelTimeModel


def derive_capacity(capacity_attr: Any = None, highway_attr: Any = None) -> float:
    """Derives capacity in vehicles/hour from explicit attribute or highway classification hierarchy."""
    if capacity_attr is not None:
        try:
            val = float(capacity_attr)
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass

    if highway_attr is not None:
        h_str = str(highway_attr[0] if isinstance(highway_attr, list) and highway_attr else highway_attr).lower()
        if "motorway" in h_str or "trunk" in h_str:
            return 4000.0
        if "primary" in h_str:
            return 2500.0
        if "secondary" in h_str:
            return 1800.0
        if "tertiary" in h_str:
            return 1400.0

    return 2000.0


class StaticTravelTimeModel(TravelTimeModel):
    """Static travel time model using free-flow speed without congestion penalties."""

    def compute_travel_time(
        self,
        length_m: float,
        free_flow_speed_kph: float,
        capacity: float = 2000.0,
        volume: float = 0.0,
        is_disabled: bool = False,
    ) -> float:
        if is_disabled or free_flow_speed_kph <= 0:
            return float("inf")
        speed_mps = free_flow_speed_kph * (1000.0 / 3600.0)
        return length_m / speed_mps


class BPRCapacityTravelTimeModel(TravelTimeModel):
    """
    Bureau of Public Roads (BPR) capacity-aware travel time model.
    t_e(v_e) = t0 * [1 + alpha * (v_e / C_e)^beta]
    where alpha = 0.15, beta = 4.0 by default.
    Guarantees monotonicity: v_e >= 0 -> t_e(v_e) >= t0.
    """

    def __init__(self, alpha: float = 0.15, beta: float = 4.0):
        if alpha < 0.0 or beta < 0.0:
            raise ValueError("BPR parameters alpha and beta must be non-negative")
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.static_model = StaticTravelTimeModel()

    def compute_travel_time(
        self,
        length_m: float,
        free_flow_speed_kph: float,
        capacity: float = 2000.0,
        volume: float = 0.0,
        is_disabled: bool = False,
    ) -> float:
        t0 = self.static_model.compute_travel_time(
            length_m=length_m,
            free_flow_speed_kph=free_flow_speed_kph,
            capacity=capacity,
            volume=volume,
            is_disabled=is_disabled,
        )
        if t0 == float("inf") or capacity <= 0.0:
            return t0

        vc_ratio = max(0.0, float(volume) / float(capacity))
        congestion_factor = 1.0 + self.alpha * (vc_ratio ** self.beta)
        return t0 * congestion_factor
