export type RiskLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'EXTREME';

export type AlertSeverity = 'ADVISORY' | 'WATCH' | 'WARNING' | 'EMERGENCY';

export type AlertStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'DISPATCHED' | 'CANCELLED';

export type RequestCategory = 'TRAPPED' | 'MEDICAL' | 'EVACUATION' | 'FOOD_WATER' | 'SHELTER' | 'ELDERLY_EVAC';

export type UrgencyLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export type AssistanceStatus = 'OPEN' | 'ASSIGNED' | 'EN_ROUTE' | 'RESOLVED';

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
  status: AssistanceStatus;
  people_count: number;
  location_name: string;
  coordinates: [number, number]; // [lat, lng]
  landmark: string;
  notes: string;
  assigned_unit?: string;
  battery_level?: number;
  estimated_water_depth?: string;
  photo_url?: string;
  nearest_shelter?: { name: string; distance: string };
  nearest_boat?: { name: string; distance: string; eta: string };
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
  };
  openRequests: {
    total: number;
    critical: number;
    assigned: number;
  };
  sensorHealth: {
    reporting: number;
    total: number;
    status: string;
    latency: string;
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
