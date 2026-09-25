# Cyclone Twin — Production Deployment Guide
**Target Architecture:** Vercel (Frontend) + Render (Backend)  
**Cloud Status:** **AWS: NOT USED**

```
┌─────────────────────────────────────────────────────────┐
│               REACT / VITE WEB CLIENT                   │
│               Hosted on Vercel Edge                     │
│               URL: https://cyclone-twin.vercel.app      │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTPS (REST / GeoJSON)
                            ▼
┌─────────────────────────────────────────────────────────┐
│               FASTAPI NETWORK ENGINE                    │
│               Hosted on Render Web Service              │
│               URL: https://cyclone-twin-backend.onrender.com │
└─────────────────────────────────────────────────────────┘
```

---

## 1. Architecture Overview
- **Frontend:** React 19 + Vite SPA hosted on **Vercel** with global CDN caching.
- **Backend:** FastAPI + NetworkX + Shapely + GeoPandas hosted on **Render** (Linux Web Service, Python 3.13).
- **Communication:** Secure HTTPS REST queries and GeoJSON feature transmissions with origin-restricted CORS.
- **Infrastructure Exclusions:** AWS (S3, ECS, Lambda, CloudFront, Amplify, API Gateway) is **NOT USED**.

---

## 2. Backend Deployment on Render

### 2.1 Service Specifications
- **Service Type:** Web Service
- **Environment:** `Python 3`
- **Region:** Oregon (US West) or Frankfurt (EU)
- **Branch:** `main`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn cyclone_twin.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path:** `/`

### 2.2 Environment Variables (Render Dashboard)
| Variable | Value | Description |
| :--- | :--- | :--- |
| `PYTHON_VERSION` | `3.13.0` | Python runtime version. |
| `ALLOWED_ORIGINS` | `https://cyclone-twin.vercel.app,http://localhost:5173,http://localhost:5174` | Allowed CORS origins (regex matches `*.vercel.app`). |
| `GEMINI_API_KEY` | *(Secret)* | Optional Gemini API key for dynamic advisory text. Falls back to deterministic rule engine if unset. |

### 2.3 Blueprint Deployment (`render.yaml`)
Alternatively, deploy using the included [`render.yaml`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/render.yaml) by connecting the repository as a **Render Blueprint**.

---

## 3. Frontend Deployment on Vercel

### 3.1 Project Settings
- **Framework Preset:** `Vite`
- **Root Directory:** `frontend`
- **Build Command:** `npm run build`
- **Output Directory:** `dist`
- **Node.js Version:** `20.x` or `22.x`

### 3.2 Environment Variables (Vercel Dashboard)
| Variable | Value | Description |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `https://cyclone-twin-backend.onrender.com` | Public HTTPS endpoint of the deployed Render backend. |

### 3.3 Routing Configuration (`vercel.json`)
SPA route handling is configured via [`frontend/vercel.json`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/frontend/vercel.json) to route client-side paths to `index.html`.

---

## 4. Step-by-Step Deployment Protocol

### Step 1: Deploy Backend to Render
1. In Render Dashboard, click **New +** $\rightarrow$ **Web Service**.
2. Select the GitHub repository `Cyclone-Twin-Critical-Access-Restoration-Engine`.
3. Set Build Command to `pip install -r requirements.txt`.
4. Set Start Command to `uvicorn cyclone_twin.main:app --host 0.0.0.0 --port $PORT`.
5. Add environment variables: `PYTHON_VERSION=3.13.0` and `ALLOWED_ORIGINS=https://cyclone-twin.vercel.app`.
6. Click **Deploy**. Note the assigned URL (e.g. `https://cyclone-twin-backend.onrender.com`).

### Step 2: Deploy Frontend to Vercel
1. In Vercel Dashboard, click **Add New Project**.
2. Select the repository and choose root directory `frontend`.
3. Under Environment Variables, set `VITE_API_BASE_URL` to your Render backend URL.
4. Click **Deploy**. Note the assigned Vercel URL (e.g. `https://cyclone-twin.vercel.app`).

### Step 3: Verify Cross-Origin Communication
1. Open the Vercel URL in Chrome.
2. Confirm the map loads and displays the baseline network from Render.
3. Open Chrome DevTools $\rightarrow$ **Network tab** to verify requests to `https://<render-url>/map/data` return `200 OK`.

---

## 5. Production Health & API Verification Checklist

| Endpoint | Method | Expected Output | Verification |
| :--- | :--- | :--- | :--- |
| `GET /` | Health | `{"status":"online","system":"Cyclone Twin"}` | Render Liveness |
| `POST /network/load` | Graph Init | `{"nodes":25,"edges":56}` | Graph Initialized |
| `POST /flood/apply` | Disruption | `{"disabled_edges":20,"corridors":3}` | Flood Applied |
| `GET /accessibility/status` | Invariants | `{"accessible_population":298000}` | Dijkstra Engine Active |
| `POST /interventions/rank` | Ranking | `Top score S(c) = +0.0724` | Multicriteria Ranked |
| `POST /interventions/clear` | Restoration | `+89,000 citizens reconnected` | Lifeline Cleared |
| `GET /map/data` | Cartography | GeoJSON FeatureCollection | Vector Rendering |
