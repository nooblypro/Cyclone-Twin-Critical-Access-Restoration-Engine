# Phase L9 — GCC Drainage & Infrastructure Evidence Provider Report
**Cyclone Twin — Critical Access Restoration Engine**

---

## 1. Objective & Overview

Phase L9 introduces a deterministic, provenance-aware **Stormwater Drainage Infrastructure Evidence Provider** representing Greater Chennai Corporation (GCC) style drainage network assets, conditions, blockage statuses, capacity factors, and connectivity anomalies.

The purpose is **NOT** to invent new flood data or execute hydrodynamic SWMM pipe flow solvers. The purpose is to expose infrastructure evidence (e.g. arterial drains, box culverts, outfalls, pumping stations) that complements physical flood exposure assessments.

---

## 2. Non-Negotiable Physical & Domain Model Invariants

```
   HAND / Terrain Topography (UNCHANGED)
                 +
   Water Exposure / Inundation (UNCHANGED)
                 +
   Drainage Infrastructure Condition (NEW EVIDENCE LAYER)
                 ↓
   Vulnerability Interpretation & Decision Support
```

### Key Physical Invariants Enforced:
1. **HAND Elevation Values UNCHANGED**: Drainage infrastructure conditions do **NOT** modify HAND terrain elevation models or slope values. HAND represents baseline topography susceptibility.
2. **Flood Inundation Calculation UNCHANGED**: Hydraulic flood depth formulas remain unaltered.
3. **Provider READ-ONLY**: `DrainageInfrastructureProvider` operations generate zero state mutations on `NetworkEngine`, `DisasterState`, or operational priorities.
4. **Forecast != Observation != State**: Forecasted rainfall or flooded areas do not automatically create unverified drain blockage observations. Ground reports must pass Phase E validation and reconciliation.

---

## 3. Data Source Provenance & Status

- **Data Status**: **`CALIBRATED / SIMULATED FIXTURE SCENARIO DATA`**
- **Provenance Tag**: `gcc_calibrated`
- **Data Source Statement**: No live GCC IoT sensor telemetry stream is currently connected to this repository. All drainage assets represent a calibrated, representative stormwater drainage scenario for Greater Chennai Corporation (GCC South Adyar, GCC Central Cooum, GCC Velachery South catchments).
- **Assumptions & Limitations**: Explicitly exposed via API and frontend interfaces.

---

## 4. Architecture & Domain Representation

### 4.1 Core Domain Entities (`cyclone_twin/domain/entities.py`)

- **`DrainageInfrastructureAsset`**:
  - `asset_id`: Unique identifier (e.g. `drain_gcc_01`)
  - `asset_name`: Human-readable label (e.g. *Arterial Stormwater Drain — Grand Southern Trunk Rd*)
  - `asset_type`: `stormwater_drain` | `culvert` | `outfall` | `pumping_station` | `drain_link` | `junction`
  - `catchment_zone`: Geographic catchment (e.g. `GCC_South_Adyar`)
  - `latitude`, `longitude`: Validated geographic coordinates
  - `condition_score`: `[0.0, 1.0]` (0.0=failed/clogged, 1.0=fully operational)
  - `capacity_cumecs`: Design discharge capacity ($m^3/s$)
  - `capacity_factor`: `[0.0, 1.0]` (0.0=no effective capacity, 1.0=nominal)
  - `blockage_status`: `open` | `partially_blocked` | `severely_blocked` | `inoperable`
  - `blockage_probability`: `[0.0, 1.0]`
  - `connectivity_status`: `connected` | `degraded` | `disconnected` | `missing_link`
  - `source`: `gcc_calibrated`
  - `is_simulated`: `True`

- **`DrainageInfrastructureSummary`**:
  - API response wrapper containing aggregated asset totals, blocked asset count, degraded connectivity count, bounding box coverage, assumptions, limitations, and provenance metadata.

- **`DrainSegment`**:
  - Preserved existing domain model for 100% backward compatibility.

### 4.2 Provider Architecture (`cyclone_twin/providers/drainage_provider.py`)

- **`DrainageInfrastructureProvider`**:
  - `get_drainage_assets(catchment_zone, blockage_status)`
  - `get_asset_by_id(asset_id)`
  - `get_drainage_summary(catchment_zone)`
  - `evaluate_drainage_vulnerability_factor(lat, lon, radius_km)`: Evaluates spatial drainage vulnerability factor `[0.0, 1.0]` based on nearby impaired/blocked drainage infrastructure using Haversine distance decay.

---

## 5. API & Pipeline Integration

### 5.1 REST Endpoint (`cyclone_twin/main.py`)
- **`GET /infrastructure/drainage`**
  - Query parameters: `catchment` (optional), `status` (optional).
  - Returns `DrainageInfrastructureSummary` with assets, provenance, source (`gcc_calibrated`), `is_simulated=True`, explicit assumptions and limitations.
  - Read-only (0 state mutation).

### 5.2 Phase E Observation Pipeline Integration (`observation_pipeline.py`)
- Added supported observation types: `"DRAIN_BLOCKED"`, `"DRAIN_CAPACITY_LOSS"`, `"DRAIN_OVERFLOW"`.
- Added aliases: `"drain_blockage"`, `"blocked_drain"`, `"drain_clogged"`, `"drain_overflow"`.
- Drainage ground observations follow standard Phase E input validation (lat/lon, NaN/Inf rejection, bounds check) and deterministic model reconciliation.

### 5.3 Voice Pipeline Integration (`voice_pipeline.py`)
- Spoken reports mentioning blocked drains or culverts (e.g. *"stormwater drain blocked near Saidapet"*) extract `observation_type="DRAIN_BLOCKED"`.
- Voice transcription remains 100% read-only until explicitly ingested through Phase E.

---

## 6. Frontend UI (`frontend/src/api.js`, `frontend/src/App.jsx`)

- Added `api.getDrainageInfrastructure(catchment, status)` wrapper.
- Added **"Drainage Infrastructure (Phase L9)"** tab to the Data & Specification modal.
- Displays:
  - GCC asset count, blocked count, degraded connectivity count.
  - Provenance badges (`gcc_calibrated`, `SIMULATED FIXTURE SCENARIO`).
  - GCC Asset Register with blockage badges (`OPEN`, `PARTIALLY_BLOCKED`, `SEVERELY_BLOCKED`, `INOPERABLE`), condition percentages, capacity factors, and observed issues.
  - Explicit physical model notice stating that HAND topography is never altered by drainage reports.

---

## 7. Verification & Testing

- **Backend Test Suite**: **312/312 passed** (21 new Phase L9 tests in [`tests/test_phase_l9_drainage_provider.py`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/tests/test_phase_l9_drainage_provider.py)).
- **Frontend Build**: **PASS** (`dist/` built in 243ms).
- **Frontend Lint**: **PASS** (0 errors).
- **Security & Validation**: Strict float bounds enforcement, NaN/Inf rejection on all entities and query inputs.

---

## 8. Summary Status Table

```
PHASE: L9
STATUS: COMPLETE

BACKEND TESTS:
312/312 PASSED

NEW L9 TESTS:
21 PASSED

FRONTEND BUILD:
PASS

FRONTEND LINT:
PASS

DRAINAGE PROVIDER:
IMPLEMENTED

GCC DATA:
CALIBRATED / SIMULATED FIXTURE SCENARIO DATA

HAND MODEL:
UNCHANGED

FLOOD MODEL:
UNCHANGED

FORECAST/OBSERVATION/STATE SEPARATION:
PASS

SECURITY:
PASS
```
