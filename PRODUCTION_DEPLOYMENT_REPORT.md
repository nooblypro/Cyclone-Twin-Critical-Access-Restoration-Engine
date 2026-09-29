# Production Deployment Verification Report: Vercel + Render Target Architecture

**System:** Cyclone Twin — Critical Access Restoration Engine  
**Deployment Target:** Vercel (Frontend) + Render (Backend)  
**Overall Status:** **DEPLOYED + VERIFIED (COMPLETE)**  
**Frontend Production URL:** `https://frontend-woad-iota-23.vercel.app`  
**Backend Production URL:** `https://cyclone-twin-backend.onrender.com`  
**Backend Test Suite:** **363/363 PASSING**  
**Frontend Quality:** Lint PASS (0 errors), Build PASS (Vite bundle `dist/`)  

---

## 1. Executive Summary & Production Architecture

The production deployment of **Cyclone Twin** is permanently established on **Vercel** (for the React 19 / Vite SPA frontend) and **Render** (for the FastAPI Python 3.13 backend).

```
Vercel Edge CDN (React 19 / Vite SPA)
       │
       │ HTTPS REST / GeoJSON Feature Transmission
       ▼
Render Web Service (FastAPI + NetworkX + Shapely)
```

Google Cloud Platform (Cloud Run, Firebase Hosting, Firestore, BigQuery, GCS, Vertex AI) and AWS are permanently **DEFERRED / NOT USED FOR PRODUCTION**.

---

## 2. Infrastructure Categorization & Deferred Services Matrix

| Component | Architecture Role | Production Status | Live URL / Implementation Details |
| :--- | :--- | :--- | :--- |
| **Frontend** | Vercel Edge Hosting | **DEPLOYED + VERIFIED** | `https://frontend-woad-iota-23.vercel.app` (HTTP 200 OK) |
| **Backend** | Render Web Service | **DEPLOYED + VERIFIED** | `https://cyclone-twin-backend.onrender.com` (HTTP 200 OK) |
| **Google Cloud Run** | Container Backend | **DEFERRED / NOT USED** | Abandoned in favor of Render Web Service |
| **Firebase Hosting** | Static Hosting | **DEFERRED / NOT USED** | Abandoned in favor of Vercel Edge Hosting |
| **Firestore** | Cloud NoSQL DB | **DEFERRED / LOCAL FALLBACK** | Process-memory state engine active (`DisasterStateManager`) |
| **Cloud Storage (GCS)** | Cloud Object Store | **DEFERRED / LOCAL FALLBACK** | Local fixture media paths active |
| **BigQuery** | Cloud Analytics Stream | **DEFERRED / LOCAL FALLBACK** | In-memory operational event logger active |
| **Vertex AI / Gemini** | Multimodal AI | **DEFERRED / LOCAL FALLBACK** | Calibrated fallback rule engine active (`AdvisoryEngine`) |

---

## 3. Production Endpoint Verification Matrix

All live HTTP endpoints were verified directly against the production deployment:

| Endpoint | Method | HTTP Status | Response Data / Verified Functionality |
| :--- | :--- | :--- | :--- |
| `https://cyclone-twin-backend.onrender.com/` | `GET` | **200 OK** | `{"status":"online","system":"Cyclone Twin","version":"1.0.0"}` |
| `https://cyclone-twin-backend.onrender.com/accessibility/status` | `GET` | **200 OK** | `{"accessible_population":477000,"isolated_facilities":[]}` |
| `https://cyclone-twin-backend.onrender.com/flood/apply` | `POST` | **200 OK** | `{"disabled_edges":20,"flood_source":"nrsc","corridors":3}` |
| `https://cyclone-twin-backend.onrender.com/interventions/rank` | `POST` | **200 OK** | `{"ranked_corridors":[{"corridor_id":"corridor_03","rank":1,"score":0.0724...}]}` |
| `https://frontend-woad-iota-23.vercel.app/` | `GET` | **200 OK** | HTML SPA root bundle (`<title>Cyclone Twin...</title>`) |

---

## 4. Production CORS Origin Audit

Empirical CORS preflight tests were conducted against the live Render backend:

- **Allowed Origin Test (`Origin: https://frontend-woad-iota-23.vercel.app`)**:
  - Response: **HTTP 200 OK**
  - Headers: `access-control-allow-origin: https://frontend-woad-iota-23.vercel.app`, `access-control-allow-credentials: true`
- **Disallowed Origin Test (`Origin: https://evil.example`)**:
  - Response: **HTTP 400 Bad Request**
  - Response Body: `Disallowed CORS origin` (No Access-Control-Allow-Origin header returned)
- **Wildcard Check**: Confirmed that `Access-Control-Allow-Origin: *` is **NOT** used in production.

---

## 5. End-to-End Workflow Verification

1. **Baseline Network $\rightarrow$ Flood Disruption**: Verified live calculation of disabled edges (`20` edges disabled under Michaung scenario).
2. **Dijkstra Accessibility Computation**: Verified Dijkstra shortest-path calculations across 25 nodes and 56 edges.
3. **Counterfactual Intervention Ranking**: Verified top corridor candidate (`corridor_03`, score `+0.0724`, `89,000` population reconnected).
4. **Localization (English $\leftrightarrow$ Tamil)**: UI locale state transitions cleanly without changing underlying machine-readable API enums.

---

## 6. Regression & Quality Verification

| Suite / Check | Result | Details |
| :--- | :--- | :--- |
| **Backend Test Suite** | **363/363 PASS** | `pytest` (0 failures, zero regressions across all phases) |
| **Frontend Linter** | **0 Errors** | `oxlint` on 9 files |
| **Frontend Production Build** | **PASS** | `vite build` compiled bundle in `dist/` |

---

## 7. Operational Limitations & Security

1. **State Persistence**: Simulation state is instance-local in process memory on Render. Cold starts re-initialize default scenario state (`477,000` baseline accessible population).
2. **Secrets & Security**: No API keys or credentials exposed in Vercel client bundle; `.env` files untracked in git.
