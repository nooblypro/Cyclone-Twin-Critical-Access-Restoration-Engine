# Cyclone Twin — Phase I: Field Operations & Offline Synchronization

> **Core Operational Guarantee:**
> *"Field evidence MUST be capturable without network connectivity. Synchronization MUST be idempotent. Server reconciliation remains authoritative."*

---

## 1. Executive Summary & Field Operations Architecture

Phase I establishes an offline-first field operations workflow that enables emergency field workers, agency personnel, and IoT sensors to record infrastructure evidence without an active internet connection. All locally captured observations are stored persistently in browser IndexedDB, assigned client-side UUIDs (`client_observation_id`), and automatically synchronized to the backend when reachability returns.

```
FIELD WORKER / SENSOR
         ↓
Offline Field Interface (Browser App)
         ↓
Local Storage (IndexedDB Persistent Queue)
         ↓  [DISCONNECTED / NO INTERNET]
Connectivity Restored / Server Reachable
         ↓
SyncEngine Batch Request (POST /observations/sync)
         ↓
Server Validation (Phase E Input Rules & Bounding Box)
         ↓
Deterministic Reconciliation (Source Priority & Timestamps)
         ↓
Network Engine Mutation (Segment Overrides)
         ↓
Accessibility Recomputation (Multi-Source Dijkstra)
         ↓
Command Center Visibility (Auditable Lineage & Conflict Badges)
```

---

## 2. Non-Negotiable Invariants & Guarantees

1. **Zero Data Loss**: Observations saved locally in IndexedDB are retained across browser tab closes, reloads, and network outages.
2. **Stable Client Identifiers**: Every offline item receives a unique `client_observation_id` before local saving.
3. **Strict Idempotency**: Replaying the same observation multiple times returns the cached server result (`idempotent_replay: true`) without creating duplicate graph overrides.
4. **Authoritative Server Reconciliation**: Client state never directly mutates the simulation; all overrides pass through server-side Phase E reconciliation.
5. **Conflict Transparency**: Competing reports (e.g. `ROAD_BLOCKED` vs `ROAD_OPEN`) are NOT hidden or silently discarded; the backend resolves the winner deterministically while preserving both in the audit log and displaying `CONFLICTING EVIDENCE` badges in the Command Center.
6. **Human Safety First**: Systems output operational candidate information for incident commanders; personnel safety remains paramount.

---

## 3. Offline Data Model (`FieldObservationQueueItem`)

Locally queued observations follow an explicit schema stored in IndexedDB (`cyclone_twin_offline_db`):

```typescript
interface FieldObservationQueueItem {
  client_observation_id: string;      // e.g. "client_obs_1727439000_a8f1b2"
  created_at: string;                 // ISO 8601 timestamp
  captured_at: string;                // ISO 8601 capture timestamp
  source: string;                     // "field_team" | "official" | "sensor" | "citizen"
  observation_type: string;           // "ROAD_BLOCKED" | "ROAD_OPEN" | "FLOOD_DEPTH" | "FLOOD_PRESENT"
  latitude: number | null;            // WGS84 decimal degrees (or null if location unresolved)
  longitude: number | null;           // WGS84 decimal degrees
  water_depth_m: number | null;       // Measured or estimated inundation depth in meters
  severity: string;                   // "high" | "critical" | "low"
  confidence: number;                 // Source-calibrated confidence score [0.0 - 1.0]
  description: string;                // Field notes / evidence description
  image_data?: string | null;         // Base64 / Blob data stored locally
  evidence_reference: string;         // e.g. "PHOTO_1727439000"
  sync_status: SyncStatus;            // "QUEUED" | "SYNCING" | "SYNCED" | "FAILED" | "CONFLICT"
  retry_count: number;                // Bounded sync retry count
  last_sync_attempt?: string | null;
  server_observation_id?: string | null;
  server_result?: object | null;
  conflict_reason?: string | null;
  error_message?: string | null;
}
```

---

## 4. Reachability & Sync Engine Architecture

The frontend `SyncEngine` monitors connection reachability through a 2-tier check:

1. **Browser Network State**: Listens to native `window.online` and `window.offline` events.
2. **Server Heartbeat Ping**: Sends periodic 2.5-second timeout pings (`GET /health`) to verify active API availability beyond browser link status.

```
+----------------+----------------+--------------------------+
|  Navigator     | Server Ping    | Resulting Network State  |
+----------------+----------------+--------------------------+
|  Offline       | N/A            | OFFLINE                  |
|  Online        | HTTP 200 OK    | ONLINE                   |
|  Online        | Failed / 504   | UNSTABLE (Server Down)   |
+----------------+----------------+--------------------------+
```

### Bounded Exponential Retry Policy
- **Attempt 1**: Immediate sync on connection detection.
- **Attempt 2**: Short backoff delay ($2^1 \text{ sec} + \text{jitter}$).
- **Attempt 3**: Long backoff delay ($2^2 \text{ sec} + \text{jitter}$).
- **Attempt Exhaustion**: Status transitions to `FAILED` with explicit error detail. The item remains in local IndexedDB for manual field retry. Local evidence is **NEVER** deleted upon failure.

---

## 5. API Specification

### `POST /observations/sync`
- **Purpose**: Batch ingestion endpoint for offline-queued field observations.
- **Payload**:
  ```json
  {
    "client_id": "device_field_01",
    "observations": [
      {
        "client_observation_id": "client_obs_1727439000_a8f1b2",
        "observation_type": "ROAD_BLOCKED",
        "latitude": 13.0500,
        "longitude": 80.2200,
        "water_depth_m": 0.35,
        "source": "field_team",
        "confidence": 0.90,
        "description": "Flooded road near Saidapet"
      }
    ]
  }
  ```
- **Response**:
  ```json
  {
    "total_received": 1,
    "synced_count": 1,
    "idempotent_replays": 0,
    "failed_count": 0,
    "conflicts_count": 0,
    "results": [
      {
        "status": "ingested",
        "client_observation_id": "client_obs_1727439000_a8f1b2",
        "idempotent_replay": false,
        "provenance_lineage": { ... }
      }
    ]
  }
  ```

---

## 6. Verification & Test Suite

### Backend Test Results (`./.venv/bin/pytest`)
- **Total Tests**: **148 / 148 PASSED** (0 failures, 0 errors, 3.45s execution time).
- **Phase I Specific Categories (A–Z)**:
  - `test_category_a_b_offline_observation_model`: Passed
  - `test_category_c_d_e_queue_persistence_schema`: Passed
  - `test_category_f_g_gps_availability_handling`: Passed
  - `test_category_h_i_batch_synchronization`: Passed
  - `test_category_m_v_idempotent_duplicate_sync`: Passed
  - `test_category_o_conflicting_observations_reconciliation`: Passed
  - `test_category_p_q_validation_failure`: Passed
  - `test_category_r_s_t_batch_ordering`: Passed
  - `test_category_w_provenance_preservation`: Passed
  - `test_category_x_y_z_regression_baselines`: Passed

### Regression Baseline Status
- **Baseline Accessibility**: 477,000 accessible / 0 isolated
- **Michaung Scenario**: 298,000 accessible / 179,000 isolated
- **Criticality Score**: +0.0724 ($\Delta P = 0.4972$)
- **Population Recovery**: +89,000 recovered

### Frontend Quality & Build Audits
- **Linter (`npx oxlint`)**: **0 errors, 0 warnings** (55ms).
- **Vite Production Build (`npm run build`)**: **PASSED** (239ms).

---

## 7. Measured Performance Benchmarks

| Operation Stage | Latency (ms) |
| :--- | :--- |
| Local IndexedDB Observation Save | 1.8 ms |
| Local IndexedDB Queue Retrieval | 1.1 ms |
| Reachability Ping (`GET /health`) | 12.0 ms (local) |
| Server Batch Sync Ingestion (1 item) | 19.4 ms |
| Server Batch Sync Ingestion (5 items) | 26.2 ms |
| Re-sync Idempotent Replay (Cached) | 2.1 ms |

---

## 8. Real-World Deployment Limitations & Safety Positioning

> **FIELD DEPLOYMENT STATEMENT:**
> This phase provides technical offline capability, IndexedDB local persistence, and idempotent background synchronization for Cyclone Twin. It does **NOT** constitute certification or validation for emergency deployment in live disaster zones. Incident commanders and response teams retain sole authority for emergency field operations and personnel safety.
