/**
 * Cyclone Twin Centralized API Client Layer
 * Handles base URLs, structured requests, timeout aborts, and sanitized error responses.
 */

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_BASE ||
  "http://localhost:8000";

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
  getAccessibilityStatus: () => fetchJson("/accessibility/status", { method: "GET", timeout: 25000 }),

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
  getMapData: () => fetchJson("/map/data", { method: "GET", timeout: 25000 }),

  // 8. Multimodal Evidence Extraction (Read-Only)
  extractEvidence: async (formDataOrJson) => {
    if (formDataOrJson instanceof FormData) {
      const res = await fetch(`${API_BASE}/observations/multimodal/extract`, {
        method: "POST",
        body: formDataOrJson,
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }
      return await res.json();
    }
    return fetchJson("/observations/multimodal/extract", {
      method: "POST",
      body: JSON.stringify(formDataOrJson),
    });
  },

  // 9. Multimodal Evidence Ingestion (Phase E Validation & Reconciliation)
  ingestEvidence: (extractionId, locationOverride = null) =>
    fetchJson("/observations/multimodal/ingest", {
      method: "POST",
      body: JSON.stringify({
        extraction_id: extractionId,
        location_override: locationOverride,
      }),
    }),

  // 9b. Voice Evidence Transcription & Extraction (Phase L8 Read-Only)
  transcribeVoice: async (formData) => {
    const res = await fetch(`${API_BASE}/observations/voice/transcribe`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }
    return await res.json();
  },

  // 9c. Voice Evidence Ingestion (Phase L8 Ingestion via Phase E)
  ingestVoice: (extractionId, locationOverride = null) =>
    fetchJson("/observations/voice/ingest", {
      method: "POST",
      body: JSON.stringify({
        extraction_id: extractionId,
        location_override: locationOverride,
      }),
    }),

  // 9d. Drainage Infrastructure Evidence (Phase L9)
  getDrainageInfrastructure: (catchment = null, status = null) => {
    const params = new URLSearchParams();
    if (catchment) params.append("catchment", catchment);
    if (status) params.append("status", status);
    const query = params.toString() ? `?${params.toString()}` : "";
    return fetchJson(`/infrastructure/drainage${query}`, { method: "GET" });
  },

  // 10. Observation Timeline
  getTimeline: () => fetchJson("/observations/timeline", { method: "GET" }),

  // 11. Batch Sync Offline Observations (Phase I Idempotent)
  syncBatch: (observations) =>
    fetchJson("/observations/sync", {
      method: "POST",
      body: JSON.stringify({ observations }),
    }),

  // 12. Current Disaster State (Phase J)
  getCurrentState: () => fetchJson("/state/current", { method: "GET" }),

  // 13. State Diff (Phase J)
  getStateDiff: (fromVer, toVer) =>
    fetchJson(`/state/diff?from_version=${fromVer}&to_version=${toVer}`, { method: "GET" }),

  // 14. Operational Alerts (Phase J)
  getAlerts: (status = null, severity = null) => {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    if (severity) params.append("severity", severity);
    const query = params.toString() ? `?${params.toString()}` : "";
    return fetchJson(`/alerts${query}`, { method: "GET" });
  },

  // 15. Apply Operator Action to Alert (Phase J)
  applyAlertAction: (alertId, action, operatorId = "Operator-01", comment = "") =>
    fetchJson(`/alerts/${alertId}/action`, {
      method: "POST",
      body: JSON.stringify({ action, operator_id: operatorId, comment }),
    }),

  // 16. Entity Traceability (Phase J)
  getTraceability: (entityId) =>
    fetchJson(`/traceability/${encodeURIComponent(entityId)}`, { method: "GET" }),

  // 17. Propose Intervention from Candidate (Phase K)
  proposeIntervention: (candidateId, operatorId = "COMMANDER-01", notes = "") =>
    fetchJson("/interventions/propose", {
      method: "POST",
      body: JSON.stringify({ candidate_id: candidateId, operator_id: operatorId, notes }),
    }),

  // 18. State Machine Transition (Phase K)
  transitionIntervention: (interventionId, toStatus, operatorId = "COMMANDER-01", assignedTeam = null, note = null) =>
    fetchJson(`/interventions/${interventionId}/transition`, {
      method: "POST",
      body: JSON.stringify({ to_status: toStatus, operator_id: operatorId, assigned_team: assignedTeam, note }),
    }),

  // 19. Record Field Update (Phase K)
  recordInterventionFieldUpdate: (interventionId, evidenceRef = null, notes = null, operatorId = "FIELD-01") =>
    fetchJson(`/interventions/${interventionId}/field-update`, {
      method: "POST",
      body: JSON.stringify({ evidence_ref: evidenceRef, notes, operator_id: operatorId }),
    }),

  // 20. List Interventions (Phase K)
  getInterventions: (status = null) => {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return fetchJson(`/interventions${query}`, { method: "GET" });
  },

  // 21. Intervention Detail (Phase K)
  getInterventionDetail: (interventionId) =>
    fetchJson(`/interventions/${interventionId}`, { method: "GET" }),

  // 22. Intervention Audit Log (Phase K)
  getInterventionAudit: (interventionId) =>
    fetchJson(`/interventions/${interventionId}/audit`, { method: "GET" }),

  // 23. Single Weather/Hazard Forecast (Phase L5 Read-Only)
  getForecast: (horizonHours = null) => {
    const query = horizonHours !== null ? `?horizon_hours=${encodeURIComponent(horizonHours)}` : "";
    return fetchJson(`/forecast${query}`, { method: "GET" });
  },

  // 24. Forecast Timeline Projection (Phase L1/L5 Read-Only)
  getForecastTimeline: (horizon = "NOW") =>
    fetchJson(`/forecast/timeline?horizon=${encodeURIComponent(horizon)}`, { method: "GET" }),

  // 25. Forecast Vulnerability Projection (Phase L5 Read-Only)
  getForecastVulnerability: (horizon = "NOW") =>
    fetchJson(`/forecast/vulnerability?horizon=${encodeURIComponent(horizon)}`, { method: "GET" }),

  // 26. Submit Citizen Report (Phase L10)
  submitCitizenReport: (reportData) =>
    fetchJson("/observations/citizen", {
      method: "POST",
      body: JSON.stringify(reportData),
    }),

  // 27. Get Citizen Observations (Phase L10)
  getCitizenObservations: (status = null, reportType = null) => {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    if (reportType) params.append("report_type", reportType);
    const query = params.toString() ? `?${params.toString()}` : "";
    return fetchJson(`/observations/citizen${query}`, { method: "GET" });
  },
};





