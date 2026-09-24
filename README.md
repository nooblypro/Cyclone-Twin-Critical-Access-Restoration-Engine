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

## 7. Interactive Demo Sequence

1. **Intact Network (BASE)**: View functioning GCC arterial corridors, 6 emergency hospitals, and 10 residential ward centroids with 477,000 accessible citizens.
2. **Apply Flood**: Click `1. APPLY MICHAUNG FLOOD`. The flood footprint is overlaid, intersecting surface roads are severed (while elevated bridge spans are preserved), isolating 179,000 citizens across 4 low-lying wards.
3. **Rank Corridors**: Click `2. RANK RESTORATION`. The engine clusters disabled segments and computes deterministic scores.
4. **Inspect Killer Demo**: Toggle `3. KILLER DEMO COMPARE` to witness the divergence between Corridor A (Low Criticality) and Corridor B (High Criticality).
5. **Inspect Breakdown & Advisory**: Click Corridor B to view progress bars for $\Delta H, \Delta P, \Delta T, \Delta D$ and the concise operational dispatch directive.
6. **Simulate Clearance**: Click `4. SIMULATE CLEARING`. The restored corridor lights up in luminous emerald on the map, restoring 89,000 citizens to the healthcare network.
7. **Inspect Manifest**: Click `MANIFEST` in the top bar to inspect full audit provenance and CRS parameters.

---

## 8. Answers to Judge & Reviewer Questions

**Q1: Why not use Machine Learning to predict road washouts?**  
*A: Disaster operations demand explainable, auditable causality. Predicting flood depth or road failure requires uncertain hydrodynamic and structural data. Cyclone Twin starts with any verified hazard footprint (satellite SAR or municipal sensor) and deterministically forecasts network accessibility consequences.*

**Q2: How does the system handle parallel bridges over flooded causeways?**  
*A: The graph uses NetworkX `MultiDiGraph`. Parallel edges between nodes are evaluated via `_active_weight()`. If a surface road floods but a parallel elevated bridge exists (`bridge == 'yes'` or `layer > 0`), the bridge remains active, maintaining network connectivity.*

**Q3: What happens if Gemini API is unreachable or rate-limited?**  
*A: The system implements a guaranteed 3-tier fallback. Tier 2 uses deterministic rule-based templates calibrated to the metric breakdown, and Tier 3 provides a static emergency directive. The core ranking engine is 100% independent and unaffected by AI availability.*

---

## 9. Limitations & Ethical Notice

- **Decision-Support Only**: Cyclone Twin is an infrastructure prioritization tool and does not replace emergency commander situational awareness or field validation.
- **Static Speeds**: Edge travel times assume free-flow speeds degraded by flood blockage; dynamic vehicular congestion is not modeled.
- **Binary Clearance**: Corridors are currently evaluated as either submerged/impassable or operational.
