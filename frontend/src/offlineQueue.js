/**
 * Browser-Native IndexedDB Persistent Offline Queue for Cyclone Twin Field Operations.
 * Stores structured field observations and image data safely without network access.
 * Retains observations across browser reloads, tab closes, and network outages.
 */

const DB_NAME = "cyclone_twin_offline_db";
const DB_VERSION = 1;
const STORE_NAME = "field_observations";

function openDB() {
  return new Promise((resolve, reject) => {
    if (!window.indexedDB) {
      reject(new Error("IndexedDB is not supported in this browser environment."));
      return;
    }

    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: "client_observation_id" });
        store.createIndex("sync_status", "sync_status", { unique: false });
        store.createIndex("created_at", "created_at", { unique: false });
      }
    };

    request.onsuccess = (event) => {
      resolve(event.target.result);
    };

    request.onerror = (event) => {
      reject(event.target.error);
    };
  });
}

export const offlineQueue = {
  /**
   * Saves a new or updated field observation to persistent local IndexedDB store.
   */
  async saveObservation(observationItem) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);

      const record = {
        client_observation_id: observationItem.client_observation_id || `client_obs_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`,
        created_at: observationItem.created_at || new Date().toISOString(),
        captured_at: observationItem.captured_at || new Date().toISOString(),
        source: observationItem.source || "field_team",
        observation_type: observationItem.observation_type || "ROAD_BLOCKED",
        latitude: observationItem.latitude ?? null,
        longitude: observationItem.longitude ?? null,
        water_depth_m: observationItem.water_depth_m ?? null,
        severity: observationItem.severity || "high",
        confidence: observationItem.confidence ?? 0.85,
        description: observationItem.description || "",
        image_data: observationItem.image_data || null, // Base64 or Blob
        evidence_reference: observationItem.evidence_reference || `FIELD_${Date.now()}`,
        sync_status: observationItem.sync_status || "QUEUED", // "QUEUED" | "SYNCING" | "SYNCED" | "FAILED" | "CONFLICT"
        retry_count: observationItem.retry_count || 0,
        last_sync_attempt: observationItem.last_sync_attempt || null,
        server_observation_id: observationItem.server_observation_id || null,
        server_result: observationItem.server_result || null,
        conflict_reason: observationItem.conflict_reason || null,
        error_message: observationItem.error_message || null,
      };

      const req = store.put(record);
      req.onsuccess = () => resolve(record);
      req.onerror = () => reject(req.error);
    });
  },

  /**
   * Retrieves all offline observations stored in local IndexedDB.
   */
  async getAllObservations() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const store = tx.objectStore(STORE_NAME);
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  },

  /**
   * Retrieves observations matching specific sync statuses (e.g. QUEUED, FAILED).
   */
  async getObservationsByStatus(statuses = ["QUEUED", "FAILED"]) {
    const all = await this.getAllObservations();
    return all.filter((item) => statuses.includes(item.sync_status));
  },

  /**
   * Updates fields for a specific observation record.
   */
  async updateObservation(clientObservationId, updates) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      const getReq = store.get(clientObservationId);

      getReq.onsuccess = () => {
        const existing = getReq.result;
        if (!existing) {
          reject(new Error(`Observation ${clientObservationId} not found in offline store.`));
          return;
        }
        const updated = { ...existing, ...updates };
        const putReq = store.put(updated);
        putReq.onsuccess = () => resolve(updated);
        putReq.onerror = () => reject(putReq.error);
      };
      getReq.onerror = () => reject(getReq.error);
    });
  },

  /**
   * Removes an observation from local IndexedDB.
   */
  async removeObservation(clientObservationId) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      const req = store.delete(clientObservationId);
      req.onsuccess = () => resolve(true);
      req.onerror = () => reject(req.error);
    });
  },

  /**
   * Clears synced observations from local store.
   */
  async clearSynced() {
    const all = await this.getAllObservations();
    const synced = all.filter((item) => item.sync_status === "SYNCED");
    for (const item of synced) {
      await this.removeObservation(item.client_observation_id);
    }
    return synced.length;
  },
};
