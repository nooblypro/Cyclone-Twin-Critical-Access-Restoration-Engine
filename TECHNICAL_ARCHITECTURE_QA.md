# CYCLONE TWIN — TECHNICAL ARCHITECTURE & SYSTEMS Q&A

This guide prepares the team to explain Cyclone Twin at three distinct levels of technical depth depending on the judge's background.

---

## LEVEL 1: NON-TECHNICAL / STRATEGIC JUDGE
*Target: City Administrators, Policy Evaluators, Venture/Social Impact Judges.*

- **What does Cyclone Twin do?**  
  It acts as a digital twin of Chennai's emergency road network during a cyclone. When floodwaters submerge roads, it calculates which neighborhoods are cut off from trauma hospitals and tells emergency teams which blocked road to clear first to save the most lives.
- **Why is it better than a flood map?**  
  A flood map shows water. Cyclone Twin shows people and hospitals. It proves that clearing a short road might help nobody if it leads to a dead-end, while clearing a critical arterial reconnects 89,000 citizens to emergency doctors.
- **Where does AI fit in?**  
  The mathematical brain calculates the numbers with 100% precision. The AI acts like an intelligent assistant that turns those numbers into clear, written briefing notes for emergency commanders.

---

## LEVEL 2: ENGINEERING / FULL-STACK JUDGE
*Target: Software Architects, System Designers, Data Engineers.*

- **Backend Architecture:**  
  Built with **FastAPI** in Python 3.13. It maintains a clean, in-memory **NetworkX MultiDiGraph** representing directed arterial road segments. State transitions (`load` $\rightarrow$ `flood` $\rightarrow$ `rank` $\rightarrow$ `clear` $\rightarrow$ `advisory`) are stateless, idempotent HTTP endpoints strictly validated with **Pydantic v2** models.
- **Graph & Algorithm Engine:**  
  Uses **Multi-Source Dijkstra on the Reversed Graph ($G^R$)**. Instead of computing shortest paths from each ward to all hospitals ($O(|W| \cdot (V + E) \log V)$), it runs a single reverse pass from all active trauma facilities simultaneously ($O((V + E) \log V)$), achieving sub-4ms computation latency.
- **Frontend Architecture:**  
  Built with **React 19 + Vite + Leaflet**. Features a centralized, timeout-protected API layer ([`frontend/src/api.js`](file:///Users/shriram/Documents/Projects/Cyclone-Twin-Critical-Access-Restoration-Engine/frontend/src/api.js)), strict typography and design tokens in vanilla CSS, and tabular figures preventing layout shift during state changes.
- **AI Isolation & Deterministic Fallback:**  
  The **Gemini 2.5 Flash** client receives only computed summary statistics. If the external LLM API times out or fails, an automated regex-safe fallback template generates the exact operational directive with zero user disruption.

---

## LEVEL 3: EXPERT / GEOSPATIAL SYSTEMS JUDGE
*Target: GIS Researchers, Transport Modellers, Operations Research Specialists.*

- **Spatial Representation & Coordinate Systems:**  
  Road vectors and polygon geometries are projected into **EPSG:32643 (UTM Zone 43N)** for accurate metric calculations (lengths in meters, speeds in km/h converted to m/s). Snapping facilities and ward centroids to graph nodes enforces a 200m spatial proximity constraint.
- **Topological Invariants & Bridge Rules:**  
  Flood intersection uses Shapely `intersects()` after `make_valid()` normalization. Infrastructure segments tagged with `bridge="yes"` or `layer > 0` are preserved across flood polygons, ensuring elevated viaducts and flyovers remain passable during surface flooding.
- **Connected Component Corridor Clustering:**  
  Disabled directed edges are grouped into undirected spatial clusters using NetworkX `connected_components` on the disabled subgraph $G[\text{disabled}]$, yielding distinct physical intervention corridors $C = \{c_1, c_2, \dots, c_k\}$.
- **Multi-Attribute Criticality Metric Formulation:**  
  $$S(c) = w_h \Delta H(c) + w_p \Delta P(c) + w_t \Delta T(c) - w_d \Delta D(c)$$
  - $\Delta H(c) = \frac{H_{\text{restored}}(c)}{H_{\text{isolated}}}$ (Fraction of isolated hospitals recovered)
  - $\Delta P(c) = \frac{P_{\text{restored}}(c)}{P_{\text{isolated}}}$ (Fraction of isolated population reconnected)
  - $\Delta T(c) = \frac{\sum_{i \in W} (T_{\text{flood}}(i) - T_{\text{restored}}(i))}{\sum_{i \in W} (T_{\text{flood}}(i) - T_{\text{base}}(i))}$ (Normalized transit time improvement)
  - $\Delta D(c) = \frac{\text{Length}(c)}{\sum_{j} \text{Length}(c_j)}$ (Normalized clearance cost / length penalty)
  - Bound: $S(c) \in [-1.0, +1.0]$, strictly descending order with deterministic tie-breaking.
- **Verification & Test Rigor:**  
  27 automated pytest suites, 8-step preflight verification harness, `oxlint` with 0 warnings, and sub-second full test execution.
