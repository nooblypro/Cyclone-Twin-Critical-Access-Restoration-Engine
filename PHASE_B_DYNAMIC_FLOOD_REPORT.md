# Cyclone Twin — Phase B Dynamic Flood Scenario Engine Report

---

## 1. Executive Summary & Deliverables Overview
Phase B connects weather inputs to dynamic flood modeling, physical network disruption, shortest-path accessibility calculation, and population isolation impact while preserving 100% backward compatibility with the calibrated Cyclone Michaung baseline scenario.

---

## 2. Architecture & Data Flow

```
Weather Input (Open-Meteo REST / Calibrated Fallback)
        ↓
HAND Flood Model (Height Above Nearest Drainage Abstraction)
        ↓
FloodScenario (Inundation Depth + Geometry Bounds)
        ↓
Network Disruption Engine (identify_flood_disabled_segments)
        ↓
Reverse Graph Multi-Source Dijkstra (compute_accessibility)
        ↓
Accessibility & Population Isolation Impact
```

---

## 3. Provider & Model Specifications

### A. Weather Ingestion Contract
- **CalibratedWeatherProvider**: Deterministic fallback supplying the 180mm Cyclone Michaung peak rainfall event.
- **OpenMeteoWeatherProvider**: Connects to Open-Meteo REST API (`https://api.open-meteo.com/v1/forecast`), applying a 4.0s timeout and graceful fallback to `CalibratedWeatherProvider` on network failure, timeout, or invalid response.

### B. HAND Flood Model
- **HAND Formula**: $D_{\text{inundation}} = \max(0, W - H_{\text{HAND}})$.
- **Dynamic Inundation Pockets**:
  - Low Rainfall (<40mm): Santhome peripheral coastal pocket only (0 isolated wards).
  - Moderate Rainfall (40–120mm): Velachery basin + Santhome pocket.
  - Heavy Rainfall ($\ge$120mm, e.g. 180mm Michaung event): All 3 major inundation pockets (Saidapet, Velachery, Santhome).

---

## 4. API Endpoints

### `POST /scenario/dynamic`
Dynamic end-to-end weather $\rightarrow$ flood $\rightarrow$ disruption pipeline.

#### Request Schema:
```json
{
  "precipitation_mm": 180.0,
  "use_live_weather": false,
  "hand_threshold_m": 0.30
}
```

#### Response Schema & Provenance Metadata:
```json
{
  "scenario_id": "hand_model_precip_180mm",
  "precipitation_mm": 180.0,
  "water_level_m": 1.44,
  "disabled_edges_count": 14,
  "corridors_count": 3,
  "accessibility": {
    "accessible_population": 298000,
    "isolated_facilities": [],
    "isolated_communities": ["COMM_JAFFERKHANPET", "COMM_MADIPAKKAM", "COMM_SAIDAPET", "COMM_VELACHERY"]
  },
  "provenance": {
    "weather_source": "manual_dynamic_scenario",
    "flood_model": "hand_model",
    "network_source": "mock_fallback",
    "hand_threshold_m": 0.3,
    "fallback_used": false,
    "scenario_type": "dynamic_phase_b"
  }
}
```

---

## 5. Verification Matrix & Test Summary

All **38 backend unit and integration tests** passed cleanly (`./.venv/bin/pytest`).

### Baseline Regression Preserved
- **Baseline Accessible Population**: **477,000** (0 isolated)
- **Michaung Flood Accessible Population**: **298,000** (179,000 isolated across 4 wards)
- **Criticality Score**: **+0.0724** (*Saidapet $\rightarrow$ Adyar Lifeline*)
- **Recovery Accessible Population**: **387,000** (**+89,000** recovered)

### Dynamic Scenario Results

| Scenario | Rainfall (mm) | Accessible Pop | Isolated Pop | Wards Isolated | Scenario Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Scenario A (Low)** | 20.0 mm | **477,000** | 0 | 0 | Minor coastal surge |
| **Scenario B (Michaung)** | 180.0 mm | **298,000** | 179,000 | 4 | Calibrated Michaung flood |
| **Scenario C (Extreme)** | 250.0 mm | **298,000** | 179,000 | 4 | Full arterial disruption |

---

## 6. Truthfulness & Known Limitations
- **Model Calibration**: The rainfall-to-inundation scaling represents a calibrated engineering model assumption, not a hydrodynamic finite-element physics solver.
- **Elevation Data**: HAND inundation bounds are derived from elevation-calibrated hydrographic pockets across GCC wards.
- **Provider Fallback**: Open-Meteo REST calls are bounded by a 4.0s timeout and fall back to deterministic calibrated values if offline.
