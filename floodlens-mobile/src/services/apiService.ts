/**
 * FloodLens Mobile Core API Service
 * Handles transparent citizen authentication, SOS transmission,
 * telemetry gauge polling, alert streaming, and shelter discovery.
 */

import { CONFIG } from '../config/api';

export type EmergencyCategory = 'evacuation' | 'medical' | 'food_water' | 'shelter' | 'other';
export type UrgencyLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export interface CitizenSOSPayload {
  citizen_name?: string;
  phone?: string;
  latitude: number;
  longitude: number;
  category: EmergencyCategory;
  people_count: number;
  needs: string[];
  landmark_notes?: string;
  urgency_level: UrgencyLevel;
}

export interface SOSResult {
  ok: boolean;
  incidentId?: string;
  data?: any;
  error?: string;
}

export interface GaugeStation {
  station_id: string;
  name: string;
  river: string;
  coordinates: [number, number]; // [lng, lat]
  current_level: number;
  warning_level: number;
  danger_level: number;
  discharge_rate: number;
  trend: 'RISING' | 'FALLING' | 'STEADY';
  status: 'CRITICAL' | 'WARNING' | 'NORMAL';
  last_reported_at: string;
}

export interface ActiveAlert {
  id: string;
  area_id: string;
  title: string;
  message: string;
  status: string;
  created_at: string;
  severity?: 'EMERGENCY' | 'WARNING' | 'ADVISORY';
  target_channels?: string[];
}

export interface ShelterFacility {
  id: string;
  name: string;
  type: string;
  capacity: number;
  current_occupancy: number;
  status: string;
  latitude: number;
  longitude: number;
  amenities: string[];
  contact_phone: string;
  distanceKm?: number;
}

export interface HealthCheckResult {
  ok: boolean;
  latencyMs: number;
  status: string;
  databaseConnected: boolean;
  error?: string;
}

// In-memory token store
let cachedAuthToken: string | null = null;

/**
 * Safely decodes base64 string across React Native and Node runtimes
 */
function decodeBase64(str: string): string {
  try {
    if (typeof atob === 'function') return atob(str);
  } catch {}
  const base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';
  let output = '';
  let buffer = 0;
  let bits = 0;
  for (let i = 0; i < base64.length; i++) {
    const char = base64.charAt(i);
    if (char === '=') break;
    const index = chars.indexOf(char);
    if (index === -1) continue;
    buffer = (buffer << 6) | index;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      output += String.fromCharCode((buffer >> bits) & 0xff);
    }
  }
  return output;
}

/**
 * Checks if a JWT token is expired or about to expire in the next 15 seconds
 */
export function isTokenExpired(jwtToken: string | null): boolean {
  if (!jwtToken) return true;
  try {
    const parts = jwtToken.split('.');
    if (parts.length !== 3) return true;
    const payloadStr = decodeBase64(parts[1]);
    const payload = JSON.parse(payloadStr);
    if (typeof payload.exp === 'number') {
      const nowSec = Math.floor(Date.now() / 1000);
      return payload.exp <= nowSec + 15; // 15s buffer
    }
  } catch {
    return false;
  }
  return false;
}

/**
 * Transparent citizen JWT authentication with forceRefresh support.
 * Invalidate cached token when expired or upon HTTP 401.
 */
export async function getCitizenToken(forceRefresh = false): Promise<string> {
  if (forceRefresh || isTokenExpired(cachedAuthToken)) {
    cachedAuthToken = null;
  } else if (cachedAuthToken) {
    return cachedAuthToken;
  }

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
        Accept: 'application/json',
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
    // Fall through to register
  }

  // 2. If login fails (fresh db), register the mobile citizen account
  try {
    const registerUrl = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.AUTH_REGISTER}`;
    const regController = new AbortController();
    const regTimer = setTimeout(() => regController.abort(), timeoutMs);

    await fetch(registerUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
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

    // 3. Retry login
    const retryController = new AbortController();
    const retryTimer = setTimeout(() => retryController.abort(), timeoutMs);

    const retryRes = await fetch(loginUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
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

/** Backward compatibility alias */
export const ensureCitizenSession = getCitizenToken;

/**
 * Transmit SOS distress beacon to POST /api/v1/assistance
 * Automatically refreshes token and retries once if HTTP 401 or token expired is returned.
 */
export async function transmitSOS(payload: CitizenSOSPayload): Promise<SOSResult> {
  // Proactively purge any stale or expired token before transmission
  if (isTokenExpired(cachedAuthToken)) {
    cachedAuthToken = null;
  }
  let token = await getCitizenToken(false);

  const detailsParts = [
    `[CITIZEN SOS DISTRESS BEACON]`,
    `Requester: ${payload.citizen_name?.trim() || 'Anonymous Civilian'}`,
    `Phone: ${payload.phone?.trim() || '+977 (Not provided)'}`,
    `Urgency: ${payload.urgency_level}`,
    `Category: ${payload.category}`,
    `Needs: ${payload.needs.length > 0 ? payload.needs.join(', ') : 'Immediate Rescue'}`,
    payload.landmark_notes ? `Landmark: ${payload.landmark_notes.trim()}` : null,
    `Souls in Group: ${payload.people_count || 1}`,
  ].filter(Boolean);

  // Strictly parse coordinates as numeric floats
  const parsedLat = parseFloat(Number(payload.latitude).toFixed(6));
  const parsedLng = parseFloat(Number(payload.longitude).toFixed(6));

  const requestBody = {
    latitude: parsedLat,
    longitude: parsedLng,
    category: payload.category,
    details: detailsParts.join(' | '),
    people_count: Math.max(1, Math.min(100, payload.people_count || 1)),
  };

  const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.ASSISTANCE_SOS}`;

  const executePost = async (authToken: string) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          Authorization: `Bearer ${authToken}`,
          'ngrok-skip-browser-warning': 'true',
          'Bypass-Tunnel-Reminder': 'true',
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });
      clearTimeout(timer);
      const body = await response.json().catch(() => ({}));
      return { response, body };
    } catch (err) {
      clearTimeout(timer);
      throw err;
    }
  };

  try {
    let { response, body } = await executePost(token);

    // If 401 Unauthorized or expired token message, immediately force refresh and retry once
    const isTokenExpired =
      response.status === 401 ||
      (typeof body.detail === 'string' &&
        (body.detail.toLowerCase().includes('expired') ||
          body.detail.toLowerCase().includes('credentials') ||
          body.detail.toLowerCase().includes('unauthorized')));

    if (isTokenExpired) {
      console.warn('[SOS Dispatch] Access token expired or invalid (HTTP 401). Requesting fresh citizen JWT and retrying...');
      token = await getCitizenToken(true);
      const retryResult = await executePost(token);
      response = retryResult.response;
      body = retryResult.body;
    }

    if (!response.ok) {
      const errorMsg =
        body.detail ||
        body.error?.message ||
        (body.error?.details?.validation_errors ? JSON.stringify(body.error.details.validation_errors) : null) ||
        `Server responded with HTTP ${response.status}`;
      return { ok: false, error: errorMsg };
    }

    return {
      ok: true,
      incidentId: body.id,
      data: body,
    };
  } catch (err: any) {
    return {
      ok: false,
      error: err.name === 'AbortError' ? 'Beacon transmission timed out. Cloud backend may be waking up.' : err.message || 'Network request failed',
    };
  }
}

/**
 * Cancel or withdraw active beacon with automatic token refresh on 401
 */
export async function cancelSOS(incidentId: string): Promise<boolean> {
  const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.ASSISTANCE_SOS}/${encodeURIComponent(incidentId)}`;

  const executePatch = async (authToken: string) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);
    try {
      const response = await fetch(url, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          status: 'cancelled',
          status_notes: 'Distress beacon cancelled by citizen (marked safe).',
        }),
        signal: controller.signal,
      });
      clearTimeout(timer);
      return response;
    } catch (err) {
      clearTimeout(timer);
      throw err;
    }
  };

  try {
    let token = await getCitizenToken(false);
    let response = await executePatch(token);

    if (response.status === 401) {
      token = await getCitizenToken(true);
      response = await executePatch(token);
    }

    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Fallback gauge telemetry for offline / disconnected states
 */
const FALLBACK_GAUGES: GaugeStation[] = [
  {
    station_id: 'gauge-chatara',
    name: 'Chatara Hydro-Station',
    river: 'Saptakoshi Main Stem',
    coordinates: [87.163, 26.871],
    current_level: 8.18,
    warning_level: 7.0,
    danger_level: 8.0,
    discharge_rate: 14250,
    trend: 'RISING',
    status: 'CRITICAL',
    last_reported_at: '2m ago',
  },
  {
    station_id: 'gauge-barrage',
    name: 'Koshi Barrage Control',
    river: 'Koshi Main Channel',
    coordinates: [86.918, 26.522],
    current_level: 74.85,
    warning_level: 74.0,
    danger_level: 75.0,
    discharge_rate: 12980,
    trend: 'RISING',
    status: 'WARNING',
    last_reported_at: '4m ago',
  },
  {
    station_id: 'gauge-mulghat',
    name: 'Mulghat Station',
    river: 'Tamor River Basin',
    coordinates: [87.332, 26.935],
    current_level: 5.62,
    warning_level: 6.0,
    danger_level: 7.0,
    discharge_rate: 4120,
    trend: 'STEADY',
    status: 'NORMAL',
    last_reported_at: '6m ago',
  },
];

/**
 * Query river telemetry gauges from GET /api/v1/monitoring/gauges
 */
export async function fetchGauges(): Promise<GaugeStation[]> {
  const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.MONITORING_GAUGES}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        'ngrok-skip-browser-warning': 'true',
      },
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (response.ok) {
      const data = await response.json();
      if (Array.isArray(data.stations) && data.stations.length > 0) {
        return data.stations.map((s: any) => ({
          station_id: s.station_id || s.id,
          name: s.name,
          river: s.river || 'Koshi Basin Stem',
          coordinates: s.coordinates || [87.16, 26.87],
          current_level: Number(s.current_level || 0),
          warning_level: Number(s.warning_level || 0),
          danger_level: Number(s.danger_level || 0),
          discharge_rate: Number(s.discharge_rate || 0),
          trend: (s.trend || 'RISING') as any,
          status: (s.status || (s.current_level >= s.danger_level ? 'CRITICAL' : s.current_level >= s.warning_level ? 'WARNING' : 'NORMAL')) as any,
          last_reported_at: s.last_reported_at || 'Just now',
        }));
      }
    }
  } catch (err) {
    clearTimeout(timer);
  }
  return FALLBACK_GAUGES;
}

/**
 * Query active emergency alerts from GET /api/v1/alerts
 */
export async function fetchAlerts(): Promise<ActiveAlert[]> {
  const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.ALERTS}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        'ngrok-skip-browser-warning': 'true',
      },
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (response.ok) {
      const data = await response.json();
      if (Array.isArray(data)) {
        return data.map((a: any) => ({
          id: a.id,
          area_id: a.area_id || 'koshi-basin',
          title: a.title,
          message: a.message,
          status: a.status,
          created_at: a.created_at || new Date().toISOString(),
          severity: a.title?.toUpperCase().includes('DANGER') || a.message?.toUpperCase().includes('CREST') ? 'EMERGENCY' : 'WARNING',
          target_channels: a.target_channels || ['CAP-SMS', 'VHF-RADIO', 'SIREN'],
        }));
      }
    }
  } catch {
    clearTimeout(timer);
  }
  return [];
}

/**
 * Fallback verified shelters across Koshi flood basin
 */
const FALLBACK_SHELTERS: ShelterFacility[] = [
  {
    id: 'shelter-prakashpur',
    name: 'Prakashpur Multi-Purpose Safe Haven',
    type: 'Elevated Cyclone & Flood Refuge',
    capacity: 450,
    current_occupancy: 140,
    status: 'ACTIVE · ACCEPTING EVACUEES',
    latitude: 26.6854,
    longitude: 87.1423,
    amenities: ['Solar Power', 'First Aid Post', 'Water Purification', 'Satellite Phone'],
    contact_phone: '+977-9852011222',
  },
  {
    id: 'shelter-inaruwa',
    name: 'Inaruwa Municipal Sports Safe Center',
    type: 'District Evacuation Complex',
    capacity: 800,
    current_occupancy: 310,
    status: 'ACTIVE · HIGH CAPACITY',
    latitude: 26.6021,
    longitude: 87.1512,
    amenities: ['Emergency Kitchen', 'Medical Isolation Ward', 'WASH Facilities'],
    contact_phone: '+977-9852044888',
  },
  {
    id: 'shelter-chatara',
    name: 'Chatara Community High Ground Haven',
    type: 'Elevated Embankment Facility',
    capacity: 350,
    current_occupancy: 95,
    status: 'ACTIVE · BOAT ACCESS READY',
    latitude: 26.8521,
    longitude: 87.1534,
    amenities: ['Boat Landing Dock', 'Fuel Reserves', 'Community Hall'],
    contact_phone: '+977-9852077999',
  },
];

/**
 * Haversine distance formula between two GPS coordinates in kilometers
 */
export function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371; // Radius of Earth in km
  const dLat = (lat2 - lat1) * (Math.PI / 180);
  const dLon = (lon2 - lon1) * (Math.PI / 180);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * (Math.PI / 180)) * Math.cos(lat2 * (Math.PI / 180)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return Math.round(R * c * 10) / 10;
}

export const calculateDistanceKm = calculateDistance;

export interface SafeRouteResult {
  ok: boolean;
  distanceKm: number;
  durationMins: number;
  waypoints: [number, number][]; // [longitude, latitude]
  summary?: string;
  isFallback?: boolean;
  error?: string;
}

/**
 * Fetch walking evacuation route to nearest shelter using OSRM public walking API
 * Query: https://router.project-osrm.org/route/v1/walking/${startLng},${startLat};${destLng},${destLat}?overview=full&geometries=geojson
 */
export async function fetchSafeRoute(
  startLat: number,
  startLng: number,
  destLat: number,
  destLng: number
): Promise<SafeRouteResult> {
  const directDistKm = calculateDistance(startLat, startLng, destLat, destLng);
  // Average flood terrain walking speed: ~4.5 km/h => ~13.3 mins per km
  const fallbackMins = Math.max(1, Math.round(directDistKm * 13.3));

  const url = `https://router.project-osrm.org/route/v1/walking/${startLng},${startLat};${destLng},${destLat}?overview=full&geometries=geojson`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (response.ok) {
      const data = await response.json();
      if (data.code === 'Ok' && Array.isArray(data.routes) && data.routes.length > 0) {
        const route = data.routes[0];
        const distKm = Math.round((route.distance / 1000) * 10) / 10;
        const durMins = Math.max(1, Math.round(route.duration / 60));
        const coords = (route.geometry?.coordinates || []) as [number, number][];

        return {
          ok: true,
          distanceKm: distKm,
          durationMins: durMins,
          waypoints: coords,
          summary: route.legs?.[0]?.summary || 'Elevated bypass corridor',
          isFallback: false,
        };
      }
    }
  } catch (err) {
    clearTimeout(timer);
  }

  // Graceful fallback to geodesic trajectory if OSRM is unreachable
  return {
    ok: true,
    distanceKm: directDistKm,
    durationMins: fallbackMins,
    waypoints: [
      [startLng, startLat],
      [destLng, destLat],
    ],
    summary: 'Direct high-ground trajectory',
    isFallback: true,
  };
}

/**
 * Query safe shelters from GET /api/v1/facilities/shelters
 */
export async function fetchShelters(userLat?: number, userLng?: number): Promise<ShelterFacility[]> {
  const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.FACILITIES_SHELTERS}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

  let shelters = FALLBACK_SHELTERS;

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        'ngrok-skip-browser-warning': 'true',
      },
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (response.ok) {
      const data = await response.json();
      if (Array.isArray(data.shelters) && data.shelters.length > 0) {
        shelters = data.shelters.map((s: any) => ({
          id: s.id,
          name: s.name,
          type: s.type || s.kind || 'Designated Refuge Facility',
          capacity: s.capacity || 300,
          current_occupancy: s.current_occupancy || Math.floor((s.capacity || 300) * 0.35),
          status: s.status || 'ACTIVE · ACCEPTING EVACUEES',
          latitude: s.location?.latitude || s.latitude || 26.6854,
          longitude: s.location?.longitude || s.longitude || 87.1423,
          amenities: s.amenities || ['Clean Water', 'First Aid', 'Emergency Shelter'],
          contact_phone: s.contact_phone || '+977-9852000000',
        }));
      }
    }
  } catch {
    clearTimeout(timer);
  }

  // Calculate distance if coordinates provided
  if (userLat && userLng) {
    shelters = shelters.map((sh) => ({
      ...sh,
      distanceKm: calculateDistanceKm(userLat, userLng, sh.latitude, sh.longitude),
    })).sort((a, b) => (a.distanceKm || 999) - (b.distanceKm || 999));
  }

  return shelters;
}

/**
 * Health check probe with live latency calculation
 */
export async function checkBackendHealth(): Promise<HealthCheckResult> {
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
        latencyMs,
        status: `HTTP ${response.status}`,
        databaseConnected: false,
        error: `Server status: ${response.status}`,
      };
    }

    const data = await response.json();
    return {
      ok: true,
      latencyMs,
      status: data.status || 'healthy',
      databaseConnected: data.database?.connected ?? true,
    };
  } catch (err: any) {
    clearTimeout(timer);
    return {
      ok: false,
      latencyMs: Date.now() - start,
      status: 'offline',
      databaseConnected: false,
      error: err.name === 'AbortError' ? 'Ping timed out (Cold standby)' : err.message || 'Offline',
    };
  }
}
