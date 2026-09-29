# PHASE L — MILESTONE L3: TIME-INDEXED FLOOD FORECASTING REPORT

## 1. Files Inspected
- `cyclone_twin/domain/entities.py` (Domain models: `VulnerabilityForecast`, `RoadVulnerability`, `WeatherForecast`, `FloodScenario`)
- `cyclone_twin/domain/__init__.py` (Domain exports)
- `cyclone_twin/providers/base.py` (Base interfaces: `WeatherProvider`, `FloodModel`)
- `cyclone_twin/providers/weather_provider.py` (Weather provider implementations: `CalibratedWeatherProvider`, `OpenMeteoWeatherProvider`)
- `cyclone_twin/providers/flood_model.py` (Flood model implementations: `CalibratedFloodModel`, `HANDFloodModel`)
- `cyclone_twin/providers/__init__.py` (Provider module exports)
- `cyclone_twin/main.py` (FastAPI backend routes & timeline handlers)
- `cyclone_twin/network_engine.py` (NetworkEngine routing & state management)
- `cyclone_twin/ranking_engine.py` (Accessibility calculation logic)
- `tests/test_phase_l_timeline.py` (L1 timeline test suite)
- `tests/test_phase_l2_vulnerability_domain.py` (L2 vulnerability domain test suite)

---

## 2. Files Changed
1. `cyclone_twin/providers/base.py`:
   - Updated `WeatherProvider.fetch_forecast()` method signature to support optional `horizon_hours: int = 0`.
2. `cyclone_twin/providers/weather_provider.py`:
   - Updated `CalibratedWeatherProvider` and `OpenMeteoWeatherProvider` to generate time-indexed precipitation curves across horizons (NOW=180mm, +2H=210mm, +4H=240mm, +8H=280mm).
   - Preserved `weather_source = "calibrated_fallback"` provenance for calibrated weather sources.
3. `cyclone_twin/providers/flood_model.py`:
   - Implemented `TimeIndexedFloodForecaster` pipeline class.
   - Computes isolated, read-only flood scenarios for target horizons (`NOW`, `+2H`, `+4H`, `+8H`).
   - Dynamically intersects flood geometry using `identify_flood_disabled_segments` from `cyclone_twin.flood_polygon_fallback` to obtain valid physical segment IDs.
   - Calculates projected accessibility and populates the `VulnerabilityForecast` entity without mutating state.
4. `cyclone_twin/providers/__init__.py`:
   - Exported `TimeIndexedFloodForecaster`.
5. `cyclone_twin/main.py`:
   - Refactored `GET /forecast/timeline` to utilize `TimeIndexedFloodForecaster`.
   - Updated response payload to return fully structured `VulnerabilityForecast` JSON data while retaining backward-compatible L1 fields.
6. `tests/test_phase_l3_time_indexed_flood.py`:
   - Created comprehensive test suite containing 16 dedicated test cases verifying all operational horizons, time calculations, state isolation, provenance, and non-mutation guarantees.

---

## 3. Time-Indexing Implementation
- Timestamps are computed explicitly using UTC timezone-aware objects:
  $$\text{forecast\_time} = \text{reference\_time} + \text{timedelta}(\text{hours}=\text{horizon\_hours})$$
- Guaranteed operational horizons: `NOW` ($0\text{H}$), `+2H` ($2\text{H}$), `+4H` ($4\text{H}$), `+8H` ($8\text{H}$).
- Naive datetime usage is completely avoided across the pipeline.

---

## 4. Weather-Provider Integration
- Reused existing `WeatherProvider` implementations (`CalibratedWeatherProvider`, `OpenMeteoWeatherProvider`).
- Reused time-indexed precipitation forecast logic without creating duplicate weather providers.
- Preserved weather provenance:
  - `"calibrated_fallback"` for synthetic/calibrated event data.
  - `"open_meteo"` for live meteorological data.

---

## 5. Flood-Model Integration
- Reused existing Height Above Nearest Drainage (HAND) flood model (`HANDFloodModel`).
- Preserved physical inundation formula:
  $$D_{\text{inundation}} = \max(0, W - H_{\text{HAND}})$$
- Dynamic water level $W$ scales hydrographic inundation pockets (Saidapet, Velachery, Santhome) based on precipitation accumulation.
- Drainage infrastructure modelling is excluded (strictly reserved for L9).

---

## 6. Projected Network Calculation
- For each horizon, an isolated instance of `NetworkEngine` is instantiated using a copy of the base road network graph (`NetworkEngine(graph=state.data_loader.graph)`).
- `identify_flood_disabled_segments` calculates predicted segment disruptions.
- Temporary disabled segments are passed to `temp_engine.disable_segments(dis_seg_ids)`.
- Accessibility metrics (`accessible_population`, `isolated_facilities`) are computed via `compute_accessibility` on the isolated instance.
- Base `NetworkEngine` and operational `DisasterState` remain untouched.

---

## 7. Forecast vs Operational State Isolation (`FORECAST != OBSERVATION != STATE`)
- **Strict Invariant Maintained**:
  - Live operational `DisasterState` is **never** mutated during forecast generation.
  - Live `NetworkEngine.disabled_segment_ids` remain unchanged before, during, and after forecast requests.
  - Field observations and intervention execution status are completely untouched.
  - Projected response models carry `is_projected_forecast = True`.

---

## 8. Provenance & Metadata
- Every `VulnerabilityForecast` carries complete, unalterable provenance:
  - `weather_source`: Weather provider identifier.
  - `flood_model`: Flood model identifier.
  - `network_source`: Road network identifier.
  - `reference_time`, `forecast_time`, `generated_at`: ISO 8601 timestamps.
  - `assumptions`: Array of modeling assumptions.
  - `limitations`: Explicit limitation note:
    > "This forecast uses the calibrated HAND-based inundation model and projected weather forcing. It is a scenario-based network accessibility forecast, not a full hydrodynamic flood prediction."

---

## 9. API Compatibility
- `GET /forecast`: Retained and functional.
- `GET /forecast/timeline`: Updated additively. Returns both L1 timeline summaries (`horizons`, `timeline`, `current_state`) and full L2/L3 `vulnerability_forecast` structures for each horizon.
- Phase K intervention and operational endpoints (`GET /interventions`, `POST /interventions/execute`, etc.) remain 100% operational and unaffected.

---

## 10. Tests Added (`tests/test_phase_l3_time_indexed_flood.py`)
1. `test_now_forecast_generated`: Validates NOW (0H) horizon generation.
2. `test_plus_2h_forecast_generated`: Validates +2H horizon generation.
3. `test_plus_4h_forecast_generated`: Validates +4H horizon generation.
4. `test_plus_8h_forecast_generated`: Validates +8H horizon generation.
5. `test_forecast_time_calculation`: Confirms `forecast_time == reference_time + horizon_hours`.
6. `test_forecast_provenance`: Verifies presence of all required provenance fields.
7. `test_is_projected_forecast_flag`: Verifies `is_projected_forecast == True`.
8. `test_weather_input_time_indexed`: Ensures precipitation changes appropriately with horizon.
9. `test_road_vulnerabilities_forecast_time`: Confirms road vulnerability records carry target `forecast_time`.
10. `test_forecast_does_not_mutate_network_state`: Confirms `NetworkEngine.disabled_segment_ids` is identical before and after.
11. `test_forecast_does_not_mutate_disaster_state`: Confirms `disaster_state_manager.version` is unchanged.
12. `test_horizon_isolation`: Ensures multiple horizons calculated sequentially do not contaminate one another.
13. `test_l1_timeline_api_backwards_compatibility`: Verifies `GET /forecast/timeline` API contract compatibility.
14. `test_l2_vulnerability_domain_validation`: Verifies `VulnerabilityForecast` Pydantic validation rules.
15. `test_phase_k_interventions_unaffected`: Verifies Phase K intervention engine remains unaffected.
16. `test_baseline_operational_state_preserved_after_all_forecasts`: Confirms operational state integrity after evaluating all 4 horizons.

---

## 11. Full Pytest Result
```
====================== 200 passed, 99 warnings in 19.23s =======================
```
- Baseline tests passing: **184 / 184**
- New L3 tests passing: **16 / 16**
- Total test count: **200 / 200 passing (100% pass rate)**

---

## 12. Frontend Lint & Build Result
- **Frontend Lint (`oxlint`)**:
  `0 errors, 3 warnings` (Pass)
- **Frontend Build (`vite build`)**:
  `✓ built in 246ms` (Pass)

---

## 13. Limitations
- Water accumulation is modeled as an empirical scaling function of rainfall using HAND topography rather than full 2D Saint-Venant shallow water equations.
- Forecast accessibility assumes current network topology remains static over the 8-hour horizon unless modified by ground observations.

---

## 14. Exact Remaining L4 Boundary
- **L3 is COMPLETE.**
- **L4 Vulnerability Projection / Scoring has NOT been implemented.**
- No probabilistic vulnerability scoring algorithms, feature weights, machine learning probability estimation, or threshold-to-probability mapping models were added in L3.
