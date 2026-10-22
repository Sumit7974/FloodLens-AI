/**
 * FastAPI integration for the authority web console.
 *
 * Intentionally keeps credentials and access tokens in module memory: a page reload
 * requires signing in again. Browser storage and network logs must not contain JWTs.
 * Operational traffic is strictly restricted to the backend's historical-demo/test
 * mode and this UI never contacts an operational alert gateway.
 */
export const DEMO_MODE = import.meta.env.VITE_USE_MOCK_DATA !== 'false';

const raw = String(import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000').replace(/\/+$/, '');
export const API_URL = raw.endsWith('/api/v1') ? raw : `${raw}/api/v1`;

export type Role = 'citizen' | 'authority' | 'admin';

export interface AuthSession {
  userId: string;
  role: Role;
}
export interface AssistanceRecord {
  id: string;
  citizen_id: string;
  latitude: number;
  longitude: number;
  category: 'evacuation' | 'medical' | 'food_water' | 'shelter' | 'other';
  status: 'pending' | 'acknowledged' | 'in_progress' | 'resolved' | 'cancelled';
  details: string | null;
  people_count: number;
  assigned_to: string | null;
  status_notes: string | null;
  created_at: string;
  updated_at: string;
}
export interface AlertRecord {
  id: string;
  area_id: string;
  title: string;
  message: string;
  status: 'draft' | 'approved' | 'dispatched' | 'cancelled';
  created_by: string;
  approved_by: string | null;
  issued_at: string | null;
  mode: string;
  target_channels: string[];
  created_at: string;
}
export interface FloodEventRecord {
  id: string;
  region_id: string;
  name: string;
  start_at: string;
  end_at: string | null;
  mode: 'historical_demo' | 'test' | 'live_observation' | 'model_estimate';
  source_refs: Record<string, unknown>;
  description: string | null;
  created_at: string;
}

export type MappableGeometry = {
  type: 'Polygon' | 'MultiPolygon';
  coordinates: unknown;
};

export interface ObservedExtentFeature {
  type: 'Feature';
  id: string;
  properties: {
    event_id: string;
    observed_at: string;
    method: string;
    area_km2: number;
    confidence: number | null;
    source_scene_ids: string[] | null;
  };
  geometry: MappableGeometry | null;
}

export interface SettlementExposureResponse {
  event_id: string;
  status: string;
  total_settlements_evaluated: number;
  total_settlements_affected: number;
  affected_settlements: unknown[];
  notes?: string | null;
}

export interface AssetExposureResponse {
  event_id: string;
  status: string;
  roads_exposed_km: number;
  structures_exposed_count: number;
  cropland_exposed_ha: number;
  exposed_assets: unknown[];
}

export interface PredictionMapResponse {
  layer_id: string;
  status: string;
  total_zones: number;
  issued_at: string | null;
  model_version: string | null;
  data_quality: string | null;
  mode: string | null;
  features: Array<{
    id: string;
    properties: {
      location_name?: string;
      model_version?: string;
      data_quality?: string;
      horizons?: Record<string, { risk_level: string; calibrated_probability: number | null }>;
    };
    geometry?: unknown;
  }>;
}

export interface ModelResearchRecord {
  version: string;
  type: string;
  status: string;
  horizons: number[];
  description: string;
  limitations: string[];
}

export interface ModelEvaluationRecord {
  id: string;
  target_type: string;
  baseline_version: string;
  candidate_version: string | null;
  metrics: Record<string, unknown>;
  reference_id: string | null;
  notes: string | null;
  created_at: string;
}

export interface EventEvaluations {
  event_id: string;
  event_name: string | null;
  status: string;
  evaluations_count: number;
  data_limitations: string[];
  results: ModelEvaluationRecord[];
}

export type BackendEvent = {
  type: string;
  event_id?: string;
  resource_id?: string;
  metadata?: Record<string, unknown>;
};

let accessToken: string | null = null;
let currentSession: AuthSession | null = null;

export function getSession(): AuthSession | null {
  return currentSession;
}
export function getAccessToken(): string | null {
  return accessToken;
}
export function clearSession(): void {
  accessToken = null;
  currentSession = null;
}
export class BackendRequestError extends Error {
  readonly status: number;
  readonly code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.name = 'BackendRequestError';
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (DEMO_MODE) throw new Error('Demo mode is enabled. Set VITE_USE_MOCK_DATA=false to use the FastAPI backend.');
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body != null) headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const abort = new AbortController();
  const timeout = setTimeout(() => abort.abort(), 8000);
  try {
    const response = await fetch(`${API_URL}${path}`, { ...init, headers, signal: abort.signal });
    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as {
        error?: { message?: string; code?: string; details?: unknown };
        detail?: string;
      };
      if (response.status === 401) clearSession();
      const code = body.error?.code || (response.status === 401 ? 'UNAUTHORIZED' : response.status === 403 ? 'FORBIDDEN' : response.status === 404 ? 'NOT_FOUND' : response.status === 409 ? 'CONFLICT' : `HTTP_${response.status}`);
      const message = body.error?.message || (typeof body.detail === 'string' ? body.detail : null) || `HTTP ${response.status}`;
      throw new BackendRequestError(response.status, message, code);
    }
    return (await response.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

export async function login(email: string, password: string): Promise<AuthSession> {
  clearSession();
  const response = await request<{
    access_token: string; user_id: string; role: Role;
  }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  if (!['authority', 'admin'].includes(response.role)) {
    throw new Error('This dashboard requires an existing authority/admin account. Citizen accounts cannot access the authority console.');
  }
  accessToken = response.access_token;
  currentSession = { userId: response.user_id, role: response.role };
  return currentSession;
}

export function requireAuthority(): void {
  if (!accessToken || !currentSession || !['authority', 'admin'].includes(currentSession.role)) {
    throw new Error('Sign in with an existing authority/admin account to use backend actions.');
  }
}

/**
 * Historical observations are always fetched from the backend's event-linked API.
 * A response from a local GIS file or generated preview is never presented as a
 * verified backend observation.
 */
export async function listHistoricalEvents(): Promise<FloodEventRecord[]> {
  const events = await request<FloodEventRecord[]>('/flood-events');
  return events.filter(event => event.mode === 'historical_demo' || event.mode === 'test');
}

export async function getObservedExtent(eventId: string): Promise<ObservedExtentFeature> {
  const feature = await request<ObservedExtentFeature>(`/flood-events/${encodeURIComponent(eventId)}/extent/geojson`);
  if (
    feature.type !== 'Feature' ||
    !feature.geometry ||
    !['Polygon', 'MultiPolygon'].includes(feature.geometry.type) ||
    !Array.isArray(feature.geometry.coordinates)
  ) {
    throw new Error('Backend flood extent does not have a valid Polygon/MultiPolygon GeoJSON geometry');
  }
  return feature;
}

export async function getSettlementExposure(eventId: string): Promise<SettlementExposureResponse> {
  return request<SettlementExposureResponse>(`/flood-events/${encodeURIComponent(eventId)}/settlements`);
}

export async function getAssetExposure(eventId: string): Promise<AssetExposureResponse> {
  return request<AssetExposureResponse>(`/flood-events/${encodeURIComponent(eventId)}/assets`);
}

export async function getPredictedRiskZones(): Promise<PredictionMapResponse> {
  return request<PredictionMapResponse>('/predictions/map');
}

export async function listResearchModels(): Promise<ModelResearchRecord[]> {
  return request<ModelResearchRecord[]>('/models');
}

export async function getEventEvaluations(eventId: string): Promise<EventEvaluations> {
  return request<EventEvaluations>(`/analytics/events/${encodeURIComponent(eventId)}`);
}

export interface GaugeStationRecord {
  station_id: string;
  name: string;
  river: string;
  coordinates: [number, number];
  current_level: number;
  warning_level: number;
  danger_level: number;
  discharge_rate: number;
  trend: string;
  last_reported_at: string;
  battery_level?: number;
  status: string;
}

export interface GaugeMonitoringResponse {
  status: string;
  stations: GaugeStationRecord[];
  readings: unknown[];
  count: number;
}

export interface WeatherMonitoringResponse {
  status: string;
  providers: string[];
  readings: unknown[];
  note: string;
}

export interface DamNotice {
  dam_name?: string;
  river?: string;
  scheduled_release_at?: string;
  discharge_m3s?: number;
  warning_level?: string;
  verified?: boolean;
  [key: string]: unknown;
}

export interface DamMonitoringResponse {
  notices: DamNotice[];
  verified_count: number;
  note: string;
}

export async function getRiverGauges(eventId?: string): Promise<GaugeStationRecord[]> {
  const path = eventId ? `/monitoring/gauges?event_id=${encodeURIComponent(eventId)}` : '/monitoring/gauges';
  const response = await request<GaugeMonitoringResponse>(path);
  return response.stations || [];
}

export async function getRiverMonitoring(eventId?: string): Promise<GaugeMonitoringResponse> {
  const path = eventId ? `/monitoring/rivers?event_id=${encodeURIComponent(eventId)}` : '/monitoring/rivers';
  return request<GaugeMonitoringResponse>(path);
}

export async function getWeatherMonitoring(): Promise<WeatherMonitoringResponse> {
  return request<WeatherMonitoringResponse>('/monitoring/weather');
}

export async function getDamMonitoring(): Promise<DamMonitoringResponse> {
  return request<DamMonitoringResponse>('/monitoring/dams');
}

export interface FacilityItem {
  id: string;
  type: string;
  name: string;
  verification_status: 'verified' | 'unverified' | 'demo_labeled' | string;
  capacity: number | null;
  contact_info: string | null;
  status_checked_at: string | null;
  location: { type: 'Point'; coordinates: [number, number] } | null;
  longitude: number | null;
  latitude: number | null;
  source: string | null;
  details: Record<string, unknown>;
  limitations: string[];
}

export interface ShelterListResponse {
  count: number;
  shelters: FacilityItem[];
  data_notes?: string;
}

export interface HospitalListResponse {
  count: number;
  hospitals: FacilityItem[];
  data_notes?: string;
}

export async function getShelters(verificationStatus?: string): Promise<ShelterListResponse> {
  const path = verificationStatus
    ? `/facilities/shelters?verification_status=${encodeURIComponent(verificationStatus)}`
    : '/facilities/shelters';
  return request<ShelterListResponse>(path);
}

export async function getHospitals(verificationStatus?: string): Promise<HospitalListResponse> {
  const path = verificationStatus
    ? `/facilities/hospitals?verification_status=${encodeURIComponent(verificationStatus)}`
    : '/facilities/hospitals';
  return request<HospitalListResponse>(path);
}

export interface RouteAssessRequest {
  route: {
    type: 'LineString';
    coordinates: [number, number][];
  };
  event_id?: string;
  evaluation_time?: string;
  cutoff_time?: string;
  buffer_meters?: number;
  evaluation_context?: Record<string, unknown>;
}

export interface RouteHazardIntersection {
  hazard_id: string;
  hazard_type: string;
  source_layer: string;
  status: string;
  observed_at: string;
  source?: string;
  confidence?: number;
  match_type?: string;
  proximity_distance_meters?: number;
  intersection_details?: Record<string, unknown>;
  notes?: string;
}

export interface RouteAssessResponse {
  route_status: 'conditional' | 'hazards_detected' | 'no_known_hazards_detected' | 'not_evaluated' | 'incomplete_data' | string;
  assessment_status: 'HAZARDS_INTERSECTED' | 'NO_KNOWN_INTERSECTIONS' | 'NOT_EVALUATED' | 'INCOMPLETE_DATA' | string;
  hazards_detected: RouteHazardIntersection[];
  event_id?: string | null;
  evaluation_time: string;
  cutoff_time_applied?: string | null;
  total_hazards_screened: number;
  hazards_intersected_count: number;
  limitations: string[];
  provenance: Record<string, unknown>;
}

export async function assessRoute(req: RouteAssessRequest): Promise<RouteAssessResponse> {
  return request<RouteAssessResponse>('/routes/assess', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export interface FloodReportResponse {
  event_id: string;
  event_name: string;
  region_id: string;
  mode: string;
  extent_observed_at: string | null;
  extent_area_km2: number | null;
  total_settlements_affected: number;
  roads_exposed_km: number;
  structures_exposed_count: number;
  cropland_exposed_ha: number;
  report_generated_at: string | null;
  status: string;
  settlements_evaluated: number;
  settlements_data_status?: string;
  assets_data_status?: string;
  data_limitations: string[];
  data_provenance?: Record<string, unknown>;
}

export async function getFloodReport(eventId: string): Promise<FloodReportResponse> {
  return request<FloodReportResponse>(`/flood-events/${encodeURIComponent(eventId)}/report`);
}

export async function downloadFloodReportExport(eventId: string, format: 'json' | 'csv'): Promise<void> {
  if (DEMO_MODE) {
    const demoCsv = `event_id,event_name,region_id,mode,status,extent_observed_at,extent_area_km2,extent_method,settlements_evaluated,settlements_affected,roads_exposed_km,structures_exposed_count,cropland_exposed_ha,exported_at\n${eventId},Koshi Basin Surge,koshi-basin,historical_demo,summary_available,2026-10-18T05:00:00Z,46.8,Sentinel-1 SAR,12,3,18.4,142,320.5,${new Date().toISOString()}`;
    const demoJson = JSON.stringify({
      event_id: eventId,
      event_name: 'Koshi Basin Surge (Historical Demo)',
      region_id: 'koshi-basin',
      mode: 'historical_demo',
      status: 'summary_available',
      extent_area_km2: 46.8,
      total_settlements_affected: 3,
      settlements_evaluated: 12,
      roads_exposed_km: 18.4,
      structures_exposed_count: 142,
      cropland_exposed_ha: 320.5,
      note: 'Demo mode export artifact. Backend is not currently attached.',
    }, null, 2);

    const blob = new Blob([format === 'csv' ? demoCsv : demoJson], {
      type: format === 'csv' ? 'text/csv' : 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `floodlens_impact_report_${eventId}.${format}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    return;
  }

  const token = getAccessToken();
  const headers = new Headers();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const res = await fetch(`${API_URL}/flood-events/${encodeURIComponent(eventId)}/report/export?format=${format}`, {
    headers,
  });
  if (!res.ok) {
    const errorBody = (await res.json().catch(() => ({}))) as { error?: { message?: string }; detail?: string };
    throw new Error(errorBody.error?.message || errorBody.detail || `Export failed with HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const disposition = res.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : `floodlens_impact_report_${eventId}.${format}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function getAssistanceQueue(): Promise<AssistanceRecord[]> {
  requireAuthority();
  return request<AssistanceRecord[]>('/assistance');
}

export async function updateAssistance(
  id: string,
  status: AssistanceRecord['status'],
  statusNotes?: string
): Promise<AssistanceRecord> {
  requireAuthority();
  return request<AssistanceRecord>(`/assistance/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ status, status_notes: statusNotes || null }),
  });
}

export async function listDemoAlerts(): Promise<AlertRecord[]> {
  requireAuthority();
  return request<AlertRecord[]>('/alerts?include_demo=true');
}

export async function createDemoDraft(areaId: string, title: string, message: string): Promise<AlertRecord> {
  requireAuthority();
  return request<AlertRecord>('/alerts', {
    method: 'POST',
    body: JSON.stringify({
      area_id: areaId,
      title: title.startsWith('[DEMO') ? title : `[DEMO ONLY] ${title}`,
      message,
      mode: 'historical_demo',
      target_channels: ['in_app'],
    }),
  });
}

export async function approveDemoDraft(id: string): Promise<AlertRecord> {
  requireAuthority();
  return request<AlertRecord>(`/alerts/${encodeURIComponent(id)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ notes: 'Historical demo review (authority action)' }),
  });
}

export async function dispatchApprovedDemo(id: string): Promise<AlertRecord> {
  requireAuthority();
  return request<AlertRecord>(`/alerts/${encodeURIComponent(id)}/dispatch`, {
    method: 'POST',
    body: JSON.stringify({ simulated: true, notes: 'Test-only in-app simulation; no public dispatch' }),
  });
}

/**
 * WebSocket reconnection uses authenticated prototype-only query-token auth.
 * Do not enable for public deployments; use short-lived tickets or secure cookies there.
 * A reconnect requests REST reconciliation instead of assuming events were not missed.
 */
export function subscribeAuthorityEvents(
  onEvent: (event: BackendEvent) => void,
  onState: (connected: boolean) => void
): () => void {
  requireAuthority();
  let stopped = false;
  let socket: WebSocket | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;
  const wsUrl = API_URL.replace(/^http/, 'ws').replace(/\/api\/v1$/, '/ws/v1/events');
  const connect = () => {
    if (stopped || !accessToken) return;
    socket = new WebSocket(`${wsUrl}?token=${encodeURIComponent(accessToken)}`);
    socket.onopen = () => {
      attempt = 0;
      onState(true);
      socket?.send(JSON.stringify({ action: 'subscribe', channel: 'authority_queue' }));
      socket?.send(JSON.stringify({ action: 'resync' }));
    };
    socket.onmessage = event => {
      try {
        const data = JSON.parse(String(event.data)) as BackendEvent;
        if (data.type) onEvent(data);
      } catch {
        // Ignore malformed events; REST is the source of truth.
      }
    };
    socket.onclose = () => {
      onState(false);
      if (!stopped && accessToken) {
        const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt++, 5));
        retry = setTimeout(connect, delay);
      }
    };
    socket.onerror = () => socket?.close();
  };
  connect();
  return () => {
    stopped = true;
    if (retry) clearTimeout(retry);
    socket?.close();
    onState(false);
  };
}
