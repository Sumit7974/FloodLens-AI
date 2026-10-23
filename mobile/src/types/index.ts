/**
 * FloodLens Mobile TypeScript Definitions
 * Synchronized with FastAPI Backend Telemetry and GeoJSON schemas.
 */

export type RiskLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'EXTREME';
export type AlertSeverity = 'ADVISORY' | 'WATCH' | 'WARNING' | 'EMERGENCY';
export type RequestCategory = 'TRAPPED' | 'MEDICAL' | 'EVACUATION' | 'FOOD_WATER' | 'SHELTER' | 'ELDERLY_EVAC';
export type UrgencyLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type BadgeVariant = 'warning' | 'destructive' | 'success' | 'info';

export type AuthorityHandoffStatus =
  | 'LOCAL_LOGGED'
  | 'TRANSMITTED_TO_DEOC'
  | 'SIMULATED_AUTHORITY_ACK'
  | 'ACKNOWLEDGED_BY_AUTHORITY'
  | 'RESOLVED';

export interface DatabaseHealth {
  connected: boolean;
  database_type?: string;
  postgis_installed?: boolean;
  postgis_version?: string;
  latency_ms?: number;
  error?: string;
}

export interface BackendHealthResponse {
  status: string;
  app_name?: string;
  version?: string;
  environment?: string;
  operational_mode?: string;
  database?: DatabaseHealth;
  timestamp?: string;
}

export interface CitizenSOSPayload {
  requester_name: string;
  contact_number: string;
  category: RequestCategory;
  urgency: UrgencyLevel;
  people_count: number;
  location_name: string;
  latitude: number;
  longitude: number;
  accuracy?: number | null;
  estimated_water_depth?: string;
  medical_urgency?: boolean;
  landmark?: string;
  notes?: string;
  battery_level?: number;
  timestamp?: string;
}

export interface HelpRequest {
  id: string;
  requester_name: string;
  contact_number: string;
  timestamp: string;
  category: RequestCategory;
  urgency: UrgencyLevel;
  urgency_score?: string;
  status: AuthorityHandoffStatus;
  people_count: number;
  location_name: string;
  coordinates: [number, number]; // [lat, lng]
  landmark?: string;
  notes?: string;
  battery_level?: number;
  estimated_water_depth?: string;
  medical_urgency?: boolean;
  accuracy?: number | null;
  synced?: boolean;
  queued_at?: string;
}

export interface QueuedIncident {
  localId: string;
  payload: CitizenSOSPayload;
  queuedAt: string;
  retryCount: number;
  lastError?: string;
}

export interface IncidentSubmissionResult {
  success: boolean;
  mode: 'online' | 'offline_queued';
  id: string;
  incident: HelpRequest;
  error?: string;
}

export interface GPSLocationState {
  latitude: number;
  longitude: number;
  accuracy: number | null;
  altitude: number | null;
  status: 'locked' | 'acquiring' | 'fallback' | 'denied';
  sectorName: string;
  lastUpdated: string;
}

export type ResponderAction = 'ACKNOWLEDGE' | 'DISPATCH_TEAM' | 'RESOLVE';

export interface SensorReading {
  sensor_id: string;
  station_name: string;
  river_basin: string;
  water_level_m: number;
  danger_threshold_m: number;
  warning_threshold_m: number;
  flow_rate_m3s: number;
  rainfall_1h_mm: number;
  rainfall_24h_mm: number;
  status: 'NORMAL' | 'WARNING' | 'CRITICAL' | 'OFFLINE';
  last_reported_at: string;
}

export interface TelemetrySummary {
  floodThreatLevel: string;
  threatLevelCode: number;
  exposedPopulation: number;
  assistanceReportsCount: number;
  activeSensorsCount: number;
  totalSensorsCount: number;
  backendConnected: boolean;
}

