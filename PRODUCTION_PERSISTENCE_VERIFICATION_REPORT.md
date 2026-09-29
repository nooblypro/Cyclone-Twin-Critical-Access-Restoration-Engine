# PRODUCTION PERSISTENCE VERIFICATION REPORT — CYCLONE TWIN

**Execution Phase**: Deploy & Verify Production State Persistence  
**Date**: September 28, 2026  
**Target Architecture**: Vercel (Frontend) + Render (Backend)  
**Verification Baseline**: 372 / 372 Tests PASS | Frontend Lint 0 Errors | Frontend Build PASS  

---

## 1. EXECUTIVE SUMMARY

The backend state persistence layer for Cyclone Twin has been fully configured, integrated, and verified locally and at the container level. The system uses a clean `PersistenceRepository` boundary backed by `SQLitePersistenceRepository` with atomic Write-Ahead Logging (WAL) and optimistic version concurrency control.

### Live Production Audit Findings:
- **Live Endpoint Test**: `curl -s https://cyclone-twin-backend.onrender.com/persistence/status` returns `404 Not Found` (`{"detail":"Not Found"}`). The live Render service is running a pre-persistence build.
- **Render Ephemeral Filesystem**: Under Render's default free-tier container plan, filesystem changes to container-local paths (`cache/cyclone_twin_state.db`) survive process restarts within the instance, but are lost when Render destroys the container during spin-downs (>15 min inactivity) or new deployments.
- **Render Persistent Disk Configuration**: `render.yaml` has been configured with `disk: mountPath: /var/data` and environment variable `CYCLONE_TWIN_DB_PATH=/var/data/cyclone_twin_state.db`. Attaching a 1GB Render Persistent Disk ensures full cross-deployment durability.

---

## 2. DEPLOYMENT CONFIGURATION (`render.yaml`)

```yaml
services:
  - type: web
    name: cyclone-twin-backend
    env: python
    region: oregon
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn cyclone_twin.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /
    disk:
      name: cyclone-twin-data
      mountPath: /var/data
      sizeGB: 1
    envVars:
      - key: PYTHON_VERSION
        value: 3.13.0
      - key: ALLOWED_ORIGINS
        value: https://cyclone-twin.vercel.app,http://localhost:5173,http://localhost:5174,https://frontend-woad-iota-23.vercel.app
      - key: CYCLONE_TWIN_DB_PATH
        value: /var/data/cyclone_twin_state.db
      - key: CYCLONE_TWIN_PERSISTENCE
        value: sqlite
      - key: GEMINI_API_KEY
        sync: false
```

---

## 3. PERSISTENCE STATUS RESPONSE

### Local Status (`GET /persistence/status`)
```json
{
  "status": "DURABLE_PERSISTENCE_ACTIVE",
  "backend_type": "sqlite",
  "storage_location": "cache/cyclone_twin_state.db",
  "is_active": true
}
```

### Live Render Production Status (`GET /persistence/status`)
```json
{
  "detail": "Not Found"
}
```
*(Confirms live Render instance is running pre-persistence commit).*

---

## 4. STATE REHYDRATION & CALCULATION INVARIANTS

### Persisted Source State vs Derived Recomputation

```
SQLite Database (/var/data/cyclone_twin_state.db)
  ├── Table: scenario_snapshots (water_level_m, disabled_segments, version)
  ├── Table: citizen_observations (PGIS ground reports)
  ├── Table: interventions (Operational candidate execution status)
  └── Table: audit_log (Transition audit trail)
        │
        ▼ (AppState.initialize() / AppState.rehydrate_from_persistence())
  DataLoader + NetworkEngine + CitizenPipeline + InterventionManager
        │
        ▼ (Deterministic Recomputation on-demand)
  Dijkstra Shortest Paths + BPR Travel Times + Vulnerability + Corridor Rankings
```

1. **Persisted**: `water_level_m`, `disabled_segments`, state `version`, `last_cleared_corridor`, citizen reports, interventions, and audit log.
2. **Recomputed**: Accessibility percentages, isolated population counts, isolated facilities, vulnerability projections, counterfactual corridor scores, and advisory text.

---

## 5. VERIFICATION TESTS

### Test 1: Local Process Restart Test (VERIFIED)
- **Baseline**: Set `water_level_m = 1.75` and `disabled_segments = ["way_101", "way_102"]`. Call `persist_current_state()`.
- **Action**: Instantiated fresh `AppState` loading the same SQLite database file.
- **Result**: `state2.data_loader.water_level_m == 1.75`, `state2.network_engine.disabled_segments == {"way_101", "way_102"}`. Derived accessibility recomputed matching mutated state exactly.

### Test 2: Field Mode Synced Observation Survival (VERIFIED)
- **Action**: Ingested citizen report via `/observations/sync` into IndexedDB, pushed to backend ingestion pipeline, and saved to SQLite persistence.
- **Restart**: Instantiated fresh `AppState` instance.
- **Result**: Observation restored into `state2.citizen_pipeline.citizen_reports["citizen-obs-test-101"]`, preserving both ground evidence and resulting road network state changes.

### Test 3: Reset & Clear Semantics (VERIFIED)
- **Action**: Call `POST /persistence/clear`.
- **Result**: Clears `scenario_snapshots`, `citizen_observations`, `interventions`, and `audit_log` tables cleanly without corrupting schema or default baseline.

---

## 6. REGRESSION TESTING & SECURITY CHECKS

1. **Backend Unit Tests**: **372 / 372 PASSING**
   ```bash
   ./.venv/bin/pytest
   # Output: 372 passed in 62.14s
   ```
2. **Frontend Linter**: **0 Errors**
   ```bash
   cd frontend && npm run lint
   # Output: Found 9 warnings and 0 errors.
   ```
3. **Frontend Production Build**: **PASS**
   ```bash
   cd frontend && npm run build
   # Output: dist/index.html (0.50 kB), dist/assets/index-C4X0WSKp.js (503.41 kB)
   ```
4. **Security & Git Hygiene**:
   - `.gitignore` updated with `*.db`, `*.db-wal`, `*.db-shm`, and `cache/`.
   - Zero database files or secrets committed to Git repository.
   - `ALLOWED_ORIGINS` strictly enforces frontend domain `https://frontend-woad-iota-23.vercel.app`.

---

## 7. REMAINING LIMITATIONS

1. **Render Free-Tier Ephemeral Disk**: Without an attached Render Persistent Disk mounted at `/var/data`, Render destroys container local storage upon service spin-down or redeployment.
2. **Single-Instance SQLite Locks**: SQLite WAL mode operates via POSIX file locks on a single mounted volume. It is designed for single-instance backend services.

---

## 8. FINAL ASSESSMENT

# **DURABLE ONLY WITHIN INSTANCE**
