/**
 * FloodLens AI — Official API & Event Contracts
 * Standardized TypeScript contracts conforming to docs/DATABASE_API_EVENT_CONTRACTS.md
 */

export interface ApiResponse<T> {
  data: T;
  isMock: boolean;
  status: 'live' | 'cached' | 'error';
  error?: string;
}

// 1. Flood Event Summary & Detail Models
export interface FloodEventSummary {
  id: string;
  name: string;
  basin: string;
  region: string;
  district: string;
  center: [number, number]; // [lon, lat]
  bounding_box: [[number, number], [number, number]]; // [[minLon, minLat], [maxLon, maxLat]]
  status: 'MONITORING' | 'SURGING' | 'RECEDING' | 'RESOLVED';
  crest_time: string;
  peak_discharge_m3s: number;
  mode: 'historical_demo' | 'live';
  date_range: string;
  hasSatelliteTruth: boolean;
}

export interface FloodEventDetail extends FloodEventSummary {
  description: string;
  satellite_pass: string;
  upstream_rainfall_mm: number;
  inundated_area_km2: number;
  population_exposed: number;
  active_warnings_count: number;
  open_assistance_count: number;
  hydrograph_url?: string;
}

// 2. Telemetry & River Gauge Stations
export type GaugeTrend = 'RISING' | 'STABLE' | 'FALLING';
export type GaugeSeverity = 'NORMAL' | 'WARNING' | 'CRITICAL' | 'OFFLINE';

export interface TelemetryReading {
  reading_id: string;
  station_id: string;
  timestamp: string;
  water_level_m: number;
  discharge_m3s: number;
  rainfall_1h_mm?: number;
  rainfall_24h_mm?: number;
  status: GaugeSeverity;
  trend: GaugeTrend;
}

export interface GaugeStation {
  station_id: string;
  name: string;
  river: string;
  coordinates: [number, number]; // [lon, lat]
  current_level: number;
  warning_level: number;
  danger_level: number;
  discharge_rate: number;
  trend: GaugeTrend;
  last_reported_at: string;
  battery_level?: number;
  status: GaugeSeverity;
}

/**
 * Maps raw backend responses (from /monitoring/gauges or /monitoring/rivers)
 * into strict GaugeStation[] contract instances.
 */
export function mapToGaugeStations(raw: any): GaugeStation[] {
  if (!raw) return [];
  const list = Array.isArray(raw)
    ? raw
    : Array.isArray(raw.stations)
    ? raw.stations
    : Array.isArray(raw.data?.stations)
    ? raw.data.stations
    : Array.isArray(raw.data)
    ? raw.data
    : Array.isArray(raw.readings)
    ? raw.readings
    : Array.isArray(raw.features)
    ? raw.features.map((f: any) => ({
        ...(f.properties || {}),
        coordinates: f.geometry?.coordinates || f.coordinates,
      }))
    : [];

  return list.map((item: any, idx: number) => {
    const source = item.properties ? { ...item.properties, coordinates: item.geometry?.coordinates || item.coordinates } : item;

    let coords: [number, number] = [87.163, 26.871];
    if (Array.isArray(source.coordinates) && source.coordinates.length >= 2) {
      const c0 = Number(source.coordinates[0]);
      const c1 = Number(source.coordinates[1]);
      // Normalize to [lon, lat]: in Nepal latitude is ~26-30°N, longitude is ~80-88°E
      if (c0 < 40 && c1 > 60) {
        coords = [c1, c0];
      } else {
        coords = [c0, c1];
      }
    } else if (source.lon != null && source.lat != null) {
      coords = [Number(source.lon), Number(source.lat)];
    } else if (source.longitude != null && source.latitude != null) {
      coords = [Number(source.longitude), Number(source.latitude)];
    }

    const currentLevel = Number(
      source.current_level ?? source.water_level_m ?? source.level ?? source.currentLevel ?? 0
    );
    const warningLevel = Number(
      source.warning_level ?? source.warning_threshold ?? source.warningThreshold ?? 7.0
    );
    const dangerLevel = Number(
      source.danger_level ?? source.danger_threshold ?? source.dangerThreshold ?? 8.0
    );
    const dischargeRate = Number(
      source.discharge_rate ?? source.discharge_m3s ?? source.flow_rate ?? source.flowRate ?? 0
    );

    let status: GaugeSeverity = 'NORMAL';
    if (source.status) {
      const s = String(source.status).toUpperCase();
      if (s === 'CRITICAL' || s === 'DANGER' || s === 'HIGH') status = 'CRITICAL';
      else if (s === 'WARNING' || s === 'MODERATE') status = 'WARNING';
      else if (s === 'OFFLINE' || s === 'ERROR') status = 'OFFLINE';
      else status = 'NORMAL';
    } else {
      if (currentLevel >= dangerLevel) status = 'CRITICAL';
      else if (currentLevel >= warningLevel) status = 'WARNING';
    }

    let trend: GaugeTrend = 'STABLE';
    if (source.trend) {
      const t = String(source.trend).toUpperCase();
      if (t.includes('RISE') || t === 'UP') trend = 'RISING';
      else if (t.includes('FALL') || t === 'DOWN') trend = 'FALLING';
      else trend = 'STABLE';
    }

    return {
      station_id: String(source.station_id || source.id || `station-${idx + 1}`),
      name: String(source.name || source.station_name || `Gauge Station ${idx + 1}`),
      river: String(source.river || source.river_name || source.waterbody || 'Koshi River'),
      coordinates: coords,
      current_level: currentLevel,
      warning_level: warningLevel,
      danger_level: dangerLevel,
      discharge_rate: dischargeRate,
      trend,
      last_reported_at: String(source.last_reported_at || source.timestamp || source.updated_at || 'Just now'),
      battery_level: source.battery_level != null ? Number(source.battery_level) : 94,
      status,
    };
  });
}

// 3. Predictive Inundation Horizons & GeoJSON Layers
export type PredictionHorizonTier = 'NOW' | '+1H' | '+3H' | '+6H';

export interface PredictionHorizon {
  horizon: PredictionHorizonTier;
  label: string;
  inflow_cusecs: number;
  dam_gates_open: string;
  peak_arrival_time: string;
  threat_level: string;
  threat_color: string;
  exposed_population_est: number;
  submerged_roads_km: number;
  wards_at_risk: string[];
}

export interface FloodPolygonFeatureCollection {
  type: 'FeatureCollection';
  properties?: {
    horizon: PredictionHorizonTier;
    event_id: string;
    model_version: string;
    calibrated_at: string;
  };
  features: Array<{
    type: 'Feature';
    id?: string | number;
    properties: {
      horizon: string;
      inundation_depth?: string;
      risk_tier?: string;
      source?: string;
      [key: string]: any;
    };
    geometry: {
      type: 'Polygon' | 'MultiPolygon';
      coordinates: number[][][] | number[][][][];
    };
  }>;
}

// 4. Citizen Assistance Reports & Authority Handoff
export type CitizenRequestCategory =
  | 'TRAPPED'
  | 'MEDICAL'
  | 'EVACUATION'
  | 'FOOD_WATER'
  | 'SHELTER'
  | 'ELDERLY_EVAC';

export type AuthorityLifecycleStatus =
  | 'LOCAL_LOGGED'
  | 'TRANSMITTED_TO_DEOC'
  | 'SIMULATED_AUTHORITY_ACK'
  | 'RESOLVED';

export interface AuthorityHandoffLog {
  timestamp: string;
  action: string;
  author: string;
}

export interface CitizenAssistanceReport {
  id: string;
  requester_name: string;
  contact: string;
  timestamp: string;
  category: CitizenRequestCategory;
  urgency: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  urgency_score: string;
  souls: number;
  location_name: string;
  coordinates: [number, number]; // [lat, lon] or [lon, lat]
  landmark?: string;
  notes?: string;
  estimated_water_depth?: string;
  battery_level?: number;
  status: AuthorityLifecycleStatus;
  authority_handoff_target?: string;
  nearest_shelter?: {
    name: string;
    distance: string;
  };
  nearest_highground?: {
    name: string;
    distance: string;
    elevationMsl?: number;
  };
  nearest_medical?: {
    name: string;
    distance: string;
    status?: string;
  };
  report_elapsed_time?: string;
  authority_verification?: string;
  audit_trail: AuthorityHandoffLog[];
}

// 5. Alert Dispatch & Audit Log Records
export interface AlertSimulationPayload {
  geofence_id: string;
  severity: 'ADVISORY' | 'WATCH' | 'WARNING' | 'EMERGENCY';
  channels: string[];
  headline: string;
  message: string;
  headline_ne?: string;
  message_ne?: string;
  designated_shelter?: string;
  issued_by: string;
  simulated_reach?: number;
  audit_hash?: string;
}

export interface AlertAuditRecord {
  id: string;
  code: string;
  geofence: string;
  severity: 'ADVISORY' | 'WATCH' | 'WARNING' | 'EMERGENCY';
  headline: string;
  description: string;
  headline_ne?: string;
  description_ne?: string;
  channels: string[];
  approved_by: string;
  dispatched_at: string;
  expires_at: string;
  population_affected: number;
  simulated_reach: number;
  audit_hash: string;
  is_drill_simulation: boolean;
  status: 'DRAFT' | 'APPROVED' | 'DISPATCHED' | 'CANCELLED';
}

// 6. Model Analytics & Spatial Verification
export interface ModelEvaluationMetrics {
  benchmark_event: string;
  dataset_coverage: string;
  baseline_version: string;
  candidate_version: string;
  iou: number; // Intersection over Union (0-1)
  precision: number;
  recall: number;
  f1_score: number;
  false_alarm_km2: number;
  missed_area_km2: number;
  true_positive_km2: number;
  breach_sensitivity_pct: number;
  validation_splits_info: string;
  evaluated_at: string;
}
