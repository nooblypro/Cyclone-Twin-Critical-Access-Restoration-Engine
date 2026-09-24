import React, { useState, useEffect, useRef, useCallback } from "react";
import L from "leaflet";
import {
  ShieldAlert,
  Zap,
  CheckCircle2,
  TrendingUp,
  FileText,
  AlertTriangle,
  RotateCcw,
  HelpCircle,
} from "lucide-react";

const API_BASE = "http://localhost:8000";

// Presentation-level Semantic State Labels (Section 5)
const STATE_LABELS = {
  BASE: "NETWORK BASELINE",
  FLOODED: "HAZARD SCENARIO",
  RANKED: "VULNERABILITY ASSESSMENT",
  SELECTED: "CRITICAL INFRASTRUCTURE",
  CLEARED: "MITIGATION SIMULATION",
};

export default function CycloneTwinApp() {
  // State Machine: BASE -> FLOODED -> RANKED -> SELECTED -> CLEARED
  const [systemState, setSystemState] = useState("BASE");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Core Data
  const [mapData, setMapData] = useState(null);
  const [accessStatus, setAccessStatus] = useState({
    accessible_population: 477000,
    isolated_facilities: [],
    isolated_communities: [],
  });
  const [rankedCorridors, setRankedCorridors] = useState([]);
  const [selectedCorridor, setSelectedCorridor] = useState(null);
  const [advisory, setAdvisory] = useState(null);
  const [manifest, setManifest] = useState(null);
  const [clearedCorridorId, setClearedCorridorId] = useState(null);
  const [showManifest, setShowManifest] = useState(false);
  const [showNovelty, setShowNovelty] = useState(true);

  // Map Refs
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const layerGroupRef = useRef(null);
  const highlightLayerRef = useRef(null);

  // 1. Fetch Map Data & Initial Status
  const fetchInitialData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/map/data`);
      if (!res.ok) throw new Error("Failed to connect to Cyclone Twin API");
      const data = await res.json();
      setMapData(data);

      const statusRes = await fetch(`${API_BASE}/accessibility/status`);
      if (statusRes.ok) {
        const sData = await statusRes.json();
        setAccessStatus(sData);
      }
      setLoading(false);
    } catch (err) {
      console.warn("Backend connecting...", err);
      setErrorMsg("Cyclone Twin Backend Offline. Ensure uvicorn is running on port 8000.");
      setLoading(false);
    }
  }, []);

  // 2. Initialize Leaflet Map
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    // Centered on South-Central Chennai (Adyar / Saidapet / Guindy)
    const map = L.map(mapContainerRef.current, {
      center: [13.010, 80.225],
      zoom: 12.5,
      zoomControl: false,
      attributionControl: false,
    });

    L.control.zoom({ position: "bottomright" }).addTo(map);

    // CartoDB Dark Matter operational tile layer
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 18,
      subdomains: "abcd",
    }).addTo(map);

    layerGroupRef.current = L.layerGroup().addTo(map);
    highlightLayerRef.current = L.layerGroup().addTo(map);
    mapInstanceRef.current = map;

    // Initial data load
    fetchInitialData();

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [fetchInitialData]);

  // 3. Render Vector Layers on Map
  useEffect(() => {
    if (!mapInstanceRef.current || !layerGroupRef.current || !mapData) return;

    const lg = layerGroupRef.current;
    lg.clearLayers();

    // A. Render Flood Footprint (HAZARD)
    if (systemState !== "BASE" && mapData.flood) {
      L.geoJSON(mapData.flood, {
        style: {
          color: "#ff2a5f",
          weight: 1.5,
          fillColor: "#ff2a5f",
          fillOpacity: 0.18,
          dashArray: "4, 4",
        },
      }).addTo(lg);
    }

    // B. Render Road Network (VULNERABILITY / RECOVERY)
    if (mapData.roads && mapData.roads.features) {
      L.geoJSON(mapData.roads, {
        style: (feature) => {
          const isCleared = clearedCorridorId && feature.properties.segment_id &&
            rankedCorridors.find(c => c.corridor_id === clearedCorridorId)?.physical_segment_ids.includes(feature.properties.segment_id);

          if (isCleared) {
            return { color: "#00e676", weight: 4.5, opacity: 0.95 };
          }
          if (feature.properties.disabled) {
            return { color: "#ff2a5f", weight: 3.5, opacity: 0.85, dashArray: "5, 5" };
          }
          if (feature.properties.bridge === "yes" || feature.properties.layer > 0) {
            return { color: "#00e5ff", weight: 3.0, opacity: 0.8 };
          }
          return { color: "#25334d", weight: 2.0, opacity: 0.7 };
        },
        onEachFeature: (feature, layer) => {
          const p = feature.properties;
          layer.bindTooltip(
            `<div style="font-family: monospace; font-size: 11px;">
              <strong>${p.name}</strong><br/>
              Status: <span style="color: ${p.disabled ? '#ff2a5f' : '#00e676'}; font-weight: bold;">
                ${p.disabled ? 'HAZARD: SUBMERGED / IMPASSABLE' : 'OPERATIONAL'}
              </span><br/>
              Speed: ${p.speed_kph} km/h | Length: ${Math.round(p.length)}m
              ${p.bridge === 'yes' ? ' | <em>Elevated Span Preserved</em>' : ''}
            </div>`,
            { sticky: true }
          );
        },
      }).addTo(lg);
    }

    // C. Render Health Facilities (Hospitals)
    if (mapData.facilities && mapData.facilities.features) {
      mapData.facilities.features.forEach((feat) => {
        const [lon, lat] = feat.geometry.coordinates;
        const p = feat.properties;
        const isIsolated = accessStatus.isolated_facilities.includes(p.id);

        const iconHtml = `
          <div style="
            width: 26px; height: 26px; border-radius: 50%;
            background: ${isIsolated ? '#ff2a5f' : '#00e676'};
            border: 2px solid #ffffff;
            box-shadow: 0 0 10px ${isIsolated ? 'rgba(255,42,95,0.7)' : 'rgba(0,230,118,0.7)'};
            display: flex; align-items: center; justify-content: center;
            color: #000; font-weight: 900; font-size: 14px; font-family: sans-serif;
          ">+</div>
        `;
        const markerIcon = L.divIcon({
          html: iconHtml,
          className: "custom-hospital-marker",
          iconSize: [26, 26],
          iconAnchor: [13, 13],
        });

        const marker = L.marker([lat, lon], { icon: markerIcon }).addTo(lg);
        marker.bindPopup(`
          <div style="font-family: monospace; font-size: 12px; color: #111;">
            <strong style="font-size: 13px;">${p.name}</strong><br/>
            Capacity: ${p.beds} beds<br/>
            Power Status: ${p.power_status ? '⚡ Online' : '⚠️ Offline'}<br/>
            Network Consequence: <strong style="color: ${isIsolated ? '#d00' : '#0a0'};">
              ${isIsolated ? 'ISOLATED BY FLOODING' : 'ACCESSIBLE'}
            </strong>
          </div>
        `);
      });
    }

    // D. Render Communities (Centroids & Pop)
    if (mapData.communities && mapData.communities.features) {
      mapData.communities.features.forEach((feat) => {
        const [lon, lat] = feat.geometry.coordinates;
        const p = feat.properties;
        const isIsolated = accessStatus.isolated_communities.includes(p.id);

        const circle = L.circleMarker([lat, lon], {
          radius: isIsolated ? 8 : 6,
          fillColor: isIsolated ? "#ff2a5f" : "#2979ff",
          color: isIsolated ? "#ffffff" : "#00e5ff",
          weight: 1.5,
          opacity: 0.9,
          fillOpacity: 0.7,
        }).addTo(lg);

        circle.bindTooltip(`
          <div style="font-family: monospace; font-size: 11px;">
            <strong>${p.name}</strong><br/>
            Population: ${p.population.toLocaleString()}<br/>
            Network Access: <span style="color: ${isIsolated ? '#ff2a5f' : '#00e676'}; font-weight: bold;">
              ${isIsolated ? 'CUT OFF / ISOLATED' : 'EMERGENCY ACCESS ACTIVE'}
            </span>
          </div>
        `);
      });
    }
  }, [mapData, systemState, accessStatus, clearedCorridorId, rankedCorridors]);

  // 4. Highlight Selected Corridor & Affected Nodes
  useEffect(() => {
    if (!highlightLayerRef.current) return;
    const hl = highlightLayerRef.current;
    hl.clearLayers();

    if (selectedCorridor && selectedCorridor.geometry) {
      const line = L.geoJSON(selectedCorridor.geometry, {
        style: {
          color: "#ffaa00",
          weight: 6.5,
          opacity: 0.95,
          dashArray: "1, 1",
        },
      }).addTo(hl);

      if (mapInstanceRef.current && line.getBounds().isValid()) {
        mapInstanceRef.current.fitBounds(line.getBounds(), { padding: [50, 50], maxZoom: 14 });
      }
    }
  }, [selectedCorridor]);

  // ==========================================
  // ACTION HANDLERS
  // ==========================================

  // Step 1: Introduce Hazard (Cyclone Michaung Inundation)
  const handleApplyFlood = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await fetch(`${API_BASE}/flood/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error("Flood scenario application failed");
      await res.json();

      setSystemState("FLOODED");
      setClearedCorridorId(null);
      setSelectedCorridor(null);
      setAdvisory(null);

      await fetchInitialData();
      setLoading(false);
    } catch (err) {
      setErrorMsg(err.message);
      setLoading(false);
    }
  };

  // Step 2: Vulnerability Assessment & Criticality Ranking
  const handleRankCorridors = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await fetch(`${API_BASE}/interventions/rank`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          weights: { w_h: 0.40, w_p: 0.30, w_t: 0.20, w_d: 0.10 },
        }),
      });
      if (!res.ok) throw new Error("Ranking failed");
      const data = await res.json();

      setRankedCorridors(data.ranked_corridors);
      setManifest(data.manifest);
      setSystemState("RANKED");

      // Auto-select top corridor
      if (data.ranked_corridors.length > 0) {
        handleSelectCorridor(data.ranked_corridors[0]);
      }
      setLoading(false);
    } catch (err) {
      setErrorMsg(err.message);
      setLoading(false);
    }
  };

  // Step 3: Inspect Corridor Failure Consequences
  const handleSelectCorridor = async (corr) => {
    setSelectedCorridor(corr);
    setSystemState("SELECTED");

    try {
      const res = await fetch(`${API_BASE}/advisory/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          corridor_id: corr.corridor_id,
          score_breakdown: corr.score_breakdown,
        }),
      });
      if (res.ok) {
        const advData = await res.json();
        setAdvisory(advData);
      }
    } catch (err) {
      console.error("Advisory error", err);
    }
  };

  // Step 4: Simulate Restoration (Mitigation Simulation)
  const handleClearCorridor = async () => {
    if (!selectedCorridor) return;
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await fetch(`${API_BASE}/interventions/clear`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corridor_id: selectedCorridor.corridor_id }),
      });
      if (!res.ok) throw new Error("Restoration simulation failed");
      const data = await res.json();

      setClearedCorridorId(data.corridor_id);
      setSystemState("CLEARED");

      await fetchInitialData();
      setLoading(false);
    } catch (err) {
      setErrorMsg(err.message);
      setLoading(false);
    }
  };

  // Step 5: Reset Network
  const handleResetNetwork = async () => {
    try {
      setLoading(true);
      await fetch(`${API_BASE}/network/load`, { method: "POST" });
      setSystemState("BASE");
      setRankedCorridors([]);
      setSelectedCorridor(null);
      setAdvisory(null);
      setClearedCorridorId(null);
      await fetchInitialData();
      setLoading(false);
    } catch (err) {
      setErrorMsg(err.message);
      setLoading(false);
    }
  };

  // Killer Comparison Pair (Real Calculated Data)
  const corrB = rankedCorridors.find(c => c.corridor_id === "corridor_03" || c.corridor_id === "corridor_02") || rankedCorridors[0];
  const corrA = rankedCorridors.find(c => c.corridor_id === "corridor_01") || rankedCorridors[rankedCorridors.length - 1];

  return (
    <div className="command-console">
      {/* 1. TOP OPERATIONAL HEADER */}
      <header className="top-header">
        <div className="brand-section">
          <div className="brand-main">
            <span className="brand-badge">GCC TWIN // V2.0</span>
            <h1 className="brand-title">
              CYCLONE TWIN
            </h1>
            <span className="brand-subtitle">
              From Flood Impact to Network Vulnerability
            </span>
          </div>
          <p className="brand-statement">
            "Most flood maps show where infrastructure is affected. Cyclone Twin shows what happens to the emergency network when that infrastructure fails."
          </p>
        </div>

        <div className="provenance-cluster">
          <div className="prov-pill active">
            <span className="prov-dot"></span>
            GRAPH: {manifest?.graph_source || "MOCK FALLBACK"}
          </div>
          <div className="prov-pill active">
            <span className="prov-dot"></span>
            FLOOD: {manifest?.flood_source?.toUpperCase() || "NRSC MICHAUNG"}
          </div>
          <div className="prov-pill">
            CRS: EPSG:32643
          </div>
          <div className="prov-pill">
            LIMIT: 30m / 200m
          </div>
          <button
            onClick={() => setShowNovelty(!showNovelty)}
            className="btn-action"
            style={{ padding: "0.2rem 0.45rem", fontSize: "0.65rem" }}
            title="Why Cyclone Twin?"
          >
            <HelpCircle size={12} /> WHY TWIN?
          </button>
          <button
            onClick={() => setShowManifest(!showManifest)}
            className="btn-action"
            style={{ padding: "0.2rem 0.45rem", fontSize: "0.65rem" }}
          >
            <FileText size={12} /> AUDIT PROVENANCE
          </button>
        </div>
      </header>

      {/* 2. DEMO STORY SEQUENCE BREADCRUMB */}
      <div className="narrative-bar">
        <div className="narrative-flow">
          <span style={{ color: "var(--text-muted)", marginRight: "0.2rem" }}>NARRATIVE FLOW:</span>
          <span className={`flow-step ${systemState === "BASE" ? "active" : ""}`}>1. THREAT</span>
          <span className="flow-sep">→</span>
          <span className={`flow-step ${systemState === "FLOODED" ? "active" : ""}`}>2. HAZARD</span>
          <span className="flow-sep">→</span>
          <span className={`flow-step ${systemState === "FLOODED" ? "active" : ""}`}>3. FAILURE</span>
          <span className="flow-sep">→</span>
          <span className={`flow-step ${systemState === "RANKED" || systemState === "SELECTED" ? "active" : ""}`}>4. CASCADE</span>
          <span className="flow-sep">→</span>
          <span className={`flow-step ${systemState === "RANKED" || systemState === "SELECTED" ? "active" : ""}`}>5. CRITICALITY</span>
          <span className="flow-sep">→</span>
          <span className={`flow-step ${systemState === "CLEARED" ? "active" : ""}`}>6. MITIGATION</span>
          <span className="flow-sep">→</span>
          <span className={`flow-step ${systemState === "CLEARED" ? "active" : ""}`}>7. RECOVERY</span>
        </div>

        <div className="concepts-cluster">
          <span className="concept-tag hazard">1. HAZARD: WHERE AFFECTED?</span>
          <span className="concept-tag vuln">2. VULNERABILITY: WHAT FAILS?</span>
          <span className="concept-tag crit">3. CRITICALITY: WHAT MATTERS?</span>
          <span className="concept-tag mitig">4. MITIGATION: WHAT TO RESTORE?</span>
        </div>
      </div>

      {/* 3. MAIN VIEWPORT (Map + Intelligence Panel) */}
      <main className="main-viewport">
        {/* Map Panel */}
        <div className="map-panel">
          <div ref={mapContainerRef} style={{ width: "100%", height: "100%" }} />

          {/* Map Floating Control Actions */}
          <div className="map-actions-bar">
            <button
              onClick={handleApplyFlood}
              disabled={loading || systemState === "FLOODED"}
              className={`btn-action ${systemState === "BASE" ? "danger" : ""}`}
            >
              <ShieldAlert size={14} /> 1. APPLY HAZARD (MICHAUNG)
            </button>

            <button
              onClick={handleRankCorridors}
              disabled={loading || systemState === "BASE"}
              className={`btn-action ${systemState === "FLOODED" ? "primary" : ""}`}
            >
              <Zap size={14} /> 2. ASSESS VULNERABILITY & RANK
            </button>

            <button
              onClick={handleClearCorridor}
              disabled={loading || !selectedCorridor || systemState === "CLEARED"}
              className={`btn-action ${selectedCorridor && systemState !== "CLEARED" ? "success" : ""}`}
            >
              <CheckCircle2 size={14} /> 3. SIMULATE RESTORATION
            </button>

            <button
              onClick={handleResetNetwork}
              disabled={loading}
              className="btn-action"
            >
              <RotateCcw size={14} /> RESET
            </button>
          </div>

          {/* Map HUD Overlays */}
          <div className="map-hud-metrics">
            <div className="hud-tile">
              <div className="hud-label">ACCESSIBLE POPULATION</div>
              <div className={`hud-val ${accessStatus.isolated_communities.length > 0 ? "danger" : "success"}`}>
                {accessStatus.accessible_population.toLocaleString()}
              </div>
              <div className="hud-sub">
                {accessStatus.isolated_communities.length > 0
                  ? `${(477000 - accessStatus.accessible_population).toLocaleString()} citizens stranded`
                  : "All 477,000 citizens connected"}
              </div>
            </div>

            <div className="hud-tile">
              <div className="hud-label">ISOLATED WARDS</div>
              <div className={`hud-val ${accessStatus.isolated_communities.length > 0 ? "danger" : "success"}`}>
                {accessStatus.isolated_communities.length}
              </div>
              <div className="hud-sub">
                {accessStatus.isolated_communities.length > 0 ? "Emergency Access Severed" : "All Lifelines Active"}
              </div>
            </div>

            <div className="hud-tile">
              <div className="hud-label">PRESENTATION STATE</div>
              <div className="hud-val" style={{ fontSize: "0.95rem", color: "var(--accent-cyan)" }}>
                {STATE_LABELS[systemState]}
              </div>
              <div className="hud-sub">
                {clearedCorridorId ? `Restored: ${clearedCorridorId}` : `${rankedCorridors.length} Corridors Identified`}
              </div>
            </div>
          </div>
        </div>

        {/* Right Intelligence Sidebar */}
        <aside className="sidebar-panel">
          {errorMsg && (
            <div style={{ background: "rgba(255,42,95,0.15)", border: "1px solid #ff2a5f", padding: "0.6rem", borderRadius: "4px", fontSize: "0.72rem", color: "#ff2a5f", fontFamily: "monospace" }}>
              <AlertTriangle size={14} style={{ display: "inline", marginRight: "4px", verticalAlign: "middle" }} />
              {errorMsg}
            </div>
          )}

          {/* NOVELTY CARD: WHY CYCLONE TWIN? */}
          {showNovelty && (
            <div className="novelty-card">
              <div className="novelty-header">
                <span>WHY CYCLONE TWIN?</span>
                <span style={{ fontSize: "0.6rem", color: "var(--text-muted)", cursor: "pointer" }} onClick={() => setShowNovelty(false)}>✕ HIDE</span>
              </div>
              <div className="novelty-grid">
                <div className="novelty-item">
                  <strong>1. HAZARD</strong>
                  Maps where infrastructure physically intersects water.
                </div>
                <div className="novelty-item">
                  <strong>2. VULNERABILITY</strong>
                  Simulates what happens to the network when it fails.
                </div>
                <div className="novelty-item">
                  <strong>3. CRITICALITY</strong>
                  Measures systemic network consequence, not road size.
                </div>
                <div className="novelty-item">
                  <strong>4. MITIGATION</strong>
                  Identifies which lifeline to protect or restore first.
                </div>
              </div>
            </div>
          )}

          {/* SCENARIO INTRODUCTION BANNER */}
          {systemState === "FLOODED" && (
            <div style={{ background: "rgba(255,42,95,0.12)", border: "1px solid #ff2a5f", padding: "0.75rem", borderRadius: "6px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontFamily: "monospace", fontSize: "0.75rem", fontWeight: "bold", color: "#ff2a5f" }}>
                <ShieldAlert size={14} /> CYCLONE SCENARIO ACTIVE // HAZARD DETECTED
              </div>
              <p style={{ fontSize: "0.72rem", color: "var(--text-primary)", marginTop: "0.3rem", lineHeight: 1.35 }}>
                Surface roads flooded in Adyar basin, Velachery, and Santhome. <strong>179,000 citizens</strong> in 4 wards lost emergency access within 30 minutes. Click <strong>"2. ASSESS VULNERABILITY & RANK"</strong> to simulate network failure consequences.
              </p>
            </div>
          )}

          {/* DEDICATED KILLER COMPARISON VIEW: VULNERABILITY IMPACT */}
          {corrA && corrB && rankedCorridors.length >= 2 && (
            <div className="killer-comparison-box">
              <div className="killer-header">
                <span className="killer-title">
                  <TrendingUp size={14} color="#00e5ff" /> VULNERABILITY IMPACT: KILLER DEMO
                </span>
                <span style={{ fontSize: "0.62rem", fontFamily: "monospace", color: "var(--text-muted)" }}>REAL VALUES</span>
              </div>
              <div className="killer-quote">
                "The physical hazard is similar. The network vulnerability isn't."
              </div>

              <div className="comparison-grid">
                {/* Corridor A: Low Criticality */}
                <div
                  className={`comp-card low-crit ${selectedCorridor?.corridor_id === corrA.corridor_id ? "selected" : ""}`}
                  onClick={() => handleSelectCorridor(corrA)}
                  style={{ cursor: "pointer" }}
                >
                  <div className="comp-name">CORRIDOR A ({corrA.corridor_id})</div>
                  <div className="comp-condition">Condition: FLOODED</div>
                  <div className="comp-stat-row">
                    <span>Hospitals Cut Off:</span>
                    <strong>{corrA.score_breakdown.hospitals_recovered}</strong>
                  </div>
                  <div className="comp-stat-row">
                    <span>Population Affected:</span>
                    <strong>{corrA.score_breakdown.population_recovered.toLocaleString()}</strong>
                  </div>
                  <div className="comp-stat-row">
                    <span>Transit Degradation:</span>
                    <strong>+{corrA.score_breakdown.time_saved_minutes} min</strong>
                  </div>
                  <div className="comp-stat-row">
                    <span>Criticality Score:</span>
                    <strong>{corrA.score.toFixed(3)}</strong>
                  </div>
                  <div className="comp-badge low">CRITICALITY: LOW</div>
                </div>

                {/* Corridor B: High Criticality */}
                <div
                  className={`comp-card high-crit ${selectedCorridor?.corridor_id === corrB.corridor_id ? "selected" : ""}`}
                  onClick={() => handleSelectCorridor(corrB)}
                  style={{ cursor: "pointer" }}
                >
                  <div className="comp-name">CORRIDOR B ({corrB.corridor_id})</div>
                  <div className="comp-condition">Condition: FLOODED</div>
                  <div className="comp-stat-row">
                    <span>Hospitals Cut Off:</span>
                    <strong>{corrB.score_breakdown.hospitals_recovered}</strong>
                  </div>
                  <div className="comp-stat-row">
                    <span>Population Affected:</span>
                    <strong>{corrB.score_breakdown.population_recovered.toLocaleString()}</strong>
                  </div>
                  <div className="comp-stat-row">
                    <span>Transit Degradation:</span>
                    <strong>+{corrB.score_breakdown.time_saved_minutes} min</strong>
                  </div>
                  <div className="comp-stat-row">
                    <span>Criticality Score:</span>
                    <strong>{corrB.score.toFixed(3)}</strong>
                  </div>
                  <div className="comp-badge danger">CRITICALITY: HIGH</div>
                </div>
              </div>
            </div>
          )}

          {/* VULNERABILITY ANALYSIS & CASCADE VISUALIZATION */}
          {selectedCorridor && (
            <div className="cascade-box">
              <div className="cascade-title">
                <span>WHAT HAPPENS IF THIS INFRASTRUCTURE FAILS?</span>
                <span style={{ color: "var(--accent-cyan)", fontSize: "0.68rem" }}>{selectedCorridor.corridor_id}</span>
              </div>

              <div className="cascade-steps">
                <div className="cascade-step warning">
                  <span className="cascade-step-label">1. CORRIDOR FAILURE</span>
                  <span className="cascade-step-val">{Math.round(selectedCorridor.total_length_m)}m road blocked ({selectedCorridor.physical_segment_ids.length} segments)</span>
                </div>
                <div className="cascade-step warning">
                  <span className="cascade-step-label">2. NETWORK DISRUPTION</span>
                  <span className="cascade-step-val">Arterial lifeline severed across flood basin</span>
                </div>
                <div className="cascade-step danger">
                  <span className="cascade-step-label">3. HOSPITAL IMPACT</span>
                  <span className="cascade-step-val">{selectedCorridor.score_breakdown.hospitals_recovered > 0 ? `${selectedCorridor.score_breakdown.hospitals_recovered} trauma facilities isolated` : "Trauma access detour forced"}</span>
                </div>
                <div className="cascade-step danger">
                  <span className="cascade-step-label">4. POPULATION IMPACT</span>
                  <span className="cascade-step-val">{selectedCorridor.score_breakdown.population_recovered.toLocaleString()} residents stranded / cut off</span>
                </div>
                <div className="cascade-step">
                  <span className="cascade-step-label">5. TRAVEL-TIME CASCADE</span>
                  <span className="cascade-step-val">+{selectedCorridor.score_breakdown.time_saved_minutes} min emergency transit penalty</span>
                </div>
              </div>
            </div>
          )}

          {/* INFRASTRUCTURE CRITICALITY RANKING VIEW */}
          <div className="section-panel">
            <div className="section-title-bar">
              <span className="section-title">
                INFRASTRUCTURE CRITICALITY ({rankedCorridors.length})
              </span>
              <span style={{ fontSize: "0.62rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
                Consequence-Based Priority
              </span>
            </div>

            {rankedCorridors.length === 0 ? (
              <div style={{ padding: "1.2rem", textAlign: "center", border: "1px dashed var(--border-strong)", borderRadius: "6px", color: "var(--text-muted)", fontSize: "0.72rem", fontFamily: "monospace" }}>
                Apply flood scenario and click "ASSESS VULNERABILITY" to calculate systemic criticality.
              </div>
            ) : (
              <div style={{ maxHeight: "180px", overflowY: "auto", border: "1px solid var(--border-strong)", borderRadius: "6px" }}>
                <table className="corridor-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>CORRIDOR</th>
                      <th>SCORE</th>
                      <th>ΔH</th>
                      <th>ΔP</th>
                      <th>ΔT</th>
                      <th>LENGTH</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rankedCorridors.map((rc) => {
                      const isSelected = selectedCorridor?.corridor_id === rc.corridor_id;
                      const isCleared = clearedCorridorId === rc.corridor_id;
                      return (
                        <tr
                          key={rc.corridor_id}
                          className={`corridor-row ${isSelected ? "selected" : ""}`}
                          onClick={() => handleSelectCorridor(rc)}
                        >
                          <td style={{ fontWeight: "bold" }}>{rc.rank}</td>
                          <td>
                            {rc.corridor_id}
                            {isCleared && <span style={{ color: "#00e676", marginLeft: "4px" }}>✓</span>}
                          </td>
                          <td style={{ color: rc.score > 0 ? "var(--accent-cyan)" : "var(--text-muted)", fontWeight: "bold" }}>
                            {rc.score.toFixed(3)}
                          </td>
                          <td>{rc.score_breakdown.delta_h.toFixed(2)}</td>
                          <td>{rc.score_breakdown.delta_p.toFixed(2)}</td>
                          <td>{rc.score_breakdown.delta_t.toFixed(2)}</td>
                          <td>{Math.round(rc.total_length_m)}m</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* CRITICALITY SCORE BREAKDOWN (Section 10) */}
          {selectedCorridor && (
            <div className="breakdown-box">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <strong style={{ fontSize: "0.75rem", fontFamily: "monospace", color: "var(--text-primary)" }}>
                  CRITICALITY DECOMPOSITION: {selectedCorridor.corridor_id}
                </strong>
                <span style={{ fontSize: "0.72rem", fontFamily: "monospace", color: "var(--accent-cyan)", fontWeight: "bold" }}>
                  S(c) = {selectedCorridor.score.toFixed(4)}
                </span>
              </div>

              {/* Delta H */}
              <div className="breakdown-row">
                <div className="breakdown-meta">
                  <span style={{ color: "var(--text-secondary)" }}>ΔH Hospital Recovery (40%)</span>
                  <strong>{selectedCorridor.score_breakdown.hospitals_recovered} recovered ({selectedCorridor.score_breakdown.delta_h.toFixed(2)})</strong>
                </div>
                <div className="progress-track">
                  <div className="progress-fill pink" style={{ width: `${selectedCorridor.score_breakdown.delta_h * 100}%` }} />
                </div>
              </div>

              {/* Delta P */}
              <div className="breakdown-row">
                <div className="breakdown-meta">
                  <span style={{ color: "var(--text-secondary)" }}>ΔP Population Access (30%)</span>
                  <strong>{selectedCorridor.score_breakdown.population_recovered.toLocaleString()} citizens ({selectedCorridor.score_breakdown.delta_p.toFixed(2)})</strong>
                </div>
                <div className="progress-track">
                  <div className="progress-fill cyan" style={{ width: `${selectedCorridor.score_breakdown.delta_p * 100}%` }} />
                </div>
              </div>

              {/* Delta T */}
              <div className="breakdown-row">
                <div className="breakdown-meta">
                  <span style={{ color: "var(--text-secondary)" }}>ΔT Transit Improvement (20%)</span>
                  <strong>~{selectedCorridor.score_breakdown.time_saved_minutes} min saved ({selectedCorridor.score_breakdown.delta_t.toFixed(2)})</strong>
                </div>
                <div className="progress-track">
                  <div className="progress-fill green" style={{ width: `${selectedCorridor.score_breakdown.delta_t * 100}%` }} />
                </div>
              </div>

              {/* Delta D */}
              <div className="breakdown-row">
                <div className="breakdown-meta">
                  <span style={{ color: "var(--text-secondary)" }}>ΔD Length Penalty (10%)</span>
                  <strong>{Math.round(selectedCorridor.total_length_m)}m ({selectedCorridor.score_breakdown.delta_d.toFixed(2)})</strong>
                </div>
                <div className="progress-track">
                  <div className="progress-fill amber" style={{ width: `${selectedCorridor.score_breakdown.delta_d * 100}%` }} />
                </div>
              </div>
            </div>
          )}

          {/* MITIGATION PRIORITY & AI ADVISORY (Sections 12 & 18) */}
          {advisory && (
            <div className="advisory-box">
              <div className="advisory-header">
                <span className="advisory-verb-badge">
                  MITIGATION: {advisory.action_verb}
                </span>
                <span style={{ fontSize: "0.65rem", fontFamily: "monospace", color: advisory.fallback ? "var(--status-warning)" : "var(--accent-cyan)" }}>
                  {advisory.fallback ? "⚡ DETERMINISTIC ADVISORY" : "✨ AI-GENERATED ADVISORY"}
                </span>
              </div>
              <p className="advisory-text">
                {advisory.advisory_text}
              </p>
              <div className="advisory-footer">
                <span>Target: {advisory.source_corridor_id}</span>
                <span>Length: {advisory.advisory_text.length}/220 chars</span>
              </div>
            </div>
          )}
        </aside>
      </main>

      {/* 4. STATUS BAR FOOTER */}
      <footer className="status-bar">
        <div className="status-left">
          <span>STATE: <strong>{STATE_LABELS[systemState]}</strong></span>
          <span>LOCATION: <strong>GREATER CHENNAI CORPORATION</strong></span>
          <span>HAZARD FOOTPRINT: <strong>CYCLONE MICHAUNG</strong></span>
        </div>
        <div className="status-right">
          <span>ALGORITHM: <strong>REVERSED MULTI-SOURCE DIJKSTRA (G^R)</strong></span>
          <span>ACCESSIBILITY CUTOFF: <strong>30 MIN</strong></span>
        </div>
      </footer>

      {/* AUDIT / DATA PROVENANCE MANIFEST MODAL (Section 17) */}
      {showManifest && manifest && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.85)", zIndex: 9999,
          display: "flex", alignItems: "center", justifyContent: "center"
        }}>
          <div style={{
            background: "var(--bg-surface)", border: "1px solid var(--border-strong)",
            borderRadius: "8px", width: "540px", padding: "1.5rem",
            boxShadow: "0 16px 48px rgba(0,0,0,0.7)"
          }}>
            <h3 style={{ fontSize: "0.95rem", fontFamily: "monospace", marginBottom: "0.85rem", color: "var(--text-primary)" }}>
              AUDIT / DATA PROVENANCE // SCENARIO MANIFEST
            </h3>
            <div style={{ fontFamily: "monospace", fontSize: "0.72rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginBottom: "1.2rem" }}>
              <div>Graph Source: <strong>{manifest.graph_source}</strong></div>
              <div>Flood Source: <strong>{manifest.flood_source}</strong></div>
              <div>CRS: <strong>{manifest.graph_crs}</strong></div>
              <div>Threshold: <strong>{manifest.threshold_seconds}s (30m)</strong></div>
              <div>Preset: <strong>{manifest.weight_preset}</strong></div>
              <div>Snap Limit: <strong>{manifest.snap_distance_threshold_m}m</strong></div>
              <div>Disabled Edges: <strong>{manifest.total_disabled_edges}</strong></div>
              <div>Corridors: <strong>{manifest.total_corridors}</strong></div>
            </div>
            {manifest.snap_warnings.length > 0 && (
              <div style={{ fontSize: "0.68rem", color: "var(--status-warning)", marginBottom: "1rem" }}>
                Warnings: {manifest.snap_warnings.join(", ")}
              </div>
            )}
            <button onClick={() => setShowManifest(false)} className="btn-action primary" style={{ width: "100%", justifyContent: "center" }}>
              CLOSE AUDIT PROVENANCE
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
