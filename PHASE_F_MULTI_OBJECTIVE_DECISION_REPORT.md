# Cyclone Twin — Phase F: Multi-Objective Intervention Decision Engine Report

## 1. What Changed
- Implemented **Deterministic Multi-Objective Intervention Decision Engine** (`MultiObjectiveDecisionEngine` in `cyclone_twin/decision_engine.py`) for counterfactual evaluation and ranking of disaster restoration proposals.
- Built counterfactual decision loop evaluating intervention candidates across 5 core objectives:
  - **$\Delta H$**: Hospital accessibility recovery ratio ($[0.0, 1.0]$)
  - **$\Delta P$**: Population accessibility recovery ratio ($[0.0, 1.0]$)
  - **$\Delta T$**: Population-weighted travel time reduction ratio ($[0.0, 1.0]$)
  - **$\Delta E$**: Social equity / vulnerability-weighted population recovery ratio ($[0.0, 1.0]$)
  - **$\Delta D$**: Cost / difficulty / length penalty ratio ($[0.0, 1.0]$)
- Extended domain candidate model (`InterventionCandidate`) to support diverse intervention types: `CORRIDOR_CLEARANCE`, `PUMP_DEPLOYMENT`, `POWER_RESTORATION`, `EMBANKMENT_STABILIZATION`, and `BRIDGE_PRIORITIZATION`.
- Enhanced `Community` model in `cyclone_twin/models.py` with `vulnerability_index` field ($[0.1, 5.0]$) to support equity-weighted recovery scoring ($\Delta E$).
- Built Pareto-optimality identification (`identify_pareto_front`) detecting non-dominated candidate proposals across multi-objective vectors $(\Delta H, \Delta P, \Delta T, \Delta E, 1 - \Delta D)$.
- Enforced **100% atomic state isolation** during counterfactual evaluation: candidate segment restorations and health facility power modifications are evaluated within a `try ... finally` block, guaranteeing clean rollback regardless of errors.
- Added API endpoint `POST /decision/evaluate` for submitting multi-objective weight configurations and candidate proposals, returning ranked interventions with full score breakdowns and Pareto flags.
- Created `tests/test_phase_f_decision_engine.py` covering 13 comprehensive tests including Pareto dominance, equity weighting, state rollback, and tiebreaker logic.

---

## 2. Architecture & Decision Flow

```
                           CURRENT DISASTER STATE
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
         Corridor Clearance / Pump          Hospital Power / Embankment
             Segment Candidate                  Facility Candidate
                     │                               │
                     └───────────────┬───────────────┘
                                     ▼
                    Counterfactual State Mutation
                (Restore Segments / Power Facility)
                                     │
                                     ▼
                      Recompute Accessibility (Dijkstra)
                                     │
                                     ▼
                   Multi-Objective Metrics Calculation
                 (ΔH, ΔP, ΔT, ΔE, ΔD & Multi-Obj Score)
                                     │
                                     ▼
                      Atomic State Isolation Rollback
                    (Re-disable Segments / Unpower Fac)
                                     │
                                     ▼
                        Pareto Front Identification &
                         Deterministic Ranking (DESC)
```

---

## 3. Multi-Objective Scoring Formula

$$S(c) = w_h \cdot \Delta H + w_p \cdot \Delta P + w_t \cdot \Delta T + w_e \cdot \Delta E - w_d \cdot \Delta D$$

Where weights satisfy $w_h, w_p, w_t, w_e, w_d \ge 0$ and $\sum w_i = 1.0$.

### Presets:
- `life_safety()`: $w_h=0.35, w_p=0.25, w_t=0.15, w_e=0.15, w_d=0.10$
- `equity_priority()`: $w_h=0.25, w_p=0.20, w_t=0.15, w_e=0.30, w_d=0.10$
- `rapid_clearance()`: $w_h=0.20, w_p=0.20, w_t=0.15, w_e=0.15, w_d=0.30$

---

## 4. Equity-Weighted Recovery Metric ($\Delta E$)

$$\Delta E = \frac{\sum_{c \in \text{Recovered}} \text{population}_c \cdot \text{vulnerability}_c}{\sum_{c \in \text{Isolated}} \text{population}_c \cdot \text{vulnerability}_c}$$

Prioritizes restoration corridors that reconnect high-vulnerability, low-lying wards (e.g. Velachery, Saidapet, Jafferkhanpet).

---

## 5. Simulation & Benchmark Regression Results

All baseline simulation metrics remain strictly preserved:

- **Baseline Accessible Population**: 477,000 (0 isolated)
- **Michaung Flood Disruption**: 298,000 accessible / 179,000 isolated
- **Top Corridor Population Contribution ($\Delta P$)**: $89,000 / 179,000 = 0.4972$
- **Corridor Restoration Recovery**: 387,000 accessible / 90,000 isolated (+89,000 recovered)

---

## 6. Test Execution Summary

- **Backend Tests**: 95/95 passing (13 new Phase F tests + 82 existing tests).
- **Frontend Oxlint**: 0 warnings, 0 errors.
- **Frontend Build**: Passed (`vite build` in 239ms).

---

## 7. Performance Measurements

- **Counterfactual Evaluation Time**: $0.85\text{ ms}$ per candidate proposal.
- **Full Pareto Front Ranking Time**: $4.2\text{ ms}$ for 10 candidate proposals across Chennai road multigraph.

---

## 8. Model Assumptions & Positioning

- **Positioning**: "Deterministic multi-objective decision engine evaluating counterfactual infrastructure interventions across health, population, travel time, social equity, and difficulty metrics."
- **Truthfulness**: Evaluates candidates deterministically using exact network Dijkstra state search; does not rely on non-deterministic LLMs or black-box predictive models.

---

## 9. Recommended Phase G

- Downstream LLM advisory engine integration and agentic tool dispatch.
