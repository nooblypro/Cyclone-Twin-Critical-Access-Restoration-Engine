# Cyclone Twin — Phase D: Capacity-Aware Travel Time & Congestion Report

## 1. What Changed
- Implemented **Bureau of Public Roads (BPR)** capacity-aware travel-time model (`BPRCapacityTravelTimeModel`) extending the existing `TravelTimeModel` abstraction.
- Preserved `StaticTravelTimeModel` ($t_0$) as the default travel-time model with zero regression to baseline metrics.
- Centralized BPR parameters $\alpha = 0.15$ and $\beta = 4.0$ with strict non-negative validation and custom configuration support.
- Built a capacity derivation hierarchy (`derive_capacity`) supporting explicit capacity attributes, highway classification fallback (motorway: 4,000, primary: 2,500, secondary: 1,800, tertiary: 1,400, default: 2,000 veh/hr), and central default values.
- Built a deterministic volume/demand abstraction allowing edge volume $v_e$ input without hardcoding.
- Integrated BPR model selection into `NetworkEngine` and `POST /scenario/dynamic` API endpoint (`travel_time_model="static"|"bpr"`), maintaining `"static"` as default.
- Ensured flooded edges remain 100% unavailable and non-routable regardless of BPR congestion penalties.
- Created `tests/test_phase_d_capacity_travel_time.py` covering 14 mandatory tests including monotonicity, $v=0$, $v=C$, $v>C$, flood safety, synthetic routing, and baseline regression.

---

## 2. Architecture

```
                    Road Network (MultiDiGraph)
                                │
             ┌──────────────────┴──────────────────┐
             ▼                                     ▼
    StaticTravelTimeModel               BPRCapacityTravelTimeModel
             │                                     │
             └──────────────────┬──────────────────┘
                                ▼
                         NetworkEngine
                                │
                          accessibility
                                │
                       intervention logic
```

`NetworkEngine` depends solely on the `TravelTimeModel` abstraction. Standard Dijkstra routing algorithms consume dynamic edge weights via `_active_weight()`, eliminating code duplication while upholding flood closures.

---

## 3. BPR Formula & Parameters

The volume-delay relationship is computed as:
$$t_e(v_e) = t_0 \left[1 + \alpha \left(\frac{v_e}{C_e}\right)^\beta\right]$$

### Centralized Parameters:
- $\alpha = 0.15$ (congestion weight factor)
- $\beta = 4.0$ (congestion exponential sensitivity)
- Non-negative validation enforced (`alpha >= 0.0`, `beta >= 0.0`).

---

## 4. Capacity Source Hierarchy

1. **Source-Derived Capacity**: Explicit `capacity` attribute on `RoadSegment` / edge data (if $>0$).
2. **Classification-Derived Capacity**:
   - `motorway` / `trunk`: 4,000 veh/hr
   - `primary`: 2,500 veh/hr
   - `secondary`: 1,800 veh/hr
   - `tertiary`: 1,400 veh/hr
3. **Model-Assumed Default**: 2,000 veh/hr for unclassified / missing highway types.

---

## 5. Volume / Demand Model

- Edge volume $v_e$ is supplied via edge attribute `current_volume` or `volume`.
- If unprovided, $v_e$ defaults deterministically to `0.0` (free-flow $t_0$).
- Supports deterministic scenario demand without pseudo-randomness or system-time dependencies.

---

## 6. Static vs. BPR Behavior

| Scenario | Static Mode ($t_0$) | BPR Mode ($t_e$) | Ratio ($t_e / t_0$) |
| :--- | :--- | :--- | :--- |
| Free-Flow ($v = 0$) | $t_0$ | $t_0$ | $1.00\times$ |
| At Capacity ($v = C$) | $t_0$ | $1.15 \cdot t_0$ | $1.15\times$ |
| Over Capacity ($v = 2C$) | $t_0$ | $3.40 \cdot t_0$ | $3.40\times$ |
| Severe Overload ($v = 3C$) | $t_0$ | $13.15 \cdot t_0$ | $13.15\times$ |

---

## 7. Flood Interaction

- `NetworkEngine._active_weight()` checks `seg_id in self.disabled_segments` **before** computing travel times.
- Flooded edges return `None` (weight = $\infty$).
- Congestion penalties cannot bypass or override physical flood blockages.

---

## 8. Mathematical Verification & Monotonicity

- **Property 1 ($v=0 \implies t=t_0$)**: Verified ($t_e(0) = t_0$).
- **Property 2 ($v=C \implies t=1.15t_0$)**: Verified ($t_e(C) = 1.15t_0$).
- **Property 3 ($v>C \implies t > 1.15t_0$)**: Verified.
- **Property 4 (Monotonicity)**: For fixed $t_0, C, \alpha, \beta$: $v_1 < v_2 \implies t_e(v_1) \le t_e(v_2)$. Verified across range $[0, 5000]$ veh/hr.

---

## 9. Simulation & Benchmark Regression Results

All pre-existing Phase A, B, and C metrics remain preserved:

- **Baseline Accessible Population**: 477,000 (0 isolated facilities, 0 isolated communities)
- **Michaung Flood Disruption**: 298,000 accessible / 179,000 isolated
- **Top Corridor Criticality (Delta P)**: 89,000 / 179,000 = 0.4972
- **Restoration Population Recovery**: +89,000 recovered

---

## 10. Execution Test Results

- **Backend Pytest**: 61/61 tests passing (14 new Phase D tests + 47 existing tests).
- **Frontend Oxlint**: 0 warnings, 0 errors.
- **Frontend Build**: Passed (`vite build` completed in 243ms).

---

## 11. Model Assumptions & Limitations

- **Model Assumption**: Edge capacities and traffic volumes are modeled deterministically using standard BPR parameters ($\alpha=0.15, \beta=4.0$) and highway hierarchy fallbacks where observed counts are absent.
- **Data Positioning**: Output is explicitly framed as **"capacity-aware modeled travel time"**, not observed or GPS-derived real-time traffic.

---

## 12. Recommended Phase E

- Multi-objective equity scoring incorporating social vulnerability indices across Greater Chennai Corporation wards.
