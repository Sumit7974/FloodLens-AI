import React, { useState } from 'react';
import {
  Circle,
  MapContainer,
  Marker,
  Polygon,
  Popup,
  TileLayer,
  Tooltip,
} from 'react-leaflet';
import L from 'leaflet';
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  CheckCircle,
  Clock,
  Gauge,
  Home,
  Layers,
  Radio,
  Send,
  ShieldAlert,
  TrendingUp,
  Users,
  Waves,
} from 'lucide-react';
import {
  HORIZON_FORECASTS,
  HYDROGRAPH_TIMELINE,
  KOSHI_INFRASTRUCTURE,
  KOSHI_SHELTERS,
  KOSHI_TELEMETRY_GAUGES,
} from '../data/geospatialData';
import type { BenchmarkScene } from '../types';

interface PredictionCentreProps {
  currentScene: BenchmarkScene;
  onNavigateToDispatcher?: (initialAlertPayload?: any) => void;
}

// Custom Leaflet DivIcon Generators to match EOC tactical design
const createGaugeIcon = (status: 'CRITICAL' | 'WARNING' | 'NORMAL') => {
  const bg =
    status === 'CRITICAL'
      ? 'bg-rose-500 border-rose-300 shadow-rose-500/50'
      : status === 'WARNING'
      ? 'bg-amber-500 border-amber-300 shadow-amber-500/50'
      : 'bg-emerald-500 border-emerald-300 shadow-emerald-500/50';

  return L.divIcon({
    className: 'custom-leaflet-marker',
    html: `
      <div class="relative flex items-center justify-center">
        <span class="animate-ping absolute inline-flex h-7 w-7 rounded-full ${bg} opacity-50"></span>
        <div class="relative w-6 h-6 rounded-full ${bg} border-2 flex items-center justify-center text-[9px] font-mono font-bold text-slate-950 shadow-lg">
          ▲
        </div>
      </div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12],
  });
};

const createShelterIcon = () => {
  return L.divIcon({
    className: 'custom-leaflet-shelter',
    html: `
      <div class="w-5 h-5 rounded-md bg-emerald-600 border border-emerald-300 flex items-center justify-center text-[10px] text-white shadow-md shadow-emerald-950">
        ⌂
      </div>
    `,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
};

const createInfraIcon = (risk: string) => {
  const color = risk === 'CRITICAL' ? 'bg-rose-600 text-rose-100' : 'bg-amber-600 text-amber-100';
  return L.divIcon({
    className: 'custom-leaflet-infra',
    html: `
      <div class="w-5 h-5 rounded bg-slate-900 border border-slate-700 flex items-center justify-center ${color} text-[10px] font-bold shadow">
        ⚡
      </div>
    `,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
};

export const PredictionCentre: React.FC<PredictionCentreProps> = ({
  currentScene,
  onNavigateToDispatcher,
}) => {
  const [horizon, setHorizon] = useState<'1h' | '3h' | '6h'>('3h');

  // Layer Toggles
  const [showIsoContours, setShowIsoContours] = useState(true);
  const [showInfrastructure, setShowInfrastructure] = useState(true);
  const [showShelters, setShowShelters] = useState(true);
  const [showGauges, setShowGauges] = useState(true);

  // Selected telemetry gauge for detailed inspection
  const [selectedGauge, setSelectedGauge] = useState(KOSHI_TELEMETRY_GAUGES[0]);

  // Advisory Generated Toast/Modal State
  const [advisoryGenerated, setAdvisoryGenerated] = useState(false);

  const forecast = HORIZON_FORECASTS[horizon];

  const handleGenerateAdvisory = () => {
    setAdvisoryGenerated(true);
    setTimeout(() => setAdvisoryGenerated(false), 4000);
    if (onNavigateToDispatcher) {
      onNavigateToDispatcher({
        horizon: horizon,
        threatLevel: forecast.threatLevel,
        population: forecast.populationAtRisk,
        wards: forecast.highRiskWards.map((w) => w.name),
      });
    }
  };

  return (
    <div className="space-y-4">
      {/* 1. TOP CONTROL BAR */}
      <div className="p-4 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] shadow-none space-y-3.5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <div className="p-1.5 border border-[#3a3a3f] bg-black text-white">
                <TrendingUp className="w-4 h-4 text-white" />
              </div>
              <div>
                <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
                  Prediction Centre — Multi-Horizon Hydrological Forecasting
                  <span className="badge-chip text-[9px] font-mono">
                    MODEL: FLOODLENS-LSTM-GNN V1.2
                  </span>
                </h1>
                <p className="font-mono text-[10px] text-[#5a5a5f] uppercase tracking-wider mt-0.5">
                  PHYSICS-INFORMED GRAPH NEURAL NETWORK // {currentScene.name} ({currentScene.district})
                </p>
              </div>
            </div>
          </div>

          {/* Interactive Time-Horizon Switcher: Ghost-outlined Pill Selectors */}
          <div className="flex items-center gap-1.5 p-1 bg-black border border-[#3a3a3f] rounded-full">
            <button
              onClick={() => setHorizon('1h')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-mono font-bold uppercase rounded-full transition-all ${
                horizon === '1h'
                  ? 'bg-white text-black'
                  : 'text-[#f0f0fa] hover:text-white'
              }`}
            >
              <Clock className="w-3 h-3" />
              <span>+1 HOUR</span>
              <span className="text-[9px] opacity-75">(MODERATE)</span>
            </button>

            <button
              onClick={() => setHorizon('3h')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-mono font-bold uppercase rounded-full transition-all ${
                horizon === '3h'
                  ? 'bg-white text-black'
                  : 'text-[#f0f0fa] hover:text-white'
              }`}
            >
              <Clock className="w-3 h-3" />
              <span>+3 HOURS</span>
              <span className="text-[9px] opacity-75">(HIGH)</span>
            </button>

            <button
              onClick={() => setHorizon('6h')}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-mono font-bold uppercase rounded-full transition-all ${
                horizon === '6h'
                  ? 'bg-white text-black'
                  : 'text-[#f0f0fa] hover:text-white'
              }`}
            >
              <AlertTriangle className="w-3 h-3" />
              <span>+6 HOURS</span>
              <span className="text-[9px] opacity-75">(SEVERE)</span>
            </button>
          </div>
        </div>

        {/* Hydraulic Indicators & Model Metadata Strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-3 border-t border-[#3a3a3f] text-xs font-mono">
          {/* Hydraulic Inflow Rate */}
          <div className="p-2.5 bg-black border border-[#3a3a3f] space-y-0.5">
            <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
              <Waves className="w-3 h-3 text-white" />
              PREDICTED INFLOW
            </span>
            <div className="font-bold text-sm text-white">
              {forecast.inflowCusecs.toLocaleString()} <span className="text-xs text-[#5a5a5f]">CUSECS</span>
            </div>
            <p className="text-[9px] text-[#5a5a5f] uppercase">ARUN + TAMOR BASIN</p>
          </div>

          {/* Dam Release Status */}
          <div className="p-2.5 bg-black border border-[#3a3a3f] space-y-0.5">
            <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
              <Activity className="w-3 h-3 text-white" />
              BARRAGE SLUICE STATUS
            </span>
            <div className="font-bold text-sm text-white">
              {forecast.damGatesOpen.toUpperCase()}
            </div>
            <p className="text-[9px] text-[#5a5a5f] uppercase">OUTFLOW: 94% CAPACITY</p>
          </div>

          {/* Crest Arrival ETA */}
          <div className="p-2.5 bg-black border border-[#3a3a3f] space-y-0.5">
            <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
              <Clock className="w-3 h-3 text-white" />
              PREDICTED CREST ETA
            </span>
            <div className="font-bold text-sm text-white">
              {forecast.peakCrestEta.toUpperCase()}
            </div>
            <p className="text-[9px] text-[#5a5a5f] uppercase">FLOW VELOCITY: 3.4 M/S</p>
          </div>

          {/* Model Confidence */}
          <div className="p-2.5 bg-black border border-[#3a3a3f] space-y-0.5">
            <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
              <BrainCircuit className="w-3 h-3 text-white" />
              CONFIDENCE INTERVAL
            </span>
            <div className="font-bold text-sm text-white">
              88.4% (TIER 1)
            </div>
            <p className="text-[9px] text-[#5a5a5f] uppercase">RUN: 18 OCT 04:30 UTC • 1.2S</p>
          </div>
        </div>
      </div>

      {/* 2. MAIN 2-COLUMN LAYOUT */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* LEFT COLUMN: INTERACTIVE LEAFLET MAP (7 cols on lg, 8 cols on xl) */}
        <div className="lg:col-span-7 xl:col-span-8 flex flex-col rounded-none bg-[#0a0a0a] border border-[#3a3a3f] overflow-hidden shadow-none">
          {/* Map Header & Layer Toggles Bar */}
          <div className="p-3 border-b border-[#3a3a3f] bg-[#000000] flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
                <Layers className="w-3.5 h-3.5 text-white" />
                MAP LAYERS:
              </span>

              {/* Iso-contours */}
              <button
                onClick={() => setShowIsoContours(!showIsoContours)}
                className={`badge-chip cursor-pointer transition-colors ${
                  showIsoContours
                    ? 'border-white text-white'
                    : 'border-[#3a3a3f] text-[#5a5a5f] hover:text-white'
                }`}
              >
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: forecast.color }}
                ></span>
                <span>ISO-CONTOURS ({horizon.toUpperCase()})</span>
              </button>

              {/* Gauges */}
              <button
                onClick={() => setShowGauges(!showGauges)}
                className={`badge-chip cursor-pointer transition-colors ${
                  showGauges
                    ? 'border-white text-white'
                    : 'border-[#3a3a3f] text-[#5a5a5f] hover:text-white'
                }`}
              >
                <Radio className="w-3 h-3" />
                <span>GAUGES</span>
              </button>

              {/* Infrastructure */}
              <button
                onClick={() => setShowInfrastructure(!showInfrastructure)}
                className={`badge-chip cursor-pointer transition-colors ${
                  showInfrastructure
                    ? 'border-white text-white'
                    : 'border-[#3a3a3f] text-[#5a5a5f] hover:text-white'
                }`}
              >
                <ShieldAlert className="w-3 h-3" />
                <span>INFRASTRUCTURE</span>
              </button>

              {/* Evacuation Shelters */}
              <button
                onClick={() => setShowShelters(!showShelters)}
                className={`badge-chip cursor-pointer transition-colors ${
                  showShelters
                    ? 'border-white text-white'
                    : 'border-[#3a3a3f] text-[#5a5a5f] hover:text-white'
                }`}
              >
                <Home className="w-3 h-3" />
                <span>SHELTERS</span>
              </button>
            </div>

            <div className="text-[11px] font-mono text-slate-400">
              Center: <span className="text-cyan-400 font-semibold">26.65°N, 87.15°E</span>
            </div>
          </div>

          {/* Leaflet Map Canvas */}
          <div className="relative w-full h-[520px] bg-[#070b14] z-0">
            <MapContainer
              center={[26.65, 87.15]}
              zoom={10}
              scrollWheelZoom={true}
              className="w-full h-full"
              style={{ background: '#090d16' }}
            >
              {/* High-Definition Dark Canvas Tile Layer (No watermark / No API key required) */}
              <TileLayer
                attribution='&copy; <a href="https://www.esri.com/">Esri</a>, DeLorme, NAVTEQ'
                url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
                maxZoom={16}
              />

              {/* Dynamic Inundation Polygon Layer */}
              {showIsoContours && (
                <>
                  <Polygon
                    positions={forecast.polygonCoords}
                    pathOptions={{
                      color: forecast.color,
                      fillColor: forecast.fillColor,
                      fillOpacity: horizon === '1h' ? 0.35 : horizon === '3h' ? 0.45 : 0.55,
                      weight: 2.5,
                      dashArray: '4 4',
                    }}
                  >
                    <Tooltip sticky>
                      <div className="p-1 font-sans">
                        <strong className="text-rose-400 block font-bold text-xs">
                          {forecast.label}
                        </strong>
                        <span className="text-[10px] text-slate-700 block">
                          Area: {forecast.inundationAreaKm2} km² • Risk: {forecast.severity}
                        </span>
                      </div>
                    </Tooltip>
                  </Polygon>

                  {/* Core River Channel Buffer */}
                  <Circle
                    center={[26.68, 87.08]}
                    radius={horizon === '1h' ? 3500 : horizon === '3h' ? 5500 : 7500}
                    pathOptions={{
                      color: forecast.color,
                      fillColor: forecast.fillColor,
                      fillOpacity: 0.15,
                      weight: 1,
                    }}
                  />
                </>
              )}

              {/* River Telemetry Gauges Markers */}
              {showGauges &&
                KOSHI_TELEMETRY_GAUGES.map((gauge) => {
                  const forecasted = gauge.forecastLevels[horizon];
                  const isCritical = forecasted >= gauge.dangerThreshold;

                  return (
                    <Marker
                      key={gauge.id}
                      position={gauge.coordinates}
                      icon={createGaugeIcon(isCritical ? 'CRITICAL' : 'WARNING')}
                      eventHandlers={{
                        click: () => setSelectedGauge(gauge),
                      }}
                    >
                      <Popup>
                        <div className="p-1 font-sans text-xs min-w-[190px]">
                          <div className="font-bold text-slate-900 flex items-center justify-between border-b pb-1 mb-1">
                            <span>{gauge.name}</span>
                            <span className="text-[9px] px-1 rounded bg-rose-100 text-rose-700 font-mono font-semibold">
                              {gauge.trend}
                            </span>
                          </div>
                          <div className="space-y-1 text-slate-700">
                            <div>River: <strong>{gauge.river}</strong></div>
                            <div>Current Level: <strong className="font-mono text-blue-700">{gauge.currentLevel}m</strong></div>
                            <div>
                              Forecasted ({horizon}):{' '}
                              <strong className={`font-mono ${isCritical ? 'text-rose-600' : 'text-amber-600'}`}>
                                {forecasted}m
                              </strong>
                            </div>
                            <div>Danger Threshold: <strong className="font-mono text-slate-900">{gauge.dangerThreshold}m</strong></div>
                            <div className="text-[10px] text-slate-500 pt-1">
                              Discharge: {gauge.flowRate.toLocaleString()} m³/s
                            </div>
                          </div>
                        </div>
                      </Popup>
                      <Tooltip permanent direction="top" offset={[0, -10]}>
                        <div className="text-[9px] font-mono font-bold text-slate-900">
                          {gauge.name.split(' ')[0]}: {forecasted}m
                        </div>
                      </Tooltip>
                    </Marker>
                  );
                })}

              {/* At-Risk Infrastructure Markers */}
              {showInfrastructure &&
                KOSHI_INFRASTRUCTURE.map((infra) => (
                  <Marker
                    key={infra.id}
                    position={infra.coordinates}
                    icon={createInfraIcon(infra.riskLevel)}
                  >
                    <Popup>
                      <div className="p-1 font-sans text-xs min-w-[180px]">
                        <span className="font-bold text-slate-900 block">{infra.name}</span>
                        <span className="text-[10px] font-semibold text-rose-700 uppercase block mb-1">
                          Risk: {infra.riskLevel}
                        </span>
                        <p className="text-[11px] text-slate-600">{infra.description}</p>
                      </div>
                    </Popup>
                  </Marker>
                ))}

              {/* Evacuation Shelters Markers */}
              {showShelters &&
                KOSHI_SHELTERS.map((shelter) => (
                  <Marker
                    key={shelter.id}
                    position={shelter.coordinates}
                    icon={createShelterIcon()}
                  >
                    <Popup>
                      <div className="p-1 font-sans text-xs min-w-[180px]">
                        <span className="font-bold text-emerald-800 block">{shelter.name}</span>
                        <div className="text-[10px] text-slate-600 mt-1 space-y-0.5">
                          <div>Capacity: <strong>{shelter.capacity}</strong> (Occupied: {shelter.currentOccupancy})</div>
                          <div>Elevation: <strong>{shelter.elevationMsl}m MSL</strong></div>
                          <div>Status: <strong className="text-emerald-700">{shelter.status}</strong></div>
                          <div>Helpline: <span className="font-mono">{shelter.contact}</span></div>
                        </div>
                      </div>
                    </Popup>
                  </Marker>
                ))}
            </MapContainer>

            {/* Tactical Legend Floating HUD */}
            <div className="absolute bottom-3 left-3 z-[1000] p-2.5 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] text-[10px] space-y-1.5 shadow-none">
              <span className="font-micro uppercase tracking-[0.96px] text-[#5a5a5f] block -mb-0.5">
                MAP SYMBOLOGY
              </span>
              <div className="flex items-center gap-2">
                <span
                  className="w-3 h-2 rounded-none"
                  style={{ backgroundColor: forecast.fillColor }}
                ></span>
                <span className="text-[#f0f0fa]">
                  {forecast.label} BOUNDARY ({forecast.inundationAreaKm2} KM²)
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping"></span>
                <span className="text-[#f0f0fa]">TELEMETRY STATION (SURGE CRIT)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-white text-black font-bold flex items-center justify-center text-[8px]">
                  ⌂
                </span>
                <span className="text-[#f0f0fa]">CIVIL EVACUATION SHELTER</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-black text-white border border-[#3a3a3f] flex items-center justify-center text-[8px]">
                  ⚡
                </span>
                <span className="text-[#f0f0fa]">CRITICAL INFRASTRUCTURE</span>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: PREDICTIVE ANALYTICS & GAUGE HYDROGRAPH (5 cols on lg, 4 cols on xl) */}
        <div className="lg:col-span-5 xl:col-span-4 space-y-3.5">
          {/* Gauge Hydrograph Card */}
          <div className="p-4 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] shadow-none space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <span className="font-micro text-[10px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
                  <Gauge className="w-3 h-3 text-white" />
                  HYDROGRAPH TREND
                </span>
                <h3 className="font-display text-xs font-bold text-white tracking-wider uppercase mt-0.5">
                  {selectedGauge.name}
                </h3>
              </div>
              <span className="badge-chip font-mono text-[9px]">
                DANGER: {selectedGauge.dangerThreshold}M
              </span>
            </div>

            {/* Visual Bar Chart / Timeline */}
            <div className="space-y-1.5 pt-1">
              <div className="flex items-center justify-between text-[10px] text-[#5a5a5f] font-mono uppercase">
                <span>TIMELINE HORIZON</span>
                <span className="text-white font-bold">DANGER THRESHOLD: 7.50M</span>
              </div>

              {/* Chart Bars */}
              <div className="grid grid-cols-7 gap-1.5 items-end h-28 pt-2 pb-1 border-b border-[#3a3a3f]">
                {HYDROGRAPH_TIMELINE.map((item, idx) => {
                  const isCurrent = item.type === 'CURRENT';
                  const isForecast = item.type === 'FORECAST';
                  const heightPercent = Math.min(100, Math.max(20, ((item.level - 5) / (9.2 - 5)) * 100));

                  return (
                    <div key={idx} className="flex flex-col items-center gap-1 h-full justify-end">
                      <span className="text-[9px] font-mono text-white font-bold">
                        {item.level.toFixed(2)}
                      </span>
                      <div
                        className={`w-full rounded-none transition-all ${
                          isCurrent
                            ? 'bg-white'
                            : isForecast
                            ? 'bg-rose-500/80 hover:bg-rose-500'
                            : 'bg-[#3a3a3f] hover:bg-[#5a5a5f]'
                        }`}
                        style={{ height: `${heightPercent}%` }}
                      />
                      <span
                        className={`text-[9px] font-mono uppercase ${
                          isCurrent ? 'text-white font-bold' : 'text-[#5a5a5f]'
                        }`}
                      >
                        {item.time}
                      </span>
                    </div>
                  );
                })}
              </div>

              <div className="flex items-center justify-between text-[10px] text-[#5a5a5f] font-mono pt-1 uppercase">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-[#3a3a3f]"></span> HISTORICAL
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-white"></span> CURRENT
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-rose-500"></span> CREST
                </span>
              </div>
            </div>
          </div>

          {/* Impact Estimation Matrix */}
          <div className="p-4 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] shadow-none space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5 text-white" />
                IMPACT MATRIX ({horizon.toUpperCase()})
              </h3>
              <span className="badge-chip border-rose-600 text-rose-300 text-[10px] font-mono">
                {forecast.threatLevel}
              </span>
            </div>

            {/* Quick Metrics */}
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-2.5 bg-black border border-[#3a3a3f]">
                <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] block">
                  POPULATION THREATENED
                </span>
                <span className="font-display text-xl font-bold text-white block mt-0.5">
                  {forecast.populationAtRisk.toLocaleString()}
                </span>
                <span className="text-[9px] text-[#5a5a5f] uppercase block mt-0.5">
                  HIGH-VULNERABILITY REACHES
                </span>
              </div>

              <div className="p-2.5 bg-black border border-[#3a3a3f]">
                <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] block">
                  INUNDATION ENVELOPE
                </span>
                <span className="font-display text-xl font-bold text-white block mt-0.5">
                  {forecast.inundationAreaKm2} <span className="font-mono text-xs font-normal text-[#5a5a5f]">KM²</span>
                </span>
                <span className="text-[9px] text-[#5a5a5f] uppercase block mt-0.5">
                  SURFACE WATER EXPANSION
                </span>
              </div>
            </div>

            {/* High-Risk Wards List */}
            <div className="space-y-1.5 pt-1">
              <span className="font-micro text-[10px] uppercase tracking-[0.96px] text-[#5a5a5f] block">
                THREATENED WARDS &amp; REACHES:
              </span>
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {forecast.highRiskWards.map((ward, idx) => (
                  <div
                    key={idx}
                    className="p-2 bg-black border border-[#3a3a3f] flex items-center justify-between text-xs font-mono"
                  >
                    <div>
                      <span className="font-bold text-white block text-[11px] uppercase">
                        {ward.name}
                      </span>
                      <span className="text-[10px] text-[#5a5a5f]">
                        DEPTH: {ward.depthRange} // {ward.population.toLocaleString()} CITIZENS
                      </span>
                    </div>
                    <span
                      className={`badge-chip text-[9px] !py-0.5 !px-1.5 ${
                        ward.hazard === 'CRITICAL'
                          ? 'border-rose-600 text-rose-300'
                          : 'border-amber-600 text-amber-300'
                      }`}
                    >
                      {ward.hazard}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick Action: Generate Geofenced Advisory Button - Signature Ghost Pill */}
            <div className="pt-2 border-t border-[#3a3a3f]">
              <button
                onClick={handleGenerateAdvisory}
                className="btn-ghost-pill w-full text-center justify-center !py-2.5 !text-xs"
              >
                <Send className="w-3.5 h-3.5" />
                <span>GENERATE GEOFENCED ADVISORY ({horizon.toUpperCase()})</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Advisory Confirmation Notification */}
      {advisoryGenerated && (
        <div className="fixed bottom-6 right-6 z-50 p-4 rounded-none bg-[#0a0a0a] border border-white text-white shadow-none animate-in slide-in-from-bottom-4 flex items-start gap-3 max-w-md">
          <CheckCircle className="w-5 h-5 text-white flex-shrink-0 mt-0.5" />
          <div className="text-xs font-mono">
            <h4 className="font-bold text-white uppercase">ADVISORY DRAFT CREATED</h4>
            <p className="text-[#f0f0fa] mt-1 text-[11px]">
              Draft broadcast populated for <strong>{forecast.populationAtRisk.toLocaleString()} citizens</strong> across{' '}
              {forecast.highRiskWards.length} wards. Ready for officer signoff in Alert Dispatcher.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
