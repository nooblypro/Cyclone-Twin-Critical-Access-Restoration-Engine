"""
Weather Provider Implementations for Cyclone Twin
Includes Open-Meteo REST provider and Calibrated Fallback provider.
"""

import logging
import time
from typing import Optional, Dict, Tuple
from datetime import datetime, timezone
import urllib.request
import json
from cyclone_twin.domain.entities import WeatherForecast
from cyclone_twin.providers.base import WeatherProvider

logger = logging.getLogger(__name__)


class CalibratedWeatherProvider(WeatherProvider):
    """Calibrated fallback provider simulating Cyclone Michaung heavy precipitation event."""

    def fetch_forecast(
        self, lat: float = 13.0827, lon: float = 80.2707, horizon_hours: Optional[int] = None
    ) -> WeatherForecast:
        if horizon_hours is None or horizon_hours >= 24:
            precip = 180.0
            horizon = 24
        elif horizon_hours == 0:
            precip = 30.0
            horizon = 0
        elif horizon_hours <= 2:
            precip = 75.0
            horizon = 2
        elif horizon_hours <= 4:
            precip = 130.0
            horizon = 4
        else:
            precip = 180.0
            horizon = 8

        return WeatherForecast(
            timestamp=datetime.now(timezone.utc),
            precipitation_mm=precip,
            precipitation_probability=95.0 if precip > 50.0 else 60.0,
            wind_speed_kmh=85.0 if precip > 100.0 else 45.0,
            forecast_horizon_hours=horizon,
            location_name="Chennai Metropolitan Area (Michaung Calibrated Event)",
            lat=lat,
            lon=lon,
            provider="calibrated_fallback",
        )


class OpenMeteoWeatherProvider(WeatherProvider):
    """Open-Meteo live REST forecast provider with automatic fallback to CalibratedWeatherProvider."""

    def __init__(self, fallback_provider: Optional[WeatherProvider] = None):
        self.fallback = fallback_provider or CalibratedWeatherProvider()
        self._cache: Dict[Tuple[float, float, Optional[int]], Tuple[float, WeatherForecast]] = {}

    def fetch_forecast(
        self, lat: float = 13.0827, lon: float = 80.2707, horizon_hours: Optional[int] = None
    ) -> WeatherForecast:
        cache_key = (round(lat, 4), round(lon, 4), horizon_hours)
        now_time = time.time()

        # 1. Return cached forecast if valid within 300s
        if cache_key in self._cache:
            ts, forecast = self._cache[cache_key]
            if now_time - ts < 300:
                return forecast

        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat:.4f}&longitude={lon:.4f}&"
            f"hourly=precipitation,wind_speed_10m&forecast_days=1"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CycloneTwinEngine/2.0"})
            with urllib.request.urlopen(req, timeout=4.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    hourly = data.get("hourly", {})
                    precip_list = hourly.get("precipitation", [0.0])
                    wind_list = hourly.get("wind_speed_10m", [0.0])

                    if horizon_hours is None or horizon_hours >= 24:
                        hours_to_take = 24
                    elif horizon_hours == 0:
                        hours_to_take = 1
                    else:
                        hours_to_take = min(len(precip_list), horizon_hours)

                    total_precip = sum(precip_list[:hours_to_take])
                    max_wind = max(wind_list[:hours_to_take]) if wind_list else 0.0

                    fc = WeatherForecast(
                        timestamp=datetime.now(timezone.utc),
                        precipitation_mm=round(total_precip, 2),
                        precipitation_probability=90.0 if total_precip > 10.0 else 20.0,
                        wind_speed_kmh=round(max_wind, 1),
                        forecast_horizon_hours=horizon_hours if horizon_hours is not None else 24,
                        location_name="Chennai (Open-Meteo Live API)",
                        lat=lat,
                        lon=lon,
                        provider="open_meteo",
                    )
                    self._cache[cache_key] = (now_time, fc)
                    return fc
        except Exception as err:
            logger.warning("Open-Meteo API fetch unavailable, using calibrated fallback: %s", err)

        # 2. Return cached forecast if present even if expired when live fetch fails
        if cache_key in self._cache:
            return self._cache[cache_key][1]

        fb = self.fallback.fetch_forecast(lat, lon, horizon_hours=horizon_hours)
        self._cache[cache_key] = (now_time, fb)
        return fb
