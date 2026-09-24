# ADR-001: Cyclone Twin Core System Architecture & Decision Record

**Date**: 2026-09-24  
**Status**: Accepted  
**Deciders**: GCC Cyclone Twin Engineering & Disaster Operations Team  

---

## 1. Context & Problem Statement

Urban flood management systems traditionally visualize *where* floodwaters accumulate (physical hazard extent). However, emergency response agencies such as the Greater Chennai Corporation (GCC) must make rapid resource-allocation decisions based on *what happens to the city's critical emergency-access network* when key transport lifelines fail.

Two road corridors may experience identical flood inundation depths yet produce radically divergent systemic impacts:
- **Corridor A**: Redundant peripheral route where surrounding communities have alternative detours to tertiary healthcare. Systemic impact: LOW.
- **Corridor B**: Vital arterial lifeline connecting dense wards across a river basin to regional trauma hospitals. Failure causes complete hospital isolation and cuts off tens of thousands of citizens. Systemic impact: HIGH.

The core engineering objective is to build a deterministic, network-aware infrastructure vulnerability and restoration prioritization engine that translates:
```
CYCLONE / FLOOD IMPACT
        ↓
INFRASTRUCTURE FAILURE
        ↓
NETWORK DISRUPTION (Multi-Source Dijkstra on G^R)
        ↓
HOSPITAL + POPULATION IMPACT
        ↓
INFRASTRUCTURE CRITICALITY
        ↓
PROTECTION / RESTORATION PRIORITY
```

---

## 2. Decision: Deterministic Graph Pipeline with Decoupled AI Advisory

We established the following architectural tenets:

1. **Deterministic Graph Simulation**:
   The mathematical core uses NetworkX `MultiDiGraph` with UTM EPSG:32643 metric projections. Routing uses multi-source Dijkstra on the *reversed graph* $G^R$ from active hospitals to communities. This computes optimal hospital accessibility across the entire city in a single deterministic pass ($O((V + E) \log V)$), guarding against parallel edge traps and directional asymmetry.

2. **Strict Multi-Criteria Scoring Formula**:
   Restoration candidates are clustered from disabled road segments into connected components. Each corridor $c$ is evaluated by temporarily re-enabling it and computing:
   $$S(c) = w_h \cdot \Delta H + w_p \cdot \Delta P + w_t \cdot \Delta T - w_d \cdot \Delta D$$
   where $\Delta H$ is normalized hospital recovery, $\Delta P$ is population recovery, $\Delta T$ is population-weighted travel time reduction for already-reachable communities, and $\Delta D$ is length/difficulty penalty. All deltas are strictly bounded in $[0, 1]$.
   Ties within $0.05$ score difference are broken by shorter corridor length (operational realism).
   Dead-end candidates producing zero delta across the network are flagged with `combined_intervention_required = True`.

3. **Gemini Decoupled as an Advisory-Only Layer**:
   LLMs (Gemini 2.5 Flash) are used exclusively for field dispatch explanation and operational communication ($\le 220$ characters, action verbs, affected wards). **Gemini is strictly prohibited from altering, calculating, or biasing the ranking.** 
   A 3-tier fallback guarantee ensures zero failure risk:
   - Tier 1: Gemini API call
   - Tier 2: Deterministic rule-based template
   - Tier 3: Static emergency dispatch fallback

4. **Geospatial Provenance & Transparency**:
   Every computation produces a `ScenarioManifest` recording `graph_source` (`osmnx_live` | `mock_fallback`), `flood_source` (`nrsc` | `manual_digitized` | `mock`), `graph_crs` (`EPSG:32643`), snapping distances, and threshold seconds ($1800$s). The system never silently degrades without provenance flags.

5. **Frontend/Backend Separation**:
   - Backend: Minimal, fast, async FastAPI application providing exact REST contracts (`/network/load`, `/flood/apply`, `/accessibility/status`, `/interventions/rank`, `/interventions/clear`, `/advisory/generate`, `/map/data`).
   - Frontend: High-density operational geospatial command console built with React + Vite + Leaflet, implementing a dark cinematic emergency cartography visual language.

---

## 3. Alternatives Considered

### Alternative 1: Machine Learning Road-Failure Probability Models
- **Pros**: Could model soil saturation curves or predictive road washouts.
- **Cons**: Requires extensive training datasets, black-box unexplainability during crisis operations, unverified predictive assertions.
- **Why not**: Violates project framing. The system starts with a flood scenario and forecasts *network consequences*, not weather or road breakdown probabilities.

### Alternative 2: Real-Time Hydrological Hydrodynamic Modeling (SWMM/HEC-RAS)
- **Pros**: Physical accuracy of 2D shallow water flow.
- **Cons**: Massive compute latency (hours per run), incompatible with rapid emergency triage (< 1 second response times required by GCC dispatchers).
- **Why not**: Hydrodynamic outputs (from NRSC satellite or municipal flood sensors) serve as polygon inputs; the twin solves the *network access* problem.

### Alternative 3: Cloud Database & Queueing Broker (Postgres/PostGIS/RabbitMQ)
- **Pros**: Distributed persistence.
- **Cons**: High operational overhead, deployment friction in emergency disaster field nodes, Docker dependencies.
- **Why not**: In-memory projected graph with deterministic caching provides sub-50ms query speeds without external daemon dependencies.

---

## 4. Consequences & Guarantees

### Positive
- **100% Deterministic Reproducibility**: Identical inputs yield identical corridor rankings across all platforms.
- **Sub-Second Execution**: Complete Dijkstra accessibility re-calculation and ranking across Chennai takes $< 80$ms.
- **Fail-Safe Operation**: If external network fails or Overpass/Gemini is unreachable, offline fallback ensures the command console operates with full functionality.
- **Verification Guarantee**: 27 unit and integration tests validate toy graphs, edge cases, parallel multi-edges, and REST contracts.

### Negative & Limitations
- Network does not model live dynamic traffic congestion or road width capacity constraints.
- Flooding is modeled as binary impassable state rather than water-depth-dependent vehicle clearance (e.g. 4x4 vs ambulance vs fire engine).

---

## 5. Verification Matrix

| Requirement | Implementation Component | Verification Evidence |
| :--- | :--- | :--- |
| Multi-source Dijkstra ($G^R$) | `NetworkEngine.community_to_hospital_times` | `test_01`, `test_05`, `test_18` |
| Parallel edge selection | `NetworkEngine._active_weight` | `test_16` |
| Bridge/Tunnel Preservation | `flood_polygon_fallback.py` | `test_21` |
| Connected Corridor Clustering | `CorridorEngine.cluster_disabled_segments` | `test_22` |
| Deterministic Ranking | `RankingEngine.rank_corridors` | `test_10`, `test_11`, `test_23` |
| Advisory Fallback ($\le 220$ chars) | `AdvisoryEngine.generate_advisory` | `test_24` |
| Scenario Manifest & Audit Trail | `DataLoader.get_manifest` | `test_25` |
| REST API Contract Compliance | `main.py` | `test_26` |
| Killer Demo Comparison | Real calculated deltas | `test_27` |
