# PHASE L10 — CITIZEN / PGIS EVIDENCE PIPELINE REPORT

## 1. Executive Summary & Objective

Phase L10 adds a **Citizen / Participatory Geographic Information System (PGIS) Evidence Layer** to Cyclone Twin — Critical Access Restoration Engine.

The objective is to enable citizens and ground observers in affected disaster areas to submit ground-level observations (such as flooded roads, blockages, passable routes, water levels, drain overflows, hospital access blockages, debris, fallen trees, power outages) while enforcing strict architectural separation between **Evidence** and **Operational State**.

### Operational Invariant preserved:

$$\text{FORECAST} \neq \text{OBSERVATION} \neq \text{STATE}$$

Citizen reports enter strictly as **UNTRUSTED OBSERVATIONAL EVIDENCE**. They do **NOT** directly mutate road network topology, flood depth rasters, HAND topography, population distributions, hospital accessibility, or counterfactual intervention rankings. State changes occur exclusively when citizen observations pass through the Phase E validation and deterministic reconciliation pipeline.

---

## 2. Core Architecture & Evidence Lifecycle

```
CITIZEN GROUND REPORT
        │
        ▼
UNTRUSTED CITIZEN EVIDENCE (Source: "citizen", Status: "SUBMITTED")
        │
        ▼
PHASE E VALIDATION (Spatial bounds, temporal freshness, schema validity)
        │
        ▼
DUPLICATE & CONFLICT EVALUATION (Spatial ≤100m, temporal window ≤30min)
        │
        ▼
DETERMINISTIC RECONCILIATION (Multi-source fusion: Official vs Citizen vs Sensor)
        │
        ▼
AUTHORITATIVE DISASTER STATE & NETWORK ENGINE MUTATION (If threshold met)
```

---

## 3. Domain Model (`CitizenObservation` & `CitizenMediaMetadata`)

Implemented in [`cyclone_twin/domain/entities.py`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/cyclone_twin/domain/entities.py):

- **`CitizenObservation`**:
  - `observation_id` (UUID str)
  - `report_type` (Controlled vocabulary str)
  - `location` (GeoLocation: `latitude` $\in [-90, 90]$, `longitude` $\in [-180, 180]$)
  - `timestamp` (Observed UTC datetime)
  - `received_at` (Server UTC datetime)
  - `description` (Sanitized string)
  - `reporter_id` (Optional str)
  - `is_anonymous` (bool, default `True`)
  - `confidence` (float $\in [0.1, 1.0]$, default `0.75`)
  - `status` (`SUBMITTED` $\rightarrow$ `VALIDATING` $\rightarrow$ `VALIDATED` $\rightarrow$ `RECONCILED` | `REJECTED`)
  - `sync_status` (`SYNCED` | `QUEUED` | `PENDING`)
  - `duplicate_candidate` (bool)
  - `conflicts_detected` (bool)
  - `media_metadata` (Optional `CitizenMediaMetadata`)
  - `provenance` (`ObservationProvenance`)

- **`CitizenMediaMetadata`**:
  - `media_id` (str)
  - `filename` (Sanitized base filename)
  - `mime_type` (Strict enum: `image/jpeg`, `image/png`, `image/webp`)
  - `file_size` (int, max 10MB)
  - `capture_timestamp` (ISO timestamp)
  - `checksum` (SHA-256 hash or fixture reference)

---

## 4. Controlled Vocabulary & Mapping

Supported categories in `CONTROLLED_REPORT_TYPES`:

| Citizen Report Type | Phase E Observation Type | Domain Significance |
|---|---|---|
| `ROAD_FLOODED` | `ROAD_BLOCKED` | Road impassability due to water inundation |
| `ROAD_BLOCKED` | `ROAD_BLOCKED` | Physical blockage / debris on corridor |
| `ROAD_PASSABLE` | `ROAD_OPEN` | Confirmed open & passable corridor |
| `WATER_LEVEL` | `FLOOD_DEPTH` | Quantitative gauge / water height observation |
| `DRAIN_OVERFLOW` | `DRAIN_OVERFLOW` | Storm drain capacity overflow |
| `HOSPITAL_ACCESS_BLOCKED` | `HOSPITAL_ACCESS` | Emergency trauma center access obstruction |
| `DEBRIS` | `ROAD_BLOCKED` | Debris pile blocking arterial road |
| `FALLEN_TREE` | `ROAD_BLOCKED` | Fallen tree obstruction |
| `BRIDGE_BLOCKED` | `ROAD_BLOCKED` | Bridge impassable |
| `POWER_OUTAGE` | `TRAFFIC_CONDITION` | Utility grid power outage |
| `OTHER` | `TRAFFIC_CONDITION` | General infrastructure hazard |

---

## 5. Security & Privacy Safeguards

- **Security**:
  - Input sanitization strips dangerous characters, HTML tags, and path traversal sequences (`../`, `..\\`).
  - Strict coordinate validation rejects `NaN`, `Infinity`, out-of-range latitude/longitude.
  - File path traversal protection on media metadata; executable extensions (`.exe`, `.sh`, `.py`, `.php`, `.js`) are strictly rejected.
  - Payloads capped at 10MB; max text length enforced.
- **Privacy**:
  - Default anonymous reporting (`is_anonymous=True`).
  - Reporter identifiers are pseudonymized (`citizen_anon_...`).
  - No PII (phone numbers, email addresses, MAC addresses) collected or stored.

---

## 6. Duplicate & Conflict Handling

- **Duplicate Detection**:
  - Evaluates spatial distance ($\le 100\text{ meters}$) and temporal delta ($\le 30\text{ minutes}$) for identical report types.
  - Candidates are flagged (`duplicate_candidate=True`) for operator review without blind deletion.
- **Conflict Handling**:
  - Opposite reports (e.g., Citizen A reports `ROAD_BLOCKED` while Citizen B reports `ROAD_PASSABLE` within $200\text{m}$) are preserved as separate distinct observations.
  - Flagged (`conflicts_detected=True`) and exposed to operator review. Reconciliation prevents arbitrary "last write wins" overwrites.

---

## 7. API Endpoints

FastAPI endpoints mounted in [`cyclone_twin/main.py`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/cyclone_twin/main.py):

1. `POST /observations/citizen`
   - Accepts citizen report JSON payload.
   - Validates coordinates, report type, media metadata, and text.
   - Preserves explicit `provenance.source = "citizen"`.
   - Ingests into Phase E pipeline without mutating state.
   - Returns 201 Created with structured `CitizenObservation` response.
2. `GET /observations/citizen`
   - Returns list of recorded citizen observations filtered by `status` or `report_type`.
3. `GET /observations/citizen/{observation_id}`
   - Returns single citizen observation detail or 404.

---

## 8. Frontend Integration

- **API Client Layer**: [`frontend/src/api.js`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/frontend/src/api.js) updated with `submitCitizenReport` and `getCitizenObservations`.
- **Citizen PGIS Submission Modal**: Dedicated focused interface in [`frontend/src/App.jsx`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/frontend/src/App.jsx) for ground observation entry (category picker, map center/GPS coordinates, text description, optional photo metadata, privacy settings, confidence slider, submission feedback).
- **Operator Evidence Registry View**: Added `Citizen PGIS (Phase L10)` tab to Data Sources modal exposing total report counts, validation status, conflict/duplicate flags, and full evidence registry table.
- **Cartographic Distinction**: Citizen observation markers rendered on Leaflet map using distinct rotated diamond icons (`createCitizenIcon`) in purple/green/slate to clearly distinguish unverified citizen evidence from authoritative road network state.

---

## 9. Verification & Test Suite

- **Phase L10 Tests**: 23 focused unit & integration tests in [`tests/test_phase_l10_citizen_pgis.py`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/tests/test_phase_l10_citizen_pgis.py).
  - Domain model creation & default values
  - Controlled report type validation & invalid type rejection
  - Coordinate validation (in-range, out-of-range, NaN, Infinity)
  - Provenance source tagging (`citizen`)
  - Text input sanitization
  - Media metadata validation (MIME types, size limits, path traversal rejection)
  - Duplicate candidate detection ($100\text{m}$ / $30\text{min}$)
  - Conflict detection (`ROAD_BLOCKED` vs `ROAD_PASSABLE`)
  - Zero state mutation invariant (observation creation leaves `NetworkEngine` unchanged)
  - API `POST /observations/citizen` & `GET /observations/citizen`
  - Integration with Phase E reconciliation pipeline
- **Full Pytest Suite**: 335/335 backend tests passing cleanly (312 baseline + 23 L10).
- **Frontend Verification**: `npm run lint` (0 errors) & `npm run build` (PASS).

---

## 10. System Limitations & Non-Claims

- **Photo Storage**: Media handling stores validated metadata fixtures locally/in-memory. Cloud object storage (S3/GCS) is not introduced.
- **Computer Vision**: No automated AI image classification of photo evidence is performed in L10; photo metadata acts as evidence attachment.
- **Production Citizen App**: This interface provides the PGIS API integration engine and web submission component; real-world deployment requires mobile PWA auth and cellular gateways.
- **HAND & Flood Model**: Topographical HAND and satellite flood models remain 100% unchanged.
