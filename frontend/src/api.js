/**
 * Cyclone Twin Centralized API Client Layer
 * Handles base URLs, structured requests, timeout aborts, and sanitized error responses.
 */

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

/**
 * Generic JSON fetch wrapper with timeout and standardized error handling.
 */
async function fetchJson(endpoint, options = {}) {
  const { timeout = 10000, headers = {}, ...rest } = options;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);

  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...rest,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      signal: controller.signal,
    });

    clearTimeout(id);

    if (!res.ok) {
      let errorDetail = `HTTP ${res.status}: ${res.statusText}`;
      try {
        const errorData = await res.json();
        if (errorData?.detail) {
          errorDetail = typeof errorData.detail === "string" ? errorData.detail : JSON.stringify(errorData.detail);
        }
      } catch {
        // Fallback to HTTP status text
      }
      throw new Error(errorDetail);
    }

    return await res.json();
  } catch (err) {
    clearTimeout(id);
    if (err.name === "AbortError") {
      throw new Error(`Request to ${endpoint} timed out after ${timeout}ms`);
    }
    throw err;
  }
}

export const api = {
  // 1. Load Road Network
  loadNetwork: () => fetchJson("/network/load", { method: "POST", body: JSON.stringify({}) }),

  // 2. Apply Flood Hazard
  applyFlood: (floodGeoJson = null) =>
    fetchJson("/flood/apply", {
      method: "POST",
      body: JSON.stringify(floodGeoJson ? { flood_geojson: floodGeoJson } : {}),
    }),

  // 3. Accessibility Status
  getAccessibilityStatus: () => fetchJson("/accessibility/status", { method: "GET" }),

  // 4. Criticality Ranking
  rankCorridors: (weights = { w_h: 0.40, w_p: 0.30, w_t: 0.20, w_d: 0.10 }) =>
    fetchJson("/interventions/rank", {
      method: "POST",
      body: JSON.stringify({ weights }),
    }),

  // 5. Simulate Corridor Restoration
  clearCorridor: (corridorId) =>
    fetchJson("/interventions/clear", {
      method: "POST",
      body: JSON.stringify({ corridor_id: corridorId }),
    }),

  // 6. Generate Operational Dispatch Advisory
  generateAdvisory: (corridorId, scoreBreakdown) =>
    fetchJson("/advisory/generate", {
      method: "POST",
      body: JSON.stringify({
        corridor_id: corridorId,
        score_breakdown: scoreBreakdown,
      }),
    }),

  // 7. Full Map Data (GeoJSON layers)
  getMapData: () => fetchJson("/map/data", { method: "GET" }),
};
