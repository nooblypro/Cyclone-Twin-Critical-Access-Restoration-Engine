# Cyclone Twin — Phase C OSMnx Dynamic Road Network Ingestion Report

---

## 1. Executive Summary
Phase C introduces dynamic road network ingestion using OSMnx (`OSMNetworkProvider`), graph quality validation, spatial coordinate-to-node mapping (`map_entity_to_nearest_node`), and normalized graph attribute translation while maintaining 100% backward compatibility with the calibrated 25-node Chennai baseline multigraph.

---

## 2. Architecture & Ingestion Flow

```
OSM Overpass API (drive network) / Bounded BBox Query
        ↓
OSMNetworkProvider (In-Process Bounded Memory Cache)
        ↓
normalize_osm_graph (Attribute Translation & Directed Topology Validation)
        ↓
Normalized MultiDiGraph (x, y, length, speed_kph, travel_time, bridge, tunnel)
        ↓
Deterministic NetworkEngine & Accessibility Engine
```

---

## 3. Provider Specifications & Normalization Rules

### A. Geographic Bounding Scope
- **Default Bounding Box (`DEFAULT_OSM_BBOX`)**: `(80.15, 12.89, 80.29, 13.09)` in unprojected EPSG:4326 degrees `(left, bottom, right, top)`.
- **Network Type**: `"drive"` (drivable vehicular road network).

### B. Graph Normalization Rules (`normalize_osm_graph`)
- **Node Normalization**: Node IDs converted to string keys; `lon`, `lat`, `x`, `y` preserved; NaN coordinate detection triggers graph rejection.
- **Edge Metadata**:
  - `length`: Float in meters ($>0.0$).
  - `speed_kph`: Derived from `maxspeed` OSM attribute or highway classification defaults (motorway: 60 km/h, primary: 50 km/h, secondary: 40 km/h, tertiary: 35 km/h, unclassified: 30 km/h).
  - `travel_time`: Static free-flow travel time $t_0 = \frac{\text{length}}{\text{speed\_kph} \cdot \frac{1000}{3600}}$.
  - `bridge` & `tunnel`: Boolean/string flag preservation (`"yes"` or `"no"`) to ensure compatibility with flood inundation logic (`identify_flood_disabled_segments`).
  - `physical_segment_id`: Derived from OSM way ID or edge tuple string.

### C. Spatial Entity Mapping (`map_entity_to_nearest_node`)
- Maps real-world coordinates `(lat, lon)` of emergency hospitals and community centroids to the nearest valid graph node ID using Haversine/Euclidean distance calculations while keeping source coordinates intact.

### D. Provider Fallback Resilience
- In-process memory cache prevents repeated Overpass downloads.
- Overpass timeouts (4.0s max timeout), DNS errors, or invalid OSM graph data trigger an automatic, safe fallback to `CalibratedNetworkProvider`.

---

## 4. API Endpoints

### `GET /network/source`
Returns diagnostic details on the active network provider.

```json
{
  "provider": "mock_fallback",
  "nodes": 25,
  "edges": 56,
  "bbox": [80.15, 12.89, 80.29, 13.09],
  "fallback_used": true,
  "network_type": "drive"
}
```

---

## 5. Verification & Test Suite Summary

All **47 backend unit and integration tests** passed cleanly (`./.venv/bin/pytest`).

### Baseline Regression Preserved
- **Baseline Accessible Population**: **477,000** (0 isolated)
- **Michaung Flood Accessible Population**: **298,000** (179,000 isolated across 4 wards)
- **Criticality Score**: **+0.0724** (*Saidapet $\rightarrow$ Adyar Lifeline*)
- **Recovery Accessible Population**: **387,000** (**+89,000** recovered)

### Phase C Test Coverage (`tests/test_phase_c_osm_network.py`)
- `test_osm_provider_construction`: Bounded query configuration.
- `test_synthetic_graph_normalization`: Attribute translation (length, speed, travel_time, bridge, tunnel).
- `test_directionality_preservation`: One-way directed edge topology preservation.
- `test_missing_attributes_handled_with_defaults`: Missing maxspeed/lanes default handling.
- `test_invalid_graph_triggers_rejection`: Empty and NaN-coordinate graph validation.
- `test_osm_provider_fallback_behavior`: Overpass failure fallback to `CalibratedNetworkProvider`.
- `test_coordinate_to_nearest_node_mapping`: Spatial entity mapping.
- `test_flood_compatibility_with_normalized_graph`: Bridge preservation and tunnel disruption under flood.
- `test_network_source_diagnostic_api`: `GET /network/source` response verification.

---

## 6. Truthfulness & Limitations
- **Geographic Bounds**: Default queries are restricted to the 14km $\times$ 22km Chennai study bounding box.
- **Provider Fallback**: Overpass live API queries apply a 4.0s timeout and fall back to the calibrated 25-node multigraph if Overpass is busy or offline.
- **Free-Flow Speeds**: Speeds are model assumptions derived from OSM `maxspeed` or highway classifications, not live real-time GPS probe feeds.
