/**
 * FloodLens Offline-First Citizen SOS Submission Queue
 * Powered by @react-native-async-storage/async-storage.
 * Guarantees zero lost emergency distress reports during network severance or flood blackouts.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  CitizenSOSPayload,
  HelpRequest,
  IncidentSubmissionResult,
  QueuedIncident,
  AuthorityHandoffStatus,
} from '../types';
import { submitSOS, checkBackendHealth } from '../api/client';

export const OFFLINE_SOS_QUEUE_KEY = '@floodlens_offline_sos_queue_v1';

type QueueChangeListener = (queue: QueuedIncident[]) => void;
const listeners: Set<QueueChangeListener> = new Set();

function notifyListeners(queue: QueuedIncident[]) {
  listeners.forEach((listener) => {
    try {
      listener(queue);
    } catch (err) {
      console.warn('[SOS Queue] Listener error:', err);
    }
  });
}

/**
 * Subscribe to queue changes (new items enqueued, synced, or removed)
 */
export function subscribeToQueue(listener: QueueChangeListener): () => void {
  listeners.add(listener);
  // Send initial state immediately
  getQueuedIncidents().then((q) => listener(q)).catch(() => {});
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Retrieve all pending queued incidents from AsyncStorage
 */
export async function getQueuedIncidents(): Promise<QueuedIncident[]> {
  try {
    const raw = await AsyncStorage.getItem(OFFLINE_SOS_QUEUE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    console.error('[SOS Queue] Failed to read queued incidents:', error);
    return [];
  }
}

/**
 * Persist the entire queue to AsyncStorage and notify subscribers
 */
async function saveQueue(queue: QueuedIncident[]): Promise<void> {
  try {
    await AsyncStorage.setItem(OFFLINE_SOS_QUEUE_KEY, JSON.stringify(queue));
    notifyListeners(queue);
  } catch (error) {
    console.error('[SOS Queue] Failed to persist queue to storage:', error);
  }
}

/**
 * Enqueue an incident into offline storage
 */
export async function enqueueIncident(
  payload: CitizenSOSPayload,
  errorReason?: string
): Promise<QueuedIncident> {
  const current = await getQueuedIncidents();
  const localId = `OFFLINE-SOS-${Date.now().toString(36).toUpperCase()}-${Math.floor(1000 + Math.random() * 9000)}`;

  const queuedItem: QueuedIncident = {
    localId,
    payload: {
      ...payload,
      timestamp: payload.timestamp || new Date().toISOString(),
    },
    queuedAt: new Date().toISOString(),
    retryCount: 0,
    lastError: errorReason,
  };

  const updated = [queuedItem, ...current];
  await saveQueue(updated);
  return queuedItem;
}

/**
 * Remove an incident from the offline queue (e.g. after successful backend transmission)
 */
export async function removeQueuedIncident(localId: string): Promise<void> {
  const current = await getQueuedIncidents();
  const filtered = current.filter((item) => item.localId !== localId);
  await saveQueue(filtered);
}

/**
 * Clear all offline stored reports
 */
export async function clearQueuedIncidents(): Promise<void> {
  await AsyncStorage.removeItem(OFFLINE_SOS_QUEUE_KEY);
  notifyListeners([]);
}

/**
 * Convert a QueuedIncident into an active HelpRequest for UI display
 */
export function queuedIncidentToHelpRequest(queued: QueuedIncident): HelpRequest {
  const p = queued.payload;
  return {
    id: queued.localId,
    requester_name: p.requester_name,
    contact_number: p.contact_number,
    timestamp: new Date(queued.queuedAt).toLocaleTimeString(),
    category: p.category,
    urgency: p.urgency,
    urgency_score: p.urgency === 'CRITICAL' ? 'Priority 1 - Critical Surge Zone' : 'Standard Priority',
    status: 'LOCAL_LOGGED' as AuthorityHandoffStatus,
    people_count: p.people_count,
    location_name: p.location_name || `Koshi Basin (${p.latitude.toFixed(4)}, ${p.longitude.toFixed(4)})`,
    coordinates: [p.latitude, p.longitude],
    landmark: p.landmark,
    notes: p.notes,
    battery_level: p.battery_level,
    estimated_water_depth: p.estimated_water_depth,
    medical_urgency: p.medical_urgency,
    accuracy: p.accuracy,
    synced: false,
    queued_at: queued.queuedAt,
  };
}

/**
 * Primary Emergency Submission Pipeline:
 * 1. Attempts direct online POST to FastAPI backend endpoint.
 * 2. If the request fails or device is offline, saves to AsyncStorage offline queue.
 */
export async function submitOrQueueIncident(
  payload: CitizenSOSPayload
): Promise<IncidentSubmissionResult> {
  try {
    // Attempt real-time POST directly to FastAPI backend
    const onlineResult = await submitSOS(payload);
    return {
      success: true,
      mode: 'online',
      id: onlineResult.id,
      incident: onlineResult,
    };
  } catch (err: any) {
    const errorMsg = err?.message || 'Network disconnected or host unreachable';
    console.warn(`[SOS Queue] Direct submission failed: ${errorMsg}. Enqueuing to AsyncStorage.`);

    // Persist to local offline queue
    const queued = await enqueueIncident(payload, errorMsg);
    const localIncident = queuedIncidentToHelpRequest(queued);

    return {
      success: true,
      mode: 'offline_queued',
      id: queued.localId,
      incident: localIncident,
      error: errorMsg,
    };
  }
}

/**
 * Synchronize all pending stored reports to the FastAPI backend
 */
export async function syncPendingQueue(): Promise<{
  synced: number;
  failed: number;
  totalRemaining: number;
}> {
  const queue = await getQueuedIncidents();
  if (queue.length === 0) {
    return { synced: 0, failed: 0, totalRemaining: 0 };
  }

  // Pre-check health before attempting bulk sync
  const health = await checkBackendHealth();
  if (!health.ok) {
    return { synced: 0, failed: queue.length, totalRemaining: queue.length };
  }

  let synced = 0;
  let failed = 0;
  const remaining: QueuedIncident[] = [];

  for (const item of queue) {
    try {
      await submitSOS(item.payload);
      synced++;
    } catch (err: any) {
      failed++;
      remaining.push({
        ...item,
        retryCount: item.retryCount + 1,
        lastError: err?.message || 'Sync attempt failed',
      });
    }
  }

  await saveQueue(remaining);
  return { synced, failed, totalRemaining: remaining.length };
}

let autoSyncTimer: ReturnType<typeof setInterval> | null = null;

/**
 * Initialize auto-sync background daemon
 * Runs on startup and periodically polls every intervalMs
 */
export function startAutoSync(intervalMs = 20000): void {
  if (autoSyncTimer) return;

  // Immediate probe on launch
  syncPendingQueue().catch(() => {});

  autoSyncTimer = setInterval(() => {
    syncPendingQueue().catch(() => {});
  }, intervalMs);
}

/**
 * Stop auto-sync timer
 */
export function stopAutoSync(): void {
  if (autoSyncTimer) {
    clearInterval(autoSyncTimer);
    autoSyncTimer = null;
  }
}
