# Cyclone Twin — Production Deployment Guide
**Target Architecture:** Firebase Hosting (Frontend) + Google Cloud Run (Backend) + Firestore + GCS + BigQuery  
**Secondary Targets:** Vercel (Frontend) + Render (Backend)

```
Firebase Hosting
       │
       ▼
React/Vite Frontend
       │
       ▼
Google Cloud Run (Containerized FastAPI)
 ┌─────┼──────────────┐
 ▼     ▼              ▼
Firestore  BigQuery  Cloud Storage
                         │
                         ▼
                    Gemini /
                    Vertex AI
```

---

## 1. Primary Google Cloud Architecture

- **Frontend:** React 19 + Vite SPA hosted on **Firebase Hosting** with automatic SSL, global CDN, and `/api/**` rewrites to Cloud Run.
- **Backend:** Containerized FastAPI + NetworkX + Shapely on **Google Cloud Run** (`asia-south1` or `us-central1`), binding dynamically to `$PORT`.
- **Database / State:** **Firestore** for disaster state snapshots, active corridor states, and citizen PGIS reports.
- **Object Storage:** **Google Cloud Storage (GCS)** for multimodal field evidence (photos/audio/notes).
- **Telemetry & Analytics:** **BigQuery** for streaming operational metrics, corridor clearance logs, and execution variance telemetry.
- **AI Engine:** **Vertex AI / Gemini 1.5** for multimodal evidence interpretation and advisory generation.

---

## 2. Google Cloud Deployment Protocol

### 2.1 One-Command Automated Deployment (`deploy_gcp.sh`)
Execute the automated deployment harness script:
```bash
./deploy_gcp.sh deploy-all
```

Or execute granular steps:
```bash
./deploy_gcp.sh check            # Validate gcloud, docker, and environment
./deploy_gcp.sh build            # Build local container image
./deploy_gcp.sh deploy-backend   # Submit container to Cloud Build and deploy to Cloud Run
./deploy_gcp.sh deploy-frontend  # Build Vite frontend and deploy to Firebase Hosting
```

### 2.2 Manual Deployment Steps

#### Step 1: Deploy Backend to Google Cloud Run
```bash
# 1. Build and push container to Google Container Registry / Artifact Registry
gcloud builds submit --tag gcr.io/cyclone-twin-gcc/cyclone-twin-backend:latest .

# 2. Deploy to Cloud Run
gcloud run deploy cyclone-twin-backend \
    --image gcr.io/cyclone-twin-gcc/cyclone-twin-backend:latest \
    --platform managed \
    --region asia-south1 \
    --allow-unauthenticated \
    --set-env-vars "GCP_PROJECT_ID=cyclone-twin-gcc,GCS_BUCKET_NAME=cyclone-twin-gcc-media" \
    --port 8080
```

#### Step 2: Deploy Frontend to Firebase Hosting
```bash
# 1. Build Vite production bundle
cd frontend && npm run build && cd ..

# 2. Deploy static site and rewrite rules
firebase deploy --only hosting --project cyclone-twin-gcc
```

### 2.3 Cloud Build CI/CD Pipeline (`cloudbuild.yaml`)
Submitting a build to Cloud Build runs automated test verification prior to deployment:
```bash
gcloud builds submit --config cloudbuild.yaml
```

---

## 3. GCP Infrastructure Fallback & Resilience
The backend features an automatic **Local Fallback Mode**:
- If `GCP_PROJECT_ID` or GCP SDK credentials are absent, `GCPFoundationService` operates with zero-downtime in-memory fallback buffers.
- Endpoints `GET /gcp/status`, `POST /gcp/snapshot`, and `POST /gcp/log-event` report active connectivity manifest and fallback statistics.

---

## 4. Alternative Deployments (Vercel & Render)

### Render (Backend)
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn cyclone_twin.main:app --host 0.0.0.0 --port $PORT`
- **Persistent Storage Mount:** Attach Render Persistent Disk at `/var/data` (1 GB)
- **Environment Variables:**
  - `CYCLONE_TWIN_DB_PATH=/var/data/cyclone_twin_state.db`
  - `CYCLONE_TWIN_PERSISTENCE=sqlite`
  - `ALLOWED_ORIGINS=https://frontend-woad-iota-23.vercel.app,https://cyclone-twin.vercel.app,http://localhost:5173`
- **Durability Guarantee:** Single-instance SQLite storage on attached volume `/var/data`. Preserves scenario snapshots, citizen observations, interventions, and operational audit log across instance restarts and deployments. Derived accessibility and ranking outputs are recomputed deterministically upon rehydration.

### Vercel (Frontend)
- **Root Directory:** `frontend`
- **Build Command:** `npm run build`
- **Environment Variable:** `VITE_API_BASE_URL=https://cyclone-twin-backend.onrender.com`

---

## 5. Production Health & API Verification Checklist

| Endpoint | Method | Expected Output | Verification |
| :--- | :--- | :--- | :--- |
| `GET /` | Health | `{"status":"online","system":"Cyclone Twin"}` | Backend Liveness |
| `GET /gcp/status` | Infrastructure | `{"status":"HEALTHY","target_architecture":{...}}` | GCP Manifest |
| `POST /network/load` | Graph Init | `{"nodes":25,"edges":56}` | Graph Initialized |
| `POST /flood/apply` | Disruption | `{"disabled_edges":20,"corridors":3}` | Flood Applied |
| `GET /accessibility/status` | Invariants | `{"accessible_population":298000}` | Dijkstra Engine Active |
| `POST /interventions/rank` | Ranking | `Top score S(c) = +0.0724` | Multicriteria Ranked |
| `POST /interventions/clear` | Restoration | `+89,000 citizens reconnected` | Lifeline Cleared |
| `GET /map/data` | Cartography | GeoJSON FeatureCollection | Vector Rendering |
