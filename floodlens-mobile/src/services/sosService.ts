/**
 * FloodLens Citizen SOS Dispatch Service
 * Synchronized with FastAPI Backend (https://floodlens-backend-4pt5.onrender.com)
 * Handles transparent citizen JWT authentication, schema normalization, and resilient transmission.
 */

import { CONFIG } from '../config/api';

export type EmergencyNeed =
  | 'Boat Evacuation'
  | 'Medical Attention'
  | 'Food / Water'
  | 'Elderly / Child Support';

export type UrgencyLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export interface CitizenSOSInput {
  citizen_name: string;
  phone: string;
  latitude: number;
  longitude: number;
  needs: EmergencyNeed[];
  landmark_notes?: string;
  urgency_level: UrgencyLevel;
  people_count?: number;
}

export interface BackendAssistanceResponse {
  id: string;
  citizen_id: string;
  latitude: number;
  longitude: number;
  category: string;
  status: string;
  details: string | null;
  people_count: number;
  created_at: string;
  updated_at: string;
}

export interface SOSSubmissionResult {
  ok: boolean;
  incidentId?: string;
  data?: BackendAssistanceResponse;
  error?: string;
}

export interface BackendHealthResult {
  ok: boolean;
  status: string;
  databaseConnected?: boolean;
  latencyMs: number;
  error?: string;
}

// In-memory bearer token cache for session persistence
let cachedAuthToken: string | null = null;

/**
 * Transparent citizen authentication helper
 * Ensures a valid citizen token exists before submitting to secured FastAPI routes.
 */
export async function ensureCitizenSession(): Promise<string> {
  if (cachedAuthToken) return cachedAuthToken;

  const email = 'citizen.mobile@floodlens.org';
  const password = 'citizenpassword123';
  const timeoutMs = CONFIG.TIMEOUT_MS;

  const loginUrl = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.AUTH_LOGIN}`;

  // 1. Attempt login
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const loginRes = await fetch(loginUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ email, password }),
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (loginRes.ok) {
      const data = await loginRes.json();
      if (data.access_token) {
        cachedAuthToken = data.access_token;
        return data.access_token;
      }
    }
  } catch {
    // If login attempt errors, fall through to registration check
  }

  // 2. If login failed (e.g. fresh database), register the citizen user
  try {
    const registerUrl = `${CONFIG.API_BASE_URL}/api/v1/auth/register`;
    const regController = new AbortController();
    const regTimer = setTimeout(() => regController.abort(), timeoutMs);

    const regRes = await fetch(registerUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({
        email,
        password,
        full_name: 'Mobile Citizen User',
        phone: '+977-9800000000',
        contact_consent: true,
      }),
      signal: regController.signal,
    });
    clearTimeout(regTimer);

    // 3. Retry login following registration
    const retryController = new AbortController();
    const retryTimer = setTimeout(() => retryController.abort(), timeoutMs);

    const retryRes = await fetch(loginUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ email, password }),
      signal: retryController.signal,
    });
    clearTimeout(retryTimer);

    if (retryRes.ok) {
      const data = await retryRes.json();
      if (data.access_token) {
        cachedAuthToken = data.access_token;
        return data.access_token;
      }
    }
  } catch {
    // Registration fallback failed
  }

  throw new Error('Unable to establish authenticated citizen session with cloud backend.');
}

/**
 * Maps high-level needs to the backend AssistanceCategory enum:
 * 'evacuation' | 'medical' | 'food_water' | 'shelter' | 'other'
 */
function mapNeedsToCategory(needs: EmergencyNeed[]): 'evacuation' | 'medical' | 'food_water' | 'shelter' | 'other' {
  if (needs.includes('Medical Attention')) return 'medical';
  if (needs.includes('Boat Evacuation')) return 'evacuation';
  if (needs.includes('Food / Water')) return 'food_water';
  if (needs.includes('Elderly / Child Support')) return 'shelter';
  return 'evacuation';
}

/**
 * Transmit Citizen SOS Distress Beacon to FastAPI POST /api/v1/assistance
 */
export async function transmitCitizenSOS(input: CitizenSOSInput): Promise<SOSSubmissionResult> {
  const token = await ensureCitizenSession();
  const category = mapNeedsToCategory(input.needs);

  // Pack rich civilian metadata into the backend `details` attribute
  const detailsParts = [
    `[CITIZEN SOS DISTRESS BEACON]`,
    `Requester: ${input.citizen_name.trim() || 'Anonymous Citizen'}`,
    `Phone: ${input.phone.trim() || '+977 (Unspecified)'}`,
    `Urgency: ${input.urgency_level}`,
    `Needs: ${input.needs.length > 0 ? input.needs.join(', ') : 'Immediate Assistance'}`,
    input.landmark_notes ? `Landmark: ${input.landmark_notes.trim()}` : null,
    `People: ${input.people_count || 1}`,
  ].filter(Boolean);

  const payload = {
    latitude: Number(input.latitude.toFixed(6)),
    longitude: Number(input.longitude.toFixed(6)),
    category,
    details: detailsParts.join(' | '),
    people_count: Math.max(1, Math.min(100, input.people_count || 1)),
  };

  const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.ASSISTANCE_SOS}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': `Bearer ${token}`,
        'ngrok-skip-browser-warning': 'true',
        'Bypass-Tunnel-Reminder': 'true',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    clearTimeout(timer);

    const body = await response.json().catch(() => ({}));

    if (!response.ok) {
      const errorMsg =
        body.detail ||
        body.error?.message ||
        (body.error?.details?.validation_errors ? JSON.stringify(body.error.details.validation_errors) : null) ||
        `Server responded with HTTP ${response.status}`;
      return {
        ok: false,
        error: errorMsg,
      };
    }

    return {
      ok: true,
      incidentId: body.id,
      data: body,
    };
  } catch (err: any) {
    clearTimeout(timer);
    if (err.name === 'AbortError') {
      return {
        ok: false,
        error: `Transmission timed out after ${CONFIG.TIMEOUT_MS / 1000}s. The cloud backend may be waking up from cold standby. Please retry.`,
      };
    }
    return {
      ok: false,
      error: err.message || 'Network request failed. Please check your internet connection.',
    };
  }
}

/**
 * Health check probe against live backend (/api/v1/health or /health)
 */
export async function checkBackendHealth(): Promise<BackendHealthResult> {
  const start = Date.now();
  const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.API_V1_HEALTH}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    clearTimeout(timer);
    const latencyMs = Date.now() - start;

    if (!response.ok) {
      return {
        ok: false,
        status: `HTTP ${response.status}`,
        latencyMs,
        error: `Status ${response.status}`,
      };
    }

    const data = await response.json();
    return {
      ok: true,
      status: data.status || 'healthy',
      databaseConnected: data.database?.connected,
      latencyMs,
    };
  } catch (err: any) {
    clearTimeout(timer);
    return {
      ok: false,
      status: 'unreachable',
      latencyMs: Date.now() - start,
      error: err.name === 'AbortError' ? 'Ping timed out (Cold start)' : err.message || 'Offline',
    };
  }
}

export interface ActiveAlert {
  id: string;
  area_id: string;
  title: string;
  message: string;
  status: string;
  created_by: string;
  approved_by?: string;
  issued_at?: string;
  mode: string;
  target_channels: string[];
  created_at: string;
}

/**
 * Query active emergency alerts from GET /api/v1/alerts
 */
export async function fetchActiveAlerts(): Promise<ActiveAlert[]> {
  const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.ALERTS}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        'ngrok-skip-browser-warning': 'true',
        'Bypass-Tunnel-Reminder': 'true',
      },
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (response.ok) {
      const data = await response.json();
      return Array.isArray(data) ? data : [];
    }
    return [];
  } catch (err) {
    clearTimeout(timer);
    console.warn('[Alerts] Failed to fetch active alerts:', err);
    return [];
  }
}

/**
 * Cancel or withdraw an active distress beacon
 */
export async function cancelCitizenSOS(incidentId: string): Promise<boolean> {
  const token = await ensureCitizenSession();
  const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.ASSISTANCE_SOS}/${encodeURIComponent(incidentId)}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        status: 'cancelled',
        status_notes: 'Distress beacon cancelled by citizen (safe).',
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    return response.ok;
  } catch {
    clearTimeout(timer);
    return false;
  }
}
