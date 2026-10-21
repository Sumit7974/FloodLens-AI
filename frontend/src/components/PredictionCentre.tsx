import React, { useState, useEffect } from 'react';
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  CheckCircle,
  Clock,
  Download,
  FileText,
  Gauge,
  Layers,
  Send,
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
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3.5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <div className="p-2 rounded bg-amber-500/20 border border-amber-500/40 text-amber-400">
                <TrendingUp className="w-4 h-4 text-amber-400" />
              </div>
              <div>
                <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
                  Prediction Centre — Multi-Horizon Hydrological Forecasting
                  <span className="px-2 py-0.5 rounded-full bg-[#38bdf8]/15 border border-[#38bdf8]/40 text-[#38bdf8] text-[9px] font-mono font-bold tracking-wider">
                    DECISION SUPPORT ONLY
                  </span>
                  <DataStatusBadge status={apiStatus} />
                </h1>
                <p className="font-mono text-[10px] text-[#38bdf8] uppercase tracking-wider mt-0.5 font-semibold">
                  PHYSICS-INFORMED GRAPH NEURAL NETWORK // {currentScene.name} ({currentScene.district})
                </p>
              </div>
            </div>
          </div>

          {/* Interactive Time-Horizon Switcher: Now, +1h, +3h, +6h */}
          <div className="flex items-center gap-1.5 p-1 bg-[#060e1d] border border-[#1e3a5f] rounded-full flex-wrap">
            <button
              onClick={() => setHorizon('Now')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-mono font-bold uppercase rounded-full transition-all cursor-pointer ${
                horizon === 'Now'
                  ? 'bg-gradient-to-r from-sky-600 to-cyan-600 text-white shadow-[0_0_10px_rgba(14,165,233,0.4)]'
                  : 'text-[#94a3b8] hover:text-white'
              }`}
            >
              <Clock className="w-3 h-3 text-cyan-300" />
              <span>NOW</span>
              <span className="text-[9px] opacity-80">(OBSERVED)</span>
            </button>

            <button
              onClick={() => setHorizon('1h')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-mono font-bold uppercase rounded-full transition-all cursor-pointer ${
                horizon === '1h'
                  ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-[0_0_10px_rgba(16,185,129,0.4)]'
                  : 'text-[#94a3b8] hover:text-white'
              }`}
            >
              <Clock className="w-3 h-3 text-emerald-300" />
              <span>+1 HOUR</span>
              <span className="text-[9px] opacity-80">(MODERATE)</span>
            </button>

            <button
              onClick={() => setHorizon('3h')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-mono font-bold uppercase rounded-full transition-all cursor-pointer ${
                horizon === '3h'
                  ? 'bg-gradient-to-r from-[#e86e25] to-[#f97316] text-white shadow-[0_0_10px_rgba(232,110,37,0.4)]'
                  : 'text-[#94a3b8] hover:text-white'
              }`}
            >
              <Clock className="w-3 h-3 text-[#fed7aa]" />
              <span>+3 HOURS</span>
              <span className="text-[9px] opacity-80">(HIGH)</span>
            </button>

            <button
              onClick={() => setHorizon('6h')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-mono font-bold uppercase rounded-full transition-all cursor-pointer ${
                horizon === '6h'
                  ? 'bg-gradient-to-r from-rose-600 to-red-600 text-white shadow-[0_0_10px_rgba(244,63,94,0.4)]'
                  : 'text-[#94a3b8] hover:text-white'
              }`}
            >
              <AlertTriangle className="w-3 h-3 text-rose-300" />
              <span>+6 HOURS</span>
              <span className="text-[9px] opacity-80">(SEVERE)</span>
            </button>
          </div>
        </div>

        {/* Hydraulic Indicators & Model Metadata Strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-3 border-t border-[#1e3a5f]/80 text-xs font-mono">
          {/* Hydraulic Inflow Rate */}
          <div className="p-2.5 rounded bg-[#0c1d38]/75 border border-[#0ea5e9]/40 space-y-0.5">
            <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#38bdf8] font-bold flex items-center gap-1">
              <Waves className="w-3 h-3 text-[#38bdf8]" />
              PREDICTED INFLOW
            </span>
            <div className="font-bold text-sm text-white">
              {forecast.inflowCusecs.toLocaleString()} <span className="text-xs text-[#38bdf8]">CUSECS</span>
            </div>
            <p className="text-[9px] text-[#94a3b8] uppercase">ARUN + TAMOR BASIN</p>
          </div>

          {/* Dam Release Status */}
          <div className="p-2.5 rounded bg-[#0c1d38]/75 border border-[#e86e25]/40 space-y-0.5">
            <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#fb923c] font-bold flex items-center gap-1">
              <Activity className="w-3 h-3 text-[#e86e25]" />
              BARRAGE SLUICE STATUS
            </span>
            <div className="font-bold text-sm text-[#fed7aa]">
              {forecast.damGatesOpen.toUpperCase()}
            </div>
            <p className="text-[9px] text-[#94a3b8] uppercase">OUTFLOW: 94% CAPACITY</p>
          </div>

          {/* Crest Arrival ETA */}
          <div className="p-2.5 rounded bg-[#0c1d38]/75 border border-[#f59e0b]/40 space-y-0.5">
            <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#fbbf24] font-bold flex items-center gap-1">
              <Clock className="w-3 h-3 text-[#f59e0b]" />
              PREDICTED CREST ETA
            </span>
            <div className="font-bold text-sm text-white">
              {forecast.peakCrestEta.toUpperCase()}
            </div>
            <p className="text-[9px] text-[#94a3b8] uppercase">FLOW VELOCITY: 3.4 M/S</p>
          </div>

          {/* Model Specification */}
          <div className="p-2.5 rounded bg-[#0c1d38]/75 border border-[#10b981]/40 space-y-0.5">
            <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#34d399] font-bold flex items-center gap-1">
              <BrainCircuit className="w-3 h-3 text-[#10b981]" />
              MODEL PROVENANCE
            </span>
            <div className="font-bold text-xs text-[#a7f3d0]">
              LSTM-GNN v1.2 (2017–2024 MONSOONS)
            </div>
            <p className="text-[9px] text-[#94a3b8] uppercase">SAMPLE DEMO TELEMETRY // VALIDATED</p>
          </div>
        </div>
      </div>

      {/* 2. MAIN 2-COLUMN LAYOUT */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* LEFT COLUMN: 3D GEOSPATIAL MAP (7 cols on lg, 8 cols on xl) */}
        <div className="lg:col-span-7 xl:col-span-8 flex flex-col space-y-2">
          {/* Layer Toggles Bar */}
          <div className="p-3 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
                <Layers className="w-3.5 h-3.5 text-white" />
                MAP LAYERS:
              </span>

              {/* Iso-contours */}
              <button
                onClick={() => setShowIsoContours(!showIsoContours)}
                className={`px-2.5 py-1 rounded-full text-[11px] font-mono font-bold uppercase transition-colors cursor-pointer border ${
                  showIsoContours
                    ? 'bg-sky-500/20 border-sky-400 text-sky-200'
                    : 'bg-black/40 border-[#1e3a5f] text-slate-400 hover:text-white'
                }`}
              >
                <span>FLOOD HORIZON ({horizon.toUpperCase()})</span>
              </button>

              {/* Gauges */}
              <button
                onClick={() => setShowGauges(!showGauges)}
                className={`px-2.5 py-1 rounded-full text-[11px] font-mono font-bold uppercase transition-colors cursor-pointer border ${
                  showGauges
                    ? 'bg-emerald-500/20 border-emerald-400 text-emerald-200'
                    : 'bg-black/40 border-[#1e3a5f] text-slate-400 hover:text-white'
                }`}
              >
                <span>GAUGES</span>
              </button>

              {/* Infrastructure */}
              <button
                onClick={() => setShowInfrastructure(!showInfrastructure)}
                className={`px-2.5 py-1 rounded-full text-[11px] font-mono font-bold uppercase transition-colors cursor-pointer border ${
                  showInfrastructure
                    ? 'bg-rose-500/20 border-rose-400 text-rose-200'
                    : 'bg-black/40 border-[#1e3a5f] text-slate-400 hover:text-white'
                }`}
              >
                <span>ROAD CUTS / DYKES</span>
              </button>

              {/* Shelters */}
              <button
                onClick={() => setShowShelters(!showShelters)}
                className={`px-2.5 py-1 rounded-full text-[11px] font-mono font-bold uppercase transition-colors cursor-pointer border ${
                  showShelters
                    ? 'bg-purple-500/20 border-purple-400 text-purple-200'
                    : 'bg-black/40 border-[#1e3a5f] text-slate-400 hover:text-white'
                }`}
              >
                <span>HIGH GROUND REFUGES</span>
              </button>
            </div>

            <div className="text-[11px] font-mono text-slate-400">
              Center: <span className="text-cyan-400 font-semibold">26.65°N, 87.05°E</span>
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
          <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <span className="font-micro text-[10px] uppercase tracking-[0.96px] text-[#38bdf8] flex items-center gap-1 font-bold">
                  <Gauge className="w-3.5 h-3.5 text-[#38bdf8]" />
                  GAUGE HYDROGRAPH COMPARISON
                </span>
                <h3 className="font-display text-sm font-bold text-white tracking-wider uppercase mt-0.5">
                  {selectedGauge.name}
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <DataStatusBadge status={telemetryStatus} />
                <span className="px-2 py-0.5 rounded-full bg-rose-500/20 border border-rose-500/50 text-rose-300 font-mono text-[9px] font-bold">
                  DANGER: {selectedGauge.dangerThreshold}M
                </span>
              </div>
            </div>

            {/* Station Selector: Chatara vs Koshi Barrage */}
            <div className="grid grid-cols-2 gap-1.5 p-1 bg-black/60 border border-[#1e3a5f] rounded-lg text-xs font-mono">
              <button
                onClick={() => setActiveGaugeStation('chatara')}
                className={`py-1 px-2 rounded font-bold text-[11px] uppercase transition-colors cursor-pointer ${
                  activeGaugeStation === 'chatara'
                    ? 'bg-sky-600 text-white'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Chatara Hydro (Inflow)
              </button>
              <button
                onClick={() => setActiveGaugeStation('barrage')}
                className={`py-1 px-2 rounded font-bold text-[11px] uppercase transition-colors cursor-pointer ${
                  activeGaugeStation === 'barrage'
                    ? 'bg-sky-600 text-white'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Koshi Barrage (Border)
              </button>
            </div>

            {/* Visual Bar Chart / Timeline */}
            <div className="space-y-1.5 pt-1">
              <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono uppercase">
                <span>STAGE ELEVATION (M)</span>
                <span className="text-rose-400 font-bold">
                  DANGER LEVEL: {selectedGauge.dangerThreshold.toFixed(2)}M
                </span>
              </div>

              {/* Chart Bars */}
              <div className="grid grid-cols-7 gap-1.5 items-end h-28 pt-2 pb-1 border-b border-[#1e3a5f]">
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
                            ? 'bg-cyan-400 shadow-[0_0_8px_#38bdf8]'
                            : isForecast
                            ? 'bg-rose-500/80 hover:bg-rose-500'
                            : 'bg-[#1e3a5f] hover:bg-[#2b5286]'
                        }`}
                        style={{ height: `${heightPercent}%` }}
                      />
                      <span
                        className={`text-[9px] font-mono uppercase ${
                          isCurrent ? 'text-cyan-400 font-bold' : 'text-slate-400'
                        }`}
                      >
                        {item.time}
                      </span>
                    </div>
                  );
                })}
              </div>

              <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono pt-1 uppercase">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-[#1e3a5f] rounded-xs"></span> HISTORICAL
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
          <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5 text-white" />
                IMPACT MATRIX ({horizon.toUpperCase()})
              </h3>
              <span className="px-2 py-0.5 rounded-full bg-rose-500/20 border border-rose-500/50 text-rose-300 text-[10px] font-mono font-bold">
                {forecast.threatLevel}
              </span>
            </div>

            {/* Quick Metrics */}
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-2.5 bg-black/60 border border-[#1e3a5f] rounded">
                <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-slate-400 block">
                  POPULATION THREATENED
                </span>
                <span className="font-display text-xl font-bold text-white block mt-0.5">
                  {forecast.populationAtRisk.toLocaleString()}
                </span>
                <span className="text-[9px] text-[#38bdf8] uppercase block mt-0.5 font-semibold">
                  HIGH-VULNERABILITY REACHES
                </span>
              </div>

              <div className="p-2.5 bg-black/60 border border-[#1e3a5f] rounded">
                <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-slate-400 block">
                  INUNDATION ENVELOPE
                </span>
                <span className="font-display text-xl font-bold text-white block mt-0.5">
                  {forecast.inundationAreaKm2} <span className="font-mono text-xs font-normal text-slate-400">KM²</span>
                </span>
                <span className="text-[9px] text-[#38bdf8] uppercase block mt-0.5 font-semibold">
                  SURFACE WATER EXPANSION
                </span>
              </div>
            </div>

            {/* High-Risk Wards List */}
            <div className="space-y-1.5 pt-1">
              <span className="font-micro text-[10px] uppercase tracking-[0.96px] text-slate-400 block">
                THREATENED WARDS &amp; REACHES:
              </span>
              <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                {forecast.highRiskWards.map((ward, idx) => (
                  <div
                    key={idx}
                    className="p-2 bg-black/60 border border-[#1e3a5f]/70 rounded flex items-center justify-between text-xs font-mono"
                  >
                    <div>
                      <span className="font-bold text-white block text-[11px] uppercase">
                        {ward.name}
                      </span>
                      <span className="text-[10px] text-slate-400">
                        DEPTH: {ward.depthRange} // {ward.population.toLocaleString()} CITIZENS
                      </span>
                    </div>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                        ward.hazard === 'CRITICAL'
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/50'
                          : 'bg-amber-500/20 text-amber-300 border border-amber-500/50'
                      }`}
                    >
                      {ward.hazard}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick Action: Draft Technical Advisory Button */}
            <div className="pt-2 border-t border-[#1e3a5f]">
              <button
                onClick={() => setShowAdvisoryModal(true)}
                className="w-full py-2.5 px-4 rounded-full bg-gradient-to-r from-sky-600 via-blue-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 text-white font-mono font-bold text-xs uppercase tracking-wider border border-sky-400/60 shadow-[0_0_15px_rgba(56,189,248,0.35)] hover:scale-[1.01] transition-all cursor-pointer flex items-center justify-center gap-2"
              >
                <FileText className="w-3.5 h-3.5" />
                <span>DRAFT TECHNICAL ADVISORY ({horizon.toUpperCase()})</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Structured Authority Advisory Modal */}
      {showAdvisoryModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-2xl rounded-lg bg-[#071326] border border-[#1e3a5f] p-5 shadow-[0_12px_48px_rgba(0,0,0,0.85)] space-y-4 font-mono text-white max-h-[90vh] flex flex-col">
            <div className="flex items-start justify-between pb-3 border-b border-[#1e3a5f]">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded bg-sky-500/20 border border-sky-500/40 text-sky-400">
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-display text-sm font-bold text-white tracking-wider uppercase">
                    TECHNICAL SITUATION BULLETIN // DEOC SUNSARI &amp; MOHA
                  </h3>
                  <p className="text-[10px] text-[#38bdf8] uppercase">
                    STRUCTURED SITUATION ADVISORY GENERATOR &bull; {horizon} HORIZON
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowAdvisoryModal(false)}
                className="text-slate-400 hover:text-white text-lg font-bold p-1 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Scrollable Bulletin Preview */}
            <div className="flex-1 overflow-y-auto space-y-3 text-xs pr-1">
              <div className="p-3 rounded bg-black/60 border border-[#1e3a5f]/80 space-y-1">
                <span className="text-[10px] text-slate-400 uppercase block font-bold">
                  Intended Civil Protection Authorities:
                </span>
                <p className="text-slate-300 text-[11px]">
                  Ministry of Home Affairs (MoHA) NEOC &bull; District Emergency Operation Centers (DEOCs Sunsari &amp; Saptari) &bull; Armed Police Force (APF) Disaster Management
                </p>
              </div>

              <div className="p-3 rounded bg-black/60 border border-[#1e3a5f]/80 space-y-1">
                <span className="text-[10px] text-slate-400 uppercase block font-bold">
                  Predicted Crest &amp; Hydrograph Summary:
                </span>
                <p className="text-white text-[11px]">
                  Chatara Gauge: 8.18m (Danger: 8.00m) &bull; Inflow: {forecast.inflowCusecs.toLocaleString()} cusecs &bull; Barrage: {forecast.damGatesOpen} &bull; Predicted Crest ETA: <strong>{forecast.peakCrestEta}</strong>.
                </p>
              </div>

              <div className="p-3 rounded bg-black/60 border border-[#1e3a5f]/80 space-y-1">
                <span className="text-[10px] text-rose-300 uppercase block font-bold">
                  At-Risk Road Cuts &amp; Embankment Scour Reaches:
                </span>
                <ul className="list-disc pl-4 space-y-0.5 text-slate-300 text-[11px]">
                  <li>East-West Highway Ch. 42+200 - 45+800: Inundation depths up to 0.9m.</li>
                  <li>Chatara Main Canal Dyke Embankment: Headworks backflow scour alert.</li>
                  <li>Koshi Embankment Spur km 12+400: Overtopping alert under 420,000 cusec discharge.</li>
                </ul>
              </div>

              <div className="p-3 rounded bg-black/60 border border-[#1e3a5f]/80 space-y-1">
                <span className="text-[10px] text-amber-300 uppercase block font-bold">
                  Recommended Evacuation &amp; Safety Perimeters:
                </span>
                <p className="text-slate-300 text-[11px]">
                  Preposition relief teams along high-clearance routes to <strong>Inaruwa Safe Hub</strong> and <strong>BPKIHS Medical Camp</strong>. Evacuate low-lying residents in Prakashpur Wards 3 &amp; 4 and Gobargadha Island immediately.
                </p>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-between pt-3 border-t border-[#1e3a5f] flex-wrap gap-2">
              <button
                onClick={handleExportBulletinJson}
                className="px-3.5 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold font-mono uppercase tracking-wider border border-slate-600 transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>EXPORT BULLETIN JSON</span>
              </button>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowAdvisoryModal(false)}
                  className="px-3 py-1.5 rounded-full border border-[#1e3a5f] hover:bg-white/10 text-xs text-slate-300 transition-colors cursor-pointer"
                >
                  CANCEL
                </button>
                <button
                  onClick={handleProceedToDispatcher}
                  className="px-4 py-1.5 rounded-full bg-gradient-to-r from-sky-600 to-blue-600 hover:from-sky-500 hover:to-blue-500 text-white text-xs font-bold tracking-wider uppercase border border-sky-400 transition-all cursor-pointer flex items-center gap-1.5"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>FORWARD TO ALERT DISPATCHER</span>
                </button>
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
