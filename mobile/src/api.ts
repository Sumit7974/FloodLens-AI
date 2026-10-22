import * as SecureStore from 'expo-secure-store';

const configured = (process.env.EXPO_PUBLIC_API_URL || 'http://10.0.2.2:8000').trim().replace(/\/+$/, '');
export const API_BASE = configured.endsWith('/api/v1') ? configured : `${configured}/api/v1`;
const TOKEN_KEY = 'floodlens_demo_citizen_token';
let token: string | null = null;

export type CitizenProfile = {
  id: string; email: string; full_name: string | null;
  role: 'citizen' | 'authority' | 'admin';
  contact_consent: boolean;
};
export type LocationRecord = {
  id: string; name: string; admin_level: number;
  geometry: Geometry | null; crs_source: string;
  metadata_json: Record<string, unknown>;
};
export type HorizonRisk = { hours: number; risk_level: string; calibrated_probability: number | null };
export type Forecast = {
  forecast_id: string; location_id: string; issued_at: string;
  mode: string; model_version: string; data_quality: string;
  horizons: HorizonRisk[]; limitations: string[];
};
export type FloodEvent = {
  id: string; region_id: string; name: string; start_at: string;
  end_at: string | null; mode: string; description: string | null;
};
export type Geometry = { type: string; coordinates: unknown };
export type ExtentFeature = {
  type: 'Feature'; id: string;
  properties: {
    event_id: string; observed_at: string; area_km2: number;
    method: string; confidence: number | null; source_scene_ids?: string[];
  };
  geometry: Geometry | null;
};
export type AlertRecord = {
  id: string; area_id: string; title: string; message: string;
  status: string; issued_at: string | null; created_at: string;
  mode: string; target_channels: string[];
};
export type Facility = {
  id: string; name: string; type: string;
  verification_status: string; status_checked_at: string | null;
  capacity: number | null; contact_info: string | null;
  longitude: number | null; latitude: number | null;
  limitations: string[]; source: string | null;
};
export type AssistanceRecord = {
  id: string; citizen_id: string; latitude: number; longitude: number;
  category: 'evacuation' | 'medical' | 'food_water' | 'shelter' | 'other';
  status: string; details: string | null; people_count: number;
  assigned_to: string | null; status_notes: string | null;
  created_at: string; updated_at: string;
};
export type AppEvent = {
  type: string; resource_id?: string; timestamp?: string;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = 'ApiError'; }
}

export async function restoreSession(): Promise<boolean> {
  try {
    token = await SecureStore.getItemAsync(TOKEN_KEY);
    return Boolean(token);
  } catch {
    token = null;
    return false;
  }
}
export async function signOut(): Promise<void> {
  token = null;
  try { await SecureStore.deleteItemAsync(TOKEN_KEY); } catch { /* Logout even if keystore is unavailable. */ }
}

async function jsonRequest<T>(path: string, init: RequestInit = {}, authenticated = false): Promise<T> {
  if (authenticated && !token) throw new ApiError(401, 'Sign in to continue.');
  const controller = new AbortController();
  const handle = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    });
    const parsed: unknown = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && authenticated) await signOut();
      const data = parsed as { detail?: string | { message?: string }; error?: { message?: string } };
      const message = typeof data.detail === 'string'
        ? data.detail : data.error?.message || 'Request failed; please try again.';
      throw new ApiError(response.status, `${message} (HTTP ${response.status})`);
    }
    return parsed as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new Error('Cannot reach FloodLens FastAPI. Check the network and configured API address.');
  } finally {
    clearTimeout(handle);
  }
}

export function getHealth(): Promise<{ status: string; database?: { connected: boolean } }> {
  return jsonRequest('/health');
}
export function getProfile(): Promise<CitizenProfile> {
  return jsonRequest('/auth/me', {}, true);
}
export async function login(email: string, password: string): Promise<CitizenProfile> {
  const result = await jsonRequest<{ access_token: string; role: string }>('/auth/login', {
    method: 'POST', body: JSON.stringify({ email: email.trim(), password }),
  });
  if (result.role !== 'citizen') throw new Error('Use a citizen account with the citizen Android app.');
  token = result.access_token;
  try {
    const profile = await getProfile();
    await SecureStore.setItemAsync(TOKEN_KEY, token);
    return profile;
  } catch (err) {
    await signOut();
    throw err;
  }
}
export async function register(email: string, password: string, fullName: string, consent: boolean): Promise<CitizenProfile> {
  await jsonRequest('/auth/register', {
    method: 'POST',
    body: JSON.stringify({
      email: email.trim(),
      password,
      full_name: fullName.trim() || null,
      contact_consent: consent,
    }),
  });
  return login(email, password);
}
export const getLocations = (): Promise<LocationRecord[]> => jsonRequest('/locations');
export const getLatestForecast = (locationId: string): Promise<Forecast> =>
  jsonRequest(`/predictions/latest?location_id=${encodeURIComponent(locationId)}`);
export const getHistoricalEvents = async (): Promise<FloodEvent[]> => {
  const events = await jsonRequest<FloodEvent[]>('/flood-events');
  return events.filter(e => e.mode === 'historical_demo' || e.mode === 'test');
};
export const getObservedExtent = (eventId: string): Promise<ExtentFeature> =>
  jsonRequest(`/flood-events/${encodeURIComponent(eventId)}/extent/geojson`);
export const getAlerts = (): Promise<AlertRecord[]> => jsonRequest('/alerts');
export const getShelters = async (): Promise<{ shelters: Facility[]; data_notes?: string }> =>
  jsonRequest('/facilities/shelters');
export const getHospitals = async (): Promise<{ hospitals: Facility[]; data_notes?: string }> =>
  jsonRequest('/facilities/hospitals');
export const getMyRequests = (): Promise<AssistanceRecord[]> =>
  jsonRequest('/assistance/mine', {}, true);
export const submitHelpRequest = (payload: {
  latitude: number; longitude: number;
  category: AssistanceRecord['category']; details: string; people_count: number;
}): Promise<AssistanceRecord> => jsonRequest('/assistance', {
  method: 'POST', body: JSON.stringify(payload),
}, true);
