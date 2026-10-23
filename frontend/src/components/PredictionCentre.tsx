import React, { useState, useEffect, useMemo } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  BrainCircuit,
  CheckCircle,
  Clock,
  Download,
  FileText,
  Gauge,
  Info,
  Layers,
  Lock,
  MapPin,
  RefreshCw,
  TrendingUp,
  Waves,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import {
  HORIZON_FORECASTS,
  HYDROGRAPH_TIMELINE,
  KOSHI_TELEMETRY_GAUGES,
} from '../data/geospatialData';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';
import { DataStatusBadge } from './common/DataStatusBadge';
import { floodLensClient } from '../services/floodLensClient';
import {
  API_URL,
  DEMO_MODE,
  getLatestForecast,
  listLocations,
  BackendRequestError,
  getAccessToken,
  type ForecastResponse,
  type LocationItem,
} from '../services/backendApi';
import type { GaugeStation } from '../types/apiContracts';
import { InteractiveHoverButton } from '@/components/ui/interactive-hover-button';
import type { BenchmarkScene } from '../types';

interface PredictionCentreProps {
  currentScene: BenchmarkScene;
  onNavigateToDispatcher?: (initialAlertPayload?: any) => void;
}

interface KnownLocation {
  id: string;
  name: string;
  reach: string;
}

const DEFAULT_KNOWN_LOCATIONS: KnownLocation[] = [
  { id: 'settlement_janakpurdham', name: 'Janakpurdham (Terai Region)', reach: 'Kamala River Reach' },
  { id: 'loc_barahachhetra_w2', name: 'Barahakshetra Ward 2', reach: 'Main Embankment Reach' },
  { id: 'loc_prakashpur_w3', name: 'Prakashpur Ward 3', reach: 'Floodplain / Embankment Reach' },
  { id: 'loc_gobargadha_w1', name: 'Gobargadha Ward 1', reach: 'Riverine Island Reach' },
];

type BackendForecastState =
  | { status: 'idle'; data: null }
  | { status: 'loading'; data: null }
  | { status: 'unauthorized'; data: null; message: string; statusCode: 401 | 403 }
  | { status: 'unavailable'; data: null; message: string; statusCode: 404 }
  | { status: 'error'; data: null; message: string }
  | { status: 'success'; data: ForecastResponse };

export const PredictionCentre: React.FC<PredictionCentreProps> = ({
  currentScene,
  onNavigateToDispatcher,
}) => {
  // Mode selection: either DEMO BENCHMARK fixture or LIVE FASTAPI BACKEND
  const [activeDataSource, setActiveDataSource] = useState<'demo' | 'backend'>(
    DEMO_MODE ? 'demo' : 'backend'
  );

  const [horizon, setHorizon] = useState<'Now' | '1h' | '3h' | '6h'>('3h');

  // Selected Location for Backend Forecasting
  const [selectedLocationId, setSelectedLocationId] = useState<string>('loc_barahachhetra_w2');
  const [availableLocations, setAvailableLocations] = useState<KnownLocation[]>(DEFAULT_KNOWN_LOCATIONS);

  // Backend Persisted Forecast Query State
  const [forecastState, setForecastState] = useState<BackendForecastState>({
    status: 'idle',
    data: null,
  });

  // Selected telemetry station for hydrograph comparison (Chatara vs Koshi Barrage)
  const [activeGaugeStation, setActiveGaugeStation] = useState<'chatara' | 'barrage'>('chatara');

  // Layer Toggles
  const [showIsoContours, setShowIsoContours] = useState(true);
  const [showInfrastructure, setShowInfrastructure] = useState(true);
  const [showShelters, setShowShelters] = useState(true);
  const [showGauges, setShowGauges] = useState(true);

  // Technical Advisory Modal State
  const [showAdvisoryModal, setShowAdvisoryModal] = useState(false);
  const [advisoryExportToast, setAdvisoryExportToast] = useState<string | null>(null);

  // Client API / Mock Adapter State for Map Layer
  const [mapApiStatus, setMapApiStatus] = useState<'live' | 'cached' | 'error'>('cached');

  // Gauge Telemetry Client State
  const [telemetryStatus, setTelemetryStatus] = useState<'live' | 'cached' | 'error'>('cached');
  const [telemetryGauges, setTelemetryGauges] = useState<GaugeStation[]>([]);

  // Discover registered locations from backend on mount or when switching to backend mode
  useEffect(() => {
    let isMounted = true;
    const fetchBackendLocations = async () => {
      try {
        const remoteLocations = await listLocations(true);
        if (isMounted && remoteLocations && remoteLocations.length > 0) {
          const merged: KnownLocation[] = [...DEFAULT_KNOWN_LOCATIONS];
          remoteLocations.forEach((loc: LocationItem) => {
            if (!merged.some((m) => m.id === loc.id)) {
              merged.push({
                id: loc.id,
                name: loc.name,
                reach: loc.admin_level === 4 ? 'Settlement Zone' : `Admin Level ${loc.admin_level}`,
              });
            }
          });
          setAvailableLocations(merged);
        }
      } catch {
        // Fall back to built-in known locations
      }
    };
    void fetchBackendLocations();
    return () => {
      isMounted = false;
    };
  }, []);

  // Fetch forecast from FastAPI backend
  const loadBackendForecast = async (locationId: string) => {
    setForecastState({ status: 'loading', data: null });
    try {
      const data = await getLatestForecast(locationId, true);
      setForecastState({ status: 'success', data });
    } catch (err: unknown) {
      if (err instanceof BackendRequestError) {
        if (err.status === 401 || err.status === 403) {
          setForecastState({
            status: 'unauthorized',
            data: null,
            message:
              'Authority authentication required. Sign in via the Backend Access Panel in the header to view persisted forecasts.',
            statusCode: err.status,
          });
          return;
        }
        if (err.status === 404) {
          setForecastState({
            status: 'unavailable',
            data: null,
            message: `No forecast records exist in PostgreSQL for location '${locationId}'. Ingest Member 3's leak-free forecast via POST /api/v1/predictions/ingest.`,
            statusCode: 404,
          });
          return;
        }
        setForecastState({
          status: 'error',
          data: null,
          message: err.message || `Backend returned HTTP ${err.status}`,
        });
        return;
      }
      setForecastState({
        status: 'error',
        data: null,
        message: `Unable to connect to backend at ${API_URL}. Verify backend service is running.`,
      });
    }
  };

  // Re-query backend forecast when location or mode changes
  useEffect(() => {
    if (activeDataSource === 'backend') {
      void loadBackendForecast(selectedLocationId);
    }
  }, [selectedLocationId, activeDataSource]);

  // Map layer query via floodLensClient
  useEffect(() => {
    let isMounted = true;
    const fetchPredictionLayer = async () => {
      const res = await floodLensClient.getPredictionLayer(currentScene.id, horizon);
      if (isMounted) {
        setMapApiStatus(res.status);
      }
    };
    fetchPredictionLayer();
    return () => {
      isMounted = false;
    };
  }, [currentScene.id, horizon]);

  // Gauge telemetry query
  useEffect(() => {
    let isMounted = true;
    const fetchGauges = async () => {
      const res = await floodLensClient.getTelemetryGauges(currentScene.id);
      if (isMounted) {
        if (res.status) {
          setTelemetryStatus(res.status);
        }
        if (res.data && res.data.length > 0) {
          setTelemetryGauges(res.data);
        }
      }
    };
    fetchGauges();
    return () => {
      isMounted = false;
    };
  }, [currentScene.id]);

  const forecastKey = horizon === 'Now' ? '1h' : horizon;
  const benchmarkForecast = HORIZON_FORECASTS[forecastKey];

  // Selected gauge details
  const activeGaugeFromClient = telemetryGauges.find((g) =>
    activeGaugeStation === 'chatara'
      ? g.station_id.includes('chatara') || g.name.toLowerCase().includes('chatara')
      : g.station_id.includes('barrage') || g.name.toLowerCase().includes('barrage')
  );

  const selectedGauge = activeGaugeFromClient
    ? {
        id: activeGaugeFromClient.station_id,
        name: activeGaugeFromClient.name,
        river: activeGaugeFromClient.river,
        coordinates: activeGaugeFromClient.coordinates,
        currentLevel: activeGaugeFromClient.current_level,
        warningThreshold: activeGaugeFromClient.warning_level,
        dangerThreshold: activeGaugeFromClient.danger_level,
        flowRate: activeGaugeFromClient.discharge_rate,
        trend: activeGaugeFromClient.trend,
      }
    : activeGaugeStation === 'chatara'
    ? KOSHI_TELEMETRY_GAUGES[0]
    : KOSHI_TELEMETRY_GAUGES[1];

  // Hydrograph points
  const hydrographPoints =
    activeGaugeStation === 'chatara'
      ? HYDROGRAPH_TIMELINE.map((p) =>
          p.time === 'Now' && selectedGauge
            ? { ...p, level: selectedGauge.currentLevel, flow: selectedGauge.flowRate }
            : p
        )
      : [
          { time: '-6h', label: '22:30 UTC', level: 73.65, flow: 8400, type: 'HISTORICAL' },
          { time: '-4h', label: '00:30 UTC', level: 73.95, flow: 9600, type: 'HISTORICAL' },
          { time: '-2h', label: '02:30 UTC', level: 74.35, flow: 11200, type: 'HISTORICAL' },
          { time: 'Now', label: '04:30 UTC', level: selectedGauge?.currentLevel ?? 74.85, flow: selectedGauge?.flowRate ?? 12980, type: 'CURRENT' },
          { time: '+1h', label: '05:30 UTC', level: 74.98, flow: 13400, type: 'FORECAST' },
          { time: '+3h', label: '07:30 UTC', level: 75.20, flow: 13950, type: 'FORECAST' },
          { time: '+6h', label: '10:30 UTC', level: 75.45, flow: 14400, type: 'FORECAST' },
        ];

  // Derived Horizon Risk from backend forecast if in backend mode
  const backendHorizonMap = useMemo(() => {
    if (forecastState.status !== 'success' || !forecastState.data) return null;
    const map = new Map<number, { risk_level: string; calibrated_probability: number | null }>();
    forecastState.data.horizons.forEach((h) => {
      map.set(h.hours, {
        risk_level: h.risk_level.toUpperCase(),
        calibrated_probability: h.calibrated_probability,
      });
    });
    return map;
  }, [forecastState]);

  // Get active risk label for pill buttons
  const getHorizonRiskDisplay = (hours: number): { label: string; isUnavailable?: boolean } => {
    if (activeDataSource === 'demo') {
      if (hours === 1) return { label: 'MODERATE (DEMO)' };
      if (hours === 3) return { label: 'HIGH (DEMO)' };
      return { label: 'SEVERE (DEMO)' };
    }

    if (forecastState.status === 'loading') return { label: 'LOADING...' };
    if (forecastState.status === 'unauthorized') return { label: 'AUTH REQUIRED', isUnavailable: true };
    if (forecastState.status === 'unavailable') return { label: 'NO RECORD', isUnavailable: true };
    if (forecastState.status === 'error') return { label: 'UNREACHABLE', isUnavailable: true };

    const item = backendHorizonMap?.get(hours);
    if (!item) return { label: 'NOT RECORDED', isUnavailable: true };

    return { label: item.risk_level };
  };

  // Active threat tier for right-side cards
  const activeThreatInfo = useMemo(() => {
    if (activeDataSource === 'demo') {
      return {
        level: benchmarkForecast.threatLevel,
        isDemo: true,
        probabilityText: 'DEM 1.5x Boundary Conformance (Offline Benchmark)',
      };
    }

    if (forecastState.status === 'loading') {
      return { level: 'LOADING...', isDemo: false, probabilityText: 'Contacting FastAPI backend...' };
    }
    if (forecastState.status === 'unauthorized') {
      return { level: 'AUTH REQUIRED', isDemo: false, probabilityText: 'Sign in with an authority account to retrieve predictions' };
    }
    if (forecastState.status === 'unavailable') {
      return { level: 'UNAVAILABLE', isDemo: false, probabilityText: 'No forecast record exists in PostgreSQL for this location' };
    }
    if (forecastState.status === 'error') {
      return { level: 'ERROR', isDemo: false, probabilityText: 'FastAPI backend connection failed' };
    }

    const currentHours = horizon === '1h' ? 1 : horizon === '3h' ? 3 : horizon === '6h' ? 6 : 1;
    const record = backendHorizonMap?.get(currentHours);
    if (!record) {
      return { level: 'NO HORIZON', isDemo: false, probabilityText: 'Horizon not returned by backend' };
    }

    const probText =
      record.calibrated_probability !== null
        ? `${Math.round(record.calibrated_probability * 100)}% (Calibrated probability)`
        : 'Uncalibrated classifier score — calibrated probability unavailable';

    return {
      level: record.risk_level,
      isDemo: false,
      probabilityText: probText,
    };
  }, [activeDataSource, forecastState, horizon, benchmarkForecast, backendHorizonMap]);

  // Technical situation bulletin payload for Ministry/DEOC
  const generateBulletinPayload = () => {
    const isBackend = activeDataSource === 'backend' && forecastState.status === 'success' && forecastState.data;
    const modelVersion = isBackend ? forecastState.data.model_version : 'FloodLens-LSTM-GNN v1.2 (Benchmark Scenario)';
    const issueTime = isBackend ? forecastState.data.issued_at : new Date().toISOString();

    return {
      bulletin_id: `ADV-KOSHI-2026-H${horizon.toUpperCase()}`,
      notice_type: 'SIMULATED TECHNICAL SITUATION BULLETIN // HISTORICAL DEMO ONLY',
      status: 'INTERNAL DECISION SUPPORT DRAFT — NOT DISPATCHED / NOT A PUBLIC WARNING',
      issued_at: issueTime,
      issuing_body: 'FloodLens AI Decision-Support Intelligence / EOC Modeling Desk',
      intended_recipients: [
        'Ministry of Home Affairs (MoHA) - NEOC',
        'District Emergency Operation Center (DEOC) Sunsari',
        'District Emergency Operation Center (DEOC) Saptari',
        'Armed Police Force (APF) Disaster Management Division',
      ],
      forecast_horizon: horizon,
      location_id: selectedLocationId,
      model_metadata: {
        architecture: modelVersion,
        source: isBackend ? `FastAPI Backend (${API_URL})` : 'Offline Benchmark Fixture',
        calibration_window: '2017–2024 Terai Monsoons (Koshi Reach)',
        risk_level: activeThreatInfo.level,
        probability_disclosure: activeThreatInfo.probabilityText,
        limitations: isBackend ? forecastState.data.limitations : [
          'Historical simulation fixture only; proxy-labelled reanalysis is not independently verified flood ground truth.',
          'Not authorized for citizen evacuation routing or automated siren dispatch.',
        ],
      },
      basin_surge_parameters: {
        chatara_stage: `${selectedGauge.currentLevel}m (Danger Threshold: ${selectedGauge.dangerThreshold}m)`,
        chatara_inflow_discharge: `${selectedGauge.flowRate} m³/s`,
        barrage_outflow_stage: '74.85m (Danger Threshold: 74.50m)',
        predicted_crest_arrival: benchmarkForecast.peakCrestEta,
        sluice_status: benchmarkForecast.damGatesOpen,
      },
      at_risk_infrastructure_segments: [
        'East-West Highway Ch. 42+200 - 45+800 (Overbank inundation expected)',
        'Chatara Main Canal Dyke Embankment (Scour alert at headworks)',
        'Koshi Spur km 12+400 (Severe hydraulic pressure on riprap revetment)',
      ],
      threatened_wards_census_exposure: benchmarkForecast.highRiskWards.map((w) => ({
        ward_name: w.name,
        estimated_depth: w.depthRange,
        exposed_population: w.population,
        hazard_tier: w.hazard,
      })),
      recommended_civil_protection_perimeters: [
        'Prioritize low-lying riverine evacuations in Prakashpur Wards 3 & 4 and Barahakshetra Ward 2 to verified high ground shelters.',
        'Activate tractor-accessible corridors to Inaruwa Municipality Safe Hub before nightfall.',
        'Issue advisory notices to APF boat stations at Chatara and Prakashpur staging points.',
      ],
      operational_warning: 'THIS BULLETIN DOES NOT CONSTITUTE AN OFFICIAL PUBLIC FLOOD WARNING OR ALERT DISPATCH.',
    };
  };

  const handleExportBulletinJson = () => {
    const data = generateBulletinPayload();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Situation_Bulletin_Koshi_${horizon}_${selectedLocationId}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    setAdvisoryExportToast('Structured technical bulletin exported (JSON format)');
    setTimeout(() => setAdvisoryExportToast(null), 3500);
  };

  const handleProceedToDispatcher = () => {
    if (onNavigateToDispatcher) {
      onNavigateToDispatcher({
        horizon,
        threatLevel: activeThreatInfo.level,
        population: benchmarkForecast.populationAtRisk,
        wards: benchmarkForecast.highRiskWards.map((w) => w.name),
        isSimulated: true,
        mode: 'historical_demo',
        title: `[DEMO ADVISORY] Koshi Basin Flood Risk (+${horizon.toUpperCase()})`,
        source: activeDataSource === 'backend' && forecastState.status === 'success' && forecastState.data
          ? `FastAPI (${forecastState.data.model_version})`
          : 'Historical Benchmark Fixture',
      });
    }
    setShowAdvisoryModal(false);
  };

  const selectedLoc = availableLocations.find((l) => l.id === selectedLocationId) || availableLocations[0];
  const hasAuthToken = !!getAccessToken();

  return (
    <div className="space-y-4">
      {/* 1. TOP CONTROL BAR */}
      <div className="p-4 sm:p-5 rounded-xl bg-zinc-950/80 border border-zinc-800/80 backdrop-blur-md space-y-4 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <div className="p-2 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300">
                <TrendingUp className="w-4 h-4 text-cyan-400" />
              </div>
              <div>
                <h1 className="font-sans text-base font-bold text-white tracking-normal uppercase flex items-center gap-2 flex-wrap">
                  Prediction Centre — Multi-Horizon Hydrological Forecasting
                  {activeDataSource === 'demo' ? (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-950/40 border border-amber-800/60 text-amber-300">
                      DEMO BENCHMARK MODE
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-cyan-950/40 border border-cyan-800/60 text-cyan-300 flex items-center gap-1">
                      <Wifi className="w-3 h-3 text-cyan-400" />
                      FASTAPI BACKEND MODE
                    </span>
                  )}
                  <DataStatusBadge status={activeDataSource === 'demo' ? 'cached' : mapApiStatus} />
                </h1>
                <p className="font-mono text-xs text-zinc-400 uppercase tracking-wider mt-0.5">
                  {activeDataSource === 'backend' && forecastState.status === 'success' && forecastState.data ? (
                    <span>
                      MODEL: <strong className="text-white">{forecastState.data.model_version.toUpperCase()}</strong> //
                      ISSUED: <strong className="text-zinc-300">{new Date(forecastState.data.issued_at).toUTCString()}</strong> //
                      QUALITY: <strong className="text-cyan-400">{forecastState.data.data_quality.toUpperCase()}</strong> //
                      MODE: <strong className="text-amber-400">{forecastState.data.mode.toUpperCase()}</strong> //
                      AUTH: <strong className={hasAuthToken ? "text-emerald-400" : "text-zinc-500"}>{hasAuthToken ? "TOKEN ATTACHED" : "UNAUTHENTICATED"}</strong>
                    </span>
                  ) : (
                    <span>
                      PHYSICS-INFORMED GRAPH NEURAL NETWORK // {currentScene.name} ({currentScene.district})
                    </span>
                  )}
                </p>
              </div>
            </div>
          </div>

          {/* Controls Cluster: Data Source Toggle + Location Selector */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Mode Switcher: Demo Benchmark vs Live Backend */}
            <div className="inline-flex items-center p-1 bg-black/80 border border-zinc-800 rounded-lg gap-1">
              <button
                type="button"
                onClick={() => setActiveDataSource('demo')}
                className={`px-2.5 py-1 text-[11px] font-mono font-semibold uppercase rounded-md transition-all cursor-pointer ${
                  activeDataSource === 'demo'
                    ? 'bg-amber-950/50 text-amber-300 border border-amber-800/60 shadow-sm'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                Demo Fixture
              </button>
              <button
                type="button"
                onClick={() => setActiveDataSource('backend')}
                className={`px-2.5 py-1 text-[11px] font-mono font-semibold uppercase rounded-md transition-all cursor-pointer flex items-center gap-1 ${
                  activeDataSource === 'backend'
                    ? 'bg-cyan-950/50 text-cyan-300 border border-cyan-800/60 shadow-sm'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                FastAPI Backend
              </button>
            </div>

            {/* Configurable Location Selector */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 bg-black/80 border border-zinc-800 rounded-lg text-xs font-mono">
              <MapPin className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              <label htmlFor="prediction-location-select" className="text-zinc-500 sr-only">
                Target Location
              </label>
              <select
                id="prediction-location-select"
                value={selectedLocationId}
                onChange={(e) => setSelectedLocationId(e.target.value)}
                className="bg-transparent text-white font-mono text-xs focus:outline-none cursor-pointer pr-1"
              >
                {availableLocations.map((loc) => (
                  <option key={loc.id} value={loc.id} className="bg-zinc-900 text-white">
                    {loc.name} ({loc.reach})
                  </option>
                ))}
              </select>
              {activeDataSource === 'backend' && (
                <button
                  type="button"
                  title="Refetch backend forecast"
                  onClick={() => loadBackendForecast(selectedLocationId)}
                  className="text-zinc-400 hover:text-white p-0.5"
                >
                  <RefreshCw className={`w-3 h-3 ${forecastState.status === 'loading' ? 'animate-spin text-cyan-400' : ''}`} />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Demo Mode Notice Banner */}
        {activeDataSource === 'demo' && (
          <aside
            role="status"
            className="p-3 rounded-lg bg-amber-950/30 border border-amber-800/50 flex items-start gap-2.5 text-xs font-mono text-amber-200/90"
          >
            <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <span className="font-bold uppercase tracking-wider text-amber-300 block">
                HISTORICAL DEMONSTRATION FIXTURE MODE
              </span>
              <p className="text-[11px] text-amber-200/80 leading-relaxed">
                Displaying pre-calibrated offline simulation benchmark for <strong>{currentScene.name}</strong>.
                Forecast values reflect synthetic/research demonstration scenarios. Switch to <em>FastAPI Backend</em> mode
                above to query live records ingested into PostgreSQL.
              </p>
            </div>
          </aside>
        )}

        {/* Backend State Banners */}
        {activeDataSource === 'backend' && (
          <>
            {forecastState.status === 'loading' && (
              <div
                role="status"
                className="p-3 rounded-lg bg-cyan-950/30 border border-cyan-800/50 flex items-center gap-2.5 text-xs font-mono text-cyan-200"
              >
                <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin shrink-0" />
                <span>
                  Querying multi-horizon forecast from FastAPI backend for <strong>{selectedLoc.name}</strong> ({selectedLocationId})...
                </span>
              </div>
            )}

            {forecastState.status === 'unauthorized' && (
              <div
                role="alert"
                className="p-3 rounded-lg bg-amber-950/40 border border-amber-700/60 flex items-start gap-2.5 text-xs font-mono text-amber-200"
              >
                <Lock className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <span className="font-bold uppercase text-amber-300 block">
                    AUTHORITY AUTHENTICATION REQUIRED (HTTP {forecastState.statusCode})
                  </span>
                  <p className="text-[11px] text-amber-200/90">
                    {forecastState.message}
                  </p>
                </div>
              </div>
            )}

            {forecastState.status === 'unavailable' && (
              <div
                role="alert"
                className="p-3 rounded-lg bg-zinc-900 border border-zinc-700/80 flex items-start gap-2.5 text-xs font-mono text-zinc-300"
              >
                <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <span className="font-bold uppercase text-zinc-200 block">
                    NO FORECAST RECORDS FOUND FOR {selectedLoc.name.toUpperCase()} (HTTP 404)
                  </span>
                  <p className="text-[11px] text-zinc-400">
                    {forecastState.message}
                  </p>
                  <p className="text-[10px] text-zinc-500">
                    Run: <code className="text-zinc-300 bg-black/60 px-1 py-0.5 rounded">python -m ml.scripts.submit_demo_forecast --features-file ml/examples/historical_demo_inputs.json --location-id {selectedLocationId} --submit</code>
                  </p>
                </div>
              </div>
            )}

            {forecastState.status === 'error' && (
              <div
                role="alert"
                className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/60 flex items-start gap-2.5 text-xs font-mono text-rose-200"
              >
                <WifiOff className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <span className="font-bold uppercase text-rose-300 block">
                    FASTAPI BACKEND UNREACHABLE
                  </span>
                  <p className="text-[11px] text-rose-200/90">{forecastState.message}</p>
                </div>
              </div>
            )}

            {forecastState.status === 'success' && forecastState.data?.limitations && forecastState.data.limitations.length > 0 && (
              <div
                role="region"
                aria-label="Model limitations"
                className="p-3 rounded-lg bg-zinc-950 border border-amber-500/40 text-xs font-mono text-amber-300/90 space-y-1.5"
              >
                <div className="font-bold uppercase flex items-center gap-1.5 text-amber-200 text-[11px]">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                  MODEL PROVENANCE & OPERATIONAL LIMITATIONS ({forecastState.data.model_version.toUpperCase()})
                </div>
                <ul className="list-disc list-inside space-y-0.5 text-zinc-300 text-[11px]">
                  {forecastState.data.limitations.map((lim, idx) => (
                    <li key={idx}>{lim}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}

        {/* Interactive Time-Horizon Switcher: Segmented Control Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1 border-t border-zinc-900">
          <div className="inline-flex items-center p-1 bg-black/80 border border-zinc-800 rounded-lg gap-1 flex-wrap">
            <button
              type="button"
              onClick={() => setHorizon('Now')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-bold uppercase rounded-md transition-all cursor-pointer ${
                horizon === 'Now'
                  ? 'bg-cyan-950/50 text-cyan-400 border border-cyan-800/60 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
              }`}
            >
              <Clock className="w-3 h-3 text-cyan-300" />
              <span>NOW</span>
              <span className="text-[9px] opacity-80">(OBSERVED)</span>
            </button>

            <button
              type="button"
              onClick={() => setHorizon('1h')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-bold uppercase rounded-md transition-all cursor-pointer ${
                horizon === '1h'
                  ? 'bg-emerald-950/50 text-emerald-400 border border-emerald-800/60 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
              }`}
            >
              <Clock className="w-3 h-3 text-emerald-300" />
              <span>+1 HOUR</span>
              <span className={`text-[9px] opacity-80 ${getHorizonRiskDisplay(1).isUnavailable ? 'text-zinc-500' : ''}`}>
                ({getHorizonRiskDisplay(1).label})
              </span>
            </button>

            <button
              type="button"
              onClick={() => setHorizon('3h')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-bold uppercase rounded-md transition-all cursor-pointer ${
                horizon === '3h'
                  ? 'bg-amber-950/50 text-amber-400 border border-amber-800/60 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
              }`}
            >
              <Clock className="w-3 h-3 text-amber-300" />
              <span>+3 HOURS</span>
              <span className={`text-[9px] opacity-80 ${getHorizonRiskDisplay(3).isUnavailable ? 'text-zinc-500' : ''}`}>
                ({getHorizonRiskDisplay(3).label})
              </span>
            </button>

            <button
              type="button"
              onClick={() => setHorizon('6h')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-bold uppercase rounded-md transition-all cursor-pointer ${
                horizon === '6h'
                  ? 'bg-rose-950/50 text-rose-400 border border-rose-800/60 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
              }`}
            >
              <Clock className="w-3 h-3 text-rose-300" />
              <span>+6 HOURS</span>
              <span className={`text-[9px] opacity-80 ${getHorizonRiskDisplay(6).isUnavailable ? 'text-zinc-500' : ''}`}>
                ({getHorizonRiskDisplay(6).label})
              </span>
            </button>
          </div>

          {/* Station Selection for Hydrograph Comparison */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-mono font-medium">
              TELEMETRY STATION:
            </span>
            <div className="inline-flex items-center p-0.5 bg-black/80 border border-zinc-800 rounded-lg text-xs font-mono">
              <button
                type="button"
                onClick={() => setActiveGaugeStation('chatara')}
                className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                  activeGaugeStation === 'chatara'
                    ? 'bg-zinc-800 text-white font-bold'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                Chatara Headworks
              </button>
              <button
                type="button"
                onClick={() => setActiveGaugeStation('barrage')}
                className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                  activeGaugeStation === 'barrage'
                    ? 'bg-zinc-800 text-white font-bold'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                Koshi Barrage
              </button>
            </div>
          </div>
        </div>

        {/* Impact Prediction Metric Cards Cluster */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
          {/* Cluster A: Discharge & Sluice Status */}
          <div className="rounded-xl bg-zinc-950/80 border border-zinc-800/80 backdrop-blur-md p-4 sm:p-5 flex flex-col justify-between space-y-3.5 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-sm uppercase tracking-wider text-zinc-200 font-semibold flex items-center gap-2">
                <Waves className="w-4 h-4 text-cyan-400" />
                PREDICTED INFLOW DISCHARGE (CHATARA GAUGE)
              </span>
              <span className="text-xs font-mono text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
                BASIN CONFLUENCE
              </span>
            </div>

            <div>
              <div className="text-3xl sm:text-4xl font-extrabold tracking-tight font-mono text-white flex items-baseline gap-2">
                <span>{benchmarkForecast.inflowCusecs.toLocaleString()}</span>
                <span className="text-sm font-sans font-semibold text-cyan-400 uppercase">CUSECS</span>
              </div>
            </div>

            <div className="border-t border-zinc-800/80 pt-3 grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="space-y-1">
                <span className="text-xs uppercase tracking-wider text-zinc-400 font-semibold block">
                  BARRAGE SLUICE STATUS
                </span>
                <span className="text-sm sm:text-base font-bold text-zinc-200 font-mono block">
                  {benchmarkForecast.damGatesOpen.toUpperCase()}
                </span>
              </div>
              <div className="space-y-1 border-l border-zinc-800/80 pl-3">
                <span className="text-xs uppercase tracking-wider text-zinc-400 font-semibold block">
                  OUTFLOW DISCHARGE
                </span>
                <span className="text-sm sm:text-base font-bold text-zinc-200 font-mono block">
                  94% CAPACITY
                </span>
              </div>
            </div>
          </div>

          {/* Cluster B: Crest Projection & Arrival */}
          <div className="rounded-xl bg-zinc-950/80 border border-zinc-800/80 backdrop-blur-md p-4 sm:p-5 flex flex-col justify-between space-y-3.5 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-sm uppercase tracking-wider text-zinc-200 font-semibold flex items-center gap-2">
                <Clock className="w-4 h-4 text-amber-400" />
                CREST PROJECTION &amp; ARRIVAL
              </span>
              <span
                className={`text-xs font-mono font-bold px-2.5 py-1 rounded uppercase ${
                  activeThreatInfo.level === 'CRITICAL' || activeThreatInfo.level === 'SEVERE'
                    ? 'text-rose-400 bg-rose-950/40 border border-rose-800/50'
                    : activeThreatInfo.level === 'HIGH'
                    ? 'text-amber-400 bg-amber-950/40 border border-amber-800/50'
                    : 'text-zinc-400 bg-zinc-900 border border-zinc-800'
                }`}
              >
                {activeThreatInfo.level} RISK
              </span>
            </div>

            <div>
              <div className="text-3xl sm:text-4xl font-extrabold tracking-tight font-mono text-white">
                {benchmarkForecast.peakCrestEta.toUpperCase()}
              </div>
            </div>

            <div className="border-t border-zinc-800/80 pt-3 grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="space-y-1">
                <span className="text-xs uppercase tracking-wider text-zinc-400 font-semibold block">
                  CRITICAL SPUR REACH
                </span>
                <span className="text-sm sm:text-base font-bold text-zinc-200 font-mono block">
                  SPUR 12+400
                </span>
              </div>
              <div className="space-y-1 border-l border-zinc-800/80 pl-3">
                <span className="text-xs uppercase tracking-wider text-zinc-400 font-semibold block">
                  CHANNEL VELOCITY
                </span>
                <span className="text-sm sm:text-base font-bold text-zinc-200 font-mono block">
                  3.4 M/S
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Cluster C: Model & Telemetry Provenance Footer Bar */}
        <div className="rounded-xl bg-zinc-950/80 border border-zinc-800/80 px-5 py-3 flex flex-wrap items-center justify-between gap-3 text-sm font-mono text-zinc-300">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-zinc-500 flex items-center gap-1.5 font-medium">
              <BrainCircuit className="w-3.5 h-3.5 text-emerald-400" />
              MODEL PROVENANCE:
            </span>
            <span className="text-zinc-200 font-medium">
              {activeDataSource === 'backend' && forecastState.status === 'success' && forecastState.data
                ? forecastState.data.model_version
                : 'LSTM-GNN v1.2 (Benchmark Fixture)'}
            </span>
            <span className="text-zinc-700 select-none">·</span>
            <span className="text-zinc-400">{activeThreatInfo.probabilityText}</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
            <span className="text-zinc-300 font-medium">
              {activeDataSource === 'backend' ? `API: ${API_URL}` : 'BENCHMARK FIXTURE ACTIVE'}
            </span>
          </div>
        </div>
      </div>

      {/* 2. MAIN 2-COLUMN LAYOUT */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* LEFT COLUMN: 3D GEOSPATIAL MAP */}
        <div className="lg:col-span-7 xl:col-span-8 flex flex-col space-y-2">
          {/* Layer Toggles Bar: Unified Segmented Control */}
          <div className="p-2 sm:p-2.5 rounded-xl bg-zinc-950/80 border border-zinc-800/80 backdrop-blur-md flex flex-wrap items-center justify-between gap-2.5 text-xs">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-mono font-medium flex items-center gap-1.5 mr-1">
                <Layers className="w-3.5 h-3.5 text-zinc-400" />
                MAP LAYERS:
              </span>

              <div className="inline-flex items-center bg-black/80 backdrop-blur-md rounded-lg p-1 border border-zinc-800 gap-1 flex-wrap">
                <button
                  type="button"
                  onClick={() => setShowIsoContours(!showIsoContours)}
                  className={`px-3 py-1 rounded-md text-xs font-mono font-semibold uppercase transition-all cursor-pointer ${
                    showIsoContours
                      ? 'bg-cyan-950/40 text-cyan-400 shadow-sm'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
                  }`}
                >
                  FLOOD HORIZON ({horizon.toUpperCase()})
                </button>

                <button
                  type="button"
                  onClick={() => setShowGauges(!showGauges)}
                  className={`px-3 py-1 rounded-md text-xs font-mono font-semibold uppercase transition-all cursor-pointer ${
                    showGauges
                      ? 'bg-cyan-950/40 text-cyan-400 shadow-sm'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
                  }`}
                >
                  GAUGES
                </button>

                <button
                  type="button"
                  onClick={() => setShowInfrastructure(!showInfrastructure)}
                  className={`px-3 py-1 rounded-md text-xs font-mono font-semibold uppercase transition-all cursor-pointer ${
                    showInfrastructure
                      ? 'bg-cyan-950/40 text-cyan-400 shadow-sm'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
                  }`}
                >
                  ROAD CUTS / DYKES
                </button>

                <button
                  type="button"
                  onClick={() => setShowShelters(!showShelters)}
                  className={`px-3 py-1 rounded-md text-xs font-mono font-semibold uppercase transition-all cursor-pointer ${
                    showShelters
                      ? 'bg-cyan-950/40 text-cyan-400 shadow-sm'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
                  }`}
                >
                  HIGH GROUND REFUGES
                </button>
              </div>
            </div>

            <div className="text-xs font-mono text-zinc-400 flex items-center gap-1.5">
              <span className="text-zinc-500">TARGET:</span>
              <span className="text-zinc-200 font-medium">{selectedLoc.name}</span>
            </div>
          </div>

          {/* 3D Geospatial Component with Animated Water Edge across Terrain */}
          <GeospatialTerrainMap
            center={currentScene.center || [87.05, 26.65]}
            zoom={currentScene.zoom || 10.8}
            pitch={currentScene.pitch || 55}
            bearing={currentScene.bearing || -15}
            activeHorizon={horizon}
            showInundation={true}
            showForecast={showIsoContours}
            showGauges={showGauges}
            showInfrastructure={showInfrastructure}
            showShelters={showShelters}
            height="580px"
          />
        </div>

        {/* RIGHT COLUMN: GAUGE HYDROGRAPH & ADVISORY GENERATOR */}
        <div className="lg:col-span-5 xl:col-span-4 space-y-3.5">
          {/* Gauge Hydrograph Card */}
          <div className="p-4 sm:p-5 rounded-xl bg-zinc-950/80 border border-zinc-800/80 backdrop-blur-md shadow-sm space-y-3.5">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[10px] uppercase tracking-wider text-zinc-400 flex items-center gap-1.5 font-medium">
                  <Gauge className="w-3.5 h-3.5 text-cyan-400" />
                  GAUGE HYDROGRAPH COMPARISON
                </span>
                <h3 className="font-sans text-sm font-bold text-white tracking-normal uppercase mt-0.5">
                  {selectedGauge.name}
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <DataStatusBadge status={telemetryStatus} />
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium text-rose-400 bg-rose-950/40 border border-rose-800/50">
                  DANGER: {selectedGauge.dangerThreshold}M
                </span>
              </div>
            </div>

            {/* Gauge Metrics Grid */}
            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="p-3 bg-[#0a0a0a] border border-zinc-800/80 rounded-md space-y-1">
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 block">CURRENT STAGE</span>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-white">{selectedGauge.currentLevel}</span>
                  <span className="text-[10px] text-zinc-400">METERS</span>
                </div>
                <span className="text-[9px] text-rose-400 block font-medium">
                  +{(selectedGauge.currentLevel - selectedGauge.dangerThreshold).toFixed(2)}m OVER DANGER
                </span>
              </div>

              <div className="p-3 bg-[#0a0a0a] border border-zinc-800/80 rounded-md space-y-1">
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 block">CURRENT FLOW</span>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-white">{selectedGauge.flowRate.toLocaleString()}</span>
                  <span className="text-[10px] text-zinc-400">M³/S</span>
                </div>
                <span className="text-[9px] text-amber-400 block font-medium uppercase">
                  {selectedGauge.trend} TREND
                </span>
              </div>
            </div>

            {/* Stage Hydrograph Timeline */}
            <div className="space-y-1.5 pt-1">
              <span className="text-[10px] uppercase tracking-wider text-zinc-400 font-medium block">
                HYDROGRAPH TRAJECTORY (OBSERVED &amp; PREDICTED):
              </span>
              <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                {hydrographPoints.map((pt, idx) => (
                  <div
                    key={idx}
                    className={`p-2 rounded-md flex items-center justify-between text-xs font-mono border ${
                      pt.time === 'Now'
                        ? 'bg-cyan-950/30 border-cyan-800/60 text-cyan-300'
                        : pt.type === 'FORECAST'
                        ? 'bg-zinc-950 border-zinc-800/80 text-zinc-300'
                        : 'bg-[#0a0a0a] border-zinc-900 text-zinc-400'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-bold w-10">{pt.time}</span>
                      <span className="text-[10px] text-zinc-500">{pt.label}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span>{pt.level.toFixed(2)}m</span>
                      <span className="text-[10px] text-zinc-500">{pt.flow.toLocaleString()} m³/s</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Decision Support & Advisory Generator Card */}
          <div className="p-4 sm:p-5 rounded-xl bg-zinc-950/80 border border-zinc-800/80 backdrop-blur-md shadow-sm space-y-3.5">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[10px] uppercase tracking-wider text-zinc-400 flex items-center gap-1.5 font-medium">
                  <Activity className="w-3.5 h-3.5 text-cyan-400" />
                  INCIDENT IMPACT &amp; EVACUATION METRICS
                </span>
                <h3 className="font-sans text-sm font-bold text-white tracking-normal uppercase mt-0.5">
                  DECISION SUPPORT DESK
                </h3>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium text-amber-400 bg-amber-950/40 border border-amber-800/50">
                HORIZON: {horizon.toUpperCase()}
              </span>
            </div>

            {/* Impact Metric Chips */}
            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="p-3 bg-[#0a0a0a] border border-zinc-800/80 rounded-md space-y-1">
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 block">POPULATION AT RISK</span>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-white">{benchmarkForecast.populationAtRisk.toLocaleString()}</span>
                  <span className="text-[10px] text-zinc-400">CITIZENS</span>
                </div>
                <span className="text-[9px] text-zinc-500 block">CENSUS 2021 PROJECTION</span>
              </div>

              <div className="p-3 bg-[#0a0a0a] border border-zinc-800/80 rounded-md space-y-1">
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 block">REACH RISK LEVEL</span>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-bold text-amber-400">{activeThreatInfo.level}</span>
                </div>
                <span className="text-[9px] text-zinc-500 block uppercase">
                  {activeDataSource === 'backend' ? selectedLoc.name : 'PRIMARY REACH'}
                </span>
              </div>
            </div>

            {/* High-Risk Wards List */}
            <div className="space-y-1.5 pt-1">
              <span className="text-[10px] uppercase tracking-wider text-zinc-400 font-medium block">
                THREATENED WARDS &amp; REACHES:
              </span>
              <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                {benchmarkForecast.highRiskWards.map((ward, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 bg-[#0d1117] border border-zinc-800/80 rounded-md flex items-center justify-between text-xs font-mono"
                  >
                    <div>
                      <span className="font-semibold text-white block text-xs">
                        {ward.name}
                      </span>
                      <span className="text-[10px] text-zinc-400">
                        DEPTH: {ward.depthRange} · {ward.population.toLocaleString()} CITIZENS
                      </span>
                    </div>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                        ward.hazard === 'CRITICAL'
                          ? 'bg-rose-950/40 text-rose-400 border border-rose-800/50'
                          : 'bg-amber-950/40 text-amber-400 border border-amber-800/50'
                      }`}
                    >
                      {ward.hazard}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick Action: Draft Technical Advisory Button */}
            <div className="pt-2 border-t border-zinc-800">
              <InteractiveHoverButton
                text={`DRAFT TECHNICAL ADVISORY (${horizon.toUpperCase()})`}
                onClick={() => setShowAdvisoryModal(true)}
                className="w-full py-2.5 text-xs font-mono tracking-wider border-cyan-500/50 bg-cyan-950/40 text-cyan-200"
                dotColor="bg-cyan-500 group-hover:bg-cyan-500"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Structured Authority Advisory Modal */}
      {showAdvisoryModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-2xl rounded-lg bg-[#0d1117] border border-zinc-800 p-5 shadow-2xl space-y-4 font-mono text-white max-h-[90vh] flex flex-col">
            <div className="flex items-start justify-between pb-3 border-b border-zinc-800">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-md bg-zinc-900 border border-zinc-800 text-cyan-400">
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-sans text-sm font-bold text-white tracking-normal uppercase">
                    TECHNICAL SITUATION BULLETIN // DEOC SUNSARI &amp; MOHA
                  </h3>
                  <p className="text-[10px] text-zinc-400 uppercase">
                    DECISION-SUPPORT ADVISORY GENERATOR · {horizon.toUpperCase()} HORIZON · {selectedLoc.name}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowAdvisoryModal(false)}
                className="text-zinc-400 hover:text-white text-lg font-bold p-1 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Advisory Safety Warning Banner */}
            <div className="p-3 rounded-md bg-amber-950/40 border border-amber-700/60 text-xs font-mono text-amber-200 space-y-1">
              <div className="font-bold flex items-center gap-1.5 text-amber-300">
                <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                <span>INTERNAL DECISION SUPPORT DRAFT — NOT DISPATCHED / NOT A PUBLIC WARNING</span>
              </div>
              <p className="text-[11px] text-amber-200/90 leading-relaxed">
                This situation bulletin is an internal civil protection planning artifact for MoHA NEOC and DEOCs.
                It does <strong>not</strong> trigger public sirens, citizen SMS, or automated alerts. Public warning issuance
                requires two-stage review and approval inside the <em>Alert Dispatcher</em>.
              </p>
            </div>

            {/* Scrollable Bulletin Preview */}
            <div className="flex-1 overflow-y-auto space-y-3 text-xs pr-1">
              <div className="p-3 rounded-md bg-[#0a0a0a] border border-zinc-800/80 space-y-1">
                <span className="text-[10px] text-zinc-400 uppercase block font-bold">
                  Intended Civil Protection Authorities:
                </span>
                <p className="text-zinc-300 text-[11px]">
                  Ministry of Home Affairs (MoHA) NEOC · District Emergency Operation Centers (DEOCs Sunsari &amp; Saptari) · Armed Police Force (APF) Disaster Management
                </p>
              </div>

              <div className="p-3 rounded-md bg-[#0a0a0a] border border-zinc-800/80 space-y-1">
                <span className="text-[10px] text-zinc-400 uppercase block font-bold">
                  Target Location &amp; Model Metadata:
                </span>
                <p className="text-zinc-300 text-[11px]">
                  Location: <strong>{selectedLoc.name} ({selectedLocationId})</strong> · Model:{' '}
                  <strong>
                    {activeDataSource === 'backend' && forecastState.status === 'success' && forecastState.data
                      ? forecastState.data.model_version
                      : 'FloodLens-LSTM-GNN v1.2 (Benchmark Fixture)'}
                  </strong>{' '}
                  · Risk Level: <strong>{activeThreatInfo.level}</strong>
                </p>
              </div>

              <div className="p-3 rounded-md bg-[#0a0a0a] border border-zinc-800/80 space-y-1">
                <span className="text-[10px] text-zinc-400 uppercase block font-bold">
                  Predicted Crest &amp; Hydrograph Summary:
                </span>
                <p className="text-white text-[11px]">
                  Chatara Gauge: {selectedGauge.currentLevel}m (Danger: {selectedGauge.dangerThreshold}m) · Inflow: {benchmarkForecast.inflowCusecs.toLocaleString()} cusecs · Barrage: {benchmarkForecast.damGatesOpen} · Predicted Crest ETA: <strong>{benchmarkForecast.peakCrestEta}</strong>.
                </p>
              </div>

              <div className="p-3 rounded-md bg-[#0a0a0a] border border-zinc-800/80 space-y-1">
                <span className="text-[10px] text-rose-300 uppercase block font-bold">
                  At-Risk Road Cuts &amp; Embankment Scour Reaches:
                </span>
                <ul className="list-disc pl-4 space-y-0.5 text-zinc-300 text-[11px]">
                  <li>East-West Highway Ch. 42+200 - 45+800: Inundation depths up to 0.9m.</li>
                  <li>Chatara Main Canal Dyke Embankment: Headworks backflow scour alert.</li>
                  <li>Koshi Embankment Spur km 12+400: Overtopping alert under 420,000 cusec discharge.</li>
                </ul>
              </div>

              <div className="p-3 rounded-md bg-[#0a0a0a] border border-zinc-800/80 space-y-1">
                <span className="text-[10px] text-amber-300 uppercase block font-bold">
                  Recommended Evacuation &amp; Safety Perimeters:
                </span>
                <p className="text-zinc-300 text-[11px]">
                  Preposition relief teams along high-clearance routes to <strong>Inaruwa Safe Hub</strong> and <strong>BPKIHS Medical Camp</strong>. Evacuate low-lying residents in Prakashpur Wards 3 &amp; 4 and Gobargadha Island immediately.
                </p>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-between pt-3 border-t border-zinc-800 flex-wrap gap-2">
              <button
                type="button"
                onClick={handleExportBulletinJson}
                className="px-3.5 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-bold font-mono uppercase tracking-wider border border-zinc-700 transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>EXPORT BULLETIN JSON</span>
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowAdvisoryModal(false)}
                  className="px-3.5 py-1.5 rounded-md border border-zinc-800 hover:bg-zinc-800 text-xs text-zinc-300 transition-colors cursor-pointer"
                >
                  CANCEL
                </button>
                <InteractiveHoverButton
                  text="FORWARD TO ALERT DISPATCHER (DRAFT)"
                  onClick={handleProceedToDispatcher}
                  className="w-72 py-1.5 text-xs font-mono tracking-wider border-cyan-500/50 bg-cyan-950/40 text-cyan-200"
                  dotColor="bg-cyan-500 group-hover:bg-cyan-500"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Export Toast */}
      {advisoryExportToast && (
        <div className="fixed bottom-6 right-6 z-50 p-4 rounded-lg bg-[#071326] border border-emerald-400 text-white shadow-xl flex items-center gap-2 text-xs font-mono animate-in slide-in-from-bottom-2">
          <CheckCircle className="w-4 h-4 text-emerald-400" />
          <span>{advisoryExportToast}</span>
        </div>
      )}
    </div>
  );
};
