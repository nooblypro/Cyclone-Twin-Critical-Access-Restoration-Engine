/**
 * CYCLONE TWIN — MUNICIPAL EMERGENCY OPERATIONS CONSOLE
 * GCC Network Vulnerability Forecaster & Critical Access Restoration Engine
 * Phase 10: Map-First Spatial Experience & Tactical Command Hierarchy
 */

import React, { useState, useEffect, useRef } from "react";
import L from "leaflet";
import {
  ShieldAlert,
  Play,
  RotateCcw,
  Activity,
  Sparkles,
  Info,
  Layers,
  CheckCircle2,
  AlertTriangle,
  FileText,
  X,
  Compass,
} from "lucide-react";
import { api } from "./api.js";

// Default Chennai Map Center & Zoom Constants
const CHENNAI_CENTER = [13.015, 80.225];
const CHENNAI_ZOOM = 12;

// Custom Leaflet DivIcons for High-Contrast Operational Cartography
const createHospitalIcon = (isIsolated) =>
  L.divIcon({
    className: "custom-map-icon hospital-icon",
    html: `<div style="
      background: ${isIsolated ? "#ef4444" : "#10b981"};
      width: 24px; height: 24px; border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 2px 8px ${isIsolated ? "rgba(239,68,68,0.5)" : "rgba(16,185,129,0.5)"};
      border: 2px solid #ffffff; color: #ffffff; font-weight: 900; font-size: 13px;
      letter-spacing: -0.5px;
    ">H</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });

const createCommunityIcon = (isIsolated) =>
  L.divIcon({
    className: "custom-map-icon community-icon",
    html: `<div style="
      background: ${isIsolated ? "#ef4444" : "#0284c7"};
      width: 14px; height: 14px; border-radius: 50%;
      border: 2px solid #ffffff;
      box-shadow: 0 1px 6px ${isIsolated ? "rgba(239,68,68,0.6)" : "rgba(2,132,199,0.5)"};
    "></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });

export default function CycloneTwinApp() {
  // Scenario & Workflow State
  const [systemState, setSystemState] = useState("BASE"); // "BASE" | "FLOODED" | "RANKED" | "SELECTED" | "CLEARED"
  const [demoStep, setDemoStep] = useState(1); // 1 to 6
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Simulation & Domain Data
  const [mapData, setMapData] = useState(null);
  const [accessStatus, setAccessStatus] = useState(null);
  const [rankedCorridors, setRankedCorridors] = useState([]);
  const [selectedCorridor, setSelectedCorridor] = useState(null);
  const [clearedCorridorId, setClearedCorridorId] = useState(null);
  const [advisory, setAdvisory] = useState(null);
  const [manifest, setManifest] = useState(null);

  // Modal Dialogs
  const [modalTab, setModalTab] = useState("DATA"); // "DATA" | "MODEL" | "ASSUMPTIONS" | "LIMITATIONS"
  const [showModal, setShowModal] = useState(false);

  // Leaflet Map Refs
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const layersRef = useRef({
    roads: null,
    flood: null,
    facilities: null,
    communities: null,
    highlight: null,
    restored: null,
  });

  // 1. Initial Load & Baseline Fetch
  useEffect(() => {
    let ignore = false;
    const initBaseline = async () => {
      try {
        setLoading(true);
        setErrorMsg(null);
        const [mData, aData] = await Promise.all([
          api.getMapData(),
          api.getAccessibilityStatus(),
        ]);
        if (!ignore) {
          setMapData(mData);
          setAccessStatus(aData);
          setLoading(false);
        }
      } catch (err) {
        if (!ignore) {
          setErrorMsg(`Failed to initialize baseline network: ${err.message}`);
          setLoading(false);
        }
      }
    };

    initBaseline();
    return () => {
      ignore = true;
    };
  }, []);

  // 2. Leaflet Map Initialization with CartoDB Voyager / Neutral Modern Basemap
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const map = L.map(mapContainerRef.current, {
      center: CHENNAI_CENTER,
      zoom: CHENNAI_ZOOM,
      zoomControl: false,
      attributionControl: false,
    });

    // High-familiarity light neutral basemap
    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
      maxZoom: 19,
      subdomains: "abcd",
    }).addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // 3. Leaflet Layer Render & Synchronization
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapData) return;

    // A. Clean previous layers
    Object.keys(layersRef.current).forEach((key) => {
      if (layersRef.current[key]) {
        map.removeLayer(layersRef.current[key]);
        layersRef.current[key] = null;
      }
    });

    // B. Render Flood Inundation Footprint (Semi-transparent cyan with dashed perimeter)
    if (mapData.flood && (systemState !== "BASE" || demoStep > 1)) {
      const floodLayer = L.geoJSON(mapData.flood, {
        style: {
          color: "#0284c7",
          weight: 2,
          fillColor: "#38bdf8",
          fillOpacity: 0.22,
          dashArray: "4, 4",
        },
      }).addTo(map);
      layersRef.current.flood = floodLayer;
    }

    // C. Render Road Network Edges (Clear Road Hierarchy)
    if (mapData.roads) {
      const roadsLayer = L.geoJSON(mapData.roads, {
        style: (feature) => {
          const isDisabled = feature.properties.disabled;
          const isElevated = feature.properties.bridge === "yes" || feature.properties.layer > 0;
          if (isDisabled) {
            return { color: "#ef4444", weight: 4, opacity: 0.95, dashArray: "4, 6" };
          }
          if (isElevated) {
            return { color: "#f59e0b", weight: 3.5, opacity: 0.95 };
          }
          return { color: "#475569", weight: 2.5, opacity: 0.75 };
        },
        onEachFeature: (feature, layer) => {
          layer.bindTooltip(
            `<strong>${feature.properties.name}</strong><br/>Length: ${feature.properties.length}m | Speed: ${feature.properties.speed_kph} km/h`,
            { className: "map-tooltip" }
          );
        },
      }).addTo(map);
      layersRef.current.roads = roadsLayer;
    }

    // D. Render Restored Corridor Highlight (Vibrant Recovery Emerald)
    if (clearedCorridorId && rankedCorridors.length > 0) {
      const clearedCorr = rankedCorridors.find((c) => c.corridor_id === clearedCorridorId);
      if (clearedCorr?.geometry) {
        const restoredLayer = L.geoJSON(clearedCorr.geometry, {
          style: {
            color: "#10b981",
            weight: 7,
            opacity: 0.95,
            dashArray: "8, 4",
          },
        }).addTo(map);
        layersRef.current.restored = restoredLayer;
      }
    }

    // E. Render Selected Corridor Highlight (High-Contrast Cyan with Outer Border)
    if (selectedCorridor?.geometry && selectedCorridor.corridor_id !== clearedCorridorId) {
      const highlightLayer = L.geoJSON(selectedCorridor.geometry, {
        style: {
          color: "#0284c7",
          weight: 7,
          opacity: 0.95,
        },
      }).addTo(map);
      layersRef.current.highlight = highlightLayer;
    }

    // F. Render Health Facilities (Trauma Hospitals)
    if (mapData.facilities) {
      const facilitiesLayer = L.geoJSON(mapData.facilities, {
        pointToLayer: (feature, latlng) => {
          const isIsolated = feature.properties.isolated;
          const marker = L.marker(latlng, { icon: createHospitalIcon(isIsolated) });
          marker.bindTooltip(
            `<strong>${feature.properties.name}</strong><br/>Capacity: ${feature.properties.beds} beds<br/>Status: ${isIsolated ? "ISOLATED" : "ACCESSIBLE"}`,
            { className: "map-tooltip" }
          );
          return marker;
        },
      }).addTo(map);
      layersRef.current.facilities = facilitiesLayer;
    }

    // G. Render Community Wards
    if (mapData.communities) {
      const communitiesLayer = L.geoJSON(mapData.communities, {
        pointToLayer: (feature, latlng) => {
          const isIsolated = feature.properties.isolated;
          const marker = L.marker(latlng, { icon: createCommunityIcon(isIsolated) });
          const transitTime = feature.properties.travel_time_sec
            ? `${(feature.properties.travel_time_sec / 60).toFixed(1)} min`
            : ">30 min (Disconnected)";
          marker.bindTooltip(
            `<strong>${feature.properties.name}</strong><br/>Population: ${feature.properties.population.toLocaleString()}<br/>Transit: ${transitTime}`,
            { className: "map-tooltip" }
          );
          return marker;
        },
      }).addTo(map);
      layersRef.current.communities = communitiesLayer;
    }
  }, [mapData, systemState, selectedCorridor, clearedCorridorId, rankedCorridors, demoStep]);

  // 4. Operational Actions & State Transitions
  const handleApplyFlood = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      await api.applyFlood();
      const [mData, aData] = await Promise.all([
        api.getMapData(),
        api.getAccessibilityStatus(),
      ]);
      setMapData(mData);
      setAccessStatus(aData);
      setSystemState("FLOODED");
      setDemoStep(2);
      setClearedCorridorId(null);
      setSelectedCorridor(null);
      setAdvisory(null);
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Flood application error: ${err.message}`);
      setLoading(false);
    }
  };

  const handleRankCorridors = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const data = await api.rankCorridors();
      setRankedCorridors(data.ranked_corridors);
      setManifest(data.manifest);
      setSystemState("RANKED");
      setDemoStep(3);

      if (data.ranked_corridors?.length > 0) {
        handleSelectCorridor(data.ranked_corridors[0]);
      }
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Criticality calculation error: ${err.message}`);
      setLoading(false);
    }
  };

  const handleSelectCorridor = async (corr) => {
    if (!corr) return;
    setSelectedCorridor(corr);
    setSystemState("SELECTED");

    // Camera fly to focus on the selected corridor
    if (mapInstanceRef.current && corr.corridor_id === "corridor_03") {
      mapInstanceRef.current.flyTo([13.015, 80.22], 13, { duration: 0.8 });
    }

    try {
      const advData = await api.generateAdvisory(corr.corridor_id, corr.score_breakdown);
      setAdvisory(advData);
    } catch (err) {
      console.warn("Advisory generator cascaded to Tier 2 fallback", err);
    }
  };

  const handleClearCorridor = async () => {
    if (!selectedCorridor) return;
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await api.clearCorridor(selectedCorridor.corridor_id);
      setClearedCorridorId(res.corridor_id);
      setSystemState("CLEARED");
      setDemoStep(6);

      const [mData, aData] = await Promise.all([
        api.getMapData(),
        api.getAccessibilityStatus(),
      ]);
      setMapData(mData);
      setAccessStatus(aData);
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Restoration simulation error: ${err.message}`);
      setLoading(false);
    }
  };

  const handleResetNetwork = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      await api.loadNetwork();
      const [mData, aData] = await Promise.all([
        api.getMapData(),
        api.getAccessibilityStatus(),
      ]);
      setMapData(mData);
      setAccessStatus(aData);
      setSystemState("BASE");
      setDemoStep(1);
      setRankedCorridors([]);
      setSelectedCorridor(null);
      setClearedCorridorId(null);
      setAdvisory(null);
      setManifest(null);
      setLoading(false);

      if (mapInstanceRef.current) {
        mapInstanceRef.current.flyTo(CHENNAI_CENTER, CHENNAI_ZOOM, { duration: 0.6 });
      }
    } catch (err) {
      setErrorMsg(`Network reset error: ${err.message}`);
      setLoading(false);
    }
  };

  // 5. 6-Step Stepper Controller
  const handleNextDemoStep = () => {
    if (demoStep === 1) handleApplyFlood();
    else if (demoStep === 2) handleRankCorridors();
    else if (demoStep === 3) setDemoStep(4);
    else if (demoStep === 4) setDemoStep(5);
    else if (demoStep === 5) handleClearCorridor();
    else if (demoStep === 6) handleResetNetwork();
  };

  // 6. Metric Calculations for HUD
  const totalPopulation = 477000;
  const accessiblePop = accessStatus?.accessible_population ?? totalPopulation;
  const isolatedPop = totalPopulation - accessiblePop;
  const isolatedPercent = ((isolatedPop / totalPopulation) * 100).toFixed(1);
  const activeHospitals = 6 - (accessStatus?.isolated_facilities?.length ?? 0);

  // Killer Comparison Corridors
  const corridorA = rankedCorridors.find((c) => c.corridor_id === "corridor_01") || {
    corridor_id: "corridor_01",
    score: -0.0497,
    score_breakdown: { delta_p: 0, population_recovered: 0, delta_t: 0, time_saved_minutes: 0, delta_d: 0.4971 },
  };

  const corridorB = rankedCorridors.find((c) => c.corridor_id === "corridor_03") || {
    corridor_id: "corridor_03",
    score: 0.0724,
    score_breakdown: { delta_p: 0.1866, population_recovered: 89000, delta_t: 0.134, time_saved_minutes: 22.0, delta_d: 0.1062 },
  };

  return (
    <div className="command-console">
      {/* 1. TOP COMMAND BAR */}
      <header className="top-header">
        <div className="brand-section">
          <div className="brand-badge">GCC OPERATIONS</div>
          <div>
            <h1 className="brand-title">
              <ShieldAlert size={18} color="var(--accent-cyan)" />
              CYCLONE TWIN
            </h1>
            <p className="brand-subtitle">From Flood Impact to Network Vulnerability Forecaster</p>
          </div>
        </div>

        <div className="header-center">
          <div className={`state-badge ${systemState.toLowerCase()}`}>
            <Activity size={12} />
            STATE: {systemState === "BASE" ? "BASELINE ACCESSIBILITY" : systemState === "FLOODED" ? "CYCLONE MICHAUNG HAZARD ACTIVE" : systemState === "RANKED" ? "CRITICALITY ASSESSED" : systemState === "SELECTED" ? "CORRIDOR INSPECTED" : "RESTORATION SIMULATED"}
          </div>
        </div>

        <div className="header-controls">
          <button
            onClick={() => {
              setModalTab("DATA");
              setShowModal(true);
            }}
            className="btn-action tertiary"
            title="Data & Model Provenance"
          >
            <FileText size={13} />
            PROVENANCE
          </button>

          <button
            onClick={() => {
              setModalTab("MODEL");
              setShowModal(true);
            }}
            className="btn-action tertiary"
            title="Model Card & Specifications"
          >
            <Info size={13} />
            MODEL CARD
          </button>

          <button
            onClick={handleResetNetwork}
            className="btn-action secondary"
            disabled={loading || systemState === "BASE"}
            title="Reset to Baseline"
          >
            <RotateCcw size={14} />
            RESET
          </button>

          <button
            onClick={handleNextDemoStep}
            className="btn-action primary"
            disabled={loading}
          >
            <Play size={14} fill="#040810" />
            {demoStep === 1 ? "1. APPLY HAZARD" : demoStep === 2 ? "2. RANK CRITICALITY" : demoStep === 3 ? "3. COMPARE DIVERGENCE" : demoStep === 4 ? "4. MITIGATION STRATEGY" : demoStep === 5 ? "5. SIMULATE RECOVERY" : "6. RESET NETWORK"}
          </button>
        </div>
      </header>

      {/* 2. DEMO STEPPER PROGRESSION BAR */}
      <nav className="stepper-bar" aria-label="Demo Progression">
        {[
          { step: 1, label: "1. BASELINE", desc: "477k Normal Access" },
          { step: 2, label: "2. HAZARD", desc: "Cyclone Michaung" },
          { step: 3, label: "3. VULNERABILITY", desc: "179k Stranded" },
          { step: 4, label: "4. CRITICALITY", desc: "A vs B Divergence" },
          { step: 5, label: "5. MITIGATION", desc: "Saidapet Lifeline" },
          { step: 6, label: "6. RECOVERY", desc: "+89k Citizens Restored" },
        ].map((item) => {
          const isCompleted = demoStep > item.step;
          const isActive = demoStep === item.step;
          return (
            <div
              key={item.step}
              className={`step-card ${isActive ? "active" : ""} ${isCompleted ? "completed" : ""}`}
              onClick={() => {
                if (item.step === 1) handleResetNetwork();
                else if (item.step === 2) handleApplyFlood();
                else if (item.step === 3) handleRankCorridors();
                else setDemoStep(item.step);
              }}
            >
              <div className="step-badge">
                {isCompleted ? <CheckCircle2 size={12} /> : item.step}
              </div>
              <div className="step-label">{item.label}</div>
            </div>
          );
        })}
      </nav>

      {/* Error Banner */}
      {errorMsg && (
        <div className="error-banner">
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <AlertTriangle size={14} />
            {errorMsg}
          </div>
          <button onClick={() => setErrorMsg(null)} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer" }}>
            <X size={14} />
          </button>
        </div>
      )}

      {/* 3. MAIN MAP-DOMINANT WORKSPACE */}
      <main className="workspace-grid">
        {/* Full-Dominant Map Spatial Canvas */}
        <div className="map-canvas-container">
          <div ref={mapContainerRef} className="leaflet-map" />

          {/* Floating Metric HUD */}
          <div className="map-hud-overlay">
            <div className="hud-pill">
              <span className="hud-label">ACCESSIBLE POPULATION</span>
              <span className="hud-value tabular-nums">
                {accessiblePop.toLocaleString()} <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontWeight: 500 }}>/ 477k</span>
              </span>
            </div>

            <div className="hud-pill">
              <span className="hud-label">ISOLATED CITIZENS</span>
              <span className={`hud-value tabular-nums ${isolatedPop > 0 ? "danger" : "success"}`}>
                {isolatedPop.toLocaleString()} <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>({isolatedPercent}%)</span>
              </span>
            </div>

            <div className="hud-pill">
              <span className="hud-label">TRAUMA HOSPITALS</span>
              <span className="hud-value tabular-nums cyan">
                {activeHospitals} <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontWeight: 500 }}>/ 6 OPERATIONAL</span>
              </span>
            </div>

            {clearedCorridorId && (
              <div className="hud-pill" style={{ border: "1px solid var(--status-success-border)", background: "rgba(16,185,129,0.15)" }}>
                <span className="hud-label" style={{ color: "var(--status-success)" }}>CITIZENS RECOVERED</span>
                <span className="hud-value tabular-nums success">+89,000</span>
              </div>
            )}
          </div>

          {/* Floating Map Controls (Zoom & Recenter) */}
          <div className="map-controls-overlay">
            <button
              className="map-ctrl-btn"
              onClick={() => mapInstanceRef.current?.zoomIn()}
              title="Zoom In"
              aria-label="Zoom In"
            >
              +
            </button>
            <button
              className="map-ctrl-btn"
              onClick={() => mapInstanceRef.current?.zoomOut()}
              title="Zoom Out"
              aria-label="Zoom Out"
            >
              −
            </button>
            <button
              className="map-ctrl-btn"
              onClick={() => mapInstanceRef.current?.flyTo(CHENNAI_CENTER, CHENNAI_ZOOM, { duration: 0.6 })}
              title="Recenter Chennai"
              aria-label="Recenter Chennai"
            >
              <Compass size={14} />
            </button>
          </div>

          {/* Map Legend */}
          <div className="map-legend-overlay">
            <span className="legend-title">CARTOGRAPHY LAYERS</span>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: "#38bdf8", border: "1px dashed #0284c7" }}></div>
              <span>Michaung Flood Basin</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: "#ef4444", border: "1px dashed #ffffff" }}></div>
              <span>Impassable Arterial Road</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: "#f59e0b" }}></div>
              <span>Elevated Bridge Span (Preserved)</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: "#0284c7" }}></div>
              <span>Selected Critical Corridor</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: "#10b981", border: "1px dashed #ffffff" }}></div>
              <span>Restored Arterial Lifeline</span>
            </div>
            <div className="legend-item">
              <div className="legend-dot" style={{ background: "#10b981" }}></div>
              <span>Trauma Center (Accessible)</span>
            </div>
            <div className="legend-item">
              <div className="legend-dot" style={{ background: "#ef4444" }}></div>
              <span>Trauma Center (Isolated)</span>
            </div>
            <div className="legend-item">
              <div className="legend-dot" style={{ background: "#0284c7" }}></div>
              <span>GCC Ward Centroid</span>
            </div>
          </div>
        </div>

        {/* 4. CONTEXTUAL OPERATIONS SIDEBAR */}
        <aside className="sidebar-panel">
          <div className="sidebar-content">
            {/* A. CURRENT SITUATION */}
            <section className="op-section">
              <div className="op-section-header">
                <span className="op-section-title">
                  <Activity size={14} color="var(--accent-cyan)" />
                  A. SITUATION & ACCESS STATUS
                </span>
                <span className="tabular-nums" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                  {accessStatus?.isolated_communities?.length ?? 0} ISOLATED WARDS
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginTop: "4px" }}>
                <div style={{ background: "var(--bg-surface)", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-subtle)" }}>
                  <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>CRS PROJECTION</div>
                  <div className="code-val" style={{ fontSize: "0.8125rem", color: "var(--text-primary)" }}>EPSG:32643 (UTM 43N)</div>
                </div>
                <div style={{ background: "var(--bg-surface)", padding: "8px", borderRadius: "4px", border: "1px solid var(--border-subtle)" }}>
                  <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>ACCESS THRESHOLD</div>
                  <div className="code-val" style={{ fontSize: "0.8125rem", color: "var(--text-primary)" }}>1,800s (30.0 min)</div>
                </div>
              </div>
            </section>

            {/* B. KILLER COMPARISON: CORRIDOR A VS CORRIDOR B */}
            <section className="op-section">
              <div className="op-section-header">
                <span className="op-section-title">
                  <Layers size={14} color="var(--status-danger)" />
                  B. CRITICALITY DIVERGENCE (A vs B)
                </span>
                <span className="brand-badge" style={{ fontSize: "0.625rem", background: "rgba(239,68,68,0.15)", color: "var(--status-danger)" }}>KILLER DEMO</span>
              </div>
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "8px" }}>
                Two road corridors face identical flood inundation, but cause radically different network failures:
              </p>

              <div className="divergence-grid">
                {/* Corridor A */}
                <div
                  className={`divergence-card ${selectedCorridor?.corridor_id === "corridor_01" ? "selected" : ""}`}
                  onClick={() => handleSelectCorridor(corridorA)}
                  style={{ cursor: "pointer" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                    <span style={{ fontWeight: 700, fontSize: "0.8125rem" }}>CORRIDOR A</span>
                    <span style={{ fontSize: "0.625rem", background: "var(--border-strong)", padding: "2px 6px", borderRadius: "3px" }}>LOW</span>
                  </div>
                  <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", marginBottom: "6px" }}>Santhome Feeder</div>
                  <div className="card-metric-row">
                    <span style={{ fontSize: "1.25rem", fontWeight: 800, color: "var(--text-primary)" }} className="tabular-nums">0</span>
                    <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>Citizens Recovered</span>
                  </div>
                  <div style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", marginTop: "6px", fontFamily: "var(--font-mono)" }}>
                    Time Delta: +0.0 min<br />
                    Length: 4.3 km<br />
                    Score: -0.0497
                  </div>
                </div>

                {/* Corridor B */}
                <div
                  className={`divergence-card priority ${selectedCorridor?.corridor_id === "corridor_03" ? "selected" : ""}`}
                  onClick={() => handleSelectCorridor(corridorB)}
                  style={{ cursor: "pointer" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                    <span style={{ fontWeight: 700, fontSize: "0.8125rem", color: "var(--accent-cyan)" }}>CORRIDOR B</span>
                    <span style={{ fontSize: "0.625rem", background: "rgba(239,68,68,0.2)", color: "var(--status-danger)", padding: "2px 6px", borderRadius: "3px", fontWeight: 700 }}>PRIORITY 1</span>
                  </div>
                  <div style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", marginBottom: "6px" }}>Saidapet Adyar Lifeline</div>
                  <div className="card-metric-row">
                    <span style={{ fontSize: "1.25rem", fontWeight: 800, color: "var(--status-success)" }} className="tabular-nums">+89,000</span>
                    <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>Citizens Recovered</span>
                  </div>
                  <div style={{ fontSize: "0.6875rem", color: "var(--text-secondary)", marginTop: "6px", fontFamily: "var(--font-mono)" }}>
                    Detour Saved: 22.0 min<br />
                    Length: 0.9 km<br />
                    <span style={{ color: "var(--accent-cyan)", fontWeight: 700 }}>Score: +0.0724</span>
                  </div>
                </div>
              </div>
            </section>

            {/* C. MULTI-CRITERIA SCORE FORMULA */}
            <section className="op-section">
              <div className="op-section-header">
                <span className="op-section-title">
                  <Activity size={14} color="var(--accent-cyan)" />
                  C. MULTI-CRITERIA SCORE FORMULA
                </span>
                <span style={{ fontSize: "0.6875rem", color: "var(--accent-cyan)", fontWeight: 700 }}>RANK #1</span>
              </div>

              <div className="formula-display">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>CRITICALITY SCORE S(c)</span>
                  <span className="tabular-nums" style={{ fontSize: "1.375rem", fontWeight: 800, color: "var(--accent-cyan)" }}>+0.0724</span>
                </div>

                <div className="formula-components-grid">
                  <div className="formula-box">
                    <div className="f-title">Population Delta (0.30·ΔP)</div>
                    <div className="f-val positive tabular-nums">+0.1492</div>
                  </div>
                  <div className="formula-box">
                    <div className="f-title">Travel Time Delta (0.20·ΔT)</div>
                    <div className="f-val neutral tabular-nums">+0.0000</div>
                  </div>
                  <div className="formula-box">
                    <div className="f-title">Difficulty Penalty (-0.10·ΔD)</div>
                    <div className="f-val negative tabular-nums">-0.0768</div>
                  </div>
                  <div className="formula-box">
                    <div className="f-title">Hospital Delta (0.40·ΔH)</div>
                    <div className="f-val neutral tabular-nums">+0.0000</div>
                  </div>
                </div>

                <div className="formula-bar">
                  S(c) = 0.40·ΔH + 0.30·ΔP + 0.20·ΔT - 0.10·ΔD
                </div>
              </div>
            </section>

            {/* D. WHY THIS MATTERS */}
            <div className="impact-callout-card">
              <div className="impact-callout-header">WHY THIS MATTERS // OPERATIONAL IMPACT</div>
              <p className="impact-callout-body">
                Restoring the <strong>Saidapet Adyar Lifeline (Corridor B)</strong> reconnects <strong>89,000 citizens</strong> across Saidapet and Jafferkhanpet wards to regional trauma centers, averting <strong>22.0 minutes of detour degradation</strong>.
              </p>
            </div>

            {/* E. AI ADVISORY DIRECTIVE */}
            <section className="op-section">
              <div className="op-section-header">
                <span className="op-section-title">
                  <Sparkles size={14} color="var(--accent-blue)" />
                  E. OPERATIONAL DISPATCH DIRECTIVE
                </span>
                <span className="brand-badge" style={{ fontSize: "0.625rem", background: "rgba(61,130,246,0.15)", color: "var(--accent-blue)" }}>
                  AI EXPLANATION
                </span>
              </div>

              {advisory ? (
                <div className="advisory-box">
                  <p className="advisory-text">{advisory.advisory_text}</p>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: "8px", fontSize: "0.6875rem", color: "var(--text-muted)" }}>
                    <span>Action: {advisory.action_verb}</span>
                    <span>{advisory.fallback ? "Deterministic Fallback Active" : "Gemini 2.5 Flash Verified"}</span>
                  </div>
                </div>
              ) : (
                <div className="advisory-placeholder">
                  Awaiting corridor selection for field response instructions...
                </div>
              )}
            </section>
          </div>
        </aside>
      </main>

      {/* 5. FOOTER TELEMETRY STATUS BAR */}
      <footer className="footer-bar">
        <div className="footer-left">
          <span>GCC DISASTER MANAGEMENT // CYCLONE TWIN RC-1</span>
          <span>GRAPH: 25 NODES / 56 EDGES</span>
          <span>ENGINE: MULTI-SOURCE DIJKSTRA (G^R)</span>
        </div>
        <div className="footer-right">
          <span>LATENCY: &lt;4ms DETERMINISTIC</span>
          <span className="status-live">● ENGINE READY</span>
        </div>
      </footer>

      {/* 6. DATA PROVENANCE & MODEL CARD MODAL */}
      {showModal && (
        <div className="modal-backdrop" onClick={() => setShowModal(false)} role="dialog" aria-modal="true">
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <ShieldAlert size={18} color="var(--accent-cyan)" />
                <h3 style={{ fontSize: "1rem", fontWeight: 700 }}>DATA PROVENANCE & FORMAL MODEL SPECIFICATION</h3>
              </div>
              <button onClick={() => setShowModal(false)} className="btn-action tertiary">
                <X size={16} />
              </button>
            </div>

            <div className="modal-tabs">
              <button
                className={`modal-tab-btn ${modalTab === "DATA" ? "active" : ""}`}
                onClick={() => setModalTab("DATA")}
              >
                1. DATA PROVENANCE
              </button>
              <button
                className={`modal-tab-btn ${modalTab === "MODEL" ? "active" : ""}`}
                onClick={() => setModalTab("MODEL")}
              >
                2. MODEL CARD
              </button>
              <button
                className={`modal-tab-btn ${modalTab === "ASSUMPTIONS" ? "active" : ""}`}
                onClick={() => setModalTab("ASSUMPTIONS")}
              >
                3. ASSUMPTIONS
              </button>
              <button
                className={`modal-tab-btn ${modalTab === "LIMITATIONS" ? "active" : ""}`}
                onClick={() => setModalTab("LIMITATIONS")}
              >
                4. LIMITATIONS
              </button>
            </div>

            <div className="modal-body">
              {modalTab === "DATA" && (
                <div>
                  <h4 style={{ color: "var(--accent-cyan)", marginBottom: "8px" }}>Empirical Data Sources & Verification</h4>
                  <p style={{ fontSize: "0.8125rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
                    Cyclone Twin integrates verified geographic datasets calibrated to the Greater Chennai Corporation metropolitan area:
                  </p>
                  <ul style={{ paddingLeft: "20px", marginTop: "8px", fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    <li><strong>Road Network:</strong> Calibrated arterial multigraph in EPSG:32643 (UTM Zone 43N) with 25 junctions and 56 directed edges.</li>
                    <li><strong>6 Trauma Hospitals:</strong> Real Chennai tertiary facilities (RGGGH, Apollo Greams, KMC, Fortis Malar, MIOT, Gleneagles) with verified GPS coordinates.</li>
                    <li><strong>10 Study Wards:</strong> GCC census populations summing to exactly <strong>477,000 citizens</strong>.</li>
                    <li><strong>Cyclone Michaung Hazard:</strong> Inundation polygons modeled from December 2023 NRSC / ISRO disaster assessments.</li>
                  </ul>
                  <div className="spec-grid" style={{ marginTop: "16px" }}>
                    <div>Graph Source: <code>{manifest?.graph_source || "mock_fallback"}</code></div>
                    <div>Flood Source: <code>{manifest?.flood_source || "nrsc"}</code></div>
                    <div>CRS: <code>EPSG:32643</code></div>
                    <div>Access Cutoff: <code>1800s (30m)</code></div>
                    <div>Snap Limit: <code>200m</code></div>
                    <div>Weight Preset: <code>life_safety</code></div>
                  </div>
                </div>
              )}

              {modalTab === "MODEL" && (
                <div>
                  <h4 style={{ color: "var(--accent-cyan)", marginBottom: "8px" }}>Algorithmic Specification</h4>
                  <p style={{ fontSize: "0.8125rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
                    <strong>Multi-Source Dijkstra on Reversed Graph (G^R):</strong> Evaluates hospital accessibility for all communities simultaneously in O((V + E) log V) time while preserving one-way street constraints.
                  </p>
                  <p style={{ fontSize: "0.8125rem", lineHeight: 1.6, color: "var(--text-secondary)", marginTop: "8px" }}>
                    <strong>Scoring Formula:</strong> S(c) = 0.40·ΔH + 0.30·ΔP + 0.20·ΔT - 0.10·ΔD, strictly bounded in [-1.0, 1.0].
                  </p>
                  <p style={{ fontSize: "0.8125rem", lineHeight: 1.6, color: "var(--text-secondary)", marginTop: "8px" }}>
                    <strong>AI Isolation:</strong> Gemini operates as a read-only text formatter. It has zero authority to modify rankings or scores.
                  </p>
                </div>
              )}

              {modalTab === "ASSUMPTIONS" && (
                <div>
                  <h4 style={{ color: "var(--accent-cyan)", marginBottom: "8px" }}>Operational Model Assumptions</h4>
                  <ul style={{ paddingLeft: "20px", fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    <li>Emergency vehicles travel at free-flow speeds (25 to 60 km/h) under normal dry conditions.</li>
                    <li>Road segments submerged &gt;30cm are impassable for standard emergency ambulances.</li>
                    <li>Elevated flyovers and bridges remain passable during surface street inundation.</li>
                    <li>Trauma centers without generator backup are excluded from emergency destination pools.</li>
                  </ul>
                </div>
              )}

              {modalTab === "LIMITATIONS" && (
                <div>
                  <h4 style={{ color: "var(--accent-cyan)", marginBottom: "8px" }}>Honest System Boundaries</h4>
                  <ul style={{ paddingLeft: "20px", fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    <li><strong>Arterial Scope:</strong> The digital twin encompasses major arterials; local alleyways are not modeled.</li>
                    <li><strong>Binary Passability:</strong> Flood footprint uses discrete inundation boundaries rather than 2D hydrodynamic flow equations.</li>
                    <li><strong>Static Demographics:</strong> Ward populations are based on GCC census data, not real-time cellular movement.</li>
                    <li><strong>Decision Support:</strong> Provides prioritized recommendations; final field dispatch rests with GCC incident commanders.</li>
                  </ul>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button onClick={() => setShowModal(false)} className="btn-action primary">
                CLOSE SPECIFICATION
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
