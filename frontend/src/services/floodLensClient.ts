/**
 * FloodLens AI — Unified Service Adapter Layer
 * Provides seamless client abstraction connecting frontend views to FastAPI endpoints
 * with automatic resilient fallback to local typed benchmark fixtures.
 */

import {
  BENCHMARK_SCENES,
  BENCHMARK_SCENARIOS_DATA,
  MOCK_HELP_REQUESTS,
} from '../data/mockData';
import {
  HORIZON_FORECASTS,
  KOSHI_TELEMETRY_GAUGES,
} from '../data/geospatialData';
import type {
  AlertAuditRecord,
  AlertSimulationPayload,
  ApiResponse,
  CitizenAssistanceReport,
  FloodEventDetail,
  FloodEventSummary,
  FloodPolygonFeatureCollection,
  GaugeStation,
  ModelEvaluationMetrics,
  PredictionHorizonTier,
} from '../types/apiContracts';
import { mapToGaugeStations } from '../types/apiContracts';
import { DEMO_MODE, createDemoDraft } from './backendApi';

export class FloodLensClient {
  private static instance: FloodLensClient;
  private readonly baseUrl: string;
  private readonly useMockData: boolean;
  private readonly requestTimeoutMs = 3500;

  private constructor() {
    const rawBackendUrl = import.meta.env.VITE_BACKEND_URL;
    const base = rawBackendUrl ? String(rawBackendUrl).replace(/\/+$/, '') : 'http://localhost:8000';
    this.baseUrl = base.endsWith('/api/v1') ? base : `${base}/api/v1`;

    const mockEnv = import.meta.env.VITE_USE_MOCK_DATA;
    // Default to true if not explicitly set to 'false'
    this.useMockData = mockEnv === undefined || mockEnv === null || String(mockEnv) === 'true';

    if (this.useMockData) {
      console.info('[FloodLens Client] Initialized in STANDALONE BENCHMARK MODE (VITE_USE_MOCK_DATA=true)');
    } else {
      console.info(`[FloodLens Client] Initialized in LIVE BACKEND MODE (${this.baseUrl})`);
    }
  }

  public static getInstance(): FloodLensClient {
    if (!FloodLensClient.instance) {
      FloodLensClient.instance = new FloodLensClient();
    }
    return FloodLensClient.instance;
  }

  /**
   * Resilient HTTP GET wrapper with timeout & automatic fallback
   */
  private async executeFetch<T>(
    endpoint: string,
    fallbackGenerator: () => T,
    methodName: string,
    options?: RequestInit,
    transform?: (raw: any) => T
  ): Promise<ApiResponse<T>> {
    if (this.useMockData) {
      console.debug(`[FloodLens Client] Using benchmark fallback for ${methodName} (Mock mode active)`);
      return {
        data: fallbackGenerator(),
        isMock: true,
        status: 'cached',
      };
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.requestTimeoutMs);

    try {
      const url = `${this.baseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          ...(options?.headers || {}),
        },
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} from ${endpoint}`);
      }

      const json = await response.json();
      const mappedData = transform ? transform(json) : (json as T);
      return {
        data: mappedData,
        isMock: false,
        status: 'live',
      };
    } catch (err: any) {
      clearTimeout(timeoutId);
      console.debug(`[FloodLens Client] Using benchmark fallback for ${methodName} (${err?.message || 'Network error'})`);
      return {
        data: fallbackGenerator(),
        isMock: true,
        status: 'error',
        error: err?.message || 'Network timeout / unreachable',
      };
    }
  }

  /**
   * 1. Get all available flood event scenarios
   */
  public async getFloodEvents(): Promise<ApiResponse<FloodEventSummary[]>> {
    return this.executeFetch(
      '/flood-events',
      () =>
        BENCHMARK_SCENES.map((s) => {
          const bounds = s.bounds || [[86.9, 26.4], [87.3, 26.9]];
          return {
            id: s.id,
            name: s.name,
            basin: s.name.split('—')[1]?.trim() || s.name,
            region: s.region,
            district: s.district,
            center: [s.center[0], s.center[1]],
            bounding_box: [
              [bounds[0][0], bounds[0][1]],
              [bounds[1][0], bounds[1][1]],
            ],
            status: 'SURGING',
            crest_time: '+3.5 Hours Estimated',
            peak_discharge_m3s: s.peak_discharge_m3s,
            mode: 'historical_demo',
            date_range: s.date_range,
            hasSatelliteTruth: s.hasSatelliteTruth !== false,
          };
        }),
      'getFloodEvents'
    );
  }

  /**
   * 2. Get specific event detail
   */
  public async getEventDetail(eventId: string): Promise<ApiResponse<FloodEventDetail>> {
    return this.executeFetch(
      `/flood-events/${eventId}`,
      () => {
        const scene = BENCHMARK_SCENES.find((s) => s.id === eventId) || BENCHMARK_SCENES[0];
        const scenario = BENCHMARK_SCENARIOS_DATA[scene.id] || BENCHMARK_SCENARIOS_DATA['koshi-basin-primary'];
        const bounds = scene.bounds || [[86.9, 26.4], [87.3, 26.9]];
        return {
          id: scene.id,
          name: scene.name,
          basin: scene.name.split('—')[1]?.trim() || scene.name,
          region: scene.region,
          district: scene.district,
          center: [scene.center[0], scene.center[1]],
          bounding_box: [
            [bounds[0][0], bounds[0][1]],
            [bounds[1][0], bounds[1][1]],
          ],
          status: 'SURGING',
          crest_time: '+3.5 Hours Estimated',
          peak_discharge_m3s: scene.peak_discharge_m3s,
          mode: 'historical_demo',
          date_range: scene.date_range,
          hasSatelliteTruth: scene.hasSatelliteTruth !== false,
          description: scene.description,
          satellite_pass: scene.satellite_pass,
          upstream_rainfall_mm: 148.6,
          inundated_area_km2: 64.2,
          population_exposed: scenario.metrics.populationAtRisk.total,
          active_warnings_count: scenario.alerts.length,
          open_assistance_count: scenario.requests.length,
        };
      },
      'getEventDetail'
    );
  }

  /**
   * 3. Get river telemetry gauge stations (targets /monitoring/gauges)
   */
  public async getTelemetryGauges(eventId: string = 'koshi-basin-primary'): Promise<ApiResponse<GaugeStation[]>> {
    const fallbackGenerator = () =>
      KOSHI_TELEMETRY_GAUGES.map((g) => ({
        station_id: g.id,
        name: g.name,
        river: g.river,
        coordinates: [g.coordinates[1], g.coordinates[0]] as [number, number], // [lon, lat]
        current_level: g.currentLevel,
        warning_level: g.warningThreshold,
        danger_level: g.dangerThreshold,
        discharge_rate: g.flowRate,
        trend: g.trend as any,
        last_reported_at: '2m ago',
        battery_level: 94,
        status: g.currentLevel >= g.dangerThreshold ? ('CRITICAL' as const) : ('WARNING' as const),
      }));

    const endpoint = eventId ? `/monitoring/gauges?event_id=${encodeURIComponent(eventId)}` : '/monitoring/gauges';

    return this.executeFetch<GaugeStation[]>(
      endpoint,
      fallbackGenerator,
      'getTelemetryGauges',
      undefined,
      (raw) => {
        const mapped = mapToGaugeStations(raw);
        return mapped.length > 0 ? mapped : fallbackGenerator();
      }
    );
  }

  /**
   * 4. Get dynamic prediction horizon polygon feature collection
   */
  public async getPredictionLayer(
    eventId: string = 'koshi-basin-primary',
    horizon: string = '3h'
  ): Promise<ApiResponse<FloodPolygonFeatureCollection>> {
    const horizonKey = (horizon.toLowerCase().replace('+', '').replace('h', '') + 'h') as '1h' | '3h' | '6h';
    return this.executeFetch(
      `/predictions/map?event_id=${eventId}&horizon=${horizon}`,
      () => {
        const forecastConfig = HORIZON_FORECASTS[horizonKey] || HORIZON_FORECASTS['3h'];
        const coords = forecastConfig.polygonCoords.map(([lat, lon]) => [lon, lat]);
        if (coords.length > 0 && (coords[0][0] !== coords[coords.length - 1][0] || coords[0][1] !== coords[coords.length - 1][1])) {
          coords.push([...coords[0]]);
        }

        return {
          type: 'FeatureCollection',
          properties: {
            horizon: (horizon.toUpperCase() as PredictionHorizonTier),
            event_id: eventId,
            model_version: 'FloodLens-LSTM-GNN v1.2',
            calibrated_at: new Date().toISOString(),
          },
          features: [
            {
              type: 'Feature',
              id: `inundation-${horizon}`,
              properties: {
                horizon: horizon.toUpperCase(),
                inflow_cusecs: forecastConfig.inflowCusecs,
                threat_level: forecastConfig.threatLevel,
                exposed_population: forecastConfig.populationAtRisk,
              },
              geometry: {
                type: 'Polygon',
                coordinates: [coords],
              },
            },
          ],
        };
      },
      'getPredictionLayer'
    );
  }

  /**
   * 5. Get citizen assistance triage reports for event
   */
  public async getAssistanceReports(eventId: string = 'koshi-basin-primary'): Promise<ApiResponse<CitizenAssistanceReport[]>> {
    return this.executeFetch(
      `/assistance?event_id=${eventId}`,
      () => {
        const scenario = BENCHMARK_SCENARIOS_DATA[eventId] || BENCHMARK_SCENARIOS_DATA['koshi-basin-primary'];
        const sourceRequests = scenario.requests || MOCK_HELP_REQUESTS;
        return sourceRequests.map((r) => ({
          id: r.id,
          requester_name: r.requester_name,
          contact: r.contact_number,
          timestamp: r.timestamp,
          category: r.category as any,
          urgency: r.urgency as any,
          urgency_score: r.urgency_score || 'Priority 1',
          souls: r.people_count,
          location_name: r.location_name,
          coordinates: r.coordinates,
          landmark: r.landmark,
          notes: r.notes,
          estimated_water_depth: r.estimated_water_depth,
          battery_level: r.battery_level,
          status: (r.handoff_status || r.status) as any,
          authority_handoff_target: r.authority_handoff_target || 'DEOC Sunsari',
          nearest_shelter: r.nearest_shelter,
          nearest_highground: r.nearest_highground,
          nearest_medical: r.nearest_medical,
          report_elapsed_time: r.report_elapsed_time,
          authority_verification: r.authority_verification,
          audit_trail: (r.activity_log || []).map((a) => ({
            timestamp: a.timestamp,
            action: a.action,
            author: a.author,
          })),
        }));
      },
      'getAssistanceReports'
    );
  }

  /**
   * 6. Update assistance ticket status and log authority handoff note
   */
  public async updateAssistanceStatus(
    reportId: string,
    status: string,
    notes?: string
  ): Promise<ApiResponse<CitizenAssistanceReport>> {
    return this.executeFetch(
      `/assistance/${reportId}`,
      () => {
        return {
          id: reportId,
          requester_name: 'Citizen (Audit Record)',
          contact: '+977 981-XXXXXXX',
          timestamp: 'Updated just now',
          category: 'TRAPPED',
          urgency: 'HIGH',
          urgency_score: 'Priority 1 - Handoff Active',
          souls: 4,
          location_name: 'Sunsari Floodplain Reach',
          coordinates: [26.68, 87.05],
          status: status as any,
          authority_handoff_target: 'DEOC Sunsari',
          audit_trail: [
            {
              timestamp: 'Just now',
              action: `Authority status updated to ${status}${notes ? `: ${notes}` : ''}`,
              author: 'EOC Duty Officer',
            },
          ],
        };
      },
      'updateAssistanceStatus',
      {
        method: 'PATCH',
        body: JSON.stringify({ status, notes }),
      }
    );
  }

  /**
   * 7. Simulation-only alert workflow.
   *
   * In backend mode this creates a DRAFT, never a dispatched alert. A separate
   * authorized human review and explicit simulated dispatch are required.
   * Network failures MUST NOT produce fake success records.
   */
  public async postSimulatedAlert(payload: AlertSimulationPayload): Promise<ApiResponse<AlertAuditRecord>> {
    if (!DEMO_MODE) {
      try {
        const draft = await createDemoDraft(payload.geofence_id, payload.headline, payload.message);
        return {
          status: 'live',
          isMock: false,
          data: {
            id: draft.id,
            code: `DEMO-${draft.id.slice(0, 8)}`,
            geofence: draft.area_id,
            severity: payload.severity,
            headline: draft.title,
            description: draft.message,
            headline_ne: payload.headline_ne,
            description_ne: payload.message_ne,
            channels: draft.target_channels,
            approved_by: draft.approved_by || '',
            dispatched_at: '',
            expires_at: '',
            population_affected: 0,
            simulated_reach: 0,
            audit_hash: '',
            is_drill_simulation: true,
            status: 'DRAFT',
          },
        };
      } catch (error) {
        return {
          status: 'error',
          isMock: false,
          data: null as unknown as AlertAuditRecord,
          error: error instanceof Error ? error.message : 'Failed to create backend draft',
        };
      }
    }

    return {
      status: 'cached',
      isMock: true,
      data: {
        id: `DEMO-${Date.now()}`,
        code: `LOCAL-DEMO-${Date.now().toString().slice(-6)}`,
        geofence: payload.geofence_id,
        severity: payload.severity,
        headline: `[DEMO ONLY] ${payload.headline}`,
        description: payload.message,
        headline_ne: payload.headline_ne,
        description_ne: payload.message_ne,
        channels: payload.channels,
        approved_by: 'Local historical demonstration only',
        dispatched_at: 'Local UI simulation (no network dispatch)',
        expires_at: '',
        population_affected: 0,
        simulated_reach: 0,
        audit_hash: 'LOCAL-DEMO-UNVERIFIED',
        is_drill_simulation: true,
        status: 'DISPATCHED',
      },
    };
  }

  /**
   * 8. Get post-disaster spatial verification & candidate model evaluation
   */
  public async getModelEvaluation(eventId: string = 'koshi-basin-primary'): Promise<ApiResponse<ModelEvaluationMetrics>> {
    return this.executeFetch(
      `/analytics/events/${eventId}`,
      () => ({
        benchmark_event: '2026 Monsoon Surge — Koshi Basin Reach',
        dataset_coverage: 'Sentinel-1 SAR VV + Sentinel-2 MSI Optical + 12 Hydro Telemetry Gauges',
        baseline_version: '1D Hydrological Baseline (v1.0)',
        candidate_version: 'Physics-Guided LSTM-GNN v1.3-RC',
        iou: 0.842,
        precision: 0.894,
        recall: 0.867,
        f1_score: 0.880,
        false_alarm_km2: 4.8,
        missed_area_km2: 3.2,
        true_positive_km2: 56.2,
        breach_sensitivity_pct: 91.0,
        validation_splits_info: '5-fold spatial cross-validation trained across 2017–2024 Terai monsoons',
        evaluated_at: '2026-10-18T05:00:00Z',
      }),
      'getModelEvaluation'
    );
  }
}

export const floodLensClient = FloodLensClient.getInstance();
