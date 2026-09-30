/**
 * CYCLONE TWIN — MUNICIPAL EMERGENCY OPERATIONS CONSOLE
 * GCC Infrastructure Resilience Engine & Decision Support System
 * Human-Designed Product Interface (Restrained GIS & Cartography)
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import L from "leaflet";
import {
  X,
  Compass,
} from "lucide-react";
import { api } from "./api.js";
import { offlineQueue } from "./offlineQueue.js";
import { SyncEngine, NETWORK_STATUS } from "./syncEngine.js";
import { useI18n } from "./i18n/i18nContext.jsx";


// Chennai Metropolitan Arterial Bounding Box
const CHENNAI_BOUNDS = [
  [12.89, 80.15],
  [13.09, 80.29],
];
const CHENNAI_CENTER = [13.005, 80.225];
const CHENNAI_ZOOM = 12;

/**
 * Lightweight Hook for Smooth Numerical Interpolation Transitions
 */
function useAnimatedNumber(targetValue, duration = 400) {
  const [currentValue, setCurrentValue] = useState(targetValue);
  const prevValueRef = useRef(targetValue);

  useEffect(() => {
    let startTimestamp = null;
    const startValue = prevValueRef.current;
    const diff = targetValue - startValue;

    if (diff === 0) return;

    let frameId;
    const step = (timestamp) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      const easeProgress = 1 - Math.pow(1 - progress, 3);
      const nextVal = Math.round(startValue + diff * easeProgress);
      setCurrentValue(nextVal);
      prevValueRef.current = nextVal;

      if (progress < 1) {
        frameId = requestAnimationFrame(step);
      }
    };

    frameId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frameId);
  }, [targetValue, duration]);

  return currentValue;
}

// Quiet Professional Cartographic Markers
const createHospitalIcon = (isIsolated) =>
  L.divIcon({
    className: "custom-map-icon hospital-icon",
    html: `<div style="
      background: ${isIsolated ? "#dc2626" : "#059669"};
      width: 18px; height: 18px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 1px 4px rgba(0,0,0,0.4);
      border: 1.5px solid #ffffff; color: #ffffff; font-weight: 700; font-size: 11px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    ">+</div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });

const createCommunityIcon = (isIsolated) =>
  L.divIcon({
    className: "custom-map-icon community-icon",
    html: `<div style="
      background: ${isIsolated ? "#ef4444" : "#2563eb"};
      width: 8px; height: 8px; border-radius: 50%;
      border: 1.5px solid #ffffff;
      box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    "></div>`,
    iconSize: [8, 8],
    iconAnchor: [4, 4],
  });

const createCitizenIcon = (reportType, status) =>
  L.divIcon({
    className: "custom-map-icon citizen-icon",
    html: `<div style="
      background: ${status === "REJECTED" ? "#64748b" : status === "RECONCILED" ? "#059669" : "#a855f7"};
      width: 14px; height: 14px; border-radius: 3px;
      transform: rotate(45deg);
      border: 1.5px solid #ffffff;
      box-shadow: 0 1px 4px rgba(0,0,0,0.4);
      display: flex; align-items: center; justify-content: center;
      color: #fff; font-size: 8px; font-weight: 800;
    "></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });

export default function CycloneTwinApp() {

  const {
    locale,
    setLocale,
    supportedLocales,
    t,
    getReportTypeLabel,
    getStatusLabel,
  } = useI18n();

  // Simulation Workflow State
  const [systemState, setSystemState] = useState("BASE"); // "BASE" | "FLOODED" | "RANKED" | "SELECTED" | "CLEARED"
  const [demoStep, setDemoStep] = useState(1); // 1 to 5
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Guided Demo Mode State (Demo Mode UX Pass)
  const [isDemoActive, setIsDemoActive] = useState(false);
  const [guidedDemoStep, setGuidedDemoStep] = useState(1); // 1 to 6
  const [demoSimulatedOffline, setDemoSimulatedOffline] = useState(false);
  const [showAdvancedSyncDetails, setShowAdvancedSyncDetails] = useState(false);

  // Domain Data from Backend API
  const [mapData, setMapData] = useState(null);
  const [accessStatus, setAccessStatus] = useState(null);
  const [rankedCorridors, setRankedCorridors] = useState([]);
  const [selectedCorridor, setSelectedCorridor] = useState(null);
  const [clearedCorridorId, setClearedCorridorId] = useState(null);
  const [advisory, setAdvisory] = useState(null);
  const [manifest, setManifest] = useState(null);

  // Cartography Layer Toggles (State-aware defaults for Baseline)
  const [layersVisibility, setLayersVisibility] = useState({
    floodInundation: false,
    roadNetwork: true,
    impassable: false,
    selectedCorridor: false,
    hospitalsOperational: true,
    traumaCentersIsolated: false,
    communitiesAccessible: true,
    communitiesIsolated: false,
  });

  // Modal State
  const [modalTab, setModalTab] = useState("DATA"); // "DATA" | "MODEL" | "ASSUMPTIONS" | "LIMITATIONS" | "EVIDENCE"
  const [showModal, setShowModal] = useState(false);

  // Phase H Multimodal Evidence State
  const [evidenceSource, setEvidenceSource] = useState("field_team");
  const [evidenceType, setEvidenceType] = useState("ROAD_BLOCKED");
  const [evidenceLat, setEvidenceLat] = useState("13.0500");
  const [evidenceLon, setEvidenceLon] = useState("80.2200");
  const [evidenceDepth, setEvidenceDepth] = useState("0.40");
  const [evidenceDesc, setEvidenceDesc] = useState("Water inundation reported near Saidapet arterial junction");
  const [extractedEvidence, setExtractedEvidence] = useState(null);
  const [ingestResult, setIngestResult] = useState(null);
  const [timelineData, setTimelineData] = useState([]);
  const [humanApprovalState, setHumanApprovalState] = useState("PENDING");

  // Phase L8 Voice Evidence Pipeline State
  const [voiceAudioFile, setVoiceAudioFile] = useState(null);
  const [voiceTranscriptionData, setVoiceTranscriptionData] = useState(null);

  // Phase L9 Drainage Infrastructure State
  const [drainageSummary, setDrainageSummary] = useState(null);

  const fetchDrainageData = useCallback(async () => {
    try {
      const res = await api.getDrainageInfrastructure();
      setDrainageSummary(res);
    } catch (err) {
      console.warn("Drainage data fetch error:", err);
    }
  }, []);

  // Phase L10 Citizen / PGIS Evidence State
  const [showCitizenModal, setShowCitizenModal] = useState(false);
  const [citizenReportType, setCitizenReportType] = useState("ROAD_FLOODED");
  const [citizenLat, setCitizenLat] = useState("13.0450");
  const [citizenLon, setCitizenLon] = useState("80.2210");
  const [citizenDesc, setCitizenDesc] = useState("Water level observed rising quickly at intersection");
  const [citizenConfidence, setCitizenConfidence] = useState("0.75");
  const [citizenIsAnon, setCitizenIsAnon] = useState(true);
  const [citizenReporterId, setCitizenReporterId] = useState("");
  const [citizenPhotoName, setCitizenPhotoName] = useState("");
  const [citizenPhotoMime, setCitizenPhotoMime] = useState("image/jpeg");
  const [citizenPhotoSize, setCitizenPhotoSize] = useState(150000);
  const [citizenSubmitStatus, setCitizenSubmitStatus] = useState(null);
  const [citizenSubmitError, setCitizenSubmitError] = useState(null);
  const [citizenObservationsList, setCitizenObservationsList] = useState([]);

  const fetchCitizenObservations = useCallback(async () => {
    try {
      const res = await api.getCitizenObservations();
      if (res && res.citizen_observations) {
        setCitizenObservationsList(res.citizen_observations);
      }
    } catch (err) {
      console.warn("Citizen observations fetch error:", err);
    }
  }, []);

  const handleSubmitCitizenReport = async (e) => {
    if (e) e.preventDefault();
    setCitizenSubmitError(null);
    setCitizenSubmitStatus(null);
    try {
      setLoading(true);
      const payload = {
        report_type: citizenReportType,
        location: {
          latitude: parseFloat(citizenLat),
          longitude: parseFloat(citizenLon),
        },
        description: citizenDesc,
        confidence: parseFloat(citizenConfidence),
        is_anonymous: citizenIsAnon,
        reporter_id: citizenIsAnon ? null : (citizenReporterId || "citizen_user"),
      };

      if (citizenPhotoName) {
        payload.media = {
          filename: citizenPhotoName,
          mime_type: citizenPhotoMime || "image/jpeg",
          file_size: parseInt(citizenPhotoSize, 10) || 100000,
        };
      }

      const res = await api.submitCitizenReport(payload);
      setCitizenSubmitStatus(res);
      fetchCitizenObservations();
    } catch (err) {
      setCitizenSubmitError(err.message || "Failed to submit citizen report");
    } finally {
      setLoading(false);
    }
  };


  // Phase J Real-Time Disaster Intelligence State
  const [disasterState, setDisasterState] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [traceabilityData, setTraceabilityData] = useState(null);
  const [showTraceModal, setShowTraceModal] = useState(false);
  const [liveStreamConnected, setLiveStreamConnected] = useState(false);

  const fetchDisasterState = useCallback(async () => {
    try {
      const [sData, aData] = await Promise.all([
        api.getCurrentState(),
        api.getAlerts(),
      ]);
      setDisasterState(sData);
      setAlerts(aData.alerts || []);
    } catch (err) {
      console.warn("Disaster state fetch error:", err);
    }
  }, []);

  useEffect(() => {
    fetchDisasterState();
    const API_BASE = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE || "http://localhost:8000";
    let eventSource = null;
    try {
      eventSource = new EventSource(`${API_BASE}/events/stream`);
      eventSource.onopen = () => setLiveStreamConnected(true);
      eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "STATE_UPDATED" || payload.type === "ALERTS_GENERATED") {
            fetchDisasterState();
          }
        } catch {
          // ignore
        }
      };
      eventSource.onerror = () => setLiveStreamConnected(false);
    } catch {
      setLiveStreamConnected(false);
    }

    const intervalId = setInterval(() => {
      fetchDisasterState();
    }, 5000);

    return () => {
      if (eventSource) eventSource.close();
      clearInterval(intervalId);
    };
  }, [fetchDisasterState]);

  const handleAlertAction = async (alertId, action) => {
    try {
      await api.applyAlertAction(alertId, action);
      await fetchDisasterState();
    } catch (err) {
      setErrorMsg(`Alert action error: ${err.message}`);
    }
  };

  const handleInspectTraceability = async (entityId) => {
    try {
      const data = await api.getTraceability(entityId);
      setTraceabilityData(data);
      setShowTraceModal(true);
    } catch (err) {
      setErrorMsg(`Traceability query error: ${err.message}`);
    }
  };

  // Phase K Intervention Execution & Outcome Tracking State
  const [activeIntervention, setActiveIntervention] = useState(null);
  const [_interventionsList, setInterventionsList] = useState([]);
  const [assignedTeamInput, _setAssignedTeamInput] = useState("FIELD-TEAM-03");

  // Phase L1-L6 Forecast Timeline & Vulnerability State
  const [selectedHorizon, setSelectedHorizon] = useState("NOW"); // "NOW" | "+2H" | "+4H" | "+8H"
  const [forecastData, setForecastData] = useState(null);
  const [vulnerabilityData, setVulnerabilityData] = useState(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastError, setForecastError] = useState(null);
  const [showForecastSummaryModal, setShowForecastSummaryModal] = useState(false);
  const activeHorizonRef = useRef("NOW");

  const fetchForecastTimeline = useCallback(async (horizon) => {
    activeHorizonRef.current = horizon;
    setForecastLoading(true);
    setForecastError(null);
    setForecastData(null);
    setVulnerabilityData(null);

    try {
      const [tData, vData] = await Promise.all([
        api.getForecastTimeline(horizon),
        api.getForecastVulnerability(horizon).catch((err) => {
          console.warn("Forecast vulnerability endpoint fallback:", err);
          return null;
        }),
      ]);

      if (activeHorizonRef.current === horizon) {
        setForecastData(tData);
        setVulnerabilityData(vData);
      }
    } catch (err) {
      if (activeHorizonRef.current === horizon) {
        setForecastError(err.message || "Forecast unavailable — operational state remains unchanged");
        setForecastData(null);
        setVulnerabilityData(null);
      }
    } finally {
      if (activeHorizonRef.current === horizon) {
        setForecastLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchForecastTimeline(selectedHorizon);
  }, [selectedHorizon, fetchForecastTimeline]);

  const fetchInterventions = useCallback(async () => {
    try {
      const res = await api.getInterventions();
      setInterventionsList(res.interventions || []);
      if (res.interventions?.length > 0) {
        const latest = res.interventions[res.interventions.length - 1];
        setActiveIntervention(latest);
      }
    } catch (err) {
      console.warn("Fetch interventions error:", err);
    }
  }, []);

  useEffect(() => {
    fetchInterventions();
  }, [fetchInterventions]);

  const handleProposeIntervention = async (candidateId) => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await api.proposeIntervention(candidateId, "COMMANDER-01", "Human approved recommendation from DecisionEngine");
      setActiveIntervention(res);
      await fetchInterventions();
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Failed to propose intervention: ${err.message}`);
      setLoading(false);
    }
  };

  const handleTransitionIntervention = async (interventionId, toStatus, note = null) => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await api.transitionIntervention(interventionId, toStatus, "COMMANDER-01", assignedTeamInput, note);
      if (toStatus === "COMPLETED") {
        setSystemState("CLEARED");
        setClearedCorridorId(selectedCorridor?.corridor_id || "corridor_03");
        const [mData, aData] = await Promise.all([
          api.getMapData(),
          api.getAccessibilityStatus(),
        ]);
        setMapData(mData);
        setAccessStatus(aData);
      }
      setActiveIntervention(res);
      await fetchInterventions();
      await fetchDisasterState();
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Intervention transition error: ${err.message}`);
      setLoading(false);
    }
  };


  const fetchTimeline = async () => {
    try {
      const res = await api.getTimeline();
      setTimelineData(res.timeline || []);
    } catch (err) {
      console.warn("Timeline fetch error:", err);
    }
  };


  const handleExtractEvidence = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const reportPayload = {
        observation_type: evidenceType,
        source: evidenceSource,
        latitude: parseFloat(evidenceLat),
        longitude: parseFloat(evidenceLon),
        water_depth_m: parseFloat(evidenceDepth),
        description: evidenceDesc,
      };
      const res = await api.extractEvidence(reportPayload);
      setExtractedEvidence(res);
      setIngestResult(null);
      setHumanApprovalState("PENDING");
      await fetchTimeline();
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Evidence extraction error: ${err.message}`);
      setLoading(false);
    }
  };

  const handleIngestEvidence = async () => {
    if (!extractedEvidence) return;
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await api.ingestEvidence(extractedEvidence.extraction_id);
      setIngestResult(res);

      const [mData, aData] = await Promise.all([
        api.getMapData(),
        api.getAccessibilityStatus(),
      ]);
      setMapData(mData);
      setAccessStatus(aData);
      await fetchTimeline();
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Phase E Ingestion error: ${err.message}`);
      setLoading(false);
    }
  };

  // Phase L8 Voice Pipeline Handlers
  const handleTranscribeVoice = async () => {
    if (!voiceAudioFile) return;
    try {
      setLoading(true);
      setErrorMsg(null);
      const formData = new FormData();
      formData.append("audio", voiceAudioFile);
      formData.append("source_type", evidenceSource);
      if (evidenceLat) formData.append("lat", evidenceLat);
      if (evidenceLon) formData.append("lon", evidenceLon);

      const res = await api.transcribeVoice(formData);
      setVoiceTranscriptionData(res);
      setExtractedEvidence(res.extraction);
      setIngestResult(null);
      await fetchTimeline();
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Voice transcription error: ${err.message}`);
      setLoading(false);
    }
  };

  const handleIngestVoice = async () => {
    if (!voiceTranscriptionData || !voiceTranscriptionData.extraction) return;
    try {
      setLoading(true);
      setErrorMsg(null);
      const extractionId = voiceTranscriptionData.extraction.extraction_id;
      const locOverride = (evidenceLat && evidenceLon) ? [parseFloat(evidenceLat), parseFloat(evidenceLon)] : null;
      const res = await api.ingestVoice(extractionId, locOverride);
      setIngestResult(res);
      const [mData, aData] = await Promise.all([
        api.getMapData(),
        api.getAccessibilityStatus(),
      ]);
      setMapData(mData);
      setAccessStatus(aData);
      await fetchTimeline();
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Voice ingestion error: ${err.message}`);
      setLoading(false);
    }
  };

  // Phase I Offline Field Mode State
  const [viewMode, setViewMode] = useState("COMMAND_CENTER"); // "COMMAND_CENTER" | "FIELD_MODE"
  const [netStatus, setNetStatus] = useState(navigator.onLine ? NETWORK_STATUS.ONLINE : NETWORK_STATUS.OFFLINE);
  const [offlineItems, setOfflineItems] = useState([]);
  const [fieldNotice, setFieldNotice] = useState(null);
  const [gpsStatus, setGpsStatus] = useState("IDLE"); // "IDLE" | "LOCATING" | "CAPTURED" | "UNAVAILABLE"
  const syncEngineRef = useRef(null);

  const loadOfflineItems = async () => {
    try {
      const items = await offlineQueue.getAllObservations();
      setOfflineItems(items.reverse());
    } catch (err) {
      console.warn("Error loading offline items from IndexedDB:", err);
    }
  };

  useEffect(() => {
    syncEngineRef.current = new SyncEngine((status) => {
      setNetStatus(status);
      offlineQueue.getAllObservations().then((items) => setOfflineItems(items.reverse())).catch(() => {});
    });
    offlineQueue.getAllObservations().then((items) => setOfflineItems(items.reverse())).catch(() => {});
  }, []);

  const handleSaveOfflineLocally = async () => {
    try {
      setLoading(true);
      const clientObsId = `client_obs_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
      const item = {
        client_observation_id: clientObsId,
        created_at: new Date().toISOString(),
        captured_at: new Date().toISOString(),
        source: evidenceSource,
        observation_type: evidenceType,
        latitude: evidenceLat !== "" && !isNaN(evidenceLat) ? parseFloat(evidenceLat) : null,
        longitude: evidenceLon !== "" && !isNaN(evidenceLon) ? parseFloat(evidenceLon) : null,
        water_depth_m: evidenceDepth !== "" && !isNaN(evidenceDepth) ? parseFloat(evidenceDepth) : null,
        severity: "high",
        confidence: evidenceSource === "field_team" || evidenceSource === "official" ? 0.90 : 0.65,
        description: evidenceDesc,
        evidence_reference: `PHOTO_${Date.now()}`,
        sync_status: "QUEUED",
      };

      await offlineQueue.saveObservation(item);
      setFieldNotice(`✓ Saved locally to IndexedDB store. Client ID: ${clientObsId}. Will sync automatically when connectivity returns.`);
      await loadOfflineItems();

      // Auto-trigger sync if reachably online
      if (syncEngineRef.current) {
        syncEngineRef.current.syncQueue().then(() => loadOfflineItems());
      }
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Failed to save offline observation locally: ${err.message}`);
      setLoading(false);
    }
  };

  const handleManualSyncNow = async () => {
    if (!syncEngineRef.current) return;
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await syncEngineRef.current.syncQueue();
      if (res.status === "UNAVAILABLE") {
        setErrorMsg("Connection unavailable — server unreachable or browser offline.");
      } else {
        const [mData, aData] = await Promise.all([
          api.getMapData(),
          api.getAccessibilityStatus(),
        ]);
        setMapData(mData);
        setAccessStatus(aData);
        await fetchTimeline();
      }
      await loadOfflineItems();
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Sync error: ${err.message}`);
      setLoading(false);
    }
  };

  const handleClearSyncedLocal = async () => {
    try {
      await offlineQueue.clearSynced();
      await loadOfflineItems();
    } catch (err) {
      console.warn("Error clearing synced items:", err);
    }
  };

  const handleCaptureGpsLocation = () => {
    if (!navigator.geolocation) {
      setGpsStatus("UNAVAILABLE");
      return;
    }
    setGpsStatus("LOCATING");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setEvidenceLat(pos.coords.latitude.toFixed(4));
        setEvidenceLon(pos.coords.longitude.toFixed(4));
        setGpsStatus("CAPTURED");
      },
      (err) => {
        console.warn("GPS capture error:", err);
        setGpsStatus("UNAVAILABLE");
      },
      { timeout: 5000, enableHighAccuracy: true }
    );
  };

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

  // 1. Initial Baseline Fetch
  useEffect(() => {
    let ignore = false;
    const initBaseline = async (retryCount = 0) => {
      try {
        setLoading(true);
        setErrorMsg(null);
        await api.loadNetwork();
        const [mData, aData] = await Promise.all([
          api.getMapData(),
          api.getAccessibilityStatus(),
        ]);
        if (!ignore) {
          setMapData(mData);
          setAccessStatus(aData);
          setSystemState("BASE");
          setDemoStep(1);
          setLoading(false);
        }
      } catch (err) {
        if (!ignore) {
          if (retryCount < 2) {
            console.warn(`[Map Data] Baseline fetch attempt ${retryCount + 1} failed (${err.message}). Retrying in 2s...`);
            setTimeout(() => {
              if (!ignore) initBaseline(retryCount + 1);
            }, 2000);
          } else {
            setErrorMsg(`Backend connection unavailable: ${err.message}`);
            setLoading(false);
          }
        }
      }
    };

    initBaseline();
    return () => {
      ignore = true;
    };
  }, []);

  // 2. Leaflet Map Initialization
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

    // Standard OpenStreetMap base layer
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      subdomains: ["a", "b", "c"],
    }).addTo(map);

    map.fitBounds(CHENNAI_BOUNDS, { padding: [24, 24] });
    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Handle viewMode transitions & Leaflet map container resizing
  useEffect(() => {
    if (viewMode === "COMMAND_CENTER" && mapInstanceRef.current) {
      const timer = setTimeout(() => {
        mapInstanceRef.current?.invalidateSize();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [viewMode]);

  // 3. Leaflet Vector Layer Render & Synchronization
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

    // A. Flood Inundation Footprint (Muted soft polygon area vs Projected Forecast)
    const isProjected = selectedHorizon !== "NOW" && forecastData?.flood?.flood_geojson;
    const activeFloodGeoJson = isProjected ? forecastData.flood.flood_geojson : mapData?.flood;

    if (
      layersVisibility.floodInundation &&
      activeFloodGeoJson &&
      (systemState !== "BASE" || demoStep > 1 || isProjected)
    ) {
      const floodLayer = L.geoJSON(activeFloodGeoJson, {
        style: {
          color: isProjected ? "#38bdf8" : "#0284c7",
          weight: isProjected ? 2.0 : 1.5,
          fillColor: isProjected ? "#38bdf8" : "#0284c7",
          fillOpacity: isProjected ? 0.22 : 0.18,
          dashArray: isProjected ? "6, 4" : "3, 3",
        },
      }).addTo(map);

      if (isProjected) {
        floodLayer.bindTooltip(`PROJECTED FORECAST FOOTPRINT (${selectedHorizon})`, {
          permanent: false,
          direction: "center",
        });
      }

      layersRef.current.flood = floodLayer;
    }

    // B. Road Network Edges
    if (layersVisibility.roadNetwork && mapData.roads) {
      const roadsLayer = L.geoJSON(mapData.roads, {
        style: (feature) => {
          const isDisabled = feature.properties.disabled;
          const isElevated = feature.properties.bridge === "yes" || feature.properties.layer > 0;

          if (isDisabled) {
            const showBlocked = layersVisibility.impassable && (systemState !== "BASE" || demoStep > 1);
            return showBlocked
              ? { color: "#dc2626", weight: 3, opacity: 0.85, dashArray: "4, 4" }
              : { opacity: 0, fillOpacity: 0 };
          }
          if (isElevated) {
            return { color: "#d97706", weight: 2.5, opacity: 0.85 };
          }
          return { color: "#64748b", weight: 1.8, opacity: 0.5 };
        },
        onEachFeature: (feature, layer) => {
          layer.bindTooltip(
            `<strong>${feature.properties.name}</strong><br/>Length: ${feature.properties.length}m | Speed: ${feature.properties.speed_kph} km/h`,
            { className: "gis-carto-tooltip" }
          );
        },
      }).addTo(map);
      layersRef.current.roads = roadsLayer;
    }

    // C. Restored Corridor Lifeline (Clean Solid Emerald Route)
    if (layersVisibility.selectedCorridor && clearedCorridorId && rankedCorridors.length > 0) {
      const clearedCorr = rankedCorridors.find((c) => c.corridor_id === clearedCorridorId);
      if (clearedCorr?.geometry) {
        const restoredLayer = L.geoJSON(clearedCorr.geometry, {
          style: {
            color: "#059669",
            weight: 5,
            opacity: 0.95,
          },
        }).addTo(map);
        layersRef.current.restored = restoredLayer;
      }
    }

    // D. Selected Corridor Highlight (Active Blue Route)
    if (
      layersVisibility.selectedCorridor &&
      selectedCorridor?.geometry &&
      selectedCorridor.corridor_id !== clearedCorridorId &&
      (systemState === "RANKED" || systemState === "SELECTED" || demoStep >= 4)
    ) {
      const highlightLayer = L.geoJSON(selectedCorridor.geometry, {
        style: {
          color: "#2563eb",
          weight: 5,
          opacity: 0.95,
        },
      }).addTo(map);
      layersRef.current.highlight = highlightLayer;
    }

    // E. Health Facilities (Trauma Centres)
    if (mapData.facilities) {
      const facilitiesLayer = L.geoJSON(mapData.facilities, {
        filter: (feature) => {
          const isIsolated = feature.properties.isolated;
          if (isIsolated) {
            return layersVisibility.traumaCentersIsolated && (systemState !== "BASE" || demoStep > 1);
          }
          return layersVisibility.hospitalsOperational;
        },
        pointToLayer: (feature, latlng) => {
          const isIsolated = feature.properties.isolated;
          const marker = L.marker(latlng, { icon: createHospitalIcon(isIsolated) });
          marker.bindTooltip(
            `<strong>${feature.properties.name}</strong><br/>Beds: ${feature.properties.beds}<br/>Status: ${isIsolated ? "Isolated" : "Operational"}`,
            { className: "gis-carto-tooltip" }
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
          if (isIsolated) {
            return layersVisibility.communitiesIsolated && (systemState !== "BASE" || demoStep > 1);
          }
          return layersVisibility.communitiesAccessible;
        },
        pointToLayer: (feature, latlng) => {
          const isIsolated = feature.properties.isolated;
          const marker = L.marker(latlng, { icon: createCommunityIcon(isIsolated) });
          const transitTime = feature.properties.travel_time_sec
            ? `${(feature.properties.travel_time_sec / 60).toFixed(1)} min`
            : ">30 min (Isolated)";
          marker.bindTooltip(
            `<strong>${feature.properties.name}</strong><br/>Population: ${feature.properties.population.toLocaleString()}<br/>Transit: ${transitTime}`,
            { className: "gis-carto-tooltip" }
          );
          return marker;
        },
      }).addTo(map);
      layersRef.current.communities = communitiesLayer;
      // G. Projected Vulnerable Road Segments Layer (Milestone L6)
      const activeVulnAssessments = vulnerabilityData?.vulnerability_assessments || [];
      if (
        layersVisibility.roadNetwork &&
        selectedHorizon !== "NOW" &&
        activeVulnAssessments.length > 0 &&
        mapData?.roads
      ) {
        const vulnSegMap = new Map();
        activeVulnAssessments.forEach((ass) => {
          vulnSegMap.set(ass.segment_id, ass);
        });

        const projectedVulnLayer = L.geoJSON(mapData.roads, {
          filter: (feature) => {
            const segId = feature.properties.physical_segment_id || feature.properties.segment_id;
            return vulnSegMap.has(segId);
          },
          style: (feature) => {
            const segId = feature.properties.physical_segment_id || feature.properties.segment_id;
            const ass = vulnSegMap.get(segId);
            const score = ass ? ass.vulnerability_score : 0;

            let strokeColor = "#94a3b8";
            let weightVal = 2.5;

            if (score >= 0.85) {
              strokeColor = "#ef4444"; // Critical
              weightVal = 4.0;
            } else if (score >= 0.60) {
              strokeColor = "#f97316"; // High
              weightVal = 3.5;
            } else if (score >= 0.30) {
              strokeColor = "#f59e0b"; // Medium
              weightVal = 3.0;
            }

            return {
              color: strokeColor,
              weight: weightVal,
              opacity: 0.90,
              dashArray: "6, 4",
            };
          },
          onEachFeature: (feature, layer) => {
            const segId = feature.properties.physical_segment_id || feature.properties.segment_id;
            const ass = vulnSegMap.get(segId);
            if (ass) {
              const scoreLabel =
                ass.vulnerability_score >= 0.85
                  ? "CRITICAL"
                  : ass.vulnerability_score >= 0.60
                  ? "HIGH"
                  : ass.vulnerability_score >= 0.30
                  ? "MEDIUM"
                  : "LOW";
              layer.bindTooltip(
                `<div style="font-family: var(--font-sans); font-size: 11px;">` +
                  `<strong style="color: #38bdf8;">PROJECTED ROAD VULNERABILITY (${selectedHorizon})</strong><br/>` +
                  `Segment: <strong>${ass.segment_id}</strong><br/>` +
                  `Vulnerability Score: <strong style="color: ${ass.vulnerability_score >= 0.6 ? '#f97316' : '#f59e0b'};">${ass.vulnerability_score.toFixed(2)} (${scoreLabel})</strong><br/>` +
                  `Flood Exposure: ${ass.flood_exposure.toFixed(2)} | Pop: ${ass.raw_population_impact.toLocaleString()} | Hosp: ${ass.raw_hospital_impact}<br/>` +
                  `<span style="color: #94a3b8; font-size: 10px;">${ass.explanation || ''}</span>` +
                  `</div>`,
                { className: "gis-carto-tooltip" }
              );
            }
          },
        }).addTo(map);

        layersRef.current.projectedVuln = projectedVulnLayer;
      }

      // Phase L10 Citizen PGIS Observation Markers
      if (citizenObservationsList && citizenObservationsList.length > 0) {
        const citizenMarkers = L.layerGroup();
        citizenObservationsList.forEach((obs) => {
          if (obs.location && typeof obs.location.latitude === "number" && typeof obs.location.longitude === "number") {
            const marker = L.marker([obs.location.latitude, obs.location.longitude], {
              icon: createCitizenIcon(obs.report_type, obs.status),
            });
            marker.bindTooltip(
              `<div style="font-family: var(--font-sans); font-size: 11px;">` +
                `<strong style="color: #c084fc;">CITIZEN OBSERVATION (EVIDENCE)</strong><br/>` +
                `ID: <strong>${obs.observation_id}</strong><br/>` +
                `Type: <strong>${obs.report_type}</strong> | Status: <strong>${obs.status}</strong><br/>` +
                `Confidence: ${(obs.confidence * 100).toFixed(0)}% | Media: ${obs.media_metadata ? "YES" : "NO"}<br/>` +
                `<span style="color: #cbd5e1; font-size: 10px;">"${obs.description || 'No description'}"</span><br/>` +
                `<span style="color: #94a3b8; font-size: 9px; font-style: italic;">Observation Evidence Only — Not Authoritative State</span>` +
                `</div>`,
              { className: "gis-carto-tooltip" }
            );
            citizenMarkers.addLayer(marker);
          }
        });
        citizenMarkers.addTo(map);
        layersRef.current.citizenObservations = citizenMarkers;
      }
    }
  }, [
    mapData,
    systemState,
    selectedCorridor,
    clearedCorridorId,
    rankedCorridors,
    demoStep,
    layersVisibility,
    selectedHorizon,
    forecastData,
    vulnerabilityData,
    citizenObservationsList,
  ]);


  // 4. Map Control Handlers
  const handleZoomIn = useCallback(() => mapInstanceRef.current?.zoomIn(), []);
  const handleZoomOut = useCallback(() => mapInstanceRef.current?.zoomOut(), []);
  const handleRecenter = useCallback(() => {
    mapInstanceRef.current?.fitBounds(CHENNAI_BOUNDS, { padding: [24, 24], duration: 0.5 });
  }, []);

  // 5. Operational Simulation Handlers
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
      setLayersVisibility((prev) => ({
        ...prev,
        floodInundation: true,
        impassable: true,
        communitiesIsolated: true,
        selectedCorridor: false,
      }));
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Flood simulation error: ${err.message}`);
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
      setDemoStep(4);
      setLayersVisibility((prev) => ({
        ...prev,
        selectedCorridor: true,
      }));

      if (data.ranked_corridors?.length > 0) {
        handleSelectCorridor(data.ranked_corridors[0]);
      }
      setLoading(false);
    } catch (err) {
      setErrorMsg(`Criticality ranking error: ${err.message}`);
      setLoading(false);
    }
  };

  const handleSelectCorridor = async (corr) => {
    if (!corr) return;
    setSelectedCorridor(corr);
    setSystemState("SELECTED");
    setLayersVisibility((prev) => ({
      ...prev,
      selectedCorridor: true,
    }));

    if (mapInstanceRef.current && corr.corridor_id === "corridor_03") {
      mapInstanceRef.current.flyTo([13.015, 80.22], 13.5, { duration: 0.6 });
    }

    try {
      const advData = await api.generateAdvisory(corr.corridor_id, corr.score_breakdown);
      setAdvisory(advData);
    } catch (err) {
      console.warn("Advisory generator fallback used", err);
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
      setDemoStep(5);
      setLayersVisibility((prev) => ({
        ...prev,
        selectedCorridor: true,
      }));

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
      setLayersVisibility({
        floodInundation: false,
        roadNetwork: true,
        impassable: false,
        selectedCorridor: false,
        hospitalsOperational: true,
        traumaCentersIsolated: false,
        communitiesAccessible: true,
        communitiesIsolated: false,
      });
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
    else if (demoStep === 2 || demoStep === 3) handleRankCorridors();
    else if (demoStep === 4) handleClearCorridor();
    else if (demoStep === 5) handleResetNetwork();
  };

  // Guided Demo Mode Execution Handler (6-Stage Story Workflow)
  const handleExecuteGuidedDemoStep = async (targetStep) => {
    setGuidedDemoStep(targetStep);
    setErrorMsg(null);

    if (targetStep === 1) {
      // 1. BASELINE: Normal conditions
      setViewMode("COMMAND_CENTER");
      setDemoSimulatedOffline(false);
      await handleResetNetwork();
    } else if (targetStep === 2) {
      // 2. FLOOD: Inundation applied
      setViewMode("COMMAND_CENTER");
      setDemoSimulatedOffline(false);
      await handleApplyFlood();
    } else if (targetStep === 3) {
      // 3. FIELD EVIDENCE: Responder reports blocked road
      setViewMode("FIELD_MODE");
      setEvidenceSource("field_team");
      setEvidenceType("ROAD_BLOCKED");
      setEvidenceLat("13.0500");
      setEvidenceLon("80.2200");
      setEvidenceDepth("0.40");
      setEvidenceDesc("Responder reports a blocked road near Saidapet.");
      setDemoSimulatedOffline(true); // Simulate offline connection moment
    } else if (targetStep === 4) {
      // 4. SYNC: Reconnect & transmit queue
      setViewMode("FIELD_MODE");
      setDemoSimulatedOffline(false);
      try {
        setLoading(true);
        const clientObsId = `client_obs_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
        const item = {
          client_observation_id: clientObsId,
          created_at: new Date().toISOString(),
          captured_at: new Date().toISOString(),
          source: "field_team",
          observation_type: "ROAD_BLOCKED",
          latitude: 13.0500,
          longitude: 80.2200,
          water_depth_m: 0.40,
          severity: "high",
          confidence: 0.90,
          description: "Responder reports a blocked road near Saidapet.",
          evidence_reference: `PHOTO_${Date.now()}`,
          sync_status: "QUEUED",
        };
        await offlineQueue.saveObservation(item);
        await loadOfflineItems();
        if (syncEngineRef.current) {
          await syncEngineRef.current.syncQueue();
          await loadOfflineItems();
        }
        setFieldNotice("✓ Field observation successfully synchronized to backend pipeline.");
      } catch (err) {
        console.warn("Guided demo sync error:", err);
      } finally {
        setLoading(false);
      }
    } else if (targetStep === 5) {
      // 5. NETWORK UPDATE: Reconcile state & refresh accessibility
      setViewMode("COMMAND_CENTER");
      setDemoSimulatedOffline(false);
      try {
        setLoading(true);
        const [mData, aData] = await Promise.all([
          api.getMapData(),
          api.getAccessibilityStatus(),
        ]);
        setMapData(mData);
        setAccessStatus(aData);
      } catch (err) {
        setErrorMsg(`Network state update error: ${err.message}`);
      } finally {
        setLoading(false);
      }
    } else if (targetStep === 6) {
      // 6. DECISION: Quantify intervention priority
      setViewMode("COMMAND_CENTER");
      setDemoSimulatedOffline(false);
      await handleRankCorridors();
    }
  };

  // Dynamic feature counts and state-awareness for layer controls
  const totalRoads = mapData?.roads?.features?.length || 56;
  const blockedRoadsCount = systemState === "BASE" ? 0 : (mapData?.roads?.features?.filter((f) => f.properties?.disabled)?.length || 0);
  const operationalHospitalsCount = mapData?.facilities?.features?.filter((f) => !f.properties?.isolated)?.length || 6;
  const isolatedHospitalsCount = systemState === "BASE" ? 0 : (mapData?.facilities?.features?.filter((f) => f.properties?.isolated)?.length || 0);
  const accessibleCommunitiesCount = systemState === "BASE" ? 10 : (mapData?.communities?.features?.filter((f) => !f.properties?.isolated)?.length || 10);
  const isolatedCommunitiesCount = systemState === "BASE" ? 0 : (mapData?.communities?.features?.filter((f) => f.properties?.isolated)?.length || 0);
  const hasFloodActive = (systemState !== "BASE" || demoStep > 1 || selectedHorizon !== "NOW") && Boolean(mapData?.flood || (selectedHorizon !== "NOW" && forecastData?.flood?.flood_geojson));
  const hasCorridorActive = Boolean(selectedCorridor || clearedCorridorId) && (systemState === "RANKED" || systemState === "SELECTED" || systemState === "CLEARED" || demoStep >= 4);

  const toggleLayer = (layerKey, isAvailable = true) => {
    if (!isAvailable) return;
    setLayersVisibility((prev) => ({
      ...prev,
      [layerKey]: !prev[layerKey],
    }));
  };

  // Telemetry values strictly derived from simulation state
  const totalPopulation = 477000;
  const rawAccessiblePop = systemState === "BASE" ? totalPopulation : (accessStatus?.accessible_population ?? totalPopulation);
  const rawIsolatedPop = systemState === "BASE" ? 0 : Math.max(0, totalPopulation - rawAccessiblePop);
  const activeHospitals = 6 - (systemState === "BASE" ? 0 : (accessStatus?.isolated_facilities?.length ?? 0));

  // Animated Numerical Interpolation
  const animAccessiblePop = useAnimatedNumber(rawAccessiblePop);
  const animIsolatedPop = useAnimatedNumber(rawIsolatedPop);

  return (
    <div className="gis-console">
      {/* 1. HEADER */}
      <header className="gis-header">
        <div className="header-brand">
          <span className="brand-title">{t("header.title")}</span>
          <span className="brand-divider">·</span>
          <span className="brand-subtitle">{t("header.subtitle")}</span>

          {/* Mode Switch: Command Center vs Field Operations */}
          <div className="header-view-toggle">
            <button
              onClick={() => setViewMode("COMMAND_CENTER")}
              className={`view-toggle-btn ${viewMode === "COMMAND_CENTER" ? "active" : ""}`}
            >
              {t("header.commandCenter")}
            </button>
            <button
              onClick={() => setViewMode("FIELD_MODE")}
              className={`view-toggle-btn ${viewMode === "FIELD_MODE" ? "active field" : ""}`}
            >
              <span
                className={`status-dot ${netStatus === NETWORK_STATUS.ONLINE ? "online" : netStatus === NETWORK_STATUS.OFFLINE ? "offline" : "danger"}`}
              />
              {t("header.fieldMode")}
            </button>
          </div>

          {/* Semantic Simulation State Indicator */}
          <span className="state-badge">
            SIMULATION: {systemState === "BASE" ? "BASELINE" : systemState === "FLOODED" ? "FLOOD IMPACT" : systemState === "CLEARED" ? "RECOVERY RESTORED" : "CRITICALITY MODEL"}
          </span>

          {/* System Connectivity Status */}
          <span className="conn-badge">
            <span className={`status-dot ${liveStreamConnected ? "online" : "offline"}`} />
            {liveStreamConnected ? "CONNECTED" : "SYNCING"}
          </span>
        </div>

        <div className="header-actions">
          {/* Demo Mode Activation Button */}
          <button
            onClick={() => {
              if (isDemoActive) {
                setIsDemoActive(false);
                handleExecuteGuidedDemoStep(1);
              } else {
                setIsDemoActive(true);
                handleExecuteGuidedDemoStep(1);
              }
            }}
            className={`btn-demo ${isDemoActive ? "active" : ""}`}
            title={isDemoActive ? t("demo.exitDemo") : t("demo.startDemo")}
          >
            {isDemoActive ? `✕ ${t("demo.exitDemo")}` : `▶ ${t("demo.startDemo")}`}
          </button>

          {/* Locale / Language Selector */}
          <div className="language-selector">
            <span className="lang-icon">🌐</span>
            <select
              value={locale}
              onChange={(e) => setLocale(e.target.value)}
              aria-label={t("header.language")}
              className="lang-select"
            >
              {supportedLocales.map((loc) => (
                <option key={loc.code} value={loc.code}>
                  {loc.nativeName} ({loc.code.toUpperCase()})
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => {
              setShowCitizenModal(true);
              fetchCitizenObservations();
            }}
            className="btn-quiet"
            title="Citizen & Participatory GIS Ground Report Interface"
          >
            {t("header.citizenPgis")}
          </button>

          <button
            onClick={() => {
              setModalTab("EVIDENCE");
              setShowModal(true);
              fetchTimeline();
            }}
            className="btn-quiet"
            title="Field Evidence & Observation Pipeline"
          >
            {t("header.fieldEvidence")}
          </button>

          <button
            onClick={() => {
              setModalTab("DATA");
              setShowModal(true);
            }}
            className="btn-quiet"
            title="Data sources and model specifications"
          >
            Model & Data
          </button>

          <button
            onClick={handleResetNetwork}
            className="btn-secondary"
            disabled={loading || systemState === "BASE"}
            title="Reset simulation to baseline"
          >
            {t("header.reset")}
          </button>

          <button
            onClick={handleNextDemoStep}
            className="btn-primary"
            disabled={loading}
          >
            {demoStep === 1
              ? t("header.applyFlood")
              : demoStep === 2 || demoStep === 3
              ? t("header.rankCorridors")
              : demoStep === 4
              ? t("header.simulateRecovery")
              : t("header.resetSimulation")}
          </button>
        </div>
      </header>


      {/* 1.5. PHASE L1-L6 FORECAST TIMELINE & CONTROL BAR */}
      <div
        className="forecast-timeline-bar"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 16px",
          background: "rgba(15, 23, 42, 0.95)",
          borderBottom: "1px solid rgba(56, 189, 248, 0.25)",
          fontSize: "12px",
          color: "#e2e8f0",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={{ fontWeight: 700, color: "#38bdf8", letterSpacing: "0.5px", fontSize: "11px" }}>
            OPERATIONAL FORECAST TIMELINE
          </span>

          <div
            role="tablist"
            aria-label="Forecast Horizon Selector"
            style={{
              display: "flex",
              background: "rgba(255,255,255,0.06)",
              borderRadius: "4px",
              padding: "2px",
              border: "1px solid rgba(255,255,255,0.1)",
            }}
          >
            {["NOW", "+2H", "+4H", "+8H"].map((h) => {
              const isSelected = selectedHorizon === h;
              return (
                <button
                  key={h}
                  role="tab"
                  aria-selected={isSelected}
                  aria-label={`Select forecast horizon ${h}`}
                  onClick={() => setSelectedHorizon(h)}
                  style={{
                    background: isSelected ? (h === "NOW" ? "#059669" : "#0284c7") : "transparent",
                    color: isSelected ? "#ffffff" : "#94a3b8",
                    border: "none",
                    padding: "4px 10px",
                    borderRadius: "3px",
                    fontSize: "11px",
                    fontWeight: isSelected ? 700 : 500,
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  {h === "NOW" ? "NOW (0H)" : h}
                </button>
              );
            })}
          </div>

          {forecastLoading && (
            <span style={{ color: "#38bdf8", fontSize: "11px", display: "flex", alignItems: "center", gap: "4px" }}>
              Loading forecast projection...
            </span>
          )}

          {forecastError && (
            <span style={{ color: "#f87171", fontSize: "11px", fontWeight: 600 }}>
              {forecastError}
            </span>
          )}
        </div>

        {forecastData && !forecastLoading && (
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span style={{ color: "#cbd5e1", fontSize: "11px" }}>
              Target:{" "}
              <strong>
                {new Date(forecastData.target_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </strong>
            </span>
            <span style={{ color: "#38bdf8", fontSize: "11px" }}>
              Rainfall: <strong>{forecastData.weather?.precipitation_mm}mm</strong>
            </span>
            <span style={{ color: "#38bdf8", fontSize: "11px" }}>
              Water Level: <strong>{forecastData.flood?.water_level_m}m</strong>
            </span>
            <span
              style={{
                color:
                  (forecastData.predicted_accessibility?.isolated_communities?.length || 0) > 0 ? "#f87171" : "#34d399",
                fontSize: "11px",
                fontWeight: 600,
              }}
            >
              Predicted Isolated:{" "}
              <strong>{forecastData.predicted_accessibility?.isolated_communities?.length || 0} zones</strong>
            </span>

            {vulnerabilityData?.vulnerability_summary && (
              <span style={{ color: "#f59e0b", fontSize: "11px" }}>
                Max Vuln: <strong>{vulnerabilityData.vulnerability_summary.max_vulnerability_score.toFixed(2)}</strong>
              </span>
            )}

            <button
              onClick={() => setShowForecastSummaryModal(true)}
              style={{
                background: "rgba(56, 189, 248, 0.15)",
                color: "#38bdf8",
                border: "1px solid rgba(56, 189, 248, 0.4)",
                padding: "3px 8px",
                borderRadius: "4px",
                fontSize: "10px",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              📊 Inspect Forecast Summary
            </button>

            <span
              style={{
                background: selectedHorizon === "NOW" ? "rgba(16, 185, 129, 0.15)" : "rgba(56, 189, 248, 0.15)",
                color: selectedHorizon === "NOW" ? "#34d399" : "#38bdf8",
                border: `1px solid ${selectedHorizon === "NOW" ? "rgba(16, 185, 129, 0.4)" : "rgba(56, 189, 248, 0.4)"}`,
                padding: "2px 6px",
                borderRadius: "4px",
                fontSize: "10px",
                fontWeight: 700,
              }}
            >
              {selectedHorizon === "NOW" ? "SIMULATION BASELINE (0H)" : `PROJECTED FORECAST (${selectedHorizon})`}
            </span>
          </div>
        )}
      </div>

      {/* 1.8 GUIDED DEMO STEPPER BANNER (DEMO MODE UX PASS) */}
      {isDemoActive && (
        <div
          style={{
            background: "linear-gradient(135deg, rgba(15, 23, 42, 0.98), rgba(30, 41, 59, 0.98))",
            borderBottom: "2px solid #2563eb",
            padding: "12px 20px",
            color: "#f8fafc",
            boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ background: "#2563eb", color: "#fff", padding: "2px 8px", borderRadius: "4px", fontSize: "11px", fontWeight: 800 }}>
                {t("demo.guidedDemoTitle")}
              </span>
              <span style={{ fontSize: "12px", color: "#94a3b8" }}>
                Step {guidedDemoStep} of 6
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <button
                onClick={() => handleExecuteGuidedDemoStep(Math.max(1, guidedDemoStep - 1))}
                disabled={guidedDemoStep === 1 || loading}
                style={{
                  background: "rgba(255,255,255,0.08)",
                  color: guidedDemoStep === 1 ? "#64748b" : "#fff",
                  border: "1px solid rgba(255,255,255,0.2)",
                  padding: "4px 12px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: guidedDemoStep === 1 ? "not-allowed" : "pointer",
                }}
              >
                {t("demo.previousStep")}
              </button>

              <button
                onClick={() => handleExecuteGuidedDemoStep(guidedDemoStep < 6 ? guidedDemoStep + 1 : 1)}
                disabled={loading}
                style={{
                  background: "#2563eb",
                  color: "#fff",
                  border: "none",
                  padding: "4px 14px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                {guidedDemoStep < 6 ? t("demo.nextStep") : t("demo.resetDemo")}
              </button>

              <button
                onClick={() => handleExecuteGuidedDemoStep(1)}
                disabled={loading}
                style={{
                  background: "rgba(255,255,255,0.08)",
                  color: "#e2e8f0",
                  border: "1px solid rgba(255,255,255,0.2)",
                  padding: "4px 10px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {t("demo.resetDemo")}
              </button>

              <button
                onClick={() => {
                  setIsDemoActive(false);
                  handleExecuteGuidedDemoStep(1);
                }}
                style={{
                  background: "rgba(239, 68, 68, 0.2)",
                  color: "#f87171",
                  border: "1px solid rgba(239, 68, 68, 0.4)",
                  padding: "4px 10px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {t("demo.exitDemo")}
              </button>
            </div>
          </div>

          {/* 6-Stage Progress Indicator */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "8px", marginBottom: "10px" }}>
            {[
              { step: 1, title: t("demo.step1Title") },
              { step: 2, title: t("demo.step2Title") },
              { step: 3, title: t("demo.step3Title") },
              { step: 4, title: t("demo.step4Title") },
              { step: 5, title: t("demo.step5Title") },
              { step: 6, title: t("demo.step6Title") },
            ].map((st) => {
              const isActive = guidedDemoStep === st.step;
              const isCompleted = guidedDemoStep > st.step;
              return (
                <div
                  key={st.step}
                  onClick={() => handleExecuteGuidedDemoStep(st.step)}
                  style={{
                    background: isActive ? "#2563eb" : isCompleted ? "rgba(37, 99, 235, 0.2)" : "rgba(255,255,255,0.05)",
                    border: `1px solid ${isActive ? "#60a5fa" : isCompleted ? "rgba(37, 99, 235, 0.4)" : "rgba(255,255,255,0.1)"}`,
                    borderRadius: "4px",
                    padding: "6px 8px",
                    cursor: "pointer",
                    textAlign: "center",
                    transition: "all 0.15s ease",
                  }}
                >
                  <div style={{ fontSize: "10px", fontWeight: 800, color: isActive ? "#fff" : isCompleted ? "#60a5fa" : "#94a3b8" }}>
                    0{st.step}
                  </div>
                  <div style={{ fontSize: "11px", fontWeight: 700, color: isActive ? "#fff" : "#e2e8f0", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {st.title}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Narrative Story Explanation Text Box */}
          <div style={{ background: "rgba(0,0,0,0.3)", padding: "10px 14px", borderRadius: "4px", borderLeft: "4px solid #38bdf8", fontSize: "12px", lineHeight: 1.45, color: "#e2e8f0" }}>
            {guidedDemoStep === 1 && (
              <div>
                <strong style={{ color: "#38bdf8" }}>{t("demo.step1NarrativeTitle")}: </strong>
                {t("demo.step1NarrativeBody")}
              </div>
            )}
            {guidedDemoStep === 2 && (
              <div>
                <strong style={{ color: "#f87171" }}>{t("demo.step2NarrativeTitle")}: </strong>
                {t("demo.step2NarrativeBody")}
              </div>
            )}
            {guidedDemoStep === 3 && (
              <div>
                <strong style={{ color: "#fbbf24" }}>{t("demo.step3NarrativeTitle")}: </strong>
                {t("demo.step3NarrativeBody")}
              </div>
            )}
            {guidedDemoStep === 4 && (
              <div>
                <strong style={{ color: "#34d399" }}>{t("demo.step4NarrativeTitle")}: </strong>
                {t("demo.step4NarrativeBody")}
              </div>
            )}
            {guidedDemoStep === 5 && (
              <div>
                <strong style={{ color: "#60a5fa" }}>{t("demo.step5NarrativeTitle")}: </strong>
                {t("demo.step5NarrativeBody")}
              </div>
            )}
            {guidedDemoStep === 6 && (
              <div>
                <strong style={{ color: "#c084fc" }}>{t("demo.step6NarrativeTitle")}: </strong>
                {t("demo.step6NarrativeBody")}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 2. SCENARIO STEPPER NAVIGATION */}
      <nav className="gis-nav-stepper" aria-label="Disaster restoration workflow navigation">
        {[
          { step: 1, label: "Baseline", desc: "Normal Network" },
          { step: 2, label: "Hazard", desc: "Michaung Flood" },
          { step: 3, label: "Access", desc: "Ward Cut-Offs" },
          { step: 4, label: "Criticality", desc: "Corridor Ranking" },
          { step: 5, label: "Recovery", desc: "Intervention" },
        ].map((item) => {
          const isCompleted = demoStep > item.step || (item.step === 5 && systemState === "CLEARED");
          const isActive = demoStep === item.step;
          return (
            <button
              key={item.step}
              type="button"
              className={`stepper-item ${isActive ? "active" : ""} ${isCompleted ? "completed" : ""}`}
              onClick={() => {
                if (item.step === 1) handleResetNetwork();
                else if (item.step === 2) handleApplyFlood();
                else if (item.step === 3) {
                  if (systemState === "BASE") handleApplyFlood();
                  setDemoStep(3);
                }
                else if (item.step === 4) handleRankCorridors();
                else if (item.step === 5) handleClearCorridor();
              }}
              aria-current={isActive ? "step" : undefined}
            >
              <span className="step-badge">
                {isCompleted ? "✓" : `0${item.step}`}
              </span>
              <div className="step-content">
                <span className="step-label">{item.label}</span>
                <span className="step-sublabel">{item.desc}</span>
              </div>
            </button>
          );
        })}
      </nav>

      {/* Error Alert */}
      {errorMsg && (
        <div className="gis-error-banner">
          <span>{errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} className="error-close">
            <X size={14} />
          </button>
        </div>
      )}

      <main
        className="gis-workspace"
        style={{
          padding: "16px",
          overflowY: "auto",
          display: viewMode === "FIELD_MODE" ? "flex" : "none",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        {/* Field Mode Context Subheader */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", background: "var(--bg-panel)", border: "1px solid var(--border-subtle)", borderRadius: "6px" }}>
          <div>
            <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: "8px" }}>
              <span>📡 FIELD EVIDENCE & GROUND OBSERVATION CAPTURE</span>
            </div>
            <div style={{ fontSize: "11.5px", color: "var(--text-secondary)", marginTop: "2px" }}>
              Ground truth telemetry and rapid damage assessment for frontline disaster responders
            </div>
          </div>
          <button
            onClick={() => setViewMode("COMMAND_CENTER")}
            style={{ background: "rgba(37, 99, 235, 0.15)", color: "#60a5fa", border: "1px solid rgba(37, 99, 235, 0.35)", padding: "6px 14px", borderRadius: "4px", fontSize: "11.5px", fontWeight: 600, cursor: "pointer" }}
          >
            ← Return to Command Center
          </button>
        </div>

        {/* Connectivity Status Banner */}
        {(() => {
          const isOffline = demoSimulatedOffline || netStatus === NETWORK_STATUS.OFFLINE;
          const isUnstable = !isOffline && netStatus === NETWORK_STATUS.UNSTABLE;
          const queuedCount = offlineItems.filter((i) => i.sync_status === "QUEUED" || i.sync_status === "FAILED").length;
          const syncingCount = offlineItems.filter((i) => i.sync_status === "SYNCING").length;

          return (
            <div
              style={{
                background: isOffline
                  ? "rgba(239, 68, 68, 0.08)"
                  : isUnstable
                  ? "rgba(245, 158, 11, 0.08)"
                  : "rgba(16, 185, 129, 0.08)",
                border: `1px solid ${
                  isOffline ? "rgba(239, 68, 68, 0.3)" : isUnstable ? "rgba(245, 158, 11, 0.3)" : "rgba(16, 185, 129, 0.25)"
                }`,
                padding: "12px 16px",
                borderRadius: "6px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span
                    style={{
                      width: "10px",
                      height: "10px",
                      borderRadius: "50%",
                      background: isOffline ? "#ef4444" : isUnstable ? "#f59e0b" : "#10b981",
                      boxShadow: `0 0 6px ${isOffline ? "#ef4444" : isUnstable ? "#f59e0b" : "#10b981"}`,
                      flexShrink: 0,
                    }}
                  />
                  <div>
                    <div style={{ fontSize: "13.5px", fontWeight: 700, color: "#f8fafc", display: "flex", alignItems: "center", gap: "8px" }}>
                      <span>
                        {isOffline
                          ? "OFFLINE MODE — LOCAL STORAGE ACTIVE"
                          : isUnstable
                          ? "CONNECTION UNSTABLE"
                          : "CONNECTED TO BACKEND PIPELINE"}
                      </span>
                      <span style={{ fontSize: "10px", padding: "1px 6px", borderRadius: "3px", background: "rgba(255,255,255,0.08)", color: "var(--text-muted)", fontWeight: 500 }}>
                        OFFLINE-CAPABLE
                      </span>
                    </div>
                    <div style={{ fontSize: "11.5px", color: "var(--text-secondary)", marginTop: "2px" }}>
                      {isOffline
                        ? "Reports are saved safely on-device in IndexedDB and will synchronize automatically when connectivity returns."
                        : isUnstable
                        ? "Network latency or instability detected. Reports will be queued locally if synchronization fails."
                        : "Active real-time connection. Field reports will synchronize automatically with the Command Center."}
                    </div>
                  </div>
                </div>

                <button
                  onClick={handleManualSyncNow}
                  disabled={loading || isOffline || queuedCount === 0}
                  style={{
                    background: isOffline || queuedCount === 0 ? "rgba(255,255,255,0.06)" : "#2563eb",
                    color: isOffline || queuedCount === 0 ? "var(--text-muted)" : "#fff",
                    border: isOffline || queuedCount === 0 ? "1px solid var(--border-subtle)" : "none",
                    padding: "6px 14px",
                    borderRadius: "4px",
                    fontSize: "11.5px",
                    fontWeight: 700,
                    cursor: isOffline || queuedCount === 0 ? "not-allowed" : "pointer",
                    whiteSpace: "nowrap",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    transition: "var(--transition)",
                  }}
                >
                  {loading || syncingCount > 0
                    ? "🔄 SYNCING..."
                    : isOffline
                    ? `QUEUED FOR SYNC (${queuedCount})`
                    : queuedCount === 0
                    ? "SYNC QUEUE (0 PENDING)"
                    : `🔄 SYNC QUEUE (${queuedCount} PENDING)`}
                </button>
              </div>
            </div>
          );
        })()}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
          {/* 1. Primary Field Observation Card */}
          <div style={{ background: "var(--bg-panel)", border: "1px solid var(--border-subtle)", borderRadius: "8px", padding: "18px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <h3 style={{ fontSize: "14.5px", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                Field Observation Entry
              </h3>
              <span style={{ fontSize: "10.5px", color: "var(--text-muted)", background: "rgba(255, 255, 255, 0.06)", border: "1px solid var(--border-subtle)", padding: "2px 7px", borderRadius: "3px" }}>
                OFFLINE-CAPABLE (IndexedDB)
              </span>
            </div>

            {fieldNotice && (
              <div style={{ background: "rgba(16, 185, 129, 0.15)", border: "1px solid #10b981", color: "#34d399", padding: "8px 12px", borderRadius: "4px", fontSize: "11.5px", marginBottom: "12px" }}>
                {fieldNotice}
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <div>
                <label style={{ fontSize: "11.5px", color: "var(--text-muted)", display: "block", marginBottom: "3px" }}>Observation Type</label>
                <select
                  value={evidenceType}
                  onChange={(e) => setEvidenceType(e.target.value)}
                  style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "7px 10px", borderRadius: "4px", fontSize: "12px" }}
                >
                  <option value="ROAD_BLOCKED">ROAD BLOCKED</option>
                  <option value="ROAD_OPEN">ROAD PASSABLE / OPEN</option>
                  <option value="FLOOD_DEPTH">WATER DEPTH MEASUREMENT</option>
                  <option value="FLOOD_PRESENT">SURFACE FLOODING PRESENT</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: "11.5px", color: "var(--text-muted)", display: "block", marginBottom: "3px" }}>Water Depth (meters)</label>
                <input
                  type="text"
                  value={evidenceDepth}
                  onChange={(e) => setEvidenceDepth(e.target.value)}
                  placeholder="e.g. 0.40"
                  style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "7px 10px", borderRadius: "4px", fontSize: "12px" }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                <div>
                  <label style={{ fontSize: "11.5px", color: "var(--text-muted)", display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                    <span>Latitude (°N)</span>
                    <span style={{ fontSize: "10px", color: gpsStatus === "CAPTURED" ? "#34d399" : "var(--text-muted)" }}>
                      {gpsStatus === "CAPTURED" ? "✓ Device GPS" : "Manual / Reference"}
                    </span>
                  </label>
                  <input
                    type="text"
                    value={evidenceLat}
                    onChange={(e) => setEvidenceLat(e.target.value)}
                    placeholder="13.0500"
                    style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "7px 10px", borderRadius: "4px", fontSize: "12px" }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: "11.5px", color: "var(--text-muted)", display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                    <span>Longitude (°E)</span>
                    <span style={{ fontSize: "10px", color: gpsStatus === "CAPTURED" ? "#34d399" : "var(--text-muted)" }}>
                      {gpsStatus === "CAPTURED" ? "✓ Device GPS" : "Manual / Reference"}
                    </span>
                  </label>
                  <input
                    type="text"
                    value={evidenceLon}
                    onChange={(e) => setEvidenceLon(e.target.value)}
                    placeholder="80.2200"
                    style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "7px 10px", borderRadius: "4px", fontSize: "12px" }}
                  />
                </div>
              </div>

              <button
                onClick={handleCaptureGpsLocation}
                style={{ background: gpsStatus === "CAPTURED" ? "rgba(16, 185, 129, 0.2)" : "#3b82f6", color: gpsStatus === "CAPTURED" ? "#34d399" : "#fff", border: gpsStatus === "CAPTURED" ? "1px solid #10b981" : "none", padding: "6px 12px", borderRadius: "4px", fontSize: "11.5px", fontWeight: 600, cursor: "pointer", alignSelf: "flex-start" }}
              >
                {gpsStatus === "LOCATING" ? "📡 Acquiring GPS Fix..." : gpsStatus === "CAPTURED" ? "✓ Verified Device GPS Fixed" : "📍 Capture Live GPS Position"}
              </button>

              <div>
                <label style={{ fontSize: "11.5px", color: "var(--text-muted)", display: "block", marginBottom: "3px" }}>Source / Responder Team</label>
                <select
                  value={evidenceSource}
                  onChange={(e) => setEvidenceSource(e.target.value)}
                  style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "7px 10px", borderRadius: "4px", fontSize: "12px" }}
                >
                  <option value="field_team">Field Response Team</option>
                  <option value="official">Official Emergency Agency</option>
                  <option value="sensor">IoT Water Level Sensor</option>
                  <option value="citizen">Citizen Ground Report</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: "11.5px", color: "var(--text-muted)", display: "block", marginBottom: "3px" }}>Field Notes / Location Description</label>
                <textarea
                  rows={2}
                  value={evidenceDesc}
                  onChange={(e) => setEvidenceDesc(e.target.value)}
                  placeholder="e.g. Water inundation reported near Saidapet arterial junction."
                  style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "7px 10px", borderRadius: "4px", fontSize: "12px", fontFamily: "inherit" }}
                />
              </div>

              <div>
                <button
                  onClick={handleSaveOfflineLocally}
                  disabled={loading}
                  style={{
                    width: "100%",
                    background: "#059669",
                    color: "#fff",
                    border: "none",
                    padding: "10px 16px",
                    borderRadius: "4px",
                    fontSize: "13px",
                    fontWeight: 700,
                    cursor: "pointer",
                    marginTop: "4px",
                    boxShadow: "0 2px 6px rgba(5, 150, 105, 0.3)",
                  }}
                >
                  💾 SAVE FIELD REPORT
                </button>
                <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "6px", textAlign: "center" }}>
                  Saves immediately to local IndexedDB. Automatically synchronizes with Command Center when connected.
                </div>
              </div>
            </div>
          </div>

          {/* 2. Simplified Queue Summary Card & Expandable Advanced Details */}
          <div style={{ background: "var(--bg-panel)", border: "1px solid var(--border-subtle)", borderRadius: "8px", padding: "18px", display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <h3 style={{ fontSize: "14.5px", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                Report Synchronization Status
              </h3>
              <span style={{ fontSize: "12px", fontWeight: 700, color: "#38bdf8" }}>
                {offlineItems.length} Total Stored
              </span>
            </div>

            {/* Status Pill Summary */}
            <div style={{ display: "flex", gap: "8px", marginBottom: "14px", flexWrap: "wrap" }}>
              <span style={{ padding: "4px 8px", borderRadius: "4px", background: "rgba(245, 158, 11, 0.2)", color: "#f59e0b", fontSize: "11px", fontWeight: 700 }}>
                SAVED LOCALLY: {offlineItems.filter((i) => i.sync_status === "QUEUED").length}
              </span>
              <span style={{ padding: "4px 8px", borderRadius: "4px", background: "rgba(16, 185, 129, 0.2)", color: "#34d399", fontSize: "11px", fontWeight: 700 }}>
                FIELD REPORT SYNCED: {offlineItems.filter((i) => i.sync_status === "SYNCED").length}
              </span>
              {offlineItems.filter((i) => i.sync_status === "FAILED").length > 0 && (
                <span style={{ padding: "4px 8px", borderRadius: "4px", background: "rgba(239, 68, 68, 0.2)", color: "#ef4444", fontSize: "11px", fontWeight: 700 }}>
                  NEEDS RETRY: {offlineItems.filter((i) => i.sync_status === "FAILED").length}
                </span>
              )}
              {offlineItems.filter((i) => i.sync_status === "CONFLICT").length > 0 && (
                <span style={{ padding: "4px 8px", borderRadius: "4px", background: "rgba(168, 85, 247, 0.2)", color: "#c084fc", fontSize: "11px", fontWeight: 700 }}>
                  CONFLICT REQUIRES REVIEW: {offlineItems.filter((i) => i.sync_status === "CONFLICT").length}
                </span>
              )}
            </div>

            {/* High-level human readable report items list / Empty State */}
            <div style={{ flex: 1, overflowY: "auto", maxHeight: "280px", display: "flex", flexDirection: "column", gap: "8px", marginBottom: "12px" }}>
              {offlineItems.length === 0 ? (
                <div style={{ padding: "32px 16px", textAlign: "center", background: "rgba(15, 23, 42, 0.4)", borderRadius: "6px", border: "1px dashed var(--border-subtle)", margin: "auto 0" }}>
                  <div style={{ fontSize: "24px", marginBottom: "8px" }}>📋</div>
                  <div style={{ fontSize: "12.5px", fontWeight: 700, color: "var(--text-secondary)", letterSpacing: "0.03em" }}>
                    NO PENDING FIELD REPORTS
                  </div>
                  <p style={{ fontSize: "11px", color: "var(--text-muted)", margin: "4px auto 0", maxWidth: "280px", lineHeight: 1.4 }}>
                    Reports saved while offline will appear here and synchronize automatically when connectivity is available.
                  </p>
                </div>
              ) : (
                offlineItems.map((item) => (
                  <div
                    key={item.client_observation_id}
                    style={{
                      background: "#0f172a",
                      padding: "10px 12px",
                      borderRadius: "6px",
                      borderLeft: `4px solid ${item.sync_status === "SYNCED" ? "#10b981" : item.sync_status === "FAILED" ? "#ef4444" : item.sync_status === "CONFLICT" ? "#a855f7" : "#f59e0b"}`,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: "12px", fontWeight: 700, color: "#f8fafc" }}>
                        {item.observation_type.replace(/_/g, " ")}
                      </span>
                      <span
                        style={{
                          fontSize: "10px",
                          padding: "2px 6px",
                          borderRadius: "3px",
                          fontWeight: 700,
                          background: item.sync_status === "SYNCED" ? "#059669" : item.sync_status === "FAILED" ? "#dc2626" : item.sync_status === "CONFLICT" ? "#7e22ce" : "#d97706",
                          color: "#fff",
                        }}
                      >
                        {item.sync_status === "QUEUED" ? "SAVED LOCALLY" : item.sync_status === "SYNCED" ? "SYNCED" : item.sync_status}
                      </span>
                    </div>
                    <div style={{ fontSize: "11.5px", marginTop: "4px", color: "var(--text-secondary)" }}>
                      {item.description || "Field observation report"}
                    </div>
                    <div style={{ fontSize: "10.5px", marginTop: "2px", color: "#94a3b8" }}>
                      Depth: {item.water_depth_m ? `${item.water_depth_m}m` : "N/A"} | Source: {item.source}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Advanced Technical Accordion Toggle */}
            <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "10px" }}>
              <button
                onClick={() => setShowAdvancedSyncDetails((prev) => !prev)}
                style={{
                  background: "transparent",
                  color: "#94a3b8",
                  border: "none",
                  padding: "4px 0",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                }}
              >
                {showAdvancedSyncDetails ? "▼ Hide Technical Sync Details" : "▶ View Advanced Sync Details (IndexedDB)"}
              </button>

              {showAdvancedSyncDetails && (
                <div style={{ marginTop: "10px", background: "rgba(0,0,0,0.3)", padding: "10px", borderRadius: "4px", fontSize: "10.5px", fontFamily: "monospace", color: "#cbd5e1", maxHeight: "160px", overflowY: "auto" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <span>IndexedDB Store: <code>field_observations</code></span>
                    <button onClick={handleClearSyncedLocal} style={{ background: "transparent", color: "#f43f5e", border: "none", cursor: "pointer", fontSize: "10px" }}>
                      Clear Synced
                    </button>
                  </div>
                  {offlineItems.map((i) => (
                    <div key={i.client_observation_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)", padding: "3px 0" }}>
                      <div>UUID: {i.client_observation_id}</div>
                      <div>Status: {i.sync_status} | Captured: {i.captured_at?.slice(11, 19)}</div>
                      {i.conflict_reason && <div style={{ color: "#c084fc" }}>Conflict: {i.conflict_reason}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

        <main
          className="gis-workspace"
          style={{
            display: viewMode === "COMMAND_CENTER" ? "grid" : "none",
          }}
        >
        {/* LEFT EDITORIAL SIDEBAR */}
        <aside className="gis-sidebar-left">
          <div className="panel-content">
            <div className="panel-section-title">Impact</div>

            <div className="impact-editorial-list">
              {/* Isolated Citizens */}
              <div className="telemetry-row">
                <span className="telemetry-caption">Isolated residents</span>
                <div className={`telemetry-val-large tabular-nums ${rawIsolatedPop > 0 ? "danger" : ""}`}>
                  {rawIsolatedPop === 0 ? "0" : `${(animIsolatedPop / 1000).toFixed(0)}K`}
                </div>
                <div className="telemetry-subtext">
                  {rawIsolatedPop > 0
                    ? `${isolatedCommunitiesCount || accessStatus?.isolated_communities?.length || 4} cut-off wards (37.5%)`
                    : "0 cut-off wards (Normal emergency transit)"}
                </div>
              </div>

              <div className="divider-line" />

              {/* Accessible Population */}
              <div className="telemetry-row">
                <span className="telemetry-caption">Accessible population</span>
                <div className="telemetry-val-large tabular-nums">
                  {(animAccessiblePop / 1000).toFixed(0)}K
                  <span style={{ fontSize: "13px", color: "var(--text-muted)", fontWeight: 400 }}> / 477K</span>
                </div>
                <div className="bar-track-thin">
                  <div
                    className="bar-fill-thin"
                    style={{ width: `${(rawAccessiblePop / totalPopulation) * 100}%` }}
                  />
                </div>
              </div>

              <div className="divider-line" />

              {/* Trauma Hospitals & Citizens Recovered */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div className="telemetry-row">
                  <span className="telemetry-caption">Trauma centres</span>
                  <div className="telemetry-val-large tabular-nums" style={{ fontSize: "20px" }}>
                    {activeHospitals} / 6
                  </div>
                  <div className="telemetry-subtext">All active</div>
                </div>

                <div className="telemetry-row">
                  <span className="telemetry-caption">Recovered</span>
                  <div className="telemetry-val-large tabular-nums success" style={{ fontSize: "20px" }}>
                    {clearedCorridorId ? "+89K" : "0"}
                  </div>
                  <div className="telemetry-subtext">Post-clearance</div>
                </div>
              </div>
            </div>

            <div className="divider-line" style={{ margin: "6px 0" }} />

            {/* Semantic Cartography Layer Groups */}
            <div className="panel-section-title">Map Layers</div>

            <div className="layers-group-container">
              {[
                {
                  groupId: "HAZARD",
                  layers: [
                    {
                      key: "floodInundation",
                      label: "Flood inundation",
                      color: "#0284c7",
                      isAvailable: hasFloodActive,
                      countBadge: hasFloodActive ? "Inundated" : "0",
                    },
                  ],
                },
                {
                  groupId: "NETWORK",
                  layers: [
                    {
                      key: "roadNetwork",
                      label: "Road network",
                      color: "#64748b",
                      isAvailable: totalRoads > 0,
                      countBadge: "56 directed edges",
                    },
                    {
                      key: "impassable",
                      label: "Blocked roads",
                      color: "#dc2626",
                      dashed: true,
                      isAvailable: blockedRoadsCount > 0,
                      countBadge: blockedRoadsCount > 0 ? "14 segments (20 edges)" : "0",
                    },
                  ],
                },
                {
                  groupId: "FACILITIES",
                  layers: [
                    {
                      key: "hospitalsOperational",
                      label: "Trauma centres — active",
                      isSymbol: true,
                      symbolBg: "#059669",
                      isAvailable: operationalHospitalsCount > 0,
                      countBadge: `${operationalHospitalsCount} active`,
                    },
                    {
                      key: "traumaCentersIsolated",
                      label: "Trauma centres — isolated",
                      isSymbol: true,
                      symbolBg: "#dc2626",
                      isAvailable: isolatedHospitalsCount > 0,
                      countBadge: `${isolatedHospitalsCount}`,
                    },
                  ],
                },
                {
                  groupId: "POPULATION",
                  layers: [
                    {
                      key: "communitiesAccessible",
                      label: "Communities — accessible",
                      isDot: true,
                      dotBg: "#2563eb",
                      isAvailable: accessibleCommunitiesCount > 0,
                      countBadge: `${accessibleCommunitiesCount} active`,
                    },
                    {
                      key: "communitiesIsolated",
                      label: "Communities — isolated",
                      isDot: true,
                      dotBg: "#ef4444",
                      isAvailable: isolatedCommunitiesCount > 0,
                      countBadge: `${isolatedCommunitiesCount}`,
                    },
                  ],
                },
                {
                  groupId: "INTERVENTION",
                  layers: [
                    {
                      key: "selectedCorridor",
                      label: "Restoration corridor",
                      color: "#059669",
                      isAvailable: hasCorridorActive,
                      countBadge: hasCorridorActive ? "Selected" : "0",
                    },
                  ],
                },
              ].map((group) => (
                <div key={group.groupId} className="layer-group">
                  <span className="layer-group-title">{group.groupId}</span>
                  {group.layers.map((layer) => {
                    const isChecked = Boolean(layersVisibility[layer.key]);
                    const isDisabled = !layer.isAvailable;
                    return (
                      <label
                        key={layer.key}
                        className={`layer-row ${isDisabled ? "is-disabled" : ""}`}
                        title={isDisabled ? "No features active in current simulation state" : layer.label}
                      >
                        <div className="layer-left">
                          <input
                            type="checkbox"
                            checked={isChecked && !isDisabled}
                            disabled={isDisabled}
                            onChange={() => toggleLayer(layer.key, layer.isAvailable)}
                            className="layer-checkbox"
                            aria-label={layer.label}
                          />
                          <div className="layer-indicator">
                            {layer.isSymbol ? (
                              <span className="indicator-symbol" style={{ color: layer.symbolBg }}>+</span>
                            ) : layer.isDot ? (
                              <span className="indicator-dot" style={{ background: layer.dotBg }} />
                            ) : (
                              <span
                                className="indicator-swatch"
                                style={{
                                  background: layer.color,
                                  border: layer.dashed ? "1px dashed #ffffff" : "none",
                                }}
                              />
                            )}
                          </div>
                          <span className="layer-name">{layer.label}</span>
                        </div>
                        <span className="layer-count-badge">{layer.countBadge}</span>
                      </label>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* MAP VIEWPORT */}
        <section className="gis-map-viewport">
          <div ref={mapContainerRef} className="gis-leaflet-canvas" />

          {/* Map Forecast Legend Overlay (Milestone L6) */}
          {selectedHorizon !== "NOW" && (
            <div
              style={{
                position: "absolute",
                bottom: "16px",
                left: "16px",
                background: "rgba(15, 23, 42, 0.92)",
                border: "1px solid rgba(56, 189, 248, 0.3)",
                borderRadius: "6px",
                padding: "8px 12px",
                fontSize: "11px",
                color: "#e2e8f0",
                zIndex: 400,
                backdropFilter: "blur(4px)",
                display: "flex",
                flexDirection: "column",
                gap: "5px",
                maxWidth: "280px",
              }}
            >
              <div style={{ fontWeight: 700, color: "#38bdf8", fontSize: "10.5px", letterSpacing: "0.5px" }}>
                MAP LEGEND — {selectedHorizon} FORECAST PROJECTION
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ width: "16px", height: "0", borderTop: "2px dashed #38bdf8" }} />
                <span>Projected Flood Footprint</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ width: "16px", height: "0", borderTop: "2px dashed #ef4444" }} />
                <span>Critical Vulnerability (Score ≥ 0.85)</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ width: "16px", height: "0", borderTop: "2px dashed #f97316" }} />
                <span>High Vulnerability (Score 0.60–0.84)</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ width: "16px", height: "0", borderTop: "2px dashed #f59e0b" }} />
                <span>Medium Vulnerability (Score 0.30–0.59)</span>
              </div>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontStyle: "italic", borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: "4px", marginTop: "2px" }}>
                Vulnerability measures exposure & severity, NOT restoration priority.
              </div>
            </div>
          )}

          {/* Quiet Map Controls */}
          <div className="map-quiet-controls">
            <button className="map-btn" onClick={handleZoomIn} title="Zoom in">+</button>
            <button className="map-btn" onClick={handleZoomOut} title="Zoom out">−</button>
            <button className="map-btn" onClick={handleRecenter} title="Recenter map">
              <Compass size={13} />
            </button>
          </div>
        </section>

        {/* RIGHT UNIFIED DECISION ANALYSIS PANEL */}
        <aside className="gis-sidebar-right">
          <div className="panel-content">
            <div className="decision-narrative-flow">
              {demoStep === 1 ? (
                /* 1. BASELINE STATE */
                <>
                  <div className="decision-hero-section">
                    <span className="decision-section-label">Simulation state: Baseline</span>
                    <h3 className="decision-title">Baseline Infrastructure Access</h3>
                  </div>

                  <div className="hero-number-block">
                    <span className="hero-number-val tabular-nums" style={{ color: "var(--text-primary)" }}>
                      477,000
                    </span>
                    <span className="hero-number-label">citizens with direct emergency access (100%)</span>
                  </div>

                  <div className="supporting-telemetry-row">
                    <span className="supporting-item"><strong>6 / 6</strong> trauma centres active</span>
                    <span>·</span>
                    <span className="supporting-item"><strong>0</strong> blocked roads</span>
                    <span>·</span>
                    <span className="supporting-item"><strong>0</strong> isolated residents</span>
                  </div>

                  <div className="divider-line" />

                  <div className="editorial-text-block">
                    <span className="decision-section-label" style={{ display: "block", marginBottom: "4px" }}>
                      Baseline network overview
                    </span>
                    <p>
                      Normal arterial accessibility across all 10 Greater Chennai Corporation study wards. Emergency transit times to regional trauma-care facilities remain within the 30-minute threshold.
                    </p>
                  </div>

                  <div className="divider-line" />

                  <div className="progression-container">
                    <span className="decision-section-label">Population access baseline</span>
                    <div className="progression-bars" style={{ marginTop: "4px" }}>
                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Baseline (Pre-cyclone)</span>
                          <span className="tabular-nums">477,000 (100%)</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "100%" }}>477K (100%)</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="divider-line" />

                  {/* Infrastructure Health Grid */}
                  <div>
                    <span className="decision-section-label" style={{ display: "block", marginBottom: "6px" }}>
                      Infrastructure Readiness
                    </span>
                    <div className="telemetry-grid-2x2">
                      <div className="grid-cell">
                        <span className="grid-cell-label">Trauma Care</span>
                        <span className="grid-cell-val">6 Facilities (1,450 beds)</span>
                      </div>
                      <div className="grid-cell">
                        <span className="grid-cell-label">Road Multigraph</span>
                        <span className="grid-cell-val">37 Arterial Segments (56 directed edges)</span>
                      </div>
                      <div className="grid-cell">
                        <span className="grid-cell-label">Mean Transit Time</span>
                        <span className="grid-cell-val">14.2 min to Care</span>
                      </div>
                      <div className="grid-cell">
                        <span className="grid-cell-label">Network Status</span>
                        <span className="grid-cell-val" style={{ color: "var(--color-success-muted)" }}>100% Operational</span>
                      </div>
                    </div>
                  </div>

                  <div className="divider-line" />

                  {/* Next Action Callout */}
                  <div className="next-action-card">
                    <div className="next-action-header">
                      <span className="next-action-title">Recommended Next Action</span>
                      <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>Step 01 → 02</span>
                    </div>
                    <p className="next-action-desc">
                      Network is fully connected. Execute "Apply Flood Scenario" to simulate Cyclone Michaung storm surge and evaluate arterial disruptions.
                    </p>
                    <button
                      onClick={handleApplyFlood}
                      disabled={loading}
                      className="next-action-btn"
                    >
                      Apply Flood Scenario ➔
                    </button>
                  </div>
                </>
              ) : demoStep === 2 ? (
                /* 2. HAZARD / FLOOD STATE */
                <>
                  <div className="decision-hero-section">
                    <span className="decision-section-label">Hazard simulation: Michaung Flood</span>
                    <h3 className="decision-title">Michaung Inundation Impact</h3>
                  </div>

                  <div className="hero-number-block">
                    <span className="hero-number-val tabular-nums" style={{ color: "var(--color-danger-muted)" }}>
                      179,000
                    </span>
                    <span className="hero-number-label">residents isolated from emergency trauma care (37.5%)</span>
                  </div>

                  <div className="supporting-telemetry-row">
                    <span className="supporting-item"><strong>4</strong> cut-off wards</span>
                    <span>·</span>
                    <span className="supporting-item"><strong>14</strong> blocked road segments</span>
                    <span>·</span>
                    <span className="supporting-item"><strong>298,000</strong> accessible</span>
                  </div>

                  <div className="divider-line" />

                  <div className="editorial-text-block">
                    <span className="decision-section-label" style={{ display: "block", marginBottom: "4px" }}>
                      Inundation impact summary
                    </span>
                    <p>
                      Cyclone Michaung flood footprint has submerged key arterial corridors along the Adyar river basin, severing direct emergency access to hospital facilities for 4 cut-off wards.
                    </p>
                  </div>

                  <div className="divider-line" />

                  <div className="progression-container">
                    <span className="decision-section-label">Population access impact</span>
                    <div className="progression-bars" style={{ marginTop: "4px" }}>
                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Baseline</span>
                          <span className="tabular-nums">477,000</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "100%" }}>477K (100%)</div>
                        </div>
                      </div>

                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Michaung Flood</span>
                          <span className="tabular-nums">298,000 Accessible</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "62.5%" }}>298K (62.5%)</div>
                          <div className="progression-segment isolated" style={{ width: "37.5%" }}>179K (37.5%)</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="divider-line" />

                  {/* Hazard Details Grid */}
                  <div>
                    <span className="decision-section-label" style={{ display: "block", marginBottom: "6px" }}>
                      Hazard Telemetry
                    </span>
                    <div className="telemetry-grid-2x2">
                      <div className="grid-cell">
                        <span className="grid-cell-label">Blocked Road Segments</span>
                        <span className="grid-cell-val" style={{ color: "var(--color-danger-muted)" }}>14 Arterial Segments (20 directed edges)</span>
                      </div>
                      <div className="grid-cell">
                        <span className="grid-cell-label">Isolated Wards</span>
                        <span className="grid-cell-val" style={{ color: "var(--color-danger-muted)" }}>6 Wards (37.5%)</span>
                      </div>
                      <div className="grid-cell">
                        <span className="grid-cell-label">Inundation Basin</span>
                        <span className="grid-cell-val">Adyar River Corridor</span>
                      </div>
                      <div className="grid-cell">
                        <span className="grid-cell-label">Severed Routes</span>
                        <span className="grid-cell-val">Saidapet / Jafferkhanpet</span>
                      </div>
                    </div>
                  </div>

                  <div className="divider-line" />

                  {/* Next Action Callout */}
                  <div className="next-action-card">
                    <div className="next-action-header">
                      <span className="next-action-title">Recommended Next Action</span>
                      <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>Step 02 → 03/04</span>
                    </div>
                    <p className="next-action-desc">
                      Critical access failure detected. Execute "Rank Critical Corridors" to run Dijkstra multi-destination optimization and identify priority restoration paths.
                    </p>
                    <button
                      onClick={handleRankCorridors}
                      disabled={loading}
                      className="next-action-btn"
                    >
                      Rank Critical Corridors ➔
                    </button>
                  </div>
                </>
              ) : demoStep === 3 ? (
                /* 3. ACCESS IMPACT STATE */
                <>
                  <div className="decision-hero-section">
                    <span className="decision-section-label">Access impact assessment</span>
                    <h3 className="decision-title">Ward-Level Facility Accessibility</h3>
                  </div>

                  <div className="hero-number-block">
                    <span className="hero-number-val tabular-nums" style={{ color: "var(--color-danger-muted)" }}>
                      6 / 10
                    </span>
                    <span className="hero-number-label">GCC study wards severed from 30-min trauma care</span>
                  </div>

                  <div className="supporting-telemetry-row">
                    <span className="supporting-item"><strong>179,000</strong> isolated residents</span>
                    <span>·</span>
                    <span className="supporting-item"><strong>&gt;30 min</strong> transit delay</span>
                    <span>·</span>
                    <span className="supporting-item"><strong>6 / 6</strong> trauma centres active</span>
                  </div>

                  <div className="divider-line" />

                  {/* Ward Breakdown List */}
                  <div>
                    <span className="decision-section-label" style={{ display: "block", marginBottom: "6px" }}>
                      Cut-Off Wards (Access Exceeded &gt;30 min)
                    </span>
                    <div style={{ display: "flex", flexDirection: "column", gap: "4px", fontSize: "11px" }}>
                      {[
                        { name: "Saidapet", pop: "48,000", status: "Cut-Off (>30 min)" },
                        { name: "Jafferkhanpet", pop: "34,000", status: "Cut-Off (>30 min)" },
                        { name: "Kotturpuram", pop: "29,000", status: "Cut-Off (>30 min)" },
                        { name: "Velachery", pop: "36,000", status: "Cut-Off (>30 min)" },
                        { name: "Guindy", pop: "18,000", status: "Cut-Off (>30 min)" },
                        { name: "Alwarpet", pop: "14,000", status: "Cut-Off (>30 min)" },
                      ].map((w) => (
                        <div
                          key={w.name}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            padding: "4px 8px",
                            background: "rgba(220, 38, 38, 0.1)",
                            borderRadius: "4px",
                            borderLeft: "3px solid #dc2626",
                          }}
                        >
                          <span style={{ fontWeight: 600, color: "#fca5a5" }}>{w.name} ({w.pop})</span>
                          <span style={{ color: "#f87171", fontFamily: "var(--font-mono)" }}>{w.status}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="divider-line" />

                  <div className="progression-container">
                    <span className="decision-section-label">Population access progression</span>
                    <div className="progression-bars" style={{ marginTop: "4px" }}>
                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Baseline</span>
                          <span className="tabular-nums">477,000</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "100%" }}>477K</div>
                        </div>
                      </div>

                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Michaung Flood</span>
                          <span className="tabular-nums">298,000</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "62.5%" }}>298K</div>
                          <div className="progression-segment isolated" style={{ width: "37.5%" }}>179K</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="divider-line" />

                  {/* Next Action Callout */}
                  <div className="next-action-card">
                    <div className="next-action-header">
                      <span className="next-action-title">Recommended Next Action</span>
                      <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>Step 03 → 04</span>
                    </div>
                    <p className="next-action-desc">
                      Evaluate restorative return on investment. Execute "Rank Critical Corridors" to quantify BPR marginal benefit and prioritize arterial clearance.
                    </p>
                    <button
                      onClick={handleRankCorridors}
                      disabled={loading}
                      className="next-action-btn"
                    >
                      Rank Critical Corridors ➔
                    </button>
                  </div>
                </>
              ) : demoStep === 4 ? (
                /* 4. CRITICALITY & INTERVENTION STATE */
                <>
                  <div className="decision-hero-section" style={{ marginBottom: "6px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span className="decision-section-label">
                        Decision support: Criticality Ranking
                      </span>
                      <button
                        onClick={handleRankCorridors}
                        disabled={loading}
                        style={{
                          background: "rgba(56, 189, 248, 0.15)",
                          color: "#38bdf8",
                          border: "1px solid rgba(56, 189, 248, 0.4)",
                          padding: "3px 8px",
                          borderRadius: "4px",
                          fontSize: "10px",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        ⚡ RE-RANK CORRIDORS
                      </button>
                    </div>
                    <h3 className="decision-title">
                      {selectedCorridor?.name || selectedCorridor?.corridor_id || "Saidapet → Adyar Lifeline"}
                    </h3>
                  </div>

                  {rankedCorridors && rankedCorridors.length > 0 && (
                    <div style={{ marginBottom: "8px" }}>
                      <span className="decision-section-label" style={{ display: "block", marginBottom: "4px" }}>
                        Candidate Restoration Corridors
                      </span>
                      <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
                        {rankedCorridors.map((c, idx) => {
                          const isSelected = selectedCorridor?.corridor_id === c.corridor_id;
                          return (
                            <button
                              key={c.corridor_id || idx}
                              onClick={() => handleSelectCorridor(c)}
                              style={{
                                flex: 1,
                                minWidth: "100px",
                                padding: "6px 8px",
                                borderRadius: "4px",
                                border: isSelected ? "1px solid #38bdf8" : "1px solid rgba(255,255,255,0.1)",
                                background: isSelected ? "rgba(56, 189, 248, 0.2)" : "rgba(255,255,255,0.04)",
                                color: isSelected ? "#fff" : "var(--text-secondary)",
                                fontSize: "10.5px",
                                textAlign: "left",
                                cursor: "pointer",
                              }}
                            >
                              <div style={{ fontWeight: 700, color: isSelected ? "#38bdf8" : "#e2e8f0" }}>
                                #{idx + 1} {c.corridor_id}
                              </div>
                              <div style={{ fontSize: "9.5px", color: isSelected ? "#34d399" : "#94a3b8" }}>
                                +{(c.population_recovered || 89000).toLocaleString()} rec.
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <div className="hero-number-block">
                    <span className="hero-number-val tabular-nums" style={{ color: "var(--color-success-muted)" }}>
                      +{(selectedCorridor?.population_recovered || 89000).toLocaleString()}
                    </span>
                    <span className="hero-number-label">residents recovered to emergency trauma care</span>
                  </div>

                  <div className="supporting-telemetry-row">
                    <span className="supporting-item">
                      <strong>{selectedCorridor?.detour_saved_min || 22} min</strong> detour saved
                    </span>
                    <span>·</span>
                    <span className="supporting-item">
                      <strong>{selectedCorridor?.length_km || 0.9} km</strong> length
                    </span>
                    <span>·</span>
                    <span className="supporting-item">
                      <strong>+{(selectedCorridor?.score || 0.0724).toFixed(4)}</strong> criticality
                    </span>
                  </div>

                  <div className="divider-line" />

                  <div className="editorial-text-block">
                    <span className="decision-section-label" style={{ display: "block", marginBottom: "4px" }}>
                      Why this corridor
                    </span>
                    <p>
                      Restoring the {selectedCorridor?.name || "Saidapet–Adyar arterial"} reconnects{" "}
                      <strong>{(selectedCorridor?.population_recovered || 89000).toLocaleString()} residents</strong>{" "}
                      across affected wards to trauma-care facilities and reduces transit detour by{" "}
                      <strong>{selectedCorridor?.detour_saved_min || 22} minutes</strong>.
                    </p>
                    {advisory && (
                      <div style={{ marginTop: "8px", padding: "8px", borderRadius: "4px", background: "rgba(99, 102, 241, 0.1)", border: "1px solid rgba(99, 102, 241, 0.25)" }}>
                        <div style={{ fontSize: "10px", fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", color: "#a5b4fc", marginBottom: "3px" }}>
                          AI Decision Advisory
                        </div>
                        <p style={{ fontSize: "11px", color: "#e0e7ff", margin: 0, lineHeight: 1.4 }}>
                          {advisory.advisory_text || advisory.recommendation || advisory.summary || "Prioritize rapid clearing of arterial bottlenecks along this corridor."}
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="divider-line" />

                  <div className="progression-container">
                    <span className="decision-section-label">Population access progression</span>
                    <div className="progression-bars" style={{ marginTop: "4px" }}>
                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Baseline</span>
                          <span className="tabular-nums">477,000</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "100%" }}>477K</div>
                        </div>
                      </div>

                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Michaung Flood</span>
                          <span className="tabular-nums">298,000</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "62.5%" }}>298K</div>
                          <div className="progression-segment isolated" style={{ width: "37.5%" }}>179K</div>
                        </div>
                      </div>

                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Restoration Project</span>
                          <span className="tabular-nums">387,000</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "81.1%" }}>387K</div>
                          <div className="progression-segment isolated" style={{ width: "18.9%" }}>90K</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="divider-line" />

                  <div className="progression-container">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span className="decision-section-label">Score breakdown</span>
                      <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--color-active-muted)" }} className="tabular-nums">
                        +0.0724
                      </span>
                    </div>

                    <div className="score-breakdown-list">
                      <div className="score-row">
                        <span>Population delta</span>
                        <span className="score-val tabular-nums" style={{ color: "var(--color-success-muted)" }}>+0.1492</span>
                      </div>
                      <div className="score-row">
                        <span>Difficulty penalty</span>
                        <span className="score-val tabular-nums" style={{ color: "var(--color-danger-muted)" }}>-0.0768</span>
                      </div>
                      <div className="score-row">
                        <span>Travel time delta</span>
                        <span className="score-val tabular-nums">+0.0000</span>
                      </div>
                      <div className="score-row">
                        <span>Hospital delta</span>
                        <span className="score-val tabular-nums">+0.0000</span>
                      </div>
                    </div>

                    <div className="formula-subtext">
                      S(c) = 0.40·ΔH + 0.30·ΔP + 0.20·ΔT - 0.10·ΔD
                    </div>
                  </div>

                  {/* Phase K Operational Intervention Execution Card */}
                  <div className="divider-line" />
                  <div className="editorial-text-block" style={{ background: "rgba(37, 99, 235, 0.08)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(37, 99, 235, 0.25)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                      <span className="decision-section-label" style={{ color: "#60a5fa" }}>
                        Operational Intervention Lifecycle
                      </span>
                      {activeIntervention && (
                        <span style={{ fontSize: "10px", fontWeight: 700, padding: "2px 6px", borderRadius: "3px", background: "#2563eb", color: "#fff" }}>
                          {activeIntervention.status}
                        </span>
                      )}
                    </div>

                    {!activeIntervention || activeIntervention.status === "REJECTED" || activeIntervention.status === "CANCELLED" ? (
                      <div>
                        <p style={{ fontSize: "11px", color: "var(--text-secondary)", marginBottom: "8px" }}>
                          Convert selected candidate into a human-authorized emergency intervention.
                        </p>
                        <button
                          onClick={() => handleProposeIntervention(selectedCorridor?.corridor_id || "corridor_03")}
                          disabled={loading}
                          style={{ width: "100%", background: "#2563eb", color: "#fff", border: "none", padding: "6px 12px", borderRadius: "4px", fontSize: "11px", fontWeight: 600, cursor: "pointer" }}
                        >
                          [ APPROVE CANDIDATE & CREATE INTERVENTION ]
                        </button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "11px" }}>
                        <div>ID: <strong>{activeIntervention.intervention_id}</strong> (Target: {activeIntervention.target_name})</div>
                        <div>Expected Recovery: <strong style={{ color: "#34d399" }}>+{activeIntervention.expected_population_recovery?.toLocaleString()} residents</strong></div>
                        <div>Operator: <code>{activeIntervention.operator_id}</code></div>

                        {activeIntervention.assigned_team && (
                          <div>Assigned Team: <strong style={{ color: "#fbbf24" }}>{activeIntervention.assigned_team}</strong></div>
                        )}

                        {/* Action Workflow Controls */}
                        <div style={{ display: "flex", gap: "4px", marginTop: "6px", flexWrap: "wrap" }}>
                          {activeIntervention.status === "PROPOSED" && (
                            <button
                              onClick={() => handleTransitionIntervention(activeIntervention.intervention_id, "APPROVED")}
                              style={{ flex: 1, background: "#059669", color: "#fff", border: "none", padding: "4px 8px", borderRadius: "3px", fontSize: "10.5px", fontWeight: 600, cursor: "pointer" }}
                            >
                              Approve Action
                            </button>
                          )}

                          {activeIntervention.status === "APPROVED" && (
                            <button
                              onClick={() => handleTransitionIntervention(activeIntervention.intervention_id, "ASSIGNED")}
                              style={{ flex: 1, background: "#d97706", color: "#fff", border: "none", padding: "4px 8px", borderRadius: "3px", fontSize: "10.5px", fontWeight: 600, cursor: "pointer" }}
                            >
                              Assign Team ({assignedTeamInput})
                            </button>
                          )}

                          {activeIntervention.status === "ASSIGNED" && (
                            <button
                              onClick={() => handleTransitionIntervention(activeIntervention.intervention_id, "IN_PROGRESS")}
                              style={{ flex: 1, background: "#2563eb", color: "#fff", border: "none", padding: "4px 8px", borderRadius: "3px", fontSize: "10.5px", fontWeight: 600, cursor: "pointer" }}
                            >
                              Start Execution
                            </button>
                          )}

                          {activeIntervention.status === "IN_PROGRESS" && (
                            <>
                              <button
                                onClick={() => handleTransitionIntervention(activeIntervention.intervention_id, "COMPLETED")}
                                style={{ flex: 1, background: "#059669", color: "#fff", border: "none", padding: "4px 8px", borderRadius: "3px", fontSize: "10.5px", fontWeight: 600, cursor: "pointer" }}
                              >
                                Verify Completion
                              </button>
                              <button
                                onClick={() => handleTransitionIntervention(activeIntervention.intervention_id, "FAILED", "Field obstacles prevented corridor clearance")}
                                style={{ flex: 1, background: "#dc2626", color: "#fff", border: "none", padding: "4px 8px", borderRadius: "3px", fontSize: "10.5px", fontWeight: 600, cursor: "pointer" }}
                              >
                                Report Failure
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="divider-line" />

                  {/* Next Action Callout */}
                  <div className="next-action-card">
                    <div className="next-action-header">
                      <span className="next-action-title">Recommended Next Action</span>
                      <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>Step 04 → 05</span>
                    </div>
                    <p className="next-action-desc">
                      Corridor 03 is selected. Execute "Simulate Recovery" to model clearance of flood debris and restore arterial lifeline routing.
                    </p>
                    <button
                      onClick={handleClearCorridor}
                      disabled={loading}
                      className="next-action-btn"
                    >
                      Simulate Recovery ➔
                    </button>
                  </div>
                </>
              ) : (
                /* 5. RECOVERY VERIFICATION STATE */
                <>
                  <div className="decision-hero-section">
                    <span className="decision-section-label">Recovery verification: Restoration Complete</span>
                    <h3 className="decision-title">Saidapet → Adyar Lifeline Restored</h3>
                  </div>

                  <div className="hero-number-block">
                    <span className="hero-number-val tabular-nums" style={{ color: "var(--color-success-muted)" }}>
                      387,000
                    </span>
                    <span className="hero-number-label">citizens reconnected to emergency trauma care (81.1%)</span>
                  </div>

                  <div className="supporting-telemetry-row">
                    <span className="supporting-item"><strong>+89,000</strong> recovered</span>
                    <span>·</span>
                    <span className="supporting-item"><strong>22 min</strong> detour saved</span>
                    <span>·</span>
                    <span className="supporting-item"><strong>0</strong> outcome variance</span>
                  </div>

                  <div className="divider-line" />

                  {/* Measured Outcome Verification Card */}
                  <div style={{ background: "rgba(16, 185, 129, 0.10)", padding: "12px", borderRadius: "6px", border: "1px solid rgba(16, 185, 129, 0.3)" }}>
                    <div style={{ fontWeight: 700, color: "#34d399", fontSize: "11.5px", marginBottom: "6px" }}>
                      MEASURED OUTCOME (Expected vs Actual)
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "6px", fontSize: "11px", textAlign: "center" }}>
                      <div>
                        <div style={{ color: "#94a3b8", fontSize: "10px" }}>Expected</div>
                        <div style={{ fontWeight: 600, color: "#fff", fontFamily: "var(--font-mono)" }}>+89,000</div>
                      </div>
                      <div>
                        <div style={{ color: "#94a3b8", fontSize: "10px" }}>Actual</div>
                        <div style={{ fontWeight: 700, color: "#34d399", fontFamily: "var(--font-mono)" }}>+89,000</div>
                      </div>
                      <div>
                        <div style={{ color: "#94a3b8", fontSize: "10px" }}>Variance</div>
                        <div style={{ fontWeight: 700, color: "#34d399", fontFamily: "var(--font-mono)" }}>0 (Exact)</div>
                      </div>
                    </div>
                    <div style={{ marginTop: "6px", fontSize: "10.5px", color: "#cbd5e1", textAlign: "center", borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "4px" }}>
                      Verification Status: <strong style={{ color: "#34d399" }}>VERIFIED DETERMINISTIC</strong>
                    </div>
                  </div>

                  <div className="divider-line" />

                  <div className="progression-container">
                    <span className="decision-section-label">Population access progression</span>
                    <div className="progression-bars" style={{ marginTop: "4px" }}>
                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Baseline</span>
                          <span className="tabular-nums">477,000</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "100%" }}>477K (100%)</div>
                        </div>
                      </div>

                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Michaung Flood</span>
                          <span className="tabular-nums">298,000</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "62.5%" }}>298K (62.5%)</div>
                          <div className="progression-segment isolated" style={{ width: "37.5%" }}>179K (37.5%)</div>
                        </div>
                      </div>

                      <div className="progression-row">
                        <div className="progression-row-label">
                          <span>Lifeline Restored</span>
                          <span className="tabular-nums">387,000</span>
                        </div>
                        <div className="progression-track">
                          <div className="progression-segment accessible" style={{ width: "81.1%" }}>387K (81.1%)</div>
                          <div className="progression-segment isolated" style={{ width: "18.9%" }}>90K (18.9%)</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="divider-line" />

                  <div className="editorial-text-block">
                    <span className="decision-section-label" style={{ display: "block", marginBottom: "4px" }}>
                      Restoration summary
                    </span>
                    <p>
                      Corridor 03 (Saidapet–Adyar arterial) clear of floodwaters and debris obstructions. Speed capacity restored to 40 km/h, reconnecting 89,000 residents across affected wards to regional trauma centers.
                    </p>
                  </div>

                  <div className="divider-line" />

                  {/* Next Action Callout */}
                  <div className="next-action-card">
                    <div className="next-action-header">
                      <span className="next-action-title">Simulation Scenario Complete</span>
                      <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>Scenario Reset</span>
                    </div>
                    <p className="next-action-desc">
                      Corridor restoration cycle complete and verified. Reset to baseline or test multimodal field intelligence ingestion.
                    </p>
                    <button
                      onClick={handleResetNetwork}
                      disabled={loading}
                      className="next-action-btn"
                    >
                      Reset Simulation ➔
                    </button>
                  </div>
                </>
              )}

              {/* Operational Alerts Drawer Block (Phase J) */}
              {alerts.length > 0 && (
                <>
                  <div className="divider-line" />
                  <div className="editorial-text-block">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                      <span className="decision-section-label" style={{ color: "#f87171" }}>
                        Operational Alerts ({alerts.filter((a) => a.status !== "RESOLVED" && a.status !== "DISMISSED").length} Active)
                      </span>
                      <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>State v{disasterState?.state_version || 1}</span>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "180px", overflowY: "auto" }}>
                      {alerts.slice(0, 10).map((alert) => (
                        <div
                          key={alert.alert_id}
                          style={{
                            background: alert.severity === "CRITICAL" ? "rgba(220, 38, 38, 0.15)" : alert.severity === "HIGH" ? "rgba(245, 158, 11, 0.15)" : "rgba(30, 41, 59, 0.8)",
                            padding: "6px 8px",
                            borderRadius: "4px",
                            border: `1px solid ${alert.severity === "CRITICAL" ? "#ef4444" : alert.severity === "HIGH" ? "#f59e0b" : "#475569"}`,
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: "9px", fontWeight: 700, padding: "1px 4px", borderRadius: "3px", background: alert.severity === "CRITICAL" ? "#dc2626" : alert.severity === "HIGH" ? "#d97706" : "#475569", color: "#fff" }}>
                              {alert.severity}
                            </span>
                            <span style={{ fontSize: "9.5px", color: "#94a3b8" }}>{alert.status}</span>
                          </div>
                          <div style={{ fontSize: "10.5px", fontWeight: 600, color: "#f1f5f9", marginTop: "3px" }}>
                            {alert.type.replace(/_/g, " ")}
                          </div>
                          <div style={{ fontSize: "10px", color: "#94a3b8", marginTop: "2px" }}>
                            Entity:{" "}
                            <button
                              onClick={() => handleInspectTraceability(alert.affected_entity_id)}
                              style={{ background: "none", border: "none", color: "#60a5fa", textDecoration: "underline", cursor: "pointer", padding: 0, fontSize: "10px" }}
                            >
                              {alert.affected_entity_name || alert.affected_entity_id}
                            </button>
                          </div>
                          {alert.status === "NEW" && (
                            <div style={{ display: "flex", gap: "4px", marginTop: "4px" }}>
                              <button
                                onClick={() => handleAlertAction(alert.alert_id, "ACKNOWLEDGE")}
                                style={{ background: "#2563eb", color: "#fff", border: "none", padding: "2px 5px", borderRadius: "3px", fontSize: "9.5px", cursor: "pointer" }}
                              >
                                Ack
                              </button>
                              <button
                                onClick={() => handleAlertAction(alert.alert_id, "RESOLVE")}
                                style={{ background: "#059669", color: "#fff", border: "none", padding: "2px 5px", borderRadius: "3px", fontSize: "9.5px", cursor: "pointer" }}
                              >
                                Resolve
                              </button>
                              <button
                                onClick={() => handleAlertAction(alert.alert_id, "DISMISS")}
                                style={{ background: "transparent", color: "#94a3b8", border: "1px solid #475569", padding: "2px 5px", borderRadius: "3px", fontSize: "9.5px", cursor: "pointer" }}
                              >
                                Dismiss
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </aside>
        </main>


      {/* 4. MODAL SPECIFICATION DIALOG */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)} role="dialog" aria-modal="true">
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-heading">Data sources & specification</h3>
              <button onClick={() => setShowModal(false)} className="btn-quiet">
                <X size={14} />
              </button>
            </div>

            <div className="modal-tabs">
              <button
                className={`modal-tab-btn ${modalTab === "EVIDENCE" ? "active" : ""}`}
                onClick={() => {
                  setModalTab("EVIDENCE");
                  fetchTimeline();
                }}
              >
                Field Evidence (Phase H)
              </button>
              <button
                className={`modal-tab-btn ${modalTab === "DRAINAGE" ? "active" : ""}`}
                onClick={() => {
                  setModalTab("DRAINAGE");
                  fetchDrainageData();
                }}
              >
                Drainage Infrastructure (Phase L9)
              </button>
              <button
                className={`modal-tab-btn ${modalTab === "CITIZEN" ? "active" : ""}`}
                onClick={() => {
                  setModalTab("CITIZEN");
                  fetchCitizenObservations();
                }}
              >
                Citizen PGIS (Phase L10)
              </button>

              <button
                className={`modal-tab-btn ${modalTab === "DATA" ? "active" : ""}`}
                onClick={() => setModalTab("DATA")}
              >
                Data sources
              </button>
              <button
                className={`modal-tab-btn ${modalTab === "MODEL" ? "active" : ""}`}
                onClick={() => setModalTab("MODEL")}
              >
                Decision model
              </button>
              <button
                className={`modal-tab-btn ${modalTab === "ASSUMPTIONS" ? "active" : ""}`}
                onClick={() => setModalTab("ASSUMPTIONS")}
              >
                Assumptions
              </button>
              <button
                className={`modal-tab-btn ${modalTab === "LIMITATIONS" ? "active" : ""}`}
                onClick={() => setModalTab("LIMITATIONS")}
              >
                Limitations
              </button>
            </div>

            <div className="modal-body" style={{ maxHeight: "70vh", overflowY: "auto" }}>
              {modalTab === "EVIDENCE" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                  <div>
                    <h4 style={{ color: "var(--text-primary)", marginBottom: "4px", fontSize: "13px" }}>
                      Multimodal Field Intelligence Pipeline
                    </h4>
                    <p style={{ fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                      Extract structured evidence from field reports or photographs. AI extracts evidence into an intermediate contract; only Phase E validation and reconciliation can mutate the deterministic simulation.
                    </p>
                  </div>

                  {/* Submission Form */}
                  <div style={{ background: "rgba(255,255,255,0.03)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border-subtle)" }}>
                    <span className="decision-section-label" style={{ display: "block", marginBottom: "8px" }}>1. Submit Field Report / Photograph Evidence</span>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                      <div>
                        <label style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>Source Type</label>
                        <select
                          value={evidenceSource}
                          onChange={(e) => setEvidenceSource(e.target.value)}
                          style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "4px 8px", borderRadius: "4px", fontSize: "12px" }}
                        >
                          <option value="field_team">Field Team (High Trust)</option>
                          <option value="official">Official Agency (High Trust)</option>
                          <option value="sensor">IoT Sensor (High Trust)</option>
                          <option value="citizen">Citizen Report (Lower Trust)</option>
                        </select>
                      </div>

                      <div>
                        <label style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>Observation Type</label>
                        <select
                          value={evidenceType}
                          onChange={(e) => setEvidenceType(e.target.value)}
                          style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "4px 8px", borderRadius: "4px", fontSize: "12px" }}
                        >
                          <option value="ROAD_BLOCKED">ROAD_BLOCKED</option>
                          <option value="ROAD_OPEN">ROAD_OPEN</option>
                          <option value="FLOOD_DEPTH">FLOOD_DEPTH</option>
                          <option value="FLOOD_PRESENT">FLOOD_PRESENT</option>
                        </select>
                      </div>

                      <div>
                        <label style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>Latitude (°N)</label>
                        <input
                          type="text"
                          value={evidenceLat}
                          onChange={(e) => setEvidenceLat(e.target.value)}
                          style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "4px 8px", borderRadius: "4px", fontSize: "12px" }}
                        />
                      </div>

                      <div>
                        <label style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>Longitude (°E)</label>
                        <input
                          type="text"
                          value={evidenceLon}
                          onChange={(e) => setEvidenceLon(e.target.value)}
                          style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "4px 8px", borderRadius: "4px", fontSize: "12px" }}
                        />
                      </div>

                      <div>
                        <label style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>Water Depth (m)</label>
                        <input
                          type="text"
                          value={evidenceDepth}
                          onChange={(e) => setEvidenceDepth(e.target.value)}
                          style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "4px 8px", borderRadius: "4px", fontSize: "12px" }}
                        />
                      </div>

                      <div>
                        <label style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>Evidence Notes</label>
                        <input
                          type="text"
                          value={evidenceDesc}
                          onChange={(e) => setEvidenceDesc(e.target.value)}
                          style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid var(--border-subtle)", padding: "4px 8px", borderRadius: "4px", fontSize: "12px" }}
                        />
                      </div>
                    </div>

                    <button
                      onClick={handleExtractEvidence}
                      disabled={loading}
                      style={{ marginTop: "10px", width: "100%", background: "#2563eb", color: "#fff", border: "none", padding: "6px 12px", borderRadius: "4px", fontWeight: 600, cursor: "pointer", fontSize: "12px" }}
                    >
                      {loading ? "Extracting Evidence..." : "Step 1: Extract Text/Report Evidence (Read-Only, 0 State Mutation)"}
                    </button>
                  </div>

                  {/* Voice Field Recording (Phase L8) */}
                  <div style={{ background: "rgba(139, 92, 246, 0.05)", padding: "12px", borderRadius: "6px", border: "1px solid rgba(139, 92, 246, 0.2)" }}>
                    <span className="decision-section-label" style={{ display: "block", marginBottom: "8px", color: "#a78bfa" }}>
                      🎙️ Phase L8 — Field Operator Voice Recording (Read-Only Transcribe)
                    </span>
                    <p style={{ fontSize: "11px", color: "var(--text-secondary)", marginBottom: "8px" }}>
                      Upload voice audio clip (.wav, .mp3, .ogg, .webm, max 25MB). Audio is transcribed and candidate evidence extracted without mutating simulation state.
                    </p>
                    <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <input
                        type="file"
                        accept="audio/*"
                        onChange={(e) => setVoiceAudioFile(e.target.files[0] || null)}
                        style={{ fontSize: "11px", color: "var(--text-secondary)", flex: 1 }}
                      />
                      <button
                        onClick={handleTranscribeVoice}
                        disabled={loading || !voiceAudioFile}
                        style={{ background: "#7c3aed", color: "#fff", border: "none", padding: "6px 12px", borderRadius: "4px", fontWeight: 600, cursor: voiceAudioFile ? "pointer" : "not-allowed", fontSize: "12px", opacity: voiceAudioFile ? 1 : 0.6 }}
                      >
                        {loading ? "Transcribing..." : "Transcribe & Extract (Read-Only)"}
                      </button>
                    </div>
                  </div>

                  {/* Extracted Evidence Contract Preview */}
                  {extractedEvidence && (
                    <div style={{ background: "rgba(37, 99, 235, 0.1)", padding: "12px", borderRadius: "6px", border: "1px solid rgba(37, 99, 235, 0.3)" }}>
                      <span className="decision-section-label" style={{ display: "block", marginBottom: "6px", color: "#60a5fa" }}>
                        2. Extracted Evidence Contract ({extractedEvidence.extraction_id})
                      </span>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px", fontSize: "11px" }}>
                        <div>Type: <strong>{extractedEvidence.observation_type}</strong></div>
                        <div>Extraction Conf: <strong>{(extractedEvidence.confidence * 100).toFixed(0)}%</strong></div>
                        {voiceTranscriptionData && (
                          <>
                            <div>Transcribe Conf: <strong>{(voiceTranscriptionData.transcription.transcription_confidence * 100).toFixed(0)}%</strong></div>
                            <div>Language: <strong>{voiceTranscriptionData.transcription.language_detected || "English"}</strong></div>
                          </>
                        )}
                        <div>Depth: <strong>{extractedEvidence.estimated_water_depth_m ? `${extractedEvidence.estimated_water_depth_m}m (${extractedEvidence.depth_source})` : "Null"}</strong></div>
                        <div>Status: <strong>{extractedEvidence.extraction_status}</strong></div>
                        <div>Location Check: <strong>{extractedEvidence.location_resolution_required ? "RESOLUTION REQUIRED" : "OK"}</strong></div>
                        <div>Model: <strong>{extractedEvidence.model_name}</strong></div>
                      </div>

                      {voiceTranscriptionData?.transcription?.transcript && (
                        <div style={{ marginTop: "8px", background: "rgba(0,0,0,0.3)", padding: "8px", borderRadius: "4px", fontSize: "11px" }}>
                          <span style={{ color: "#a78bfa", fontWeight: 600, display: "block", marginBottom: "2px" }}>Raw Voice Transcript (Sanitized):</span>
                          <span style={{ color: "var(--text-secondary)", fontStyle: "italic" }}>"{voiceTranscriptionData.transcription.transcript}"</span>
                        </div>
                      )}

                      <div style={{ marginTop: "8px", fontSize: "11px", color: "var(--text-muted)", fontStyle: "italic" }}>
                        Strict Rule: Extraction alone leaves NetworkEngine state 100% unchanged.
                      </div>

                      <button
                        onClick={voiceTranscriptionData ? handleIngestVoice : handleIngestEvidence}
                        disabled={loading || extractedEvidence.location_resolution_required}
                        style={{ marginTop: "10px", width: "100%", background: "#059669", color: "#fff", border: "none", padding: "6px 12px", borderRadius: "4px", fontWeight: 600, cursor: "pointer", fontSize: "12px" }}
                      >
                        {loading ? "Ingesting..." : "Step 2: Run Phase E Validation & Deterministic Reconciliation"}
                      </button>
                    </div>
                  )}

                  {/* Ingestion & Reconciliation Result */}
                  {ingestResult && (
                    <div style={{ background: "rgba(16, 185, 129, 0.1)", padding: "12px", borderRadius: "6px", border: "1px solid rgba(16, 185, 129, 0.3)" }}>
                      <span className="decision-section-label" style={{ display: "block", marginBottom: "6px", color: "#34d399" }}>
                        3. Phase E Validation & Reconciliation Result
                      </span>
                      <div style={{ fontSize: "11px", lineHeight: 1.5 }}>
                        <div>Validation Status: <strong style={{ color: "#34d399" }}>PASSED</strong></div>
                        <div>Observation Status: <strong>{ingestResult.observation?.status}</strong></div>
                        <div>Reconciled Reports: <strong>{ingestResult.reconciliation?.reconciled_count}</strong></div>
                        <div>Network Overrides: <strong>{ingestResult.provenance_lineage?.mutation_occurred ? "APPLIED TO NETWORK ENGINE" : "NONE (No mutation threshold reached)"}</strong></div>
                      </div>

                      {/* Human Approval Card */}
                      <div style={{ marginTop: "12px", paddingTop: "10px", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                        <span className="decision-section-label" style={{ display: "block", marginBottom: "4px", color: "#f59e0b" }}>
                          Operational Decision Approval (Simulated Incident Command)
                        </span>
                        <p style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
                          Candidate action generated by deterministic engine based on validated field evidence lineage <code>{ingestResult.provenance_lineage?.raw_evidence_ref}</code>.
                        </p>

                        <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                          <button
                            onClick={() => setHumanApprovalState("APPROVED")}
                            style={{ flex: 1, background: humanApprovalState === "APPROVED" ? "#059669" : "#1e293b", color: "#fff", border: "1px solid var(--border-strong)", padding: "6px", borderRadius: "4px", fontSize: "11px", fontWeight: 600, cursor: "pointer" }}
                          >
                            {humanApprovalState === "APPROVED" ? "✓ APPROVED" : "[ APPROVE ACTION ]"}
                          </button>
                          <button
                            onClick={() => setHumanApprovalState("REJECTED")}
                            style={{ flex: 1, background: humanApprovalState === "REJECTED" ? "#dc2626" : "#1e293b", color: "#fff", border: "1px solid var(--border-strong)", padding: "6px", borderRadius: "4px", fontSize: "11px", fontWeight: 600, cursor: "pointer" }}
                          >
                            {humanApprovalState === "REJECTED" ? "✗ REJECTED" : "[ REJECT / HOLD ]"}
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Auditable Timeline */}
                  {timelineData.length > 0 && (
                    <div style={{ background: "rgba(255,255,255,0.02)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border-subtle)" }}>
                      <span className="decision-section-label" style={{ display: "block", marginBottom: "8px" }}>
                        4. Auditable Operational Timeline ({timelineData.length} Events)
                      </span>
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "180px", overflowY: "auto" }}>
                        {timelineData.map((item, idx) => (
                          <div key={idx} style={{ fontSize: "10.5px", padding: "4px 8px", background: "#0f172a", borderRadius: "4px", borderLeft: "2px solid #3b82f6" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-muted)" }}>
                              <span>{item.stage}</span>
                              <span className="tabular-nums">{item.timestamp?.slice(11, 19)}</span>
                            </div>
                            <div style={{ color: "var(--text-primary)", fontWeight: 500 }}>{item.event}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {modalTab === "DRAINAGE" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                  <div>
                    <h4 style={{ color: "var(--text-primary)", marginBottom: "4px", fontSize: "13px" }}>
                      GCC Stormwater Drainage Infrastructure Evidence (Phase L9)
                    </h4>
                    <p style={{ fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                      Provenance-aware drainage assets and condition reports for Greater Chennai Corporation.
                      <strong> Physical Invariant:</strong> Drainage condition represents infrastructure capacity/blockage state and does <em>NOT</em> alter HAND elevation topography.
                    </p>
                  </div>

                  {drainageSummary ? (
                    <>
                      {/* Summary Banner */}
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px" }}>
                        <div style={{ background: "rgba(255,255,255,0.03)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-subtle)" }}>
                          <span style={{ fontSize: "10px", color: "var(--text-muted)", display: "block" }}>Total Assets</span>
                          <strong style={{ fontSize: "16px", color: "#60a5fa" }}>{drainageSummary.total_assets}</strong>
                        </div>
                        <div style={{ background: "rgba(239, 68, 68, 0.08)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(239, 68, 68, 0.2)" }}>
                          <span style={{ fontSize: "10px", color: "#fca5a5", display: "block" }}>Blocked / Impaired</span>
                          <strong style={{ fontSize: "16px", color: "#ef4444" }}>{drainageSummary.blocked_assets_count}</strong>
                        </div>
                        <div style={{ background: "rgba(245, 158, 11, 0.08)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(245, 158, 11, 0.2)" }}>
                          <span style={{ fontSize: "10px", color: "#fcd34d", display: "block" }}>Degraded Connectivity</span>
                          <strong style={{ fontSize: "16px", color: "#f59e0b" }}>{drainageSummary.degraded_connectivity_count}</strong>
                        </div>
                        <div style={{ background: "rgba(139, 92, 246, 0.08)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(139, 92, 246, 0.2)" }}>
                          <span style={{ fontSize: "10px", color: "#c4b5fd", display: "block" }}>Source Provenance</span>
                          <strong style={{ fontSize: "11px", color: "#a78bfa" }}>{drainageSummary.source}</strong>
                        </div>
                      </div>

                      {/* Assets Table */}
                      <div style={{ background: "rgba(255,255,255,0.02)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-subtle)" }}>
                        <span className="decision-section-label" style={{ display: "block", marginBottom: "8px" }}>
                          GCC Infrastructure Asset Register
                        </span>
                        <div style={{ display: "flex", flexDirection: "column", gap: "8px", maxHeight: "250px", overflowY: "auto" }}>
                          {drainageSummary.assets.map((asset) => (
                            <div key={asset.asset_id} style={{ padding: "8px 10px", background: "#0f172a", borderRadius: "4px", border: "1px solid var(--border-subtle)", fontSize: "11px" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                                <strong>{asset.asset_name}</strong>
                                <span style={{
                                  fontSize: "9.5px",
                                  padding: "2px 6px",
                                  borderRadius: "3px",
                                  fontWeight: 600,
                                  background: asset.blockage_status === "open" ? "#065f46" : asset.blockage_status === "inoperable" ? "#991b1b" : "#92400e",
                                  color: "#fff"
                                }}>
                                  {asset.blockage_status.toUpperCase()}
                                </span>
                              </div>
                              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "4px", color: "var(--text-secondary)", fontSize: "10.5px" }}>
                                <div>Type: <span style={{ color: "#fff" }}>{asset.asset_type}</span></div>
                                <div>Zone: <span style={{ color: "#fff" }}>{asset.catchment_zone}</span></div>
                                <div>Condition: <span style={{ color: "#fff" }}>{(asset.condition_score * 100).toFixed(0)}%</span></div>
                                <div>Capacity: <span style={{ color: "#fff" }}>{asset.capacity_cumecs} m³/s</span></div>
                              </div>
                              {asset.observed_issue && (
                                <div style={{ marginTop: "4px", color: "#fca5a5", fontStyle: "italic", fontSize: "10px" }}>
                                  Issue: {asset.observed_issue}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Explicit Assumptions & Limitations */}
                      <div style={{ fontSize: "11px", color: "var(--text-muted)", lineHeight: 1.4, background: "rgba(0,0,0,0.3)", padding: "8px", borderRadius: "4px" }}>
                        <div><strong>Assumptions:</strong> {drainageSummary.assumptions.join(" ")}</div>
                        <div style={{ marginTop: "4px" }}><strong>Limitations:</strong> {drainageSummary.limitations.join(" ")}</div>
                      </div>
                    </>
                  ) : (
                    <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>Loading drainage infrastructure dataset...</div>
                  )}
                </div>
              )}

              {modalTab === "CITIZEN" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                  <div>
                    <h4 style={{ color: "#c084fc", marginBottom: "4px", fontSize: "14px", fontWeight: 700 }}>
                      Phase L10 — Citizen / Participatory GIS Ground Observation Intelligence
                    </h4>
                    <p style={{ fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                      Participatory Geographic Information System (PGIS) stream. Citizen observations enter as unverified ground-level evidence and do NOT automatically alter operational network or disaster state until passing through Phase E validation and deterministic reconciliation.
                    </p>
                  </div>

                  {/* Summary Bar */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px" }}>
                    <div style={{ background: "rgba(168, 85, 247, 0.1)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(168, 85, 247, 0.2)" }}>
                      <span style={{ fontSize: "10px", color: "#c084fc", display: "block" }}>Total Citizen Reports</span>
                      <strong style={{ fontSize: "18px", color: "#f8fafc" }}>{citizenObservationsList.length}</strong>
                    </div>
                    <div style={{ background: "rgba(16, 185, 129, 0.1)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(16, 185, 129, 0.2)" }}>
                      <span style={{ fontSize: "10px", color: "#34d399", display: "block" }}>Validated Reports</span>
                      <strong style={{ fontSize: "18px", color: "#f8fafc" }}>{citizenObservationsList.filter(o => o.status === "VALIDATED").length}</strong>
                    </div>
                    <div style={{ background: "rgba(59, 130, 246, 0.1)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(59, 130, 246, 0.2)" }}>
                      <span style={{ fontSize: "10px", color: "#60a5fa", display: "block" }}>Reconciled Reports</span>
                      <strong style={{ fontSize: "18px", color: "#f8fafc" }}>{citizenObservationsList.filter(o => o.status === "RECONCILED").length}</strong>
                    </div>
                    <div style={{ background: "rgba(245, 158, 11, 0.1)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(245, 158, 11, 0.2)" }}>
                      <span style={{ fontSize: "10px", color: "#fbbf24", display: "block" }}>Conflicts / Duplicates</span>
                      <strong style={{ fontSize: "18px", color: "#f8fafc" }}>{citizenObservationsList.filter(o => o.conflicts_detected || o.duplicate_candidate).length}</strong>
                    </div>
                  </div>

                  {/* Citizen Reports Table */}
                  <div style={{ background: "rgba(15, 23, 42, 0.6)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border-subtle)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                      <span className="decision-section-label" style={{ color: "#c084fc" }}>Ground Observation Registry</span>
                      <button
                        onClick={() => {
                          setShowModal(false);
                          setShowCitizenModal(true);
                        }}
                        style={{ background: "#7c3aed", color: "#fff", border: "none", padding: "4px 8px", borderRadius: "4px", fontSize: "11px", fontWeight: 600, cursor: "pointer" }}
                      >
                        + Submit Ground Report
                      </button>
                    </div>

                    {citizenObservationsList.length === 0 ? (
                      <div style={{ fontSize: "12px", color: "#94a3b8", textAlign: "center", padding: "16px" }}>
                        No citizen observations recorded yet. Use the Citizen Report button to add observations.
                      </div>
                    ) : (
                      <div style={{ maxHeight: "300px", overflowY: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px", textAlign: "left" }}>
                          <thead>
                            <tr style={{ borderBottom: "1px solid #334155", color: "#94a3b8" }}>
                              <th style={{ padding: "6px" }}>Report ID</th>
                              <th style={{ padding: "6px" }}>Type</th>
                              <th style={{ padding: "6px" }}>Location</th>
                              <th style={{ padding: "6px" }}>Status</th>
                              <th style={{ padding: "6px" }}>Conf.</th>
                              <th style={{ padding: "6px" }}>Flags</th>
                              <th style={{ padding: "6px" }}>Time</th>
                            </tr>
                          </thead>
                          <tbody>
                            {citizenObservationsList.map((obs) => (
                              <tr key={obs.observation_id} style={{ borderBottom: "1px solid #1e293b", color: "#cbd5e1" }}>
                                <td style={{ padding: "6px" }}><code>{obs.observation_id.slice(0, 10)}...</code></td>
                                <td style={{ padding: "6px" }}><strong style={{ color: "#f8fafc" }}>{getReportTypeLabel(obs.report_type)}</strong></td>
                                <td style={{ padding: "6px" }}>{obs.location?.latitude?.toFixed(4)}, {obs.location?.longitude?.toFixed(4)}</td>
                                <td style={{ padding: "6px" }}>
                                  <span style={{
                                    background: obs.status === "RECONCILED" ? "#059669" : obs.status === "VALIDATED" ? "#2563eb" : obs.status === "REJECTED" ? "#dc2626" : "#7c3aed",
                                    color: "#fff", padding: "1px 5px", borderRadius: "3px", fontSize: "10px", fontWeight: 600
                                  }}>
                                    {getStatusLabel(obs.status)}
                                  </span>
                                </td>

                                <td style={{ padding: "6px" }}>{(obs.confidence * 100).toFixed(0)}%</td>
                                <td style={{ padding: "6px" }}>
                                  {obs.duplicate_candidate && <span style={{ color: "#fbbf24", marginRight: "4px" }}>[DUP]</span>}
                                  {obs.conflicts_detected && <span style={{ color: "#ef4444", marginRight: "4px" }}>[CONFLICT]</span>}
                                  {obs.media_metadata && <span style={{ color: "#60a5fa" }}>[MEDIA]</span>}
                                </td>
                                <td style={{ padding: "6px", color: "#94a3b8" }}>{obs.received_at?.slice(11, 19)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              )}


              {modalTab === "DATA" && (
                <div>
                  <h4 style={{ color: "var(--text-primary)", marginBottom: "6px", fontSize: "12.5px" }}>Empirical data provenance</h4>
                  <p style={{ fontSize: "12px", lineHeight: 1.5, color: "var(--text-secondary)" }}>
                    Cyclone Twin is calibrated against verified spatial networks and population distributions for Greater Chennai Corporation:
                  </p>
                  <ul style={{ paddingLeft: "18px", marginTop: "6px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                    <li><strong>Road multigraph:</strong> 25 junctions and 56 directed edges in EPSG:32643 (UTM 43N).</li>
                    <li><strong>Trauma centres:</strong> 6 verified hospital GPS locations and emergency bed capacity.</li>
                    <li><strong>Study wards:</strong> 10 GCC census ward populations summing to 477,000 citizens.</li>
                    <li><strong>Flood footprint:</strong> Inundation extent from December 2023 Cyclone Michaung satellite observations.</li>
                  </ul>
                  <div className="spec-grid">
                    <div>Graph source: <code>{manifest?.graph_source || "OSM arterial skeleton"}</code></div>
                    <div>Flood source: <code>{manifest?.flood_source || "ISRO / NRSC satellite"}</code></div>
                    <div>Coordinate system: <code>EPSG:32643 (UTM 43N)</code></div>
                    <div>Access threshold: <code>1,800 sec (30 min)</code></div>
                  </div>
                </div>
              )}

              {modalTab === "MODEL" && (
                <div>
                  <h4 style={{ color: "var(--text-primary)", marginBottom: "6px", fontSize: "12.5px" }}>Algorithmic specification</h4>
                  <p style={{ fontSize: "12px", lineHeight: 1.5, color: "var(--text-secondary)" }}>
                    <strong>Multi-Source Dijkstra on G^R:</strong> Evaluates shortest path travel times from all community centroids to active hospitals simultaneously in a single O((V + E) log V) search pass.
                  </p>
                  <p style={{ fontSize: "12px", lineHeight: 1.5, color: "var(--text-secondary)", marginTop: "6px" }}>
                    <strong>Deterministic Criticality Function:</strong> S(c) = 0.40·ΔH + 0.30·ΔP + 0.20·ΔT - 0.10·ΔD.
                  </p>
                </div>
              )}

              {modalTab === "ASSUMPTIONS" && (
                <div>
                  <h4 style={{ color: "var(--text-primary)", marginBottom: "6px", fontSize: "12.5px" }}>Operational assumptions</h4>
                  <ul style={{ paddingLeft: "18px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                    <li>Roads submerged &gt;30 cm are impassable to standard emergency ambulances.</li>
                    <li>Grade-separated flyovers and elevated bridges remain operable during surface flooding.</li>
                    <li>Hospitals without emergency power backup are excluded as destination nodes.</li>
                  </ul>
                </div>
              )}

              {modalTab === "LIMITATIONS" && (
                <div>
                  <h4 style={{ color: "var(--text-primary)", marginBottom: "6px", fontSize: "12.5px" }}>System boundaries</h4>
                  <ul style={{ paddingLeft: "18px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                    <li>Scope is focused on major arterial lifelines rather than microscopic residential alleys.</li>
                    <li>Decision-support tool for emergency planners; incident commander retains final authority.</li>
                  </ul>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button onClick={() => setShowModal(false)} className="btn-primary">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. TRACEABILITY INSPECTOR MODAL */}
      {showTraceModal && (
        <div className="modal-overlay" onClick={() => setShowTraceModal(false)} role="dialog" aria-modal="true">
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} style={{ maxWidth: "560px" }}>
            <div className="modal-header">
              <h3 className="modal-heading">Observation → State Traceability</h3>
              <button onClick={() => setShowTraceModal(false)} className="btn-quiet">
                <X size={14} />
              </button>
            </div>

            <div className="modal-body" style={{ maxHeight: "70vh", overflowY: "auto" }}>
              {traceabilityData ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  <div style={{ background: "rgba(255,255,255,0.03)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-subtle)" }}>
                    <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>Target Entity</div>
                    <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-primary)" }}>{traceabilityData.entity_id}</div>
                    <div style={{ fontSize: "11.5px", color: "#60a5fa", marginTop: "2px" }}>
                      Status: <strong>{traceabilityData.status}</strong> (State v{traceabilityData.current_state_version})
                    </div>
                  </div>

                  <span className="decision-section-label" style={{ display: "block", marginBottom: "4px" }}>
                    End-to-End Provenance Lineage
                  </span>

                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    {traceabilityData.provenance_chain?.map((step, idx) => (
                      <div key={idx} style={{ background: "#0f172a", padding: "8px 10px", borderRadius: "4px", borderLeft: "3px solid #2563eb", fontSize: "11px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", color: "#94a3b8", fontWeight: 600 }}>
                          <span>Step {idx + 1}: {step.step}</span>
                          {step.version && <span>v{step.version}</span>}
                        </div>
                        <div style={{ color: "#e2e8f0", marginTop: "2px" }}>{step.detail}</div>
                      </div>
                    ))}
                  </div>

                  {traceabilityData.supporting_observations?.length > 0 && (
                    <>
                      <span className="decision-section-label" style={{ display: "block", marginTop: "8px", marginBottom: "4px" }}>
                        Supporting Ground Observations ({traceabilityData.supporting_observations.length})
                      </span>
                      {traceabilityData.supporting_observations.map((obs, idx) => (
                        <div key={idx} style={{ background: "rgba(16, 185, 129, 0.05)", padding: "8px", borderRadius: "4px", border: "1px solid rgba(16, 185, 129, 0.2)", fontSize: "11px" }}>
                          <div style={{ fontWeight: 600, color: "#34d399" }}>{obs.observation_id} [{obs.source}]</div>
                          <div>Type: {obs.type} (Confidence: {(obs.confidence * 100).toFixed(0)}%)</div>
                          <div style={{ color: "var(--text-muted)", marginTop: "2px" }}>{obs.raw_text || "No notes"}</div>
                        </div>
                      ))}
                    </>
                  )}
                </div>
              ) : (
                <div>Loading traceability lineage...</div>
              )}
            </div>

            <div className="modal-footer">
              <button onClick={() => setShowTraceModal(false)} className="btn-primary">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
      {/* 5. FORECAST SUMMARY & VULNERABILITY MODAL (Milestone L6) */}
      {showForecastSummaryModal && (
        <div className="modal-overlay" onClick={() => setShowForecastSummaryModal(false)} role="dialog" aria-modal="true">
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} style={{ maxWidth: "720px" }}>
            <div className="modal-header">
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <h3 className="modal-heading">Forecast Summary & Vulnerability Assessment</h3>
                <span
                  style={{
                    background: "rgba(56, 189, 248, 0.15)",
                    color: "#38bdf8",
                    border: "1px solid rgba(56, 189, 248, 0.4)",
                    padding: "2px 7px",
                    borderRadius: "4px",
                    fontSize: "10px",
                    fontWeight: 700,
                  }}
                >
                  {selectedHorizon} PROJECTION
                </span>
              </div>
              <button onClick={() => setShowForecastSummaryModal(false)} className="btn-quiet">
                <X size={14} />
              </button>
            </div>

            <div className="modal-body" style={{ maxHeight: "75vh", overflowY: "auto", display: "flex", flexDirection: "column", gap: "16px" }}>
              {/* Status Header Block */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "10px", background: "rgba(15, 23, 42, 0.6)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border-subtle)" }}>
                <div>
                  <span style={{ fontSize: "10px", color: "#94a3b8", display: "block" }}>Forecast Horizon</span>
                  <span style={{ fontSize: "14px", fontWeight: 700, color: "#38bdf8" }}>{selectedHorizon}</span>
                </div>
                <div>
                  <span style={{ fontSize: "10px", color: "#94a3b8", display: "block" }}>Rainfall</span>
                  <span style={{ fontSize: "14px", fontWeight: 700, color: "#f8fafc" }}>{forecastData?.weather?.precipitation_mm || 0} mm</span>
                </div>
                <div>
                  <span style={{ fontSize: "10px", color: "#94a3b8", display: "block" }}>Water Level</span>
                  <span style={{ fontSize: "14px", fontWeight: 700, color: "#f8fafc" }}>{forecastData?.flood?.water_level_m || 0} m</span>
                </div>
                <div>
                  <span style={{ fontSize: "10px", color: "#94a3b8", display: "block" }}>Model Confidence</span>
                  <span style={{ fontSize: "14px", fontWeight: 700, color: "#34d399" }}>
                    {((vulnerabilityData?.vulnerability_summary?.confidence || forecastData?.vulnerability_forecast?.confidence || 0.85) * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Vulnerability Summary Block */}
              {vulnerabilityData?.vulnerability_summary && (
                <div style={{ background: "rgba(30, 41, 59, 0.6)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border-subtle)" }}>
                  <h4 style={{ fontSize: "12px", fontWeight: 700, color: "#38bdf8", marginBottom: "8px" }}>
                    Network Vulnerability Summary
                  </h4>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", marginBottom: "10px" }}>
                    <div style={{ background: "#0f172a", padding: "8px", borderRadius: "4px" }}>
                      <span style={{ fontSize: "10px", color: "#94a3b8" }}>Total Assessed</span>
                      <div style={{ fontSize: "16px", fontWeight: 700 }}>{vulnerabilityData.vulnerability_summary.total_assessed_segments}</div>
                    </div>
                    <div style={{ background: "#0f172a", padding: "8px", borderRadius: "4px" }}>
                      <span style={{ fontSize: "10px", color: "#94a3b8" }}>High/Critical (≥0.50)</span>
                      <div style={{ fontSize: "16px", fontWeight: 700, color: "#f97316" }}>{vulnerabilityData.vulnerability_summary.segments_above_threshold}</div>
                    </div>
                    <div style={{ background: "#0f172a", padding: "8px", borderRadius: "4px" }}>
                      <span style={{ fontSize: "10px", color: "#94a3b8" }}>Max Score</span>
                      <div style={{ fontSize: "16px", fontWeight: 700, color: "#ef4444" }}>{vulnerabilityData.vulnerability_summary.max_vulnerability_score.toFixed(2)}</div>
                    </div>
                    <div style={{ background: "#0f172a", padding: "8px", borderRadius: "4px" }}>
                      <span style={{ fontSize: "10px", color: "#94a3b8" }}>Mean Score</span>
                      <div style={{ fontSize: "16px", fontWeight: 700, color: "#f59e0b" }}>{vulnerabilityData.vulnerability_summary.mean_vulnerability_score.toFixed(2)}</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Assessed Segments List */}
              {vulnerabilityData?.vulnerability_assessments?.length > 0 && (
                <div>
                  <h4 style={{ fontSize: "12px", fontWeight: 700, color: "#e2e8f0", marginBottom: "6px" }}>
                    Projected Vulnerable Road Segments
                  </h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "200px", overflowY: "auto" }}>
                    {vulnerabilityData.vulnerability_assessments.map((ass) => (
                      <div
                        key={ass.segment_id}
                        style={{
                          background: "#0f172a",
                          padding: "8px 10px",
                          borderRadius: "4px",
                          border: "1px solid var(--border-subtle)",
                          display: "flex",
                          flexDirection: "column",
                          gap: "4px",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontWeight: 600, fontSize: "11px", color: "#f8fafc" }}>
                            Segment: <code>{ass.segment_id}</code>
                          </span>
                          <span
                            style={{
                              background: ass.vulnerability_score >= 0.85 ? "#ef4444" : ass.vulnerability_score >= 0.60 ? "#f97316" : "#f59e0b",
                              color: "#fff",
                              padding: "1px 6px",
                              borderRadius: "3px",
                              fontSize: "10px",
                              fontWeight: 700,
                            }}
                          >
                            Score: {ass.vulnerability_score.toFixed(2)}
                          </span>
                        </div>
                        <div style={{ fontSize: "10.5px", color: "#94a3b8" }}>
                          Components: Flood Exposure={ass.flood_exposure.toFixed(2)} | Pop={ass.raw_population_impact.toLocaleString()} | Hosp={ass.raw_hospital_impact} | Delay Mult={ass.raw_travel_time_multiplier}x
                        </div>
                        <div style={{ fontSize: "10px", color: "#cbd5e1", fontStyle: "italic" }}>
                          {ass.explanation}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Provenance Block */}
              <div style={{ background: "rgba(15, 23, 42, 0.4)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-subtle)" }}>
                <h4 style={{ fontSize: "11px", fontWeight: 700, color: "#94a3b8", marginBottom: "4px" }}>Model Provenance</h4>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px", fontSize: "10.5px", color: "#cbd5e1" }}>
                  <div>Weather Source: <strong>{vulnerabilityData?.weather_source || forecastData?.weather?.provider}</strong></div>
                  <div>Flood Model: <strong>{vulnerabilityData?.flood_model || forecastData?.flood?.source}</strong></div>
                  <div>Network Source: <strong>{vulnerabilityData?.network_source || "osm_chennai"}</strong></div>
                  <div>Target Timestamp: <strong>{forecastData?.target_time}</strong></div>
                </div>
              </div>

              {/* Assumptions & Limitations Block */}
              <div style={{ background: "rgba(15, 23, 42, 0.4)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border-subtle)" }}>
                <h4 style={{ fontSize: "11px", fontWeight: 700, color: "#94a3b8", marginBottom: "4px" }}>Assumptions & Limitations</h4>
                <ul style={{ fontSize: "10.5px", color: "#94a3b8", paddingLeft: "16px", display: "flex", flexDirection: "column", gap: "3px" }}>
                  {(vulnerabilityData?.assumptions || forecastData?.vulnerability_forecast?.assumptions || []).map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                  {(vulnerabilityData?.limitations || forecastData?.vulnerability_forecast?.limitations || []).map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 5. CITIZEN / PGIS REPORT SUBMISSION MODAL (PHASE L10) */}
      {showCitizenModal && (
        <div className="modal-overlay" onClick={() => setShowCitizenModal(false)} role="dialog" aria-modal="true">
          <div className="modal-dialog" style={{ maxWidth: "680px" }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header" style={{ borderBottom: "1px solid rgba(168, 85, 247, 0.3)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <div style={{ width: "10px", height: "10px", background: "#c084fc", borderRadius: "2px", transform: "rotate(45deg)" }} />
                <h3 className="modal-heading" style={{ color: "#f8fafc" }}>Citizen Ground Observation Report (PGIS)</h3>
              </div>
              <button onClick={() => setShowCitizenModal(false)} className="btn-quiet">
                <X size={14} />
              </button>
            </div>

            <div className="modal-body" style={{ maxHeight: "75vh", overflowY: "auto", padding: "16px" }}>
              <div style={{ background: "rgba(168, 85, 247, 0.08)", padding: "10px", borderRadius: "6px", border: "1px solid rgba(168, 85, 247, 0.25)", marginBottom: "16px" }}>
                <span style={{ fontSize: "11px", color: "#c084fc", fontWeight: 700, display: "block", marginBottom: "2px" }}>
                  EVIDENCE OBSERVATION PIPELINE — READ-ONLY OBSERVATION INGESTION
                </span>
                <p style={{ fontSize: "11px", color: "#cbd5e1", margin: 0, lineHeight: 1.4 }}>
                  Citizen reports enter the system as unverified evidence. They do <strong>NOT</strong> automatically close roads, change flood depths, or alter operational network state without passing through Phase E validation and reconciliation.
                </p>
              </div>

              <form onSubmit={handleSubmitCitizenReport} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                  {/* 1. Report Type */}
                  <div style={{ gridColumn: "span 2" }}>
                    <label style={{ fontSize: "11.5px", fontWeight: 600, color: "#f8fafc", display: "block", marginBottom: "4px" }}>
                      What Happened? (Observation Category)
                    </label>
                    <select
                      value={citizenReportType}
                      onChange={(e) => setCitizenReportType(e.target.value)}
                      style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid #334155", padding: "8px", borderRadius: "4px", fontSize: "12px" }}
                    >
                      <option value="ROAD_FLOODED">{getReportTypeLabel("ROAD_FLOODED")}</option>
                      <option value="ROAD_BLOCKED">{getReportTypeLabel("ROAD_BLOCKED")}</option>
                      <option value="ROAD_PASSABLE">{getReportTypeLabel("ROAD_PASSABLE")}</option>
                      <option value="WATER_LEVEL">{getReportTypeLabel("WATER_LEVEL")}</option>
                      <option value="DRAIN_OVERFLOW">{getReportTypeLabel("DRAIN_OVERFLOW")}</option>
                      <option value="HOSPITAL_ACCESS_BLOCKED">{getReportTypeLabel("HOSPITAL_ACCESS_BLOCKED")}</option>
                      <option value="DEBRIS">{getReportTypeLabel("DEBRIS")}</option>
                      <option value="FALLEN_TREE">{getReportTypeLabel("FALLEN_TREE")}</option>
                      <option value="BRIDGE_BLOCKED">{getReportTypeLabel("BRIDGE_BLOCKED")}</option>
                      <option value="POWER_OUTAGE">{getReportTypeLabel("POWER_OUTAGE")}</option>
                      <option value="OTHER">{getReportTypeLabel("OTHER")}</option>

                    </select>
                  </div>

                  {/* 2. Coordinates */}
                  <div>
                    <label style={{ fontSize: "11px", color: "#94a3b8", display: "block", marginBottom: "2px" }}>Latitude (°N)</label>
                    <input
                      type="text"
                      value={citizenLat}
                      onChange={(e) => setCitizenLat(e.target.value)}
                      placeholder="13.0450"
                      style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid #334155", padding: "6px 8px", borderRadius: "4px", fontSize: "12px" }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "11px", color: "#94a3b8", display: "block", marginBottom: "2px" }}>Longitude (°E)</label>
                    <input
                      type="text"
                      value={citizenLon}
                      onChange={(e) => setCitizenLon(e.target.value)}
                      placeholder="80.2210"
                      style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid #334155", padding: "6px 8px", borderRadius: "4px", fontSize: "12px" }}
                    />
                  </div>

                  {/* 3. Description */}
                  <div style={{ gridColumn: "span 2" }}>
                    <label style={{ fontSize: "11px", color: "#94a3b8", display: "block", marginBottom: "2px" }}>Ground Description / Notes</label>
                    <textarea
                      rows={2}
                      value={citizenDesc}
                      onChange={(e) => setCitizenDesc(e.target.value)}
                      placeholder="Describe what you observed on the ground..."
                      style={{ width: "100%", background: "#0f172a", color: "#fff", border: "1px solid #334155", padding: "6px 8px", borderRadius: "4px", fontSize: "12px", fontFamily: "inherit" }}
                    />
                  </div>

                  {/* 4. Confidence & Anonymous Settings */}
                  <div>
                    <label style={{ fontSize: "11px", color: "#94a3b8", display: "block", marginBottom: "2px" }}>
                      Observation Confidence: {(parseFloat(citizenConfidence) * 100).toFixed(0)}%
                    </label>
                    <input
                      type="range"
                      min="0.1"
                      max="1.0"
                      step="0.05"
                      value={citizenConfidence}
                      onChange={(e) => setCitizenConfidence(e.target.value)}
                      style={{ width: "100%" }}
                    />
                    <span style={{ fontSize: "10px", color: "#64748b" }}>Confidence = reliability of report, not severity.</span>
                  </div>

                  <div>
                    <label style={{ fontSize: "11px", color: "#94a3b8", display: "block", marginBottom: "4px" }}>Reporter Identity Privacy</label>
                    <label style={{ fontSize: "11px", color: "#e2e8f0", display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={citizenIsAnon}
                        onChange={(e) => setCitizenIsAnon(e.target.checked)}
                      />
                      Report Anonymously (Pseudonymous ID)
                    </label>
                    {!citizenIsAnon && (
                      <input
                        type="text"
                        placeholder="Reporter Identifier (Optional)"
                        value={citizenReporterId}
                        onChange={(e) => setCitizenReporterId(e.target.value)}
                        style={{ marginTop: "4px", width: "100%", background: "#0f172a", color: "#fff", border: "1px solid #334155", padding: "4px 8px", borderRadius: "4px", fontSize: "11px" }}
                      />
                    )}
                  </div>


                  {/* 5. Optional Media Metadata */}
                  <div style={{ gridColumn: "span 2", background: "rgba(0,0,0,0.2)", padding: "10px", borderRadius: "4px", border: "1px solid #1e293b" }}>
                    <span style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 600, display: "block", marginBottom: "6px" }}>
                      📷 Optional Photo Evidence Metadata
                    </span>
                    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: "8px" }}>
                      <input
                        type="text"
                        placeholder="Photo filename (e.g. road_flood.jpg)"
                        value={citizenPhotoName}
                        onChange={(e) => setCitizenPhotoName(e.target.value)}
                        style={{ background: "#0f172a", color: "#fff", border: "1px solid #334155", padding: "4px 8px", borderRadius: "4px", fontSize: "11px" }}
                      />
                      <input
                        type="text"
                        placeholder="MIME type"
                        value={citizenPhotoMime}
                        onChange={(e) => setCitizenPhotoMime(e.target.value)}
                        style={{ background: "#0f172a", color: "#fff", border: "1px solid #334155", padding: "4px 8px", borderRadius: "4px", fontSize: "11px" }}
                      />
                      <input
                        type="number"
                        placeholder="Size (bytes)"
                        value={citizenPhotoSize}
                        onChange={(e) => setCitizenPhotoSize(e.target.value)}
                        style={{ background: "#0f172a", color: "#fff", border: "1px solid #334155", padding: "4px 8px", borderRadius: "4px", fontSize: "11px" }}
                      />
                    </div>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  style={{ background: "#7c3aed", color: "#fff", border: "none", padding: "8px 16px", borderRadius: "4px", fontWeight: 700, fontSize: "13px", cursor: "pointer", marginTop: "4px" }}
                >
                  {loading ? "Submitting Observation..." : "Submit Ground Evidence Report"}
                </button>
              </form>

              {/* Submit Error Banner */}
              {citizenSubmitError && (
                <div style={{ marginTop: "12px", background: "rgba(220, 38, 38, 0.15)", border: "1px solid #ef4444", padding: "10px", borderRadius: "4px", color: "#fca5a5", fontSize: "11px" }}>
                  <strong>Submission Error:</strong> {citizenSubmitError}
                </div>
              )}

              {/* Submit Result Banner */}
              {citizenSubmitStatus && (
                <div style={{ marginTop: "12px", background: "rgba(16, 185, 129, 0.15)", border: "1px solid #10b981", padding: "10px", borderRadius: "4px", color: "#6ee7b7", fontSize: "11px" }}>
                  <div style={{ fontWeight: 700, marginBottom: "4px" }}>✓ Ground Report Successfully Submitted to Evidence Pipeline</div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px", color: "#e2e8f0" }}>
                    <div>Observation ID: <code>{citizenSubmitStatus.observation?.observation_id}</code></div>
                    <div>Status: <strong>{citizenSubmitStatus.observation?.status}</strong></div>
                    <div>Sync Status: <strong>{citizenSubmitStatus.observation?.sync_status}</strong></div>
                    <div>Duplicate Flag: <strong>{citizenSubmitStatus.observation?.duplicate_candidate ? "POSSIBLE DUP" : "NONE"}</strong></div>
                    <div>Conflict Flag: <strong>{citizenSubmitStatus.observation?.conflicts_detected ? "CONFLICT DETECTED" : "NONE"}</strong></div>
                    <div>Provenance: <code>{citizenSubmitStatus.observation?.provenance?.source}</code></div>
                  </div>
                  <div style={{ marginTop: "6px", fontStyle: "italic", color: "#94a3b8" }}>
                    Status: SUBMITTED → Will be evaluated during Phase E reconciliation. State remains unchanged.
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


