import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle,
  Clock,
  Download,
  FileText,
  Gauge,
  Layers,
  TrendingUp,
  Users,
  Waves,
  X
} from 'lucide-react';
import {
  HORIZON_FORECASTS,
  HYDROGRAPH_TIMELINE,
  KOSHI_TELEMETRY_GAUGES,
} from '../data/geospatialData';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';
import { DataStatusBadge } from './common/DataStatusBadge';
import { floodLensClient } from '../services/floodLensClient';
import type { GaugeStation } from '../types/apiContracts';
import { InteractiveHoverButton } from '@/components/ui/interactive-hover-button';
import type { BenchmarkScene } from '../types';

interface PredictionCentreProps {
  currentScene: BenchmarkScene;
  onNavigateToDispatcher?: (initialAlertPayload?: any) => void;
}

export const PredictionCentre: React.FC<PredictionCentreProps> = ({
  currentScene,
  onNavigateToDispatcher,
}) => {
  const [horizon, setHorizon] = useState<'Now' | '1h' | '3h' | '6h'>('3h');

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

  // Client API / Mock Adapter State
  const [apiStatus, setApiStatus] = useState<'live' | 'cached' | 'error'>('cached');

  // Gauge Telemetry Client State
  const [telemetryStatus, setTelemetryStatus] = useState<'live' | 'cached' | 'error'>('cached');
  const [telemetryGauges, setTelemetryGauges] = useState<GaugeStation[]>([]);

  useEffect(() => {
    let isMounted = true;
    const fetchPredictionLayer = async () => {
      const res = await floodLensClient.getPredictionLayer(currentScene.id, horizon);
      if (isMounted) {
        setApiStatus(res.status);
      }
    };
    fetchPredictionLayer();
    return () => {
      isMounted = false;
    };
  }, [currentScene.id, horizon]);

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
  const forecast = HORIZON_FORECASTS[forecastKey];

  // Selected gauge details (mapped from client or benchmark fallback)
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
    ? KOSHI_TELEMETRY_GAUGES[0] // Chatara
    : KOSHI_TELEMETRY_GAUGES[1]; // Koshi Barrage

  // Hydrograph data points customized per station with dynamic live telemetry injection
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

  // Technical situation bulletin payload for Ministry/DEOC
  const generateBulletinPayload = () => {
    return {
      bulletin_id: `ADV-KOSHI-2026-H${horizon.toUpperCase()}`,
      issued_at: new Date().toISOString(),
      issuing_body: 'FloodLens AI Decision-Support Intelligence / EOC Modeling Desk',
      intended_recipients: [
        'Ministry of Home Affairs (MoHA) - NEOC',
        'District Emergency Operation Center (DEOC) Sunsari',
        'District Emergency Operation Center (DEOC) Saptari',
        'Armed Police Force (APF) Disaster Management Division',
      ],
      forecast_horizon: horizon,
      model_metadata: {
        architecture: 'Physics-Informed LSTM-GNN v1.2',
        calibration_window: '2017–2024 Terai Monsoons (Koshi Reach)',
        validation_accuracy: 'DEM 1.5x Inundation Boundary Conformance',
      },
      basin_surge_parameters: {
        chatara_stage: '8.18m (Danger Threshold: 8.00m)',
        chatara_inflow_discharge: '13,240 m³/s (467,500 cusecs)',
        barrage_outflow_stage: '74.85m (Danger Threshold: 74.50m)',
        predicted_crest_arrival: forecast.peakCrestEta,
        sluice_status: forecast.damGatesOpen,
      },
      at_risk_infrastructure_segments: [
        'East-West Highway Ch. 42+200 - 45+800 (Overbank inundation expected)',
        'Chatara Main Canal Dyke Embankment (Scour alert at headworks)',
        'Koshi Spur km 12+400 (Severe hydraulic pressure on riprap revetment)',
      ],
      threatened_wards_census_exposure: forecast.highRiskWards.map((w) => ({
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
    };
  };

  const handleExportBulletinJson = () => {
    const data = generateBulletinPayload();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Situation_Bulletin_Koshi_${horizon}.json`;
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
        horizon: horizon,
        threatLevel: forecast.threatLevel,
        population: forecast.populationAtRisk,
        wards: forecast.highRiskWards.map((w) => w.name),
      });
    }
    setShowAdvisoryModal(false);
  };

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
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-zinc-900 border border-zinc-800 text-zinc-400">
                    DECISION SUPPORT ONLY
                  </span>
                  <DataStatusBadge status={apiStatus} />
                </h1>
                <p className="font-mono text-xs text-zinc-400 uppercase tracking-wider mt-0.5">
                  PHYSICS-INFORMED GRAPH NEURAL NETWORK // {currentScene.name} ({currentScene.district})
                </p>
              </div>
            </div>
          </div>

          {/* Interactive Time-Horizon Switcher: Segmented Control Bar */}
          <div className="inline-flex items-center p-1 bg-black/80 border border-zinc-800 rounded-lg gap-1 flex-wrap">
            <button
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
              onClick={() => setHorizon('1h')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-bold uppercase rounded-md transition-all cursor-pointer ${
                horizon === '1h'
                  ? 'bg-emerald-950/50 text-emerald-400 border border-emerald-800/60 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
              }`}
            >
              <Clock className="w-3 h-3 text-emerald-300" />
              <span>+1 HOUR</span>
              <span className="text-[9px] opacity-80">(MODERATE)</span>
            </button>

            <button
              onClick={() => setHorizon('3h')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-bold uppercase rounded-md transition-all cursor-pointer ${
                horizon === '3h'
                  ? 'bg-amber-950/50 text-amber-400 border border-amber-800/60 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
              }`}
            >
              <Clock className="w-3 h-3 text-amber-300" />
              <span>+3 HOURS</span>
              <span className="text-[9px] opacity-80">(HIGH)</span>
            </button>

            <button
              onClick={() => setHorizon('6h')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-bold uppercase rounded-md transition-all cursor-pointer ${
                horizon === '6h'
                  ? 'bg-rose-950/50 text-rose-400 border border-rose-800/60 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
              }`}
            >
              <AlertTriangle className="w-3 h-3 text-rose-300" />
              <span>+6 HOURS</span>
              <span className="text-[9px] opacity-80">(SEVERE)</span>
            </button>
          </div>
        </div>

        {/* Unified Metric Clusters (De-boxified into Clusters A & B with Hairline Dividers) */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4 pt-2">
          {/* Cluster A: Hydraulic Inflow & Sluice Operations */}
          <div className="rounded-xl bg-zinc-950/80 border border-zinc-800/80 backdrop-blur-md p-4 sm:p-5 flex flex-col justify-between space-y-3.5 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-sm uppercase tracking-wider text-zinc-200 font-semibold flex items-center gap-2">
                <Waves className="w-4 h-4 text-cyan-400" />
                HYDRAULIC INFLOW &amp; SLUICE OPS
              </span>
              <span className="text-xs font-mono text-zinc-400 uppercase tracking-wide font-medium">
                ARUN + TAMOR BASIN
              </span>
            </div>

            <div>
              <div className="text-3xl sm:text-4xl font-extrabold tracking-tight font-mono text-white flex items-baseline gap-2">
                <span>{forecast.inflowCusecs.toLocaleString()}</span>
                <span className="text-sm font-sans font-semibold text-cyan-400 uppercase">CUSECS</span>
              </div>
            </div>

            {/* Hairline Divider with Sluice & Outflow stats */}
            <div className="border-t border-zinc-800/80 pt-3 grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="space-y-1">
                <span className="text-xs uppercase tracking-wider text-zinc-400 font-semibold block">
                  BARRAGE SLUICE STATUS
                </span>
                <span className="text-sm sm:text-base font-bold text-zinc-200 font-mono block">
                  {forecast.damGatesOpen.toUpperCase()}
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
                  forecast.threatLevel === 'CRITICAL'
                    ? 'text-rose-400 bg-rose-950/40 border border-rose-800/50'
                    : 'text-amber-400 bg-amber-950/40 border border-amber-800/50'
                }`}
              >
                {forecast.threatLevel} RISK
              </span>
            </div>

            <div>
              <div className="text-3xl sm:text-4xl font-extrabold tracking-tight font-mono text-white">
                {forecast.peakCrestEta.toUpperCase()}
              </div>
            </div>

            {/* Hairline Divider with Spur Location, Flow Velocity & Hazard State */}
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
            <span className="text-zinc-200 font-medium">LSTM-GNN v1.2</span>
            <span className="text-zinc-700 select-none">·</span>
            <span className="text-zinc-400">CALIBRATION: 2017–2024 MONSOONS</span>
            <span className="text-zinc-700 select-none hidden sm:inline">·</span>
            <span className="text-zinc-400 hidden sm:inline">COUPLING: SAINT-VENANT 1D/2D</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
            <span className="text-zinc-300 font-medium">TELEMETRY UPLINK VALIDATED</span>
          </div>
        </div>
      </div>

      {/* 2. MAIN 2-COLUMN LAYOUT */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* LEFT COLUMN: 3D GEOSPATIAL MAP (7 cols on lg, 8 cols on xl) */}
        <div className="lg:col-span-7 xl:col-span-8 flex flex-col space-y-2">
          {/* Layer Toggles Bar: Unified Segmented Control */}
          <div className="p-2 sm:p-2.5 rounded-xl bg-zinc-950/80 border border-zinc-800/80 backdrop-blur-md flex flex-wrap items-center justify-between gap-2.5 text-xs">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-mono font-medium flex items-center gap-1.5 mr-1">
                <Layers className="w-3.5 h-3.5 text-zinc-400" />
                MAP LAYERS:
              </span>

              {/* Segmented Control Bar */}
              <div className="inline-flex items-center bg-black/80 backdrop-blur-md rounded-lg p-1 border border-zinc-800 gap-1 flex-wrap">
                <button
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
              <span className="text-zinc-500">CENTER:</span>
              <span className="text-zinc-200 font-medium">26.65°N, 87.05°E</span>
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

            {/* Station Selector: Chatara vs Koshi Barrage Segmented Control */}
            <div className="grid grid-cols-2 gap-1 p-1 bg-black/80 border border-zinc-800 rounded-lg text-xs font-mono">
              <button
                onClick={() => setActiveGaugeStation('chatara')}
                className={`py-1.5 px-2 rounded-md font-medium text-xs uppercase transition-colors cursor-pointer ${
                  activeGaugeStation === 'chatara'
                    ? 'bg-zinc-800 text-white font-semibold shadow-sm'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                Chatara Hydro (Inflow)
              </button>
              <button
                onClick={() => setActiveGaugeStation('barrage')}
                className={`py-1.5 px-2 rounded-md font-medium text-xs uppercase transition-colors cursor-pointer ${
                  activeGaugeStation === 'barrage'
                    ? 'bg-zinc-800 text-white font-semibold shadow-sm'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                Koshi Barrage (Border)
              </button>
            </div>

            {/* Visual Bar Chart / Timeline */}
            <div className="space-y-2 pt-1">
              <div className="flex items-center justify-between text-[10px] text-zinc-400 font-mono uppercase">
                <span>STAGE ELEVATION (M)</span>
                <span className="text-rose-400 font-semibold">
                  DANGER LEVEL: {selectedGauge.dangerThreshold.toFixed(2)}M
                </span>
              </div>

              {/* Chart Bars */}
              <div className="grid grid-cols-7 gap-1.5 items-end h-28 pt-2 pb-1 border-b border-zinc-800">
                {hydrographPoints.map((item, idx) => {
                  const isCurrent = item.type === 'CURRENT';
                  const isForecast = item.type === 'FORECAST';
                  const minBase = activeGaugeStation === 'chatara' ? 5 : 72;
                  const maxBase = activeGaugeStation === 'chatara' ? 9.5 : 76.5;
                  const heightPercent = Math.min(
                    100,
                    Math.max(20, ((item.level - minBase) / (maxBase - minBase)) * 100)
                  );

                  return (
                    <div key={idx} className="flex flex-col items-center gap-1 h-full justify-end">
                      <span className="text-[9px] font-mono text-white font-bold">
                        {item.level.toFixed(2)}
                      </span>
                      <div
                        className={`w-full rounded-xs transition-all ${
                          isCurrent
                            ? 'bg-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.4)]'
                            : isForecast
                            ? 'bg-rose-500/80 hover:bg-rose-500'
                            : 'bg-zinc-700 hover:bg-zinc-600'
                        }`}
                        style={{ height: `${heightPercent}%` }}
                      />
                      <span
                        className={`text-[9px] font-mono uppercase ${
                          isCurrent ? 'text-cyan-400 font-bold' : 'text-zinc-500'
                        }`}
                      >
                        {item.time}
                      </span>
                    </div>
                  );
                })}
              </div>

              <div className="flex items-center justify-between text-[10px] text-zinc-400 font-mono pt-1 uppercase">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-zinc-700 rounded-xs"></span> HISTORICAL
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-cyan-400 rounded-xs"></span> CURRENT
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-rose-500 rounded-xs"></span> PREDICTED CREST
                </span>
              </div>
            </div>
          </div>

          {/* Impact Estimation Matrix & Authority Advisory Generator */}
          <div className="p-4 sm:p-5 rounded-xl bg-zinc-950/80 border border-zinc-800/80 backdrop-blur-md shadow-sm space-y-3.5">
            <div className="flex items-center justify-between">
              <h3 className="font-sans text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5 text-zinc-400" />
                IMPACT MATRIX ({horizon.toUpperCase()})
              </h3>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium text-rose-400 bg-rose-950/40 border border-rose-800/50">
                {forecast.threatLevel}
              </span>
            </div>

            {/* Quick Metrics */}
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-3 bg-[#0d1117] border border-zinc-800 rounded-md">
                <span className="text-[10px] uppercase tracking-wider text-zinc-400 font-medium block">
                  POPULATION THREATENED
                </span>
                <span className="font-mono text-2xl font-bold text-white block mt-1 tracking-tight">
                  {forecast.populationAtRisk.toLocaleString()}
                </span>
                <span className="text-[10px] text-zinc-500 uppercase block mt-1">
                  SETTLEMENT EXPOSURE
                </span>
              </div>

              <div className="p-3 bg-[#0d1117] border border-zinc-800 rounded-md">
                <span className="text-[10px] uppercase tracking-wider text-zinc-400 font-medium block">
                  INUNDATION ENVELOPE
                </span>
                <span className="font-mono text-2xl font-bold text-white block mt-1 tracking-tight">
                  {forecast.inundationAreaKm2} <span className="font-sans text-xs font-normal text-zinc-400">KM²</span>
                </span>
                <span className="text-[10px] text-zinc-500 uppercase block mt-1">
                  SURFACE WATER SPREAD
                </span>
              </div>
            </div>

            {/* High-Risk Wards List */}
            <div className="space-y-1.5 pt-1">
              <span className="text-[10px] uppercase tracking-wider text-zinc-400 font-medium block">
                THREATENED WARDS &amp; REACHES:
              </span>
              <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                {forecast.highRiskWards.map((ward, idx) => (
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
                    STRUCTURED SITUATION ADVISORY GENERATOR · {horizon} HORIZON
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowAdvisoryModal(false)}
                className="text-zinc-400 hover:text-white text-lg font-bold p-1 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
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
                  Predicted Crest &amp; Hydrograph Summary:
                </span>
                <p className="text-white text-[11px]">
                  Chatara Gauge: 8.18m (Danger: 8.00m) · Inflow: {forecast.inflowCusecs.toLocaleString()} cusecs · Barrage: {forecast.damGatesOpen} · Predicted Crest ETA: <strong>{forecast.peakCrestEta}</strong>.
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
                onClick={handleExportBulletinJson}
                className="px-3.5 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-bold font-mono uppercase tracking-wider border border-zinc-700 transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>EXPORT BULLETIN JSON</span>
              </button>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowAdvisoryModal(false)}
                  className="px-3.5 py-1.5 rounded-md border border-zinc-800 hover:bg-zinc-800 text-xs text-zinc-300 transition-colors cursor-pointer"
                >
                  CANCEL
                </button>
                <InteractiveHoverButton
                  text="FORWARD TO DISPATCHER"
                  onClick={handleProceedToDispatcher}
                  className="w-56 py-1.5 text-xs font-mono tracking-wider border-cyan-500/50 bg-cyan-950/40 text-cyan-200"
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
