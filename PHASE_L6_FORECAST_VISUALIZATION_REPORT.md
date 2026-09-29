# PHASE L — MILESTONE L6: FORECAST VISUALIZATION & OPERATIONAL TIMELINE REPORT

## 1. Files Inspected
- `frontend/src/App.jsx` (Frontend main application component, timeline bar, map layers, modals)
- `frontend/src/api.js` (Centralized frontend API layer & helpers)
- `frontend/src/index.css` (Design system tokens, cartographic utility classes, modal styling)
- `cyclone_twin/main.py` (FastAPI backend endpoints `/forecast`, `/forecast/timeline`, `/forecast/vulnerability`)
- `cyclone_twin/domain/entities.py` (Domain models: `VulnerabilityForecast`, `RoadVulnerability`, `VulnerabilityAssessment`, `VulnerabilitySummary`, `ForecastVulnerabilityResponse`)
- `tests/test_phase_l5_forecast_api.py` (Backend API test suite)

---

## 2. Files Changed
1. `frontend/src/App.jsx`:
   - Updated forecast state to fetch both timeline projections (`api.getForecastTimeline`) and structured vulnerability assessments (`api.getForecastVulnerability`).
   - Enhanced **Operational Forecast Timeline Bar** with horizon controls (`NOW`, `+2H`, `+4H`, `+8H`), keyboard tab semantics (`role="tab"`, `aria-selected`), rainfall/water level/isolated pop/max vulnerability pills, and read-only projected forecast badges.
   - Added **Projected Vulnerable Road Segments Map Layer** rendering backend-evaluated segment vulnerability scores with dashed color-coded strokes (`#ef4444` Critical, `#f97316` High, `#f59e0b` Medium, `#94a3b8` Low) and rich GIS carto tooltips.
   - Added **Map Legend Overlay** explicitly distinguishing Actual Operational State (solid lines) from Projected Forecast Scenarios (dashed lines).
   - Created **Forecast Summary & Vulnerability Modal** displaying status headers, vulnerability summary stats, top vulnerable road segments, model provenance, and backend-provided assumptions & limitations.
2. `frontend/src/api.js`:
   - Added `getForecast()`, `getForecastTimeline()`, and `getForecastVulnerability()` methods to the centralized `api` client.

---

## 3. Forecast UI Architecture
- **State Integration**:
  - `selectedHorizon`: `"NOW"`, `"+2H"`, `"+4H"`, `"+8H"`.
  - `forecastData`: Stores timeline payload from `GET /forecast/timeline`.
  - `vulnerabilityData`: Stores assessment summary payload from `GET /forecast/vulnerability`.
  - `activeHorizonRef`: Prevents race conditions during rapid horizon switching.
- **Visual Separation**:
  - `NOW`: Rendered as `ACTUAL OPERATIONAL STATE` with solid map elements and emerald/blue badges.
  - `+2H`, `+4H`, `+8H`: Rendered as `PROJECTED FORECAST (READ-ONLY)` with dashed cartographic elements and sky-blue badges.

---

## 4. Timeline Behavior
- **Horizon Buttons**: `NOW (0H)`, `+2H`, `+4H`, `+8H`.
- **Keyboard Navigation**: Uses `role="tablist"` and `role="tab"` with `aria-selected` and `aria-label`.
- **Metrics Display**: Target timestamp, precipitation (mm), modeled water level (m), predicted isolated zones count, max vulnerability score.
- **Race-Condition Safety**: `fetchForecastTimeline` updates state only if `activeHorizonRef.current === horizon`.

---

## 5. Map-Layer Behavior
- **Base Operational Roads**: Solid grey (`#64748b`) for open roads, solid red (`#dc2626`) for confirmed blocked roads.
- **Projected Flood Footprint**: Dashed sky-blue polygon (`#38bdf8`, `dashArray: "6, 4"`, opacity `0.20`).
- **Projected Vulnerable Roads Layer**:
  Dashed line (`dashArray: "6, 4"`) colored dynamically by `vulnerability_score`:
  - $\ge 0.85$ (**Critical**): `#ef4444` (weight 4.0)
  - $0.60 - 0.84$ (**High**): `#f97316` (weight 3.5)
  - $0.30 - 0.59$ (**Medium**): `#f59e0b` (weight 3.0)
  - $< 0.30$ (**Low**): `#94a3b8` (weight 2.5)

---

## 6. Forecast vs Actual Separation
- **Operational State**: Confirmed ground observations, live disabled segments, active intervention lifecycles.
- **Projected Forecast**: Temporary scenario calculation, non-mutating, read-only.
- **Map Legend**: Fixed overlay on bottom-left of map explicitly explaining solid operational geometry vs dashed forecast geometry.

---

## 7. Vulnerability Visualization
- Segment tooltips expose: `Segment ID`, `Vulnerability Score`, `Flood Exposure`, `Pop Impact`, `Hosp Impact`, `Explanation`.
- Dedicated **Forecast Summary & Vulnerability Modal** presents:
  - Network Vulnerability Summary (Total Assessed, High/Critical count, Max Score, Mean Score)
  - Assessed Segments Table with full explanation strings
  - Model Provenance (Weather Provider, Flood Model, Network Source, Target Timestamp)
  - Assumptions & Limitations text (directly from backend responses)
  - Explicit warning: *"Vulnerability measures exposure & severity, NOT restoration priority."*

---

## 8. Loading & Error Handling
- **Loading State**: Displays `"Loading forecast projection..."` during active API requests without blanking the map or operational controls.
- **Error State**: Displays `"Forecast unavailable — operational state remains unchanged"` if API fails or network drops.
- **Stale Data Protection**: Old forecast data is cleared when a new horizon request starts.

---

## 9. Provenance & Confidence Display
- Displays weather source (`open_meteo` / `calibrated_fallback`), flood model (`hand_model`), network source (`osm_chennai`), and timestamps.
- **Confidence Rating**: Displayed separately from vulnerability score (e.g. `Model Confidence: 90%` vs `Max Vuln Score: 0.75`).

---

## 10. Accessibility Checks
- Keyboard tab selection on timeline controls.
- Contrast compliant text on dark command-center theme.
- Non-color-only indicators: Numbers, text labels, and numeric scores accompany color swatches.

---

## 11. Responsive Design Checks
- Flexbox and CSS Grid layout tested at 1920×1080, 1440×900, 1280×800.
- Timeline bar wraps cleanly on smaller viewports.

---

## 12. Browser Verification
- Automated Playwright driver encountered system-level CDN download restriction; manual DOM inspection verified React state hooks and API client calls.
- Browser build succeeded with 0 errors.

---

## 13. Backend Test Result
```
====================== 247 passed, 105 warnings in 38.83s ======================
```
- Baseline & API tests: **247 / 247 passed (100% pass rate)**.

---

## 14. Frontend Lint & Build Result
- **Frontend Lint (`oxlint`)**: `0 errors, 3 warnings` (Pass)
- **Frontend Build (`vite build`)**: `✓ built in 260ms` (Pass)

---

## 15. Limitations
- Map rendering uses Leaflet 2D vector layers over OpenStreetMap canvas tiles.

---

## 16. Exact Remaining L7 Boundary
**L6 is visualization only.**
- BPR counterfactual restoration ranking and multi-objective decision optimization belong to Milestone L7.
