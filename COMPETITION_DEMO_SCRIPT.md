# CYCLONE TWIN — COMPETITION DEMO SCRIPT

**Project:** Cyclone Twin — From Flood Impact to Network Vulnerability  
**Target Duration:** 3 Minutes (Live Standard) | 5 Minutes (Extended Q&A / Technical Deep Dive)  
**Target Audience:** Competition Judges, Municipal Engineers, Disaster Management Authorities  

---

## 3-MINUTE COMPETITION SCRIPT (STANDARD)

### 0:00–0:20 — THE HOOK & CORE PREMISE
*(Speaker stands confidently, points to the live screen in Baseline state)*

> **"Two roads can experience the exact same flood hazard, but their consequences for the city's emergency network can be completely different."**
>
> *(Pause for 2 seconds)*
>
> **"Most flood maps tell emergency managers where water is. Cyclone Twin tells them what happens to the trauma hospital network when critical infrastructure fails. We turn physical flood impact into actionable network vulnerability forecasting."**

---

### 0:20–0:40 — STEP 1: BASELINE EMERGENCY ACCESSIBILITY
*(Action: UI shows Step 1 Active / Baseline Accessibility)*

> **"Here is our calibrated Greater Chennai Corporation emergency network: 25 key arterial junctions, 56 directed segments, 6 tertiary trauma hospitals, and 10 residential ward clusters representing 477,000 citizens.**
>
> **Under normal dry conditions, every community reaches trauma care within our 30-minute critical access threshold. Baseline accessibility is 100%—477,000 citizens connected."**

---

### 0:40–1:05 — STEP 2: HAZARD INUNDATION SCENARIO
*(Action: Click `1. APPLY HAZARD` button $\rightarrow$ Stepper advances to Step 2)*

> **"When Cyclone Michaung hits, we introduce the satellite-derived flood inundation footprint.**
>
> **We do not predict the weather; we ingest the hazard footprint to forecast network consequence. Ten arterial road segments are inundated and severed.**
>
> **Look at the primary metric HUD: accessible population collapses from 477,000 down to 298,000. 179,000 citizens—37.5% of the study population—are now completely isolated from emergency medical access."**

---

### 1:05–1:30 — STEP 3: VULNERABILITY & GRAPH CASCADE
*(Action: Click `2. RANK CRITICALITY` button $\rightarrow$ Stepper advances to Step 3)*

> **"Now the critical question: What happens to the network?**
>
> **Our topological engine performs multi-source reverse Dijkstra across the reversed network graph $G^R$ in under 4 milliseconds. It discovers that floodwaters have severed access to southern and western wards.**
>
> **Spatial clustering groups the 10 severed segments into 3 contiguous intervention corridors."**

---

### 1:30–2:00 — STEP 4: CRITICALITY DIVERGENCE (THE KILLER DEMO)
*(Action: Click `3. COMPARE DIVERGENCE` button $\rightarrow$ Stepper advances to Step 4, highlighting Corridor A vs Corridor B)*

> **"Look at this comparison: Corridor A—Santhome Feeder—and Corridor B—Saidapet Adyar Lifeline.**
>
> **Both roads are flooded. Both are impassable. But their network values are radically divergent.**
>
> **If Chennai deploys pumps to clear Corridor A, exactly ZERO isolated citizens regain hospital access. It is an operational dead-end.**
>
> **If crews clear Corridor B, 89,000 citizens across Saidapet and Jafferkhanpet are reconnected to trauma care. Our multi-criteria formula $S(c) = 0.40\Delta H + 0.30\Delta P + 0.20\Delta T - 0.10\Delta D$ ranks Corridor B as Priority #1 with a score of +0.0724."**

---

### 2:00–2:25 — STEP 5: MITIGATION STRATEGY & TACTICAL DIRECTIVE
*(Action: Click `4. MITIGATION STRATEGY` button $\rightarrow$ Stepper advances to Step 5)*

> **"The engine identifies Corridor B as the highest-consequence intervention. It provides a field dispatch directive: deploy high-capacity dewatering pumps across 14.2 km of arterial corridor to restore primary east-west emergency connectivity."**

---

### 2:25–2:45 — STEP 6: SIMULATED RECOVERY & POPULATION RECONNECTION
*(Action: Click `5. SIMULATE RECOVERY` button $\rightarrow$ Stepper advances to Step 6)*

> **"We simulate clearing Corridor B.**
>
> **Instantly, the graph updates: the corridor lights up green. Accessible population climbs from 298,000 to 387,000. Exactly 89,000 citizens are restored to the emergency trauma network, and isolation drops from 37.5% to 18.9%."**

---

### 2:45–3:00 — AI EXPLANATION & CLOSING
*(Action: Point to Sidebar Section E / AI Advisory badge)*

> **"Finally, Google Gemini is used solely as an explanatory advisory layer to convert these deterministic calculations into clear, auditable operational briefs for incident commanders. The math decides; the AI explains.**
>
> **Cyclone Twin transforms disaster management from mapping where water is to understanding which infrastructure saves the most lives."**
>
> *(Stop speaking. Await judge questions.)*

---

## 5-MINUTE EXTENDED DEMO SCRIPT (FOR TECHNICAL DEEP DIVES)

### 0:00–0:30 — Problem Framing & Scientific Gap
- Detail why existing GIS maps produce decision paralysis during urban floods.
- Explain the gap between hydrodynamic flood models (depth/velocity) and transportation network accessibility.
- State the research question: *How can municipal emergency operations prioritize clearance when resources are strictly constrained?*

### 0:30–1:15 — System Architecture & Data Provenance
- Open the **MODEL CARD / PROVENANCE** modal.
- Explain EPSG:32643 UTM projection, arterial multigraph representation (NetworkX `MultiDiGraph`), 6 tertiary facilities (RGGGH, Apollo, KMC, Malar, MIOT, Gleneagles), and 10 GCC ward clusters (477,000 census population).
- Highlight bridge and elevated flyover preservation invariants: bridges spanning flood zones remain passable.

### 1:15–2:15 — Inundation & Multi-Source Reverse Dijkstra
- Trigger Hazard Inundation and explain reverse graph multi-source Dijkstra ($G^R$):
  - Why reverse Dijkstra? Propagating shortest paths backward from all 6 hospitals simultaneously computes the exact nearest-hospital travel time for all 10 wards in $O((V + E) \log V)$ time instead of running $|W|$ independent Dijkstra passes.
  - Explain the 30-minute (1,800s) critical access threshold.

### 2:15–3:30 — Criticality Formulation & Divergence Breakdown
- Walk through the exact mathematical components of $S(c) = w_h \Delta H + w_p \Delta P + w_t \Delta T - w_d \Delta D$:
  - $\Delta H$: Hospital accessibility delta (normalized).
  - $\Delta P$: Population recovery delta ($89,000 / 179,000 = +0.4972$).
  - $\Delta T$: Travel time improvement delta.
  - $\Delta D$: Clearance difficulty / length penalty.
- Demonstrate why Santhome Feeder yields a negative score ($-0.0497$) due to length penalty with zero population recovery.

### 3:30–4:30 — Simulation, State Consistency & Verification
- Execute Corridor B clearance.
- Show mathematical conservation: Baseline ($477\text{k} + 0\text{k}$) $\rightarrow$ Flood ($298\text{k} + 179\text{k}$) $\rightarrow$ Restoration ($387\text{k} + 90\text{k}$).
- Highlight test coverage: 27/27 automated pytest cases covering parallel edges, disconnected nodes, weights normalization, and deterministic tie-breaking.

### 4:30–5:00 — Operational Deployment & Honest Limitations
- Detail the three core operational boundaries:
  1. Calibrated arterial network rather than full local street network.
  2. Supplied inundation footprint rather than real-time 2D hydrodynamic simulation.
  3. Static ward census population rather than live cellular mobility.
- Conclude on how this modular decision-support tool plugs into municipal GCC disaster workflows.
