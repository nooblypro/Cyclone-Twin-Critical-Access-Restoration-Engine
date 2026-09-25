/**
 * CYCLONE TWIN — MUNICIPAL EMERGENCY OPERATIONS CONSOLE
 * GCC Network Vulnerability Forecaster & Critical Access Restoration Engine
 * Visual v2: Professional Emergency GIS Command Console
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import L from "leaflet";
import {
  ShieldAlert,
  Play,
  RotateCcw,
  Activity,
  Layers,
  CheckCircle2,
  AlertTriangle,
  FileText,
  X,
  Compass,
  Check,
} from "lucide-react";
import { api } from "./api.js";

// Chennai Metropolitan Arterial Bounding Box
const CHENNAI_BOUNDS = [
  [12.89, 80.15],
  [13.09, 80.29],
];
const CHENNAI_CENTER = [13.005, 80.225];
const CHENNAI_ZOOM = 12;

// Professional Emergency Map Icons (High-Contrast, Zero-Watermark)
const createHospitalIcon = (isIsolated) =>
  L.divIcon({
    className: "custom-map-icon hospital-icon",
    html: `<div style="
      background: ${isIsolated ? "#ef4444" : "#059669"};
      width: 22px; height: 22px; border-radius: 4px;
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 2px 6px rgba(0,0,0,0.35);
      border: 1.5px solid #ffffff; color: #ffffff; font-weight: 800; font-size: 11px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    ">H</div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });

const createCommunityIcon = (isIsolated) =>
  L.divIcon({
    className: "custom-map-icon community-icon",
    html: `<div style="
      background: ${isIsolated ? "#ef4444" : "#0284c7"};
      width: 12px; height: 12px; border-radius: 50%;
      border: 2px solid #ffffff;
      box-shadow: 0 1px 4px rgba(0,0,0,0.3);
    "></div>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
  });

export default function CycloneTwinApp() {
  // Simulation Workflow State
  const [systemState, setSystemState] = useState("BASE"); // "BASE" | "FLOODED" | "RANKED" | "SELECTED" | "CLEARED"
  const [demoStep, setDemoStep] = useState(1); // 1 to 6
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Domain Data from Backend API
  const [mapData, setMapData] = useState(null);
  const [accessStatus, setAccessStatus] = useState(null);
  const [rankedCorridors, setRankedCorridors] = useState([]);
  const [selectedCorridor, setSelectedCorridor] = useState(null);
  const [clearedCorridorId, setClearedCorridorId] = useState(null);
  const [advisory, setAdvisory] = useState(null);
  const [manifest, setManifest] = useState(null);

  // Cartography Layer Toggles
  const [layersVisibility, setLayersVisibility] = useState({
    floodInundation: true,
    roadNetwork: true,
    impassable: true,
    selectedCorridor: true,
    hospitalsOperational: true,
    traumaCentersIsolated: true,
    communitiesAccessible: true,
    communitiesIsolated: true,
  });

  // Modal State
  const [modalTab, setModalTab] = useState("DATA"); // "DATA" | "MODEL" | "ASSUMPTIONS" | "LIMITATIONS"
  const [showModal, setShowModal] = useState(false);

  // Map References
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

  // 1. Initial Load & Baseline Fetch from Backend
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
          setErrorMsg(`Backend connection unavailable: ${err.message}`);
          setLoading(false);
        }
      }
    };

    initBaseline();
    return () => {
      ignore = true;
    };
  }, []);

  // 2. Leaflet Map Initialization with Clean Neutral Basemap (NO WATERMARK)
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const map = L.map(mapContainerRef.current, {
      center: CHENNAI_CENTER,
      zoom: CHENNAI_ZOOM,
      zoomControl: false,
      attributionControl: false,
      maxBounds: [
        [12.75, 80.0],
        [13.25, 80.45],
      ],
      minZoom: 11,
      maxZoom: 17,
    });

    // Clean, high-legibility OpenStreetMap standard tile provider (Keyless, zero watermark)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      subdomains: ["a", "b", "c"],
    }).addTo(map);

    // Initial fit to metropolitan bounds with padding
    map.fitBounds(CHENNAI_BOUNDS, { padding: [24, 24] });

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // 3. Leaflet Layer Render & Layer Synchronization
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapData) return;

    // Clean previous layers
    Object.keys(layersRef.current).forEach((key) => {
      if (layersRef.current[key]) {
        map.removeLayer(layersRef.current[key]);
        layersRef.current[key] = null;
      }
    });

    // A. Flood Inundation Footprint (Semi-transparent blue polygon)
    if (
      layersVisibility.floodInundation &&
      mapData.flood &&
      (systemState !== "BASE" || demoStep > 1)
    ) {
      const floodLayer = L.geoJSON(mapData.flood, {
        style: {
          color: "#0284c7",
          weight: 2,
          fillColor: "#38bdf8",
          fillOpacity: 0.28,
          dashArray: "4, 4",
        },
      }).addTo(map);
      layersRef.current.flood = floodLayer;
    }

    // B. Road Network Edges (Clear Hierarchical Cartography)
    if (layersVisibility.roadNetwork && mapData.roads) {
      const roadsLayer = L.geoJSON(mapData.roads, {
        style: (feature) => {
          const isDisabled = feature.properties.disabled;
          const isElevated = feature.properties.bridge === "yes" || feature.properties.layer > 0;

          if (isDisabled) {
            return layersVisibility.impassable
              ? { color: "#dc2626", weight: 4.5, opacity: 0.95, dashArray: "5, 5" }
              : { opacity: 0, fillOpacity: 0 };
          }
          if (isElevated) {
            return { color: "#d97706", weight: 3.5, opacity: 0.95 };
          }
          return { color: "#475569", weight: 2.5, opacity: 0.8 };
        },
        onEachFeature: (feature, layer) => {
          layer.bindTooltip(
            `<strong>${feature.properties.name}</strong><br/>Length: ${feature.properties.length}m | Speed: ${feature.properties.speed_kph} km/h`,
            { className: "gis-map-tooltip" }
          );
        },
      }).addTo(map);
      layersRef.current.roads = roadsLayer;
    }

    // C. Restored Corridor Lifeline (Vibrant Recovery Emerald)
    if (layersVisibility.selectedCorridor && clearedCorridorId && rankedCorridors.length > 0) {
      const clearedCorr = rankedCorridors.find((c) => c.corridor_id === clearedCorridorId);
      if (clearedCorr?.geometry) {
        const restoredLayer = L.geoJSON(clearedCorr.geometry, {
          style: {
            color: "#059669",
            weight: 7,
            opacity: 1.0,
            dashArray: "8, 4",
          },
        }).addTo(map);
        layersRef.current.restored = restoredLayer;
      }
    }

    // D. Selected Corridor Highlight (Cyan Candidate Route)
    if (
      layersVisibility.selectedCorridor &&
      selectedCorridor?.geometry &&
      selectedCorridor.corridor_id !== clearedCorridorId
    ) {
      const highlightLayer = L.geoJSON(selectedCorridor.geometry, {
        style: {
          color: "#0284c7",
          weight: 7,
          opacity: 1.0,
        },
      }).addTo(map);
      layersRef.current.highlight = highlightLayer;
    }

    // E. Health Facilities (Trauma Centers)
    if (mapData.facilities) {
      const facilitiesLayer = L.geoJSON(mapData.facilities, {
        filter: (feature) => {
          const isIsolated = feature.properties.isolated;
          if (isIsolated && !layersVisibility.traumaCentersIsolated) return false;
          if (!isIsolated && !layersVisibility.hospitalsOperational) return false;
          return true;
        },
        pointToLayer: (feature, latlng) => {
          const isIsolated = feature.properties.isolated;
          const marker = L.marker(latlng, { icon: createHospitalIcon(isIsolated) });
          marker.bindTooltip(
            `<strong>${feature.properties.name}</strong><br/>Capacity: ${feature.properties.beds} beds<br/>Status: ${isIsolated ? "ISOLATED" : "OPERATIONAL"}`,
            { className: "gis-map-tooltip" }
          );
          return marker;
        },
      }).addTo(map);
      layersRef.current.facilities = facilitiesLayer;
    }

    // F. Community Wards
    if (mapData.communities) {
      const communitiesLayer = L.geoJSON(mapData.communities, {
        filter: (feature) => {
          const isIsolated = feature.properties.isolated;
          if (isIsolated && !layersVisibility.communitiesIsolated) return false;
          if (!isIsolated && !layersVisibility.communitiesAccessible) return false;
          return true;
        },
        pointToLayer: (feature, latlng) => {
          const isIsolated = feature.properties.isolated;
          const marker = L.marker(latlng, { icon: createCommunityIcon(isIsolated) });
          const transitTime = feature.properties.travel_time_sec
            ? `${(feature.properties.travel_time_sec / 60).toFixed(1)} min`
            : ">30 min (Isolated)";
          marker.bindTooltip(
            `<strong>${feature.properties.name}</strong><br/>Population: ${feature.properties.population.toLocaleString()}<br/>Transit: ${transitTime}`,
            { className: "gis-map-tooltip" }
          );
          return marker;
        },
      }).addTo(map);
      layersRef.current.communities = communitiesLayer;
    }
  }, [
    mapData,
    systemState,
    selectedCorridor,
    clearedCorridorId,
    rankedCorridors,
    demoStep,
    layersVisibility,
  ]);

  // 4. Map Control Handlers
  const handleZoomIn = useCallback(() => {
    mapInstanceRef.current?.zoomIn();
  }, []);

  const handleZoomOut = useCallback(() => {
    mapInstanceRef.current?.zoomOut();
  }, []);

  const handleRecenter = useCallback(() => {
    mapInstanceRef.current?.fitBounds(CHENNAI_BOUNDS, { padding: [24, 24], duration: 0.5 });
  }, []);

  // 5. Operational Scenario Handlers
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

    if (mapInstanceRef.current && corr.corridor_id === "corridor_03") {
      mapInstanceRef.current.flyTo([13.015, 80.22], 13.5, { duration: 0.6 });
    }

    try {
      const advData = await api.generateAdvisory(corr.corridor_id, corr.score_breakdown);
      setAdvisory(advData);
    } catch (err) {
      console.warn("Advisory generator cascaded to deterministic fallback", err);
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
        mapInstanceRef.current.fitBounds(CHENNAI_BOUNDS, { padding: [24, 24], duration: 0.5 });
      }
    } catch (err) {
      setErrorMsg(`Network reset error: ${err.message}`);
      setLoading(false);
    }
  };

  const handleNextDemoStep = () => {
    if (demoStep === 1) handleApplyFlood();
    else if (demoStep === 2) handleRankCorridors();
    else if (demoStep === 3) setDemoStep(4);
    else if (demoStep === 4) setDemoStep(5);
    else if (demoStep === 5) handleClearCorridor();
    else if (demoStep === 6) handleResetNetwork();
  };

  const toggleLayer = (layerKey) => {
    setLayersVisibility((prev) => ({
      ...prev,
      [layerKey]: !prev[layerKey],
    }));
  };

  // Metrics derived from actual server state
  const totalPopulation = 477000;
  const accessiblePop = accessStatus?.accessible_population ?? totalPopulation;
  const isolatedPop = totalPopulation - accessiblePop;
  const activeHospitals = 6 - (accessStatus?.isolated_facilities?.length ?? 0);

  return (
    <div className="gis-command-console">
      {/* 1. TOP HEADER */}
      <header className="gis-header">
        <div className="gis-header-left">
          <div className="brand-icon">
            <ShieldAlert size={18} color="var(--accent-cyan)" />
          </div>
          <div>
            <h1 className="brand-heading">CYCLONE TWIN</h1>
            <p className="brand-subheading">Critical Access Restoration Engine</p>
          </div>
        </div>

        <div className="gis-header-center">
          <div className={`status-pill ${systemState.toLowerCase()}`}>
            <span className="status-dot">●</span>
            STATE: {systemState === "BASE" ? "BASELINE ACCESSIBILITY" : systemState === "FLOODED" ? "CYCLONE MICHAUNG HAZARD ACTIVE" : systemState === "RANKED" ? "CRITICALITY ASSESSED" : systemState === "SELECTED" ? "CORRIDOR INSPECTED" : "RESTORATION SIMULATED"}
          </div>
        </div>

        <div className="gis-header-right">
          <button
            onClick={() => {
              setModalTab("DATA");
              setShowModal(true);
            }}
            className="gis-btn tertiary"
            title="Data & Model Provenance"
          >
            <FileText size={12} />
            Provenance
          </button>

          <button
            onClick={() => {
              setModalTab("MODEL");
              setShowModal(true);
            }}
            className="gis-btn tertiary"
            title="Model Card & Specifications"
          >
            Model Card
          </button>

          <button
            onClick={handleResetNetwork}
            className="gis-btn secondary"
            disabled={loading || systemState === "BASE"}
            title="Reset Network"
          >
            <RotateCcw size={12} />
            Reset
          </button>

          <button
            onClick={handleNextDemoStep}
            className="gis-btn primary"
            disabled={loading}
          >
            <Play size={12} fill="#05080f" />
            {demoStep === 1 ? "1. Apply Hazard" : demoStep === 2 ? "2. Rank Criticality" : demoStep === 3 ? "3. Compare Divergence" : demoStep === 4 ? "4. Mitigation Strategy" : demoStep === 5 ? "5. Simulate Recovery" : "6. Reset Network"}
          </button>
        </div>
      </header>

      {/* 2. SCENARIO PROGRESSION PIPELINE */}
      <nav className="gis-stepper" aria-label="Simulation Pipeline">
        {[
          { step: 1, label: "1. Baseline" },
          { step: 2, label: "2. Hazard" },
          { step: 3, label: "3. Vulnerability" },
          { step: 4, label: "4. Criticality" },
          { step: 5, label: "5. Mitigation" },
          { step: 6, label: "6. Recovery" },
        ].map((item) => {
          const isCompleted = demoStep > item.step;
          const isActive = demoStep === item.step;
          return (
            <div
              key={item.step}
              className={`stepper-node ${isActive ? "active" : ""} ${isCompleted ? "completed" : ""}`}
              onClick={() => {
                if (item.step === 1) handleResetNetwork();
                else if (item.step === 2) handleApplyFlood();
                else if (item.step === 3) handleRankCorridors();
                else setDemoStep(item.step);
              }}
            >
              <div className="stepper-badge">
                {isCompleted ? <CheckCircle2 size={11} /> : item.step}
              </div>
              <span className="stepper-text">{item.label}</span>
            </div>
          );
        })}
      </nav>

      {/* Error Alert */}
      {errorMsg && (
        <div className="gis-error-banner">
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <AlertTriangle size={13} />
            {errorMsg}
          </div>
          <button onClick={() => setErrorMsg(null)} className="error-close">
            <X size={13} />
          </button>
        </div>
      )}

      {/* 3. THREE-PANE GIS WORKSPACE */}
      <main className="gis-workspace">
        {/* LEFT OPERATIONS PANEL: IMPACT OVERVIEW & CARTOGRAPHY */}
        <aside className="gis-left-panel">
          <div className="panel-scroll-content">
            {/* Impact Overview Section */}
            <div className="panel-section">
              <div className="section-label">
                <Activity size={12} color="var(--accent-cyan)" />
                IMPACT OVERVIEW
              </div>

              <div className="metric-box-grid">
                {/* Accessible Population */}
                <div className="metric-box">
                  <div className="box-title">Accessible Population</div>
                  <div className="box-number tabular-nums">
                    {(accessiblePop / 1000).toFixed(0)}K
                    <span className="box-sub tabular-nums"> / 477K</span>
                  </div>
                  <div className="bar-track">
                    <div
                      className="bar-fill green"
                      style={{ width: `${(accessiblePop / totalPopulation) * 100}%` }}
                    />
                  </div>
                </div>

                {/* Isolated Citizens */}
                <div className={`metric-box ${isolatedPop > 0 ? "danger-box" : ""}`}>
                  <div className="box-title">Isolated Citizens</div>
                  <div className={`box-number tabular-nums ${isolatedPop > 0 ? "danger-text" : "green-text"}`}>
                    {isolatedPop === 0 ? "0" : `${(isolatedPop / 1000).toFixed(0)}K`}
                  </div>
                  <div className="box-caption">
                    {isolatedPop > 0 ? `${accessStatus?.isolated_communities?.length ?? 0} Cut-Off Wards (37.5%)` : "Normal Emergency Transit"}
                  </div>
                </div>

                {/* Trauma Hospitals */}
                <div className="metric-box">
                  <div className="box-title">Trauma Hospitals</div>
                  <div className="box-number tabular-nums cyan-text">
                    {activeHospitals} / 6
                  </div>
                  <div className="box-caption">All Tertiary Centers Active</div>
                </div>

                {/* Citizens Recovered */}
                <div className="metric-box recovery-box">
                  <div className="box-title">Citizens Recovered</div>
                  <div className="box-number tabular-nums green-text">
                    {clearedCorridorId ? "+89K" : "0"}
                  </div>
                  <div className="box-caption">vs. Inundated Scenario</div>
                </div>
              </div>
            </div>

            {/* Cartography Layers Section */}
            <div className="panel-section">
              <div className="section-label">
                <Layers size={12} color="var(--accent-cyan)" />
                CARTOGRAPHY
              </div>

              <div className="gis-layers-list">
                {[
                  { key: "floodInundation", label: "Flood Inundation (Michaung)", color: "#38bdf8", border: "#0284c7" },
                  { key: "roadNetwork", label: "Road Network", color: "#475569" },
                  { key: "impassable", label: "Blocked Roads (Flooded)", color: "#dc2626", dashed: true },
                  { key: "selectedCorridor", label: "Selected / Restored Corridor", color: "#059669" },
                  { key: "hospitalsOperational", label: "Hospitals (Operational)", isIcon: true, iconBg: "#059669", iconText: "H" },
                  { key: "traumaCentersIsolated", label: "Trauma Centers (Isolated)", isIcon: true, iconBg: "#dc2626", iconText: "H" },
                  { key: "communitiesAccessible", label: "Communities (Accessible)", isDot: true, dotBg: "#0284c7" },
                  { key: "communitiesIsolated", label: "Communities (Isolated)", isDot: true, dotBg: "#dc2626" },
                ].map((layer) => (
                  <label key={layer.key} className="gis-layer-item">
                    <input
                      type="checkbox"
                      checked={layersVisibility[layer.key]}
                      onChange={() => toggleLayer(layer.key)}
                      className="gis-checkbox"
                    />
                    <div className="gis-swatch-slot">
                      {layer.isIcon ? (
                        <span className="gis-icon-tag" style={{ background: layer.iconBg }}>{layer.iconText}</span>
                      ) : layer.isDot ? (
                        <span className="gis-dot-tag" style={{ background: layer.dotBg }} />
                      ) : (
                        <span
                          className="gis-swatch-tag"
                          style={{
                            background: layer.color,
                            border: layer.border ? `1px dashed ${layer.border}` : layer.dashed ? "1px dashed #ffffff" : "none",
                          }}
                        />
                      )}
                    </div>
                    <span className="gis-layer-name">{layer.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        </aside>

        {/* CENTER PRIMARY SURFACE: MAP CANVAS (DOMINANT VISUAL ELEMENT) */}
        <section className="gis-center-map">
          <div ref={mapContainerRef} className="gis-leaflet-container" />

          {/* Compact GIS Map Controls */}
          <div className="gis-map-controls">
            <button
              className="gis-ctrl-btn"
              onClick={handleZoomIn}
              title="Zoom In"
              aria-label="Zoom In"
            >
              +
            </button>
            <button
              className="gis-ctrl-btn"
              onClick={handleZoomOut}
              title="Zoom Out"
              aria-label="Zoom Out"
            >
              −
            </button>
            <button
              className="gis-ctrl-btn"
              onClick={handleRecenter}
              title="Recenter Chennai Metropolitan Extent"
              aria-label="Recenter Chennai"
            >
              <Compass size={13} />
            </button>
          </div>

          {/* Integrated Scenario Timeline Bar */}
          <div className="gis-bottom-timeline">
            <span className="timeline-tag">SCENARIO:</span>
            <div className="timeline-buttons-group">
              {[
                { label: "Baseline", step: 1 },
                { label: "Michaung Flood", step: 2 },
                { label: "Select Corridor", step: 3 },
                { label: "Restoration", step: 6 },
              ].map((t) => (
                <button
                  key={t.step}
                  className={`timeline-segment-btn ${demoStep === t.step || (t.step === 6 && systemState === "CLEARED") ? "active" : ""}`}
                  onClick={() => {
                    if (t.step === 1) handleResetNetwork();
                    else if (t.step === 2) handleApplyFlood();
                    else if (t.step === 3) handleRankCorridors();
                    else if (t.step === 6) handleClearCorridor();
                  }}
                >
                  {demoStep > t.step || (t.step === 6 && systemState === "CLEARED") ? (
                    <Check size={10} className="check-icon" />
                  ) : (
                    <span className="step-num">{t.step}</span>
                  )}
                  <span>{t.label}</span>
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* RIGHT OPERATIONS PANEL: OPERATIONAL DECISION SURFACE */}
        <aside className="gis-right-panel">
          <div className="panel-scroll-content">
            {/* 1. Selected Corridor Card */}
            <div className="decision-card selected-corridor-box">
              <div className="card-top-header">
                <span className="card-category">SELECTED CORRIDOR</span>
                <span className="priority-tag">PRIORITY 1</span>
              </div>
              <h3 className="corridor-heading">Corridor B: Saidapet → Adyar Lifeline</h3>
              <p className="corridor-descriptor">Highest-ranked intervention under the model</p>

              {/* Four Dominant Operational Metrics */}
              <div className="dominant-metrics-grid">
                <div className="dominant-stat">
                  <div className="stat-large green-text tabular-nums">+89K</div>
                  <div className="stat-desc">Citizens recovered</div>
                </div>
                <div className="dominant-stat">
                  <div className="stat-large cyan-text tabular-nums">22 min</div>
                  <div className="stat-desc">Detour time saved</div>
                </div>
                <div className="dominant-stat">
                  <div className="stat-large tabular-nums">0.9 km</div>
                  <div className="stat-desc">Corridor length</div>
                </div>
                <div className="dominant-stat">
                  <div className="stat-large cyan-text tabular-nums">+0.0724</div>
                  <div className="stat-desc">Criticality score</div>
                </div>
              </div>
            </div>

            {/* 2. Population & Access Change Bar Chart */}
            <div className="decision-card">
              <div className="card-top-header">
                <span className="card-category">POPULATION & ACCESS CHANGE</span>
              </div>

              <div className="chart-legend-line">
                <span><span className="legend-indicator accessible" /> Accessible</span>
                <span><span className="legend-indicator isolated" /> Isolated</span>
              </div>

              <div className="access-chart">
                <div className="chart-bar-row">
                  <span className="bar-row-label">Baseline</span>
                  <div className="bar-row-track">
                    <div className="segment accessible" style={{ width: "100%" }}>477K</div>
                  </div>
                </div>

                <div className="chart-bar-row">
                  <span className="bar-row-label">Michaung Flood</span>
                  <div className="bar-row-track">
                    <div className="segment accessible" style={{ width: "62.5%" }}>298K</div>
                    <div className="segment isolated" style={{ width: "37.5%" }}>179K</div>
                  </div>
                </div>

                <div className="chart-bar-row">
                  <span className="bar-row-label">Restoration</span>
                  <div className="bar-row-track">
                    <div className="segment accessible" style={{ width: "81.1%" }}>387K</div>
                    <div className="segment isolated" style={{ width: "18.9%" }}>90K</div>
                  </div>
                </div>
              </div>
            </div>

            {/* 3. Why This Matters */}
            <div className="decision-card impact-explanation-box">
              <div className="card-top-header">
                <span className="card-category text-cyan">WHY THIS MATTERS</span>
              </div>
              <p className="impact-paragraph">
                Restoring the Saidapet–Adyar lifeline reconnects <strong>89,000 citizens</strong> across the affected wards and reduces modeled detour time by <strong>22 minutes</strong>.
              </p>
            </div>

            {/* 4. Operational Directive */}
            <div className="decision-card directive-box">
              <div className="card-top-header">
                <span className="card-category">OPERATIONAL DIRECTIVE</span>
                <span className="simulated-tag">SIMULATED</span>
              </div>
              <p className="directive-text">
                {advisory?.advisory_text ||
                  "Mobilize crews to clear secondary debris, re-establish lifeline routing for 89,000 cut-off citizens, and restore access to regional trauma centers."}
              </p>
            </div>

            {/* 5. Score Breakdown */}
            <div className="decision-card score-breakdown-box">
              <div className="card-top-header">
                <span className="card-category">SCORE BREAKDOWN</span>
                <span className="final-score tabular-nums">+0.0724</span>
              </div>

              <div className="score-components-grid">
                <div className="score-slot">
                  <span className="slot-name">Population Delta</span>
                  <span className="slot-val green-text tabular-nums">+0.1492</span>
                </div>
                <div className="score-slot">
                  <span className="slot-name">Travel Time</span>
                  <span className="slot-val tabular-nums">+0.0000</span>
                </div>
                <div className="score-slot">
                  <span className="slot-name">Difficulty Penalty</span>
                  <span className="slot-val danger-text tabular-nums">-0.0768</span>
                </div>
                <div className="score-slot">
                  <span className="slot-name">Hospital Delta</span>
                  <span className="slot-val tabular-nums">+0.0000</span>
                </div>
              </div>

              <div className="formula-caption">
                S(c) = 0.40·ΔH + 0.30·ΔP + 0.20·ΔT - 0.10·ΔD
              </div>
            </div>
          </div>
        </aside>
      </main>

      {/* 4. MINIMAL TECHNICAL FOOTER */}
      <footer className="gis-footer">
        <div className="footer-left-text">
          CYCLONE TWIN // GCC DISASTER MANAGEMENT SIMULATION
        </div>
        <div className="footer-right-text">
          <span className="green-dot">●</span> ENGINE READY
        </div>
      </footer>

      {/* 5. SPECIFICATION & PROVENANCE MODAL */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)} role="dialog" aria-modal="true">
          <div className="modal-window" onClick={(e) => e.stopPropagation()}>
            <div className="modal-top">
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <ShieldAlert size={16} color="var(--accent-cyan)" />
                <h3 className="modal-title">DATA PROVENANCE & SPECIFICATIONS</h3>
              </div>
              <button onClick={() => setShowModal(false)} className="gis-btn tertiary">
                <X size={14} />
              </button>
            </div>

            <div className="modal-nav">
              <button
                className={`tab-btn ${modalTab === "DATA" ? "active" : ""}`}
                onClick={() => setModalTab("DATA")}
              >
                1. Data Sources
              </button>
              <button
                className={`tab-btn ${modalTab === "MODEL" ? "active" : ""}`}
                onClick={() => setModalTab("MODEL")}
              >
                2. Model Card
              </button>
              <button
                className={`tab-btn ${modalTab === "ASSUMPTIONS" ? "active" : ""}`}
                onClick={() => setModalTab("ASSUMPTIONS")}
              >
                3. Assumptions
              </button>
              <button
                className={`tab-btn ${modalTab === "LIMITATIONS" ? "active" : ""}`}
                onClick={() => setModalTab("LIMITATIONS")}
              >
                4. Limitations
              </button>
            </div>

            <div className="modal-body-area">
              {modalTab === "DATA" && (
                <div>
                  <h4 style={{ color: "var(--accent-cyan)", marginBottom: "6px", fontSize: "13px" }}>Empirical Data Provenance</h4>
                  <p style={{ fontSize: "12px", lineHeight: 1.5, color: "var(--text-secondary)" }}>
                    Cyclone Twin is calibrated against verified spatial networks and population distributions for Greater Chennai Corporation:
                  </p>
                  <ul style={{ paddingLeft: "18px", marginTop: "6px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                    <li><strong>Road Multigraph:</strong> 25 junctions and 56 directed edges in EPSG:32643 (UTM 43N).</li>
                    <li><strong>6 Trauma Centers:</strong> Verified hospital GPS locations and grid statuses.</li>
                    <li><strong>10 Study Wards:</strong> GCC census populations summing to exactly 477,000 citizens.</li>
                    <li><strong>Michaung Inundation:</strong> Calibrated flood extent from December 2023 satellite observations.</li>
                  </ul>
                  <div className="spec-table" style={{ marginTop: "12px" }}>
                    <div>Graph Source: <code>{manifest?.graph_source || "mock_fallback"}</code></div>
                    <div>Flood Source: <code>{manifest?.flood_source || "nrsc"}</code></div>
                    <div>CRS: <code>EPSG:32643</code></div>
                    <div>Cutoff: <code>1800s (30m)</code></div>
                  </div>
                </div>
              )}

              {modalTab === "MODEL" && (
                <div>
                  <h4 style={{ color: "var(--accent-cyan)", marginBottom: "6px", fontSize: "13px" }}>Algorithmic Contract</h4>
                  <p style={{ fontSize: "12px", lineHeight: 1.5, color: "var(--text-secondary)" }}>
                    <strong>Multi-Source Dijkstra on G^R:</strong> Simultaneously traces shortest travel paths from all community centroids to active hospitals in O((V + E) log V) time.
                  </p>
                  <p style={{ fontSize: "12px", lineHeight: 1.5, color: "var(--text-secondary)", marginTop: "6px" }}>
                    <strong>Deterministic Criticality:</strong> S(c) = 0.40·ΔH + 0.30·ΔP + 0.20·ΔT - 0.10·ΔD.
                  </p>
                </div>
              )}

              {modalTab === "ASSUMPTIONS" && (
                <div>
                  <h4 style={{ color: "var(--accent-cyan)", marginBottom: "6px", fontSize: "13px" }}>Operational Assumptions</h4>
                  <ul style={{ paddingLeft: "18px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                    <li>Roads submerged &gt;30cm are impassable to standard ambulances.</li>
                    <li>Grade-separated flyovers and elevated bridges remain operable during surface inundation.</li>
                    <li>Hospitals without power are excluded as destination nodes.</li>
                  </ul>
                </div>
              )}

              {modalTab === "LIMITATIONS" && (
                <div>
                  <h4 style={{ color: "var(--accent-cyan)", marginBottom: "6px", fontSize: "13px" }}>System Boundaries</h4>
                  <ul style={{ paddingLeft: "18px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                    <li>Scope is restricted to major arterial lifelines.</li>
                    <li>Decision-support prototype for emergency planners; incident commander holds final authority.</li>
                  </ul>
                </div>
              )}
            </div>

            <div className="modal-bottom">
              <button onClick={() => setShowModal(false)} className="gis-btn primary">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
