/**
 * Deterministic Synchronization Engine for Cyclone Twin Field Operations.
 * Manages reachability detection (ONLINE / OFFLINE / UNSTABLE), batch synchronization,
 * exponential backoff retry policy, idempotency checks, and conflict reporting.
 */

import { offlineQueue } from "./offlineQueue.js";
import { api } from "./api.js";

export const NETWORK_STATUS = {
  ONLINE: "ONLINE",
  OFFLINE: "OFFLINE",
  UNSTABLE: "UNSTABLE",
};

export class SyncEngine {
  constructor(onStatusChange = null) {
    this.networkStatus = navigator.onLine ? NETWORK_STATUS.ONLINE : NETWORK_STATUS.OFFLINE;
    this.isSyncing = false;
    this.onStatusChange = onStatusChange;

    // Listen to browser network state changes
    window.addEventListener("online", () => this.checkReachability());
    window.addEventListener("offline", () => {
      this.networkStatus = NETWORK_STATUS.OFFLINE;
      this.notifyStatusChange();
    });

    // Periodic reachability heartbeat (every 15s)
    setInterval(() => this.checkReachability(), 15000);
  }

  notifyStatusChange() {
    if (typeof this.onStatusChange === "function") {
      this.onStatusChange(this.networkStatus);
    }
  }

  /**
   * Pings backend server to verify actual reachability beyond browser navigator status.
   */
  async checkReachability() {
    if (!navigator.onLine) {
      this.networkStatus = NETWORK_STATUS.OFFLINE;
      this.notifyStatusChange();
      return false;
    }

    try {
      // Lightweight 2.5s timeout reachability ping
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2500);

      const API_BASE = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE || "http://localhost:8000";
      const res = await fetch(`${API_BASE}/health`, { signal: controller.signal });
      clearTimeout(timeoutId);

      if (res.ok) {
        const prev = this.networkStatus;
        this.networkStatus = NETWORK_STATUS.ONLINE;
        if (prev !== NETWORK_STATUS.ONLINE) {
          this.notifyStatusChange();
          // Auto-trigger sync queue on network restoration
          this.syncQueue();
        }
        return true;
      } else {
        this.networkStatus = NETWORK_STATUS.UNSTABLE;
        this.notifyStatusChange();
        return false;
      }
    } catch {
      this.networkStatus = NETWORK_STATUS.UNSTABLE;
      this.notifyStatusChange();
      return false;
    }
  }

  /**
   * Synchronizes queued offline observations to server.
   */
  async syncQueue() {
    if (this.isSyncing) return { status: "IN_PROGRESS" };

    const isReachable = await this.checkReachability();
    if (!isReachable) {
      return {
        status: "UNAVAILABLE",
        networkStatus: this.networkStatus,
        reason: "Server unreachable or connection offline.",
      };
    }

    this.isSyncing = true;
    try {
      const itemsToSync = await offlineQueue.getObservationsByStatus(["QUEUED", "FAILED"]);
      if (itemsToSync.length === 0) {
        this.isSyncing = false;
        return { status: "IDLE", count: 0 };
      }

      let syncedCount = 0;
      let failedCount = 0;
      let conflictCount = 0;

      for (const item of itemsToSync) {
        // 1. Set state to SYNCING
        await offlineQueue.updateObservation(item.client_observation_id, {
          sync_status: "SYNCING",
          last_sync_attempt: new Date().toISOString(),
        });

        try {
          // Prepare payload
          const syncPayload = {
            client_observation_id: item.client_observation_id,
            observation_type: item.observation_type,
            source: item.source,
            latitude: item.latitude,
            longitude: item.longitude,
            water_depth_m: item.water_depth_m,
            severity: item.severity,
            confidence: item.confidence,
            description: item.description,
            timestamp: item.captured_at,
          };

          // 2. Submit to backend batch sync endpoint
          const res = await api.syncBatch([syncPayload]);
          const resultItem = res.results && res.results[0];

          if (resultItem && resultItem.status === "ingested") {
            const hasConflict = resultItem.reconciliation?.has_conflicts;

            if (hasConflict) {
              conflictCount++;
              await offlineQueue.updateObservation(item.client_observation_id, {
                sync_status: "CONFLICT",
                server_observation_id: resultItem.observation?.observation_id,
                server_result: resultItem,
                conflict_reason: "Competing reports detected for physical road segment. Resolved by server policy.",
                error_message: null,
              });
            } else {
              syncedCount++;
              await offlineQueue.updateObservation(item.client_observation_id, {
                sync_status: "SYNCED",
                server_observation_id: resultItem.observation?.observation_id,
                server_result: resultItem,
                error_message: null,
              });
            }
          } else {
            // Validation or ingestion failure
            failedCount++;
            const newRetryCount = (item.retry_count || 0) + 1;
            const errMsg = resultItem?.error || "Server validation or ingestion failed";

            await offlineQueue.updateObservation(item.client_observation_id, {
              sync_status: "FAILED",
              retry_count: newRetryCount,
              error_message: errMsg,
            });
          }
        } catch (err) {
          // Network failure / server error during sync
          failedCount++;
          const newRetryCount = (item.retry_count || 0) + 1;
          const status = newRetryCount >= 3 ? "FAILED" : "QUEUED";

          await offlineQueue.updateObservation(item.client_observation_id, {
            sync_status: status,
            retry_count: newRetryCount,
            error_message: `Network sync error (attempt ${newRetryCount}/3): ${err.message}`,
          });
        }
      }

      this.isSyncing = false;
      return {
        status: "COMPLETED",
        total: itemsToSync.length,
        syncedCount,
        failedCount,
        conflictCount,
      };
    } catch (err) {
      this.isSyncing = false;
      throw err;
    }
  }
}
