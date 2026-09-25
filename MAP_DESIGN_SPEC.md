# CYCLONE TWIN — SPATIAL MAP DESIGN SPECIFICATION
**Standard:** Modern High-Legibility Emergency Operations Cartography  
**Version:** 1.0 (Phase 10 Production Spec)  
**Target:** Cyclone Twin Geospatial Decision-Support Prototype

---

## 1. Executive Summary & Design Vision
Cyclone Twin bridges heavy graph-theoretic infrastructure analysis with the intuitive, frictionless spatial clarity of modern digital mapping (e.g., Google Maps / Apple Maps).

In high-stress emergency operations and hackathon judge demonstrations, spatial cognitive load must be minimized. The map is **the primary workspace**, not a background graphic. The user must immediately recognize:
1. Urban geography (streets, rivers, water bodies, landmarks).
2. The physical hazard extent (satellite-calibrated inundation footprint).
3. The functional status of critical access corridors (normal, severed, elevated, prioritized, restored).
4. Facility operating status (emergency hospitals, power grid health, isolated population zones).

---

## 2. Basemap Foundation
- **Provider / Tile Source:** CartoDB Voyager (`https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png`)
- **Cartographic Characteristics:**
  - **Landmass Tone:** Soft neutral light gray (`#f4f5f7` / `#e9ecef`) to prevent dark-mode color muddiness.
  - **Water Bodies:** Clean, distinct light blue (`#cde2f2`) representing the Adyar River, Cooum River, Buckingham Canal, and Bay of Bengal.
  - **Base Road Network & Labels:** Crisp, high-legibility typography and subtle road arteries providing immediate real-world spatial orientation across Chennai metropolitan zones (Saidapet, Velachery, Guindy, T. Nagar, Anna Nagar).
  - **Attribution & Max Zoom:** OpenStreetMap contributors, CARTO; max zoom level `19`.

---

## 3. Road Hierarchy & Emergency Layer Styling

The vector overlay layers are styled with explicit visual hierarchy to immediately communicate network topology without visual clutter:

| Layer Category | Color Token | Hex Code | Weight | Dash Pattern | Opacity | Operational Meaning |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Normal / Active Road** | Slate Gray | `#64748b` | `3.5px` | Solid | `0.75` | Operable arterial road under current conditions. |
| **Flood Severed Edge** | Hazard Red | `#ef4444` | `4.5px` | `8, 6` (Dashed) | `0.90` | Inundated road segment with zero functional vehicular throughput. |
| **Elevated Infrastructure** | Golden Amber | `#f59e0b` | `4.5px` | Solid | `0.95` | Grade-separated flyover / bridge preserved above flood level. |
| **Selected Corridor** | Critical Cyan | `#0284c7` | `7.0px` | Solid (Glow) | `1.00` | Focused candidate corridor evaluated for intervention. |
| **Restored Lifeline** | Emergency Green | `#10b981` | `5.5px` | Solid | `1.00` | Prioritized corridor cleared in simulation, reconnecting isolated zones. |
| **Flood Inundation Polygon** | Translucent Marine | `#3b82f6` | `1.5px` border | Solid border | Fill: `0.22`, Stroke: `0.70` | Modeled surface water extent (ISRO/NRSC calibrated footprint). |

---

## 4. Facility Markers & Population Pins

### 4.1 Hospitals & Emergency Medical Centers
- **Badge Shape:** Modern rounded squircle (`30px × 30px`) with high-elevation drop shadow (`0 4px 12px rgba(0,0,0,0.18)`).
- **Iconography:** High-contrast white emergency cross on operational blue/red background.
- **Power Grid Indicator:** 
  - *Grid Active:* Emerald border dot (`#10b981`).
  - *Generator Backup / Outage:* Pulsing amber warning dot (`#f59e0b`).
- **Interactive Tooltip:** Displays facility name, bed count, primary trauma capability, and live accessibility status.

### 4.2 Population Centroids & Communities
- **Badge Shape:** Circular node with population scaling.
- **Color Coding:**
  - *Accessible ($< 15\text{ min}$):* Slate Emerald (`#059669`).
  - *Delay / Extended Detour ($15 - 45\text{ min}$):* Caution Amber (`#d97706`).
  - *Completely Severed ($> 45\text{ min}$ / $\infty$):* Critical Carmine (`#dc2626`).
- **Data Payload:** Popover details resident count, nearest active hospital, shortest-path travel time, and bottleneck road segment.

---

## 5. Floating Overlays & HUD Architecture

To maintain a true **Map-First UI**, all operational statistics and controls float seamlessly above the viewport using glassmorphic card tokens:

```
+-------------------------------------------------------------------------------+
|  [ Cyclone Twin Operations Console ]   [ Metric HUD: Accessible / Isolated ]  |
|                                                                               |
|  [ Map Canvas - CartoDB Voyager ]                    [ Floating Controls ]   |
|                                                      |  (+) Zoom In       |   |
|                                                      |  (-) Zoom Out      |   |
|                                                      |  (O) Recenter      |   |
|                                                                               |
|  [ Floating Map Legend ]                                                      |
|  * Severed  * Bridge  * Restored  * Inundation                                |
+-------------------------------------------------------------------------------+
```

1. **Floating Metric HUD (Top-Left / Top-Center):**
   - Translucent frosted glass (`rgba(255, 255, 255, 0.92)` with `backdrop-filter: blur(12px)`).
   - Instant delta display showing total modeled population ($477\text{k}$), accessible count, isolated percentage, and active disruption state.
2. **Floating Navigation Control Pill (Top-Right):**
   - Sleek vertical pill with `+` (Zoom In), `-` (Zoom Out), and `Compass` (Recenter to Chennai Metropolitan Bounds).
   - High-contrast tactile hover states with micro-transitions.
3. **Floating Cartography Legend (Bottom-Left):**
   - Compact visual key explaining road layer symbols, line dashes, and polygon colors without obscuring active corridors.

---

## 6. Dynamic Camera Transitions & Bounds

- **Initial State View:** Bounded to Chennai South / Central Metropolitan Corridor (`[12.96, 80.18]` to `[13.06, 80.28]`).
- **Corridor Selection Focus (`flyTo`):**
  - Smooth animation targeting corridor centroid with zoom `14.5`.
  - Duration: **800ms** (fast enough for snappy hackathon demos, smooth enough to preserve spatial orientation).
  - Bounds padding: Minimum `40px` margin to ensure vector geometry is never occluded by floating sidebars.
- **Reset to Global Overview (`flyToBounds`):**
  - Smooth return to complete scenario bounding box.
  - Duration: **600ms** easing.

---

## 7. Accessibility, Contrast & Performance Standards
- **Contrast Ratios:** All text, badges, and vector outlines maintain a minimum of **4.5:1** contrast ratio against the light neutral basemap, complying with **WCAG 2.2 AA**.
- **Rendering Performance:** 60 FPS continuous panning via hardware-accelerated SVG/Canvas rendering in Leaflet. Zero DOM layer leaks on step transitions.
