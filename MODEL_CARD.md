# CYCLONE TWIN — FORMAL MODEL CARD
**Release Candidate 1 (RC-1)**  
*Model Version: 1.0.0-rc1 | Domain: Network Consequence Forecaster for Disaster Management*

---

## 1. Model Overview & Purpose

### Primary Purpose
**Cyclone Twin** is a deterministic network-consequence simulator and decision-support engine developed for the **Greater Chennai Corporation (GCC)** Disaster Management Department. 

Rather than forecasting weather or hydrodynamic flood propagation, Cyclone Twin translates a supplied flood inundation footprint into **systemic emergency access vulnerability**—quantifying which hospitals become unreachable and which communities lose emergency access within a 30-minute critical access threshold, and ranking road corridors by restoration priority.

```
CYCLONE / FLOOD HAZARD
        ↓
PHYSICAL INFRASTRUCTURE DISRUPTION
        ↓
NETWORK ACCESSIBILITY CONSEQUENCE (Multi-Source Dijkstra on G^R)
        ↓
HOSPITAL & POPULATION ACCESSIBILITY IMPACT
        ↓
CORRIDOR CRITICALITY RANKING S(c)
        ↓
ACTIONABLE FIELD RESTORATION DISPATCH
```

---

## 2. Model Inputs & Outputs

### Inputs
1. **Road Network Graph ($G$)**: Projected NetworkX `MultiDiGraph` with string node IDs, metric edge lengths ($m$), design speeds ($\text{km/h}$), bridge/tunnel attributes, and layer metadata in **EPSG:32643** (UTM Zone 43N).
2. **Hazard Footprint**: GeoJSON Polygon or MultiPolygon representing flood inundation extents (calibrated to Cyclone Michaung December 2023 or custom uploaded).
3. **Health Facilities ($F$)**: Georeferenced tertiary trauma and emergency hospitals with coordinate locations, bed capacity, and power grid operating status.
4. **Community Population Nodes ($C$)**: Georeferenced GCC ward administrative centroids with census-derived population counts.
5. **Multi-Criteria Optimization Weights ($W$)**: User-defined or preset importance parameters $(w_h, w_p, w_t, w_d)$ such that $\sum w_i = 1.0$ and $w_i \ge 0$.

### Outputs
1. **Baseline & Disrupted Accessibility State**: Accessible citizen population, isolated ward list, isolated hospital list, and community-to-hospital transit times.
2. **Restoration Corridor Clusters ($K$)**: Contiguous connected components of disabled road segments.
3. **Deterministic Criticality Score $S(c)$**: Multi-criteria ranking with exact component deltas $(\Delta H, \Delta P, \Delta T, \Delta D)$.
4. **Counterfactual Recovery Simulation**: Projected citizens, hospitals, and travel time recovered upon corridor clearance.
5. **AI Field Advisory**: Schema-constrained operational dispatch text ($\le 220$ characters) generated via Gemini (or deterministic Tier 2 fallback).

---

## 3. Algorithmic Foundation & Formulas

### 3.1 Multi-Source Shortest Path on Reversed Graph ($G^R$)
To compute emergency hospital reachability for all $N$ communities in a single pass, the engine executes **Multi-Source Dijkstra on the reversed graph** $G^R$, setting all active powered hospitals as source nodes with initial distance $d(h) = 0$:
$$\text{Time Complexity}: \mathcal{O}((V + E) \log V)$$
This accounts for one-way street directions while yielding the exact minimum transit time from each ward to its closest operational hospital.

### 3.2 Parallel Edge Arbitration
For multiple directed edges between nodes $u$ and $v$, the engine inspects all parallel edges and selects the minimum active travel time:
$$w_{\text{active}}(u, v) = \min \{ \text{travel\_time}(e) \mid e \in E(u, v), \text{physical\_segment}(e) \notin \text{DisabledSegments} \}$$
Returns $\emptyset$ (impassable) if and only if all parallel edges are disabled.

### 3.3 Multi-Criteria Corridor Criticality Formulation
For each candidate restoration corridor $c$, the network consequences are computed counterfactually:
$$S(c) = w_h \cdot \Delta H(c) + w_p \cdot \Delta P(c) + w_t \cdot \Delta T(c) - w_d \cdot \Delta D(c)$$

- **Hospital Recovery Delta ($\Delta H \in [0, 1]$)**:
  $$\Delta H = \begin{cases} \frac{\max(0, |F_{\text{iso}}^{\text{base}}| - |F_{\text{iso}}^{\text{cand}}|)}{|F_{\text{iso}}^{\text{base}}|} & \text{if } |F_{\text{iso}}^{\text{base}}| > 0 \\ 0 & \text{otherwise} \end{cases}$$

- **Population Recovery Delta ($\Delta P \in [0, 1]$)**:
  $$\Delta P = \begin{cases} \frac{\max(0, P_{\text{acc}}^{\text{cand}} - P_{\text{acc}}^{\text{base}})}{P_{\text{iso}}^{\text{base}}} & \text{if } P_{\text{iso}}^{\text{base}} > 0 \\ 0 & \text{otherwise} \end{cases}$$

- **Travel Time Improvement Delta ($\Delta T \in [0, 1]$)**:
  $$\Delta T = \frac{\sum_{c \in C_{\text{reachable}}} \text{Pop}(c) \cdot \frac{\max(0, T_{\text{before}}(c) - T_{\text{after}}(c))}{T_{\text{before}}(c)}}{\sum_{c \in C_{\text{reachable}}} \text{Pop}(c)}$$

- **Clearance Difficulty Penalty ($\Delta D \in [0, 1]$)**:
  $$\Delta D = \frac{\text{Length}(c)}{\max_{k} \text{Length}(k)}$$

### 3.4 Operational Realism Tiebreaker
If $|S(c_1) - S(c_2)| < 0.05$, the corridor with the smaller physical length ($\text{Length}(c)$) is prioritized to favor lower crew resource expenditure.

---

## 4. Data Sources & Calibration

| Dataset | Source / Reference | Representation | Type |
|---|---|---|---|
| **Road Network** | Greater Chennai Arterial Grid (OSMnx / GCC Survey) | 25 nodes, 56 directed edges, EPSG:32643 UTM 43N | Calibrated Arterial Graph |
| **Hospitals** | Chennai Tertiary Trauma Centers (RGGGH, Apollo, KMC, Fortis Malar, MIOT, Gleneagles) | 6 real coordinates, bed counts, power switches | Real Locations, Calibrated Telemetry |
| **Wards** | Greater Chennai Corporation Ward Census Data | 10 ward centroids, 477,000 population aggregate | Calibrated Census Data |
| **Flood Hazard** | Cyclone Michaung (Dec 2023) Inundation Footprint (NRSC / ISRO model) | MultiPolygon (Saidapet, Velachery, Santhome basins) | Calibrated Scenario Polygon |

---

## 5. Explicit Model Assumptions & Limitations

1. **Binary Physical Inundation**: A road segment intersecting a ground-level flood polygon is assumed impassable. Continuous flood depth (e.g. 10cm vs 1m) and flow velocity are not simulated.
2. **Elevated Bridge Preservation**: Road segments with `bridge == "yes"` or `layer > 0` are preserved against surface water intersection. This represents structural elevation, not hydrodynamic surge analysis.
3. **Static Speed Mapping**: Edge travel times are derived from road classification design speeds ($25\text{--}60\text{ km/h}$). Dynamic microscopic traffic jams or vehicle breakdown delays are omitted.
4. **Centroid Snapping**: Community populations and hospital access points are mapped to their nearest network node within a calibrated $200\text{m}$ metric radius.
5. **AI Role Constraint**: Gemini LLM operates strictly as an explanatory natural language dispatcher. Gemini **never** calculates, alters, or biases scores or rankings.

---

## 6. Non-Goals

- **NOT** a weather forecasting or cyclone trajectory model.
- **NOT** a hydrodynamic or hydrological runoff simulation.
- **NOT** an autonomous vehicle guidance or real-time traffic signal platform.
- **NOT** a clinical triage or patient dispatch authority.
