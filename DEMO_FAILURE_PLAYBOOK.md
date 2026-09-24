# CYCLONE TWIN — DEMO FAILURE PLAYBOOK

**Purpose:** Emergency recovery manual for live presentations, judge evaluations, and competition demonstrations.  
**Rule:** Zero panic. Every failure mode has a deterministic, pre-verified recovery path.

---

## 1. BACKEND FAILS TO START OR CRASHES
- **Symptom:** Terminal shows `Connection Refused` on `http://localhost:8000`.
- **Immediate Fix:**
  ```bash
  cd /Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine
  ./.venv/bin/uvicorn cyclone_twin.main:app --host 127.0.0.1 --port 8000 --reload
  ```
- **Verification:** Run `curl http://localhost:8000/accessibility/status` in a background terminal. Status should return `200 OK`.

---

## 2. FRONTEND VITE SERVER DOWN OR NOT ACCESSIBLE
- **Symptom:** Browser shows `Cannot connect to localhost:5174`.
- **Immediate Fix:**
  ```bash
  cd /Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/frontend
  npm run dev
  ```
- **Verification:** Open `http://localhost:5174/` in Chrome.

---

## 3. API TIMEOUT OR NETWORK DISCONNECTION
- **Symptom:** A step button shows a loading spinner or an error banner appears.
- **Immediate Fix:**
  1. Click the top-right **`RESET`** button in the UI.
  2. The frontend [`api.js`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/frontend/src/api.js) automatically aborts stale promises after 10,000ms.
  3. Re-click the current step button.

---

## 4. GEMINI API KEY EXPIRED / LLM RATE LIMITED
- **Symptom:** Advisory panel displays fallback notice or Gemini API 429 error.
- **Presenter Pivot:**
  > *"Notice how the system immediately deployed its deterministic fallback generator. The mathematical rankings, population recovery figures, and score breakdowns operate with 100% autonomy without requiring external cloud connectivity."*
- **Technical Note:** The backend automatically returns the pre-compiled deterministic advisory template with `fallback: true` (verified in Test 24).

---

## 5. EXTERNAL BASEMAP TILES FAIL TO LOAD (OFFLINE MODE)
- **Symptom:** Dark map background shows no street raster or shows API key watermark.
- **Presenter Pivot:**
  > *"Cyclone Twin operates entirely on vector graph topology. Even in a complete telecom blackout where external satellite tile servers are offline, our topological vector layers, flood polygons, hospital markers, and ward centroids render locally on canvas."*

---

## 6. ACCIDENTAL WRONG CLICK OR OUT-OF-ORDER STEP
- **Symptom:** Clicked `RESET` or advanced past the intended demo step.
- **Immediate Fix:**
  1. Simply click **`RESET`** in the top bar.
  2. The state resets to Step 1 in <100ms.
  3. Step through rapidly: `1. APPLY HAZARD` $\rightarrow$ `2. RANK CRITICALITY` $\rightarrow$ `3. COMPARE DIVERGENCE`.

---

## 7. PROJECTOR / DISPLAY RESOLUTION MISMATCH
- **Symptom:** Projector forces a compact 1280×720 or 1024×768 resolution, or UI looks too large.
- **Immediate Fix:**
  - Press `Cmd + 0` (or `Ctrl + 0`) in Chrome to reset browser zoom to exactly 100%.
  - If text is slightly large on older 1024×768 projectors, press `Cmd + -` once (90% zoom).
  - The responsive CSS grid automatically adjusts sidebars and HUD badges without clipping.

---

## 8. COMPLETE MACHINE / BROWSER CRASH BACKUP
- **Contingency:** High-resolution screenshots of all 6 verified states are archived in the repository and available for instant offline slide presentation:
  1. `Baseline Accessibility (100% / 477k)`
  2. `Hazard Inundation (179k isolated)`
  3. `Criticality Inspection (Top Corridor #1)`
  4. `Criticality Divergence (Corridor A vs B)`
  5. `Mitigation Strategy (14.2 km dewatering)`
  6. `Simulated Recovery (387k accessible / +89k recovered)`
