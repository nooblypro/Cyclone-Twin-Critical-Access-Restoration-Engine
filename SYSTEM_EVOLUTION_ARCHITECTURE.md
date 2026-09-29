# Cyclone Twin — Strategic Evolution Architecture Report
## From Calibrated Disaster Simulator → Dynamic Urban Resilience Decision Engine

---

## Executive Summary

This architecture report documents the strategic evolution of **Cyclone Twin** from a calibrated disaster restoration simulator into a dynamic, multi-layer urban resilience decision engine. The evolution preserves 100% of the existing deterministic simulation core, REST API contracts, and calibrated scenario outputs while introducing scalable provider abstractions for weather forecasting, flood dynamics, capacity-aware routing, agentic AI orchestration, and participatory citizen GIS.

---

## System Architectural Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ LAYER 4 — PRESENTATION                                                      │
│ Strategic Command Center (GIS Console)  ·  Citizen Lifeline Interface      │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
┌───────────────────────────────────────▼─────────────────────────────────────┐
│ LAYER 3 — PREDICTIVE & AGENTIC INTELLIGENCE                                 │
│ Open-Meteo Weather Ingestion  ·  HAND Flood Model  ·  Observation Pipeline  │
│ AI Agent Tool Registry  ·  Vulnerability Scoring                            │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
┌───────────────────────────────────────▼─────────────────────────────────────┐
│ LAYER 2 — DETERMINISTIC SIMULATION CORE (SOURCE OF TRUTH)                   │
│ Reverse Graph Multi-Source Dijkstra  ·  Counterfactual Corridor Evaluator  │
│ BPR Capacity Routing  ·  Equity-Weighted Multi-Objective Prioritization    │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
┌───────────────────────────────────────▼─────────────────────────────────────┐
│ LAYER 1 — DATA & PROVIDER ABSTRACTIONS                                      │
│ RoadNetworkProvider  ·  WeatherProvider  ·  FloodModel  ·  TravelTimeModel  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Repository Reconnaissance & Migration Plan

### 1. Existing System Assets Preserved
- **Network Multigraph**: 25 nodes, 56 directed edges in EPSG:32643 (UTM 43N).
- **Core Population & Trauma Data**: 10 study wards summing to 477,000 citizens; 6 regional trauma hospitals.
- **Deterministic Metrics**:
  - Baseline Accessible Pop: **477,000**
  - Michaung Flood Accessible Pop: **298,000** (179,000 isolated)
  - Criticality Score: **+0.0724** (Saidapet $\rightarrow$ Adyar corridor)
  - Recovery Accessible Pop: **387,000** (**+89,000** recovered)
- **Deployment & API**: FastAPI backend on Render, React/Vite frontend on Vercel.

### 2. Files Changed & Files Untouched

| File / Component | Status | Role in Evolution |
| :--- | :--- | :--- |
| `cyclone_twin/domain/entities.py` | **NEW** | Domain entities (`WeatherForecast`, `FloodScenario`, `RoadSegment`, `PopulationZone`, `InfrastructureObservation`). |
| `cyclone_twin/providers/` | **NEW** | Provider abstractions (`WeatherProvider`, `FloodModel`, `RoadNetworkProvider`, `TravelTimeModel`, `AgenticToolRegistry`). |
| `tests/test_providers.py` | **NEW** | Provider suite (5 tests covering Open-Meteo, HAND, BPR routing, observation pipeline). |
| `cyclone_twin/main.py` | **EXTENDED** | Added optional extension routes (`/forecast`, `/observations/submit`, `/agent/tools`) without breaking contract. |
| `cyclone_twin/network_engine.py` | **UNTOUCHED** | Core Dijkstra search and accessibility logic intact. |
| `cyclone_twin/ranking_engine.py` | **UNTOUCHED** | Counterfactual corridor evaluation and score breakdown intact. |
| `tests/test_cyclone_twin.py` | **UNTOUCHED** | All 27 core regression tests passing. |

---

## Implemented Phase A Provider Abstractions

1. **WeatherProvider Interface (`cyclone_twin/providers/weather_provider.py`)**:
   - `CalibratedWeatherProvider`: Fallback returning Cyclone Michaung 180mm rainfall event.
   - `OpenMeteoWeatherProvider`: Live REST integration with Open-Meteo API (`https://api.open-meteo.com/v1/forecast`), with automatic fallback on timeout/offline.

2. **FloodModel Interface (`cyclone_twin/providers/flood_model.py`)**:
   - `CalibratedFloodModel`: Returns calibrated Michaung inundation geometry.
   - `HANDFloodModel`: Height Above Nearest Drainage model ($D_{\text{inundation}} = \max(0, W - H_{\text{HAND}})$).

3. **RoadNetworkProvider Interface (`cyclone_twin/providers/network_provider.py`)**:
   - `CalibratedNetworkProvider`: Loads Chennai 25-node arterial graph.
   - `OSMNetworkProvider`: OSMnx integration wrapper with fallback.

4. **TravelTimeModel Interface (`cyclone_twin/providers/travel_time_model.py`)**:
   - `StaticTravelTimeModel`: Free-flow travel time $t_0$.
   - `BPRCapacityTravelTimeModel`: Bureau of Public Roads congestion formula $t_e(v_e) = t_0 [1 + \alpha (v_e / C_e)^\beta]$ with $\alpha=0.15, \beta=4.0$.

5. **Observation Pipeline & Agent Tools (`cyclone_twin/providers/`)**:
   - `ObservationIngestionPipeline`: Normalizes citizen/sensor reports into validated `InfrastructureObservation` objects.
   - `AgenticToolRegistry`: Structured tool interface for LLM orchestrators.

---

## Next Steps in Phased Roadmap

- **Phase B**: Connect HAND flood model outputs directly to dynamic graph edge disabling thresholds.
- **Phase C**: Scale OSMnx ingestion for expanded regional coverage.
- **Phase D**: Enable live toggle for BPR capacity-constrained travel time routing in the UI.
- **Phase E**: Expose equity-weighted scoring in the corridor ranking weights configuration.
