# CYCLONE TWIN
### From Flood Impact to Network Vulnerability

A network-aware infrastructure vulnerability forecaster and critical access restoration engine for the **Greater Chennai Corporation (GCC)**.

---

## 1. Executive Summary & Core Innovation

Most flood maps show **WHERE** infrastructure is physically submerged.

**Cyclone Twin** shows **WHAT HAPPENS** to the city's emergency healthcare access network when that infrastructure fails.

The system translates:
```
CYCLONE / FLOOD IMPACT
        ↓
INFRASTRUCTURE FAILURE
        ↓
NETWORK CONSEQUENCE (Multi-Source Dijkstra on G^R)
        ↓
HOSPITAL + POPULATION IMPACT
        ↓
INFRASTRUCTURE CRITICALITY
        ↓
PROTECTION / RESTORATION PRIORITY
```

### What Cyclone Twin IS
- A deterministic network-consequence simulator.
- Quantifies which hospitals become unreachable and which communities lose emergency access within a 30-minute critical access threshold.
- Ranks infrastructure corridors by systemic network criticality rather than merely physical geometry or road width.
- Evaluates multi-criteria recovery potential: recovered hospitals ($\Delta H$), recovered population ($\Delta P$), transit time savings ($\Delta T$), and clearance difficulty ($\Delta D$).

### What Cyclone Twin IS NOT
- Does **NOT** predict cyclone paths, weather formation, or meteorological variables.
- Does **NOT** predict flood depths or surface water hydrodynamic propagation.
- Does **NOT** use black-box machine learning to predict road-failure probabilities.
- Does **NOT** claim clinical emergency or autonomous dispatch validation.

---

## 2. The Killer Demo: Network Criticality Divergence

Two road corridors can experience the exact same physical hazard while producing radically different network consequences:

| Dimension | Corridor A (Santhome Feeder) | Corridor B (Saidapet Adyar Lifeline) |
| :--- | :--- | :--- |
| **Physical Condition** | Flooded (Impassable) | Flooded (Impassable) |
| **Hospitals Recovered** | 0 | 0 (maintains link to trauma centers) |
| **Population Recovered** | 0 citizens | **89,000 citizens** |
| **Travel Time Delta** | $+0$ min | $+22$ min degradation averted |
| **Calculated Score** | $-0.0497$ | $+0.0724$ |
| **Network Criticality** | **LOW** | **HIGH (TOP RESTORATION PRIORITY)** |

> *"The physical hazard is similar. The network vulnerability isn't."*

All figures are generated in real-time from the graph topology and Dijkstra calculations.

---

## 3. Mathematical & Algorithmic Foundation

### Graph Model
- NetworkX `MultiDiGraph` projected to **EPSG:32643** (UTM Zone 43N metric coordinate reference system).
- Node IDs normalized to strings.
- Parallel edges inspected via `_active_weight()`: selects the minimum active travel time and ignores disabled segments.
- Missing edge geometries are automatically reconstructed as `LineString` from node coordinates (TEST 20).
- Edge preservation:
  - `bridge == "yes"` OR `layer > 0` $\rightarrow$ **PRESERVED** (elevated roadways stay open).
  - `tunnel == "yes"` OR `layer < 0` $\rightarrow$ **DISABLED** (submerged).

### Routing & Accessibility ($G^R$)
- Hospital-to-community emergency transit is computed using **Multi-Source Dijkstra on the reversed graph** $G^R$, with active health facilities as sources.
- A single pass computes the minimum travel time from every ward to its nearest operational hospital in $O((V + E) \log V)$ time.
- Power filtering: unpowered hospitals are excluded as active destinations. If all hospitals lose power, an all-isolated state is returned without exceptions.

### Corridor Clustering
- Contiguous disabled road segments are grouped into connected components using an undirected graph projection of physical segments.
- Zero-edge components are discarded.

### Deterministic Ranking Formula
For each candidate restoration corridor $c$, the segments are temporarily restored and the network is re-evaluated:

$$S(c) = w_h \cdot \Delta H + w_p \cdot \Delta P + w_t \cdot \Delta T - w_d \cdot \Delta D$$

- **$\Delta H$**: Normalized hospital recovery fraction $\in [0, 1]$.
- **$\Delta P$**: Normalized population recovery fraction $\in [0, 1]$.
- **$\Delta T$**: Population-weighted travel time improvement for communities reachable both before and after $\in [0, 1]$.
- **$\Delta D$**: Normalized corridor length/clearance difficulty penalty $\in [0, 1]$.
- **Tiebreaker**: If $|top\_score - second\_score| < 0.05$, sorted by `total_length_m` ascending (operational realism).
- **Dead-end Detection**: If $\Delta H = 0$, $\Delta P = 0$, and $\Delta T = 0$, flags `combined_intervention_required = True`.

### Default Life-Safety Weight Preset
$$w_h = 0.40, \quad w_p = 0.30, \quad w_t = 0.20, \quad w_d = 0.10$$
*(Weights are validated to be non-negative and sum to exactly 1.0).*

---

## 4. System Architecture

```
                 ┌────────────────────────────────┐
                 │       Operational Console      │
                 │   (React / Leaflet Dark Map)   │
                 └───────────────┬────────────────┘
                                 │
                                 ▼
                 ┌────────────────────────────────┐
                 │          FastAPI API           │
                 │        (Rest / CORS)           │
                 └───────────────┬────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
   DataLoader              NetworkEngine          RankingEngine
 (OSMnx / Mock)          (Multi-Source G^R)     (Deterministic)
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 ▼
                         Scenario Results
                                 │
                                 ▼
                           Advisory Layer
                                 │
                                 ▼
                     Gemini 2.5 Flash / Fallback
```

### Decoupled AI Advisory Layer
Gemini 2.5 Flash is strictly an explanatory layer for field dispatch generation ($\le 220$ characters, action verbs like `DEPLOY_PUMPS` or `CLEAR_DEBRIS`). **Gemini never calculates or alters the ranking.**
A 3-tier fallback ensures zero downtime:
1. Gemini API call
2. Deterministic rule-based template
3. Static emergency response fallback

---

## 5. REST API Specification

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/network/load` | Reloads Chennai arterial road multigraph |
| `POST` | `/flood/apply` | Disables flood-intersecting roads & clusters corridors |
| `GET` | `/accessibility/status` | Returns accessible population and isolated facility/ward IDs |
| `POST` | `/interventions/rank` | Calculates multi-criteria scores and returns `ScenarioManifest` |
| `POST` | `/interventions/clear` | Simulates clearing a corridor and returns updated graph state |
| `POST` | `/advisory/generate` | Generates dispatch directive ($\le 220$ chars) with fallback |
| `GET` | `/map/data` | Returns complete GeoJSON layers for direct map rendering |

---

## 6. Getting Started & Execution

### Prerequisites
- Python 3.10+ (Tested on Python 3.13)
- Node.js v18+ (Tested on Node v25)

### 1. Setup Virtual Environment & Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Preflight Sanity Check
```bash
python scripts/preflight.py
```

### 3. Run Automated Pytest Suite
```bash
pytest -v tests/test_cyclone_twin.py
```

### 4. Launch Backend API Server
```bash
uvicorn cyclone_twin.main:app --host 0.0.0.0 --port 8000
```

### 5. Launch Frontend Console
```bash
cd frontend
npm install
npm run dev -- --port 5174
```
Open [http://localhost:5174](http://localhost:5174) in your browser.

---

## 7. Guided 6-Step Competition Demo Sequence

The application provides a guided stepper (`NEXT DEMO STEP`) designed for live judge evaluations:

1. **STEP 1: SHOW NETWORK (BASE)**: View functioning GCC arterial corridors, 6 emergency trauma hospitals, and 10 residential ward centroids with 477,000 accessible citizens under normal conditions.
2. **STEP 2: APPLY HAZARD**: Overlays the Cyclone Michaung flood polygon. Low-lying surface roads are severed while elevated bridge spans are preserved, isolating 179,000 citizens across 4 low-lying wards (Saidapet, Jafferkhanpet, Velachery, Madipakkam).
3. **STEP 3: ASSESS VULNERABILITY**: Multi-source Dijkstra on $G^R$ clusters disabled road segments into 3 contiguous corridors and deterministically scores them.
4. **STEP 4: COMPARE CRITICALITY (KILLER DEMO)**: Side-by-side comparison of Corridor A (Santhome Feeder, score $-0.050$, 0 pop recovered) vs Corridor B (Saidapet / Velachery Lifeline, score $+0.072$, 89,000 pop recovered) proving: *"The physical hazard is similar. The network vulnerability isn't."*
5. **STEP 5: MITIGATION PRIORITY**: Inspects Rank #1 with a deterministic "Why This Matters" consequence statement and the active Life Safety formula breakdown ($0.40/0.30/0.20/0.10$).
6. **STEP 6: SHOW RECOVERY**: Simulates clearing the priority lifeline. The corridor turns vibrant emerald, recovering 89,000 cut-off residents and reconnecting 2 wards.
7. **RESET SCENARIO**: Restores the pristine 477,000-citizen baseline without browser reload.

---

## 8. Answers to Judge & Reviewer Questions

**Q1: What exactly are you predicting?**  
*A: We are not predicting the flood itself. We forecast emergency healthcare network consequences and accessibility loss under a supplied flood scenario.*

**Q2: Where does the flood data come from?**  
*A: Satellite-derived flood inundation extents (NRSC / ISRO Disaster Management Support) or verified municipal water-logging polygons.*

**Q3: Why not use Machine Learning to predict road washouts?**  
*A: Disaster operations demand explainable, auditable causality. Predicting flood depth or road failure requires uncertain hydrodynamic and structural data. Cyclone Twin starts with any verified hazard footprint and deterministically forecasts network accessibility consequences.*

**Q4: How does the system handle parallel bridges over flooded causeways?**  
*A: The graph uses NetworkX `MultiDiGraph`. Parallel edges between nodes are evaluated via `_active_weight()`. If a surface road floods but a parallel elevated bridge exists (`bridge == 'yes'` or `layer > 0`), the bridge remains active, maintaining network connectivity.*

**Q5: What happens if Gemini API is unreachable or rate-limited?**  
*A: The system implements a guaranteed 3-tier fallback. Tier 2 uses deterministic rule-based templates calibrated to the metric breakdown, and Tier 3 provides a static emergency directive. The core ranking engine is 100% independent and unaffected by AI availability.*

---

## 9. Technical Limitations & Operational Boundaries

- **Decision-Support Only**: Cyclone Twin is an infrastructure prioritization tool and does not replace emergency commander situational awareness or field validation.
- **Static Free-Flow Speeds**: Edge travel times assume free-flow design speeds degraded by flood blockage; dynamic vehicular congestion is not modeled.
- **Binary Passability**: Corridors are currently evaluated as either submerged/impassable or operational.
- **No Real-Time Hydrology**: Does not compute rainfall runoff or hydrodynamics.
- **No Live Sensor Stream**: Inputs are based on validated GIS layers and satellite rasters.

---

## 10. Repository & Project Structure

```
.
├── cyclone_twin/                    # Core Python Backend Package
│   ├── main.py                      # FastAPI app, endpoints, request ID telemetry
│   ├── models.py                    # Pydantic v2 schemas and validation contracts
│   ├── network_engine.py            # NetworkX MultiDiGraph, EPSG:32643, Dijkstra on G^R
│   ├── corridor_engine.py           # Connected component clustering on disabled links
│   ├── ranking_engine.py            # Deterministic multi-criteria scoring S(c)
│   ├── advisory_engine.py           # 3-tier advisory (Gemini 2.5 Flash + fallback)
│   ├── data_loader.py               # OSMnx network fetcher & satellite polygon loader
│   ├── mock_chennai_graph.py        # Chennai 10-ward baseline graph (offline resilient)
│   └── flood_polygon_fallback.py    # Cyclone Michaung flood extent (offline resilient)
├── frontend/                        # Operational Web Console
│   ├── src/App.jsx                  # Single-page cockpit, Leaflet map, guided stepper
│   ├── src/index.css                # Dark mode design tokens, formula styling
│   └── vite.config.js               # Vite build configuration
├── tests/
│   └── test_cyclone_twin.py         # 27 comprehensive pytest tests (100% pass)
├── scripts/
│   └── preflight.py                 # 8-point system preflight sanity validator
├── docs/
│   └── ADR-001-cyclone-twin-architecture.md  # Architectural Decision Record
└── logs/
    └── FINAL_VERIFICATION.md        # Comprehensive Phase 3 verification evidence
```
