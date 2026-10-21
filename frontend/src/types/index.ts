export type RiskLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'EXTREME';

export type AlertSeverity = 'ADVISORY' | 'WATCH' | 'WARNING' | 'EMERGENCY';

export type AlertStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'DISPATCHED' | 'CANCELLED';

export type RequestCategory = 'TRAPPED' | 'MEDICAL' | 'EVACUATION' | 'FOOD_WATER' | 'SHELTER' | 'ELDERLY_EVAC';

export type UrgencyLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export type AuthorityHandoffStatus =
  | 'LOCAL_LOGGED'
  | 'TRANSMITTED_TO_DEOC'
  | 'SIMULATED_AUTHORITY_ACK'
  | 'ACKNOWLEDGED_BY_AUTHORITY'
  | 'RESOLVED';

// Backwards compatibility alias
export type AssistanceStatus = AuthorityHandoffStatus | 'OPEN' | 'ASSIGNED' | 'EN_ROUTE';

export type SensorStatus = 'NORMAL' | 'WARNING' | 'CRITICAL' | 'OFFLINE';

export type TrendDirection = 'RISING' | 'STABLE' | 'FALLING';

export interface Alert {
  id: string;
  code: string;
  headline: string;
  description: string;
  headline_ne?: string;
  description_ne?: string;
  severity: AlertSeverity;
  risk_level: RiskLevel;
  geofence: string;
  population_affected: number;
  status: AlertStatus;
  issued_at: string;
  expires_at: string;
  channels: string[];
  approved_by: string;
  dispatched_at: string;
  evacuation_notice: boolean;
  safe_shelter?: string;
  read_rate?: number;
  reach_count?: number;
  audit_hash?: string;
  is_drill_simulation?: boolean;
}

export interface ActivityLogEntry {
  timestamp: string;
  action: string;
  author: string;
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
  landmark: string;
  notes: string;
  handoff_status?: AuthorityHandoffStatus;
  authority_handoff_target?: string;
  assigned_unit?: string; // Legacy alias for authority handoff target
  authority_verification?: string;
  report_elapsed_time?: string;
  battery_level?: number;
  estimated_water_depth?: string;
  photo_url?: string;
  nearest_shelter?: { name: string; distance: string };
  nearest_highground?: { name: string; distance: string; elevationMsl?: number };
  nearest_medical?: { name: string; distance: string; status?: string };
  nearest_boat?: { name: string; distance: string; eta?: string }; // Legacy field
  activity_log?: ActivityLogEntry[];
}

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
  status: SensorStatus;
  last_reported_at: string;
  trend: TrendDirection;
  battery_percent: number;
}

export interface BenchmarkScene {
  id: string;
  name: string;
  region: string;
  district: string;
  event_type: string;
  date_range: string;
  peak_discharge_m3s: number;
  satellite_pass: string;
  description: string;
  center: [number, number]; // [lng, lat] for MapLibre
  zoom: number;
  pitch?: number;
  bearing?: number;
  bounds?: [[number, number], [number, number]]; // [[swLng, swLat], [neLng, neLat]]
  hasSatelliteTruth?: boolean;
}

export interface MetricSummary {
  floodThreat: {
    level: string;
    levelCode: number;
    trend: TrendDirection;
    trendLabel: string;
    description: string;
  };
  populationAtRisk: {
    total: number;
    settlementsCount: number;
    criticalZones: number;
    trend: string;
    censusCalculationNote?: string;
  };
  openRequests: {
    total: number;
    critical: number;
    assigned: number; // Represents transmitted/acknowledged
    transmittedToDeoc?: number;
  };
  sensorHealth: {
    reporting: number;
    total: number;
    status: string;
    latency: string;
    modelStats?: string;
  };
}

export type NavigationItemId =
  | 'command-overview'
  | 'prediction-centre'
  | 'satellite-intel'
  | 'response-ops'
  | 'alert-dispatcher'
  | 'model-analytics';

export interface NavigationItem {
  id: NavigationItemId;
  label: string;
  badge?: string;
  badgeColor?: string;
  sublabel?: string;
}
