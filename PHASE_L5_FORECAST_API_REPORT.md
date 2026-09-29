# PHASE L — MILESTONE L5: FORECAST API & INTEGRATION CONTRACT REPORT

## 1. Files Inspected
- `cyclone_twin/main.py` (FastAPI backend routes & application setup)
- `cyclone_twin/domain/entities.py` (Domain models: `VulnerabilityForecast`, `RoadVulnerability`, `VulnerabilityAssessment`, `VulnerabilitySummary`, `ForecastVulnerabilityResponse`)
- `cyclone_twin/domain/__init__.py` (Domain module exports)
- `cyclone_twin/providers/weather_provider.py` (`OpenMeteoWeatherProvider`, `CalibratedWeatherProvider`)
- `cyclone_twin/providers/flood_model.py` (`TimeIndexedFloodForecaster`, `HANDFloodModel`)
- `cyclone_twin/providers/vulnerability_engine.py` (`DeterministicVulnerabilityEngine`)
- `cyclone_twin/providers/network_provider.py` (`OSMNetworkProvider`)
- `tests/test_phase_l_timeline.py` (L1 forecast timeline unit tests)
- `tests/test_phase_l3_time_indexed_flood.py` (L3 time-indexed flood unit tests)
- `tests/test_phase_l4_vulnerability_projection.py` (L4 vulnerability projection unit tests)
- `frontend/src/api.js` (Frontend centralized API client)
- `frontend/src/App.jsx` (Frontend React main application)

---

## 2. Files Changed
1. `cyclone_twin/domain/entities.py`:
   - Added `ForecastVulnerabilityResponse` Pydantic model representing the typed public API contract for `GET /forecast/vulnerability`.
2. `cyclone_twin/domain/__init__.py`:
   - Exported `ForecastVulnerabilityResponse`.
3. `cyclone_twin/main.py`:
   - Enhanced `GET /forecast` with additive contract fields (`reference_time`, `forecast_time`, `horizon`, `horizon_hours`, `rainfall_mm`, `weather_source`, `is_projected_forecast = True`).
   - Preserved `GET /forecast/timeline` read-only timeline contract for horizons (`NOW`, `+2H`, `+4H`, `+8H`).
   - Created `GET /forecast/vulnerability` route exposing L4 vulnerability projections for target horizon scenarios with strict query parameter validation.
4. `frontend/src/api.js`:
   - Added `getForecast(horizonHours)`, `getForecastTimeline(horizon)`, and `getForecastVulnerability(horizon)` helper methods.
5. `tests/test_phase_l5_forecast_api.py` (New File):
   - Added 25 unit tests verifying route statuses, horizon parameter validation, provenance, assessment lists, non-exposure of restoration priorities, state isolation, determinism, secret non-leakage, and OpenAPI schema generation.

---

## 3. Endpoint Contract Summary

### 1. `GET /forecast`
- **Description**: Returns weather and basic hazard forecast representation for a given location and optional horizon offset.
- **Query Parameters**:
  - `horizon_hours` (optional int): Offset in hours (e.g. `0`, `2`, `4`, `8`).
  - `lat` (float, default `13.0827`): Latitude.
  - `lon` (float, default `80.2707`): Longitude.
- **Contract Fields**: `timestamp`, `precipitation_mm`, `precipitation_probability`, `wind_speed_kmh`, `location_name`, `provider`, `reference_time`, `forecast_time`, `horizon`, `horizon_hours`, `rainfall_mm`, `weather_source`, `is_projected_forecast: True`.

### 2. `GET /forecast/timeline`
- **Description**: Returns multi-horizon timeline projections for `NOW`, `+2H`, `+4H`, `+8H`.
- **Query Parameters**:
  - `horizon` (string, default `"NOW"`): Target horizon (`NOW`, `+2H`, `+4H`, `+8H`).
  - `lat` (float, default `13.0827`), `lon` (float, default `80.2707`).
- **Contract Fields**: `horizon`, `horizon_hours`, `reference_time`, `target_time`, `weather`, `flood`, `predicted_disabled_segments_count`, `predicted_accessibility`, `vulnerability_forecast`, `is_projected_forecast: True`.

### 3. `GET /forecast/vulnerability`
- **Description**: Returns L4 vulnerability assessment and summary for a selected forecast horizon (`NOW`, `+2H`, `+4H`, `+8H`).
- **Query Parameters**:
  - `horizon` (string, default `"NOW"`): Target horizon (`NOW`, `+2H`, `+4H`, `+8H`).
- **Contract Fields**: `horizon`, `horizon_hours`, `reference_time`, `forecast_time`, `generated_at`, `weather_source`, `flood_model`, `network_source`, `vulnerability_summary`, `vulnerability_assessments`, `provenance`, `assumptions`, `limitations`, `is_projected_forecast: True`.
- **Explicit Invariant**: Does **NOT** expose restoration priority or intervention candidate rankings.

---

## 4. Typed Response Schemas (`Pydantic`)
All public forecast endpoints utilize typed Pydantic models:
- `ForecastVulnerabilityResponse`
- `VulnerabilitySummary`
- `VulnerabilityAssessment`
- `VulnerabilityForecast`
- `WeatherForecast`

This ensures complete OpenAPI documentation generation at `/openapi.json`.

---

## 5. Validation Behavior
- Query parameter `horizon` for `GET /forecast/vulnerability` strictly validates supported inputs (`NOW`, `+2H`, `+4H`, `+8H`, or numeric `0`, `2`, `4`, `8`).
- Invalid inputs (e.g. `GET /forecast/vulnerability?horizon=garbage`) immediately return a structured **400 Bad Request**:
  ```json
  {
    "detail": "Invalid forecast horizon 'garbage'. Supported horizons: NOW, +2H, +4H, +8H."
  }
  ```

---

## 6. Error & Security Behavior
- Exception responses return clean, structured JSON.
- **No Stack Traces**: Controlled error responses suppress internal tracebacks.
- **No File System Paths**: Server file paths (`/Users/...`) are stripped.
- **No Secrets Exposed**: API keys (`GEMINI_API_KEY`), tokens, and private credentials are excluded from responses.

---

## 7. Provenance & Metadata
Every response includes:
- `weather_source`: e.g. `"open_meteo"` or `"calibrated_fallback"`
- `flood_model`: e.g. `"hand_model"`
- `network_source`: e.g. `"osm_chennai"`
- `reference_time`, `forecast_time`, `generated_at`: ISO 8601 UTC timestamps
- `assumptions` and `limitations` arrays

---

## 8. State-Isolation Verification (`FORECAST != OBSERVATION != STATE`)
- Operational `DisasterState.state_version` before and after: **Identical**
- Operational `NetworkEngine.disabled_segments` before and after: **Identical**
- Active observations before and after: **Identical**
- Active/completed interventions before and after: **Identical**

---

## 9. Frontend API Client Changes (`frontend/src/api.js`)
Added typed helper methods to `api`:
```javascript
getForecast: (horizonHours = null) => ...
getForecastTimeline: (horizon = "NOW") => ...
getForecastVulnerability: (horizon = "NOW") => ...
```

---

## 10. OpenAPI Verification
Verified OpenAPI schema generation at `/openapi.json`:
- Endpoint `/forecast` registered with parameter and response schemas.
- Endpoint `/forecast/timeline` registered with parameter and response schemas.
- Endpoint `/forecast/vulnerability` registered with parameter, `ForecastVulnerabilityResponse` schema, and 400 error schema.

---

## 11. Test Suite (`tests/test_phase_l5_forecast_api.py`)
Added 25 comprehensive unit tests:
1. `test_get_forecast_200`: `GET /forecast` returns HTTP 200.
2. `test_get_forecast_timeline_200`: `GET /forecast/timeline?horizon=NOW` returns HTTP 200.
3. `test_get_forecast_vulnerability_now_200`: `GET /forecast/vulnerability?horizon=NOW` returns HTTP 200.
4. `test_plus_2h_vulnerability_forecast`: `+2H` horizon vulnerability query works.
5. `test_plus_4h_vulnerability_forecast`: `+4H` horizon vulnerability query works.
6. `test_plus_8h_vulnerability_forecast`: `+8H` horizon vulnerability query works.
7. `test_invalid_vulnerability_horizon_handled`: Returns 400 Bad Request for invalid horizon.
8. `test_forecast_response_contains_provenance`: Provenance metadata included.
9. `test_vulnerability_response_contains_assessments`: Assessment list included.
10. `test_vulnerability_response_contains_summary`: Summary statistics included.
11. `test_vulnerability_response_does_not_contain_intervention_priority`: Omits restoration priority fields.
12. `test_forecast_endpoints_do_not_mutate_disaster_state`: 0 mutation to `DisasterState`.
13. `test_forecast_endpoints_do_not_mutate_network_engine`: 0 mutation to `NetworkEngine`.
14. `test_forecast_endpoints_do_not_mutate_observations`: 0 mutation to observations.
15. `test_forecast_endpoints_do_not_mutate_interventions`: 0 mutation to interventions.
16. `test_repeated_identical_requests_are_deterministic`: Deterministic response data.
17. `test_forecast_horizons_are_isolated`: Horizon requests independent.
18. `test_existing_l1_timeline_remains_compatible`: L1 timeline backward compatible.
19. `test_l2_domain_models_remain_valid`: L2 domain models intact.
20. `test_l3_forecast_generation_remains_valid`: L3 forecaster intact.
21. `test_l4_scoring_remains_valid`: L4 vulnerability engine intact.
22. `test_phase_k_remains_valid`: Phase K intervention routes intact.
23. `test_no_stack_traces_exposed_on_controlled_provider_failure`: No stack traces in error outputs.
24. `test_no_secrets_exposed_in_responses`: No API keys or secrets in response text.
25. `test_openapi_schema_generation`: OpenAPI schema exposes all forecast routes.

---

## 12. Full Pytest Result
```
====================== 247 passed, 105 warnings in 51.48s ======================
```
- Baseline tests passing: **222 / 222**
- New L5 tests passing: **25 / 25**
- Total test count: **247 / 247 passing (100% pass rate)**

---

## 13. Frontend Lint & Build Result
- **Frontend Lint (`oxlint`)**: `0 errors, 3 warnings` (Pass)
- **Frontend Build (`vite build`)**: `✓ built in 248ms` (Pass)

---

## 14. Limitations
- Public forecast API endpoints deliver deterministic scenario-based projections; they do not perform real-time streaming web sockets (which is managed by Phase J real-time alert state).

---

## 15. Exact Remaining L6 Boundary
**L5 provides the API integration contract. It does not implement forecast visualization.**
- Forecast visualization UI (map footprints, timeline sliders, chart overlays) will be owned by Milestone L6.
