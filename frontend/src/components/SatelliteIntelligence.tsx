import React, { useState } from 'react';
import {
  BrainCircuit,
  CheckCircle,
  Cloud,
  Download,
  Eye,
  Layers,
  Radio,
  Satellite,
  Send,
  Split,
} from 'lucide-react';
import { SATELLITE_COMPARISON_DATA } from '../data/geospatialData';
import type { BenchmarkScene } from '../types';

interface SatelliteIntelligenceProps {
  currentScene: BenchmarkScene;
  onSendToResponseOps?: () => void;
}

export const SatelliteIntelligence: React.FC<SatelliteIntelligenceProps> = ({
  currentScene,
  onSendToResponseOps,
}) => {
  // Scene modality toggle: Optical vs SAR
  const [modality, setModality] = useState<'optical' | 'sar'>('optical');

  // Comparison view mode: Split Slider vs Side-by-Side Dual View
  const [viewMode, setViewMode] = useState<'split-slider' | 'side-by-side'>('split-slider');

  // Slider position (0 to 100 percent)
  const [sliderPos, setSliderPos] = useState(52);

  // Status message state
  const [notification, setNotification] = useState<string | null>(null);

  const sceneConfig = SATELLITE_COMPARISON_DATA.scenes[modality];
  const stats = SATELLITE_COMPARISON_DATA.statistics;

  const handleDownloadGeoJSON = () => {
    // Generate mock GeoJSON blob
    const mockGeoJSON = {
      type: 'FeatureCollection',
      event: currentScene.name,
      modality: sceneConfig.title,
      detectionDate: '2026-10-18T04:42:00Z',
      statistics: stats,
      features: [
        {
          type: 'Feature',
          properties: { classification: 'NEWLY_FLOODED', areaKm2: 64.2, depth_est: '1.2m' },
          geometry: {
            type: 'Polygon',
            coordinates: [
              [
                [87.15, 26.85],
                [87.2, 26.83],
                [87.17, 26.77],
                [87.14, 26.71],
                [87.09, 26.64],
                [87.04, 26.57],
                [86.97, 26.5],
                [86.91, 26.47],
                [86.87, 26.52],
                [87.15, 26.85],
              ],
            ],
          },
        },
      ],
    };

    const blob = new Blob([JSON.stringify(mockGeoJSON, null, 2)], {
      type: 'application/geo+json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `FloodLens_${modality.toUpperCase()}_FloodMask_Koshi.geojson`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    setNotification('GeoJSON Inundation Mask exported successfully (EPSG:4326)');
    setTimeout(() => setNotification(null), 3500);
  };

  const handleSendToOps = () => {
    setNotification('Satellite Inundation Mask dispatched to Response Operations & Citizen Routing');
    setTimeout(() => setNotification(null), 3500);
    if (onSendToResponseOps) {
      onSendToResponseOps();
    }
  };

  return (
    <div className="space-y-3.5">
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3.5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 flex-wrap">
            <div className="p-2 rounded bg-purple-500/20 border border-purple-500/40 text-purple-400">
              <Satellite className="w-4 h-4 text-purple-400" />
            </div>
            <div>
              <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
                Earth Observation &amp; Satellite Flood Intelligence
                <span className="px-2 py-0.5 rounded-full bg-purple-500/15 border border-purple-500/40 text-purple-300 text-[9px] font-mono font-bold tracking-wider">
                  AUTOMATED WATER EXTRACTION
                </span>
              </h1>
              <p className="font-mono text-[10px] text-[#38bdf8] uppercase tracking-wider mt-0.5 font-semibold">
                COPERNICUS SENTINEL CONSTELLATION // MNDWI &amp; SAR BACKSCATTER // {currentScene.name}
              </p>
            </div>
          </div>

          {/* Scene Modality Selector: Colored Pill Style */}
          <div className="flex items-center gap-1.5 p-1 bg-[#060e1d] border border-[#1e3a5f] rounded-full text-xs">
            <button
              onClick={() => setModality('optical')}
              className={`flex items-center gap-1.5 px-3 py-1 font-mono font-bold uppercase rounded-full transition-all cursor-pointer ${
                modality === 'optical'
                  ? 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-[0_0_10px_rgba(168,85,247,0.4)]'
                  : 'text-[#94a3b8] hover:text-white'
              }`}
            >
              <Eye className="w-3.5 h-3.5 text-purple-300" />
              <span>SENTINEL-2 OPTICAL (NDWI)</span>
            </button>

            <button
              onClick={() => setModality('sar')}
              className={`flex items-center gap-1.5 px-3 py-1 font-mono font-bold uppercase rounded-full transition-all cursor-pointer ${
                modality === 'sar'
                  ? 'bg-gradient-to-r from-sky-600 to-blue-600 text-white shadow-[0_0_10px_rgba(14,165,233,0.4)]'
                  : 'text-[#94a3b8] hover:text-white'
              }`}
            >
              <Radio className="w-3.5 h-3.5 text-sky-300" />
              <span>SENTINEL-1 SAR (RADAR)</span>
            </button>
          </div>
        </div>

        {/* Acquisition Dates & Cloud Quality Badges */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 pt-3 border-t border-[#3a3a3f] text-xs font-mono">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-micro text-[10px] uppercase tracking-[0.96px] text-[#5a5a5f]">
              ACQUISITIONS:
            </span>
            <span className="badge-chip text-[10px]">
              BASELINE: 28 JUL (NORMAL)
            </span>
            <span className="text-[#3a3a3f]">VS</span>
            <span className="badge-chip text-[10px] border-rose-600 text-rose-300">
              PEAK: 18 OCT (SURGE PASS)
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Cloud Cover & Processing Quality Badge */}
            <div className="badge-chip text-[10px]">
              <Cloud className="w-3 h-3 text-white" />
              <span>CLOUD: {sceneConfig.cloudCover.toUpperCase()}</span>
              <span className="text-[#3a3a3f]">•</span>
              <span>{sceneConfig.qualityTag.toUpperCase()}</span>
            </div>

            {/* View Mode Toggle */}
            <div className="flex items-center bg-black p-0.5 border border-[#3a3a3f]">
              <button
                onClick={() => setViewMode('split-slider')}
                className={`p-1 text-xs transition-colors ${
                  viewMode === 'split-slider'
                    ? 'bg-white text-black'
                    : 'text-[#5a5a5f] hover:text-white'
                }`}
                title="Split Wipe Slider"
              >
                <Split className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setViewMode('side-by-side')}
                className={`p-1 text-xs transition-colors ${
                  viewMode === 'side-by-side'
                    ? 'bg-white text-black'
                    : 'text-[#5a5a5f] hover:text-white'
                }`}
                title="Side-by-side Dual Panels"
              >
                <Layers className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 2. MAIN LAYOUT: INTERACTIVE VISUALIZER + STATS PANEL */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* LEFT COLUMN: INTERACTIVE VISUALIZER (8 cols on lg/xl) */}
        <div className="lg:col-span-8 flex flex-col rounded-xl bg-slate-900 border border-slate-800 overflow-hidden shadow-2xl">
          {/* Top Visualizer HUD Bar */}
          <div className="px-4 py-2.5 border-b border-slate-800 bg-slate-950/80 flex items-center justify-between text-xs">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 font-bold text-white uppercase text-[11px]">
                <Satellite className="w-3.5 h-3.5 text-cyan-400" />
                {sceneConfig.title}
              </div>
              <span className="text-slate-500">•</span>
              <span className="text-[10px] font-mono text-slate-400">
                Res: {sceneConfig.resolution}
              </span>
            </div>

            <div className="text-[11px] font-mono text-cyan-400">
              {viewMode === 'split-slider'
                ? `Wipe Divider: ${sliderPos}%`
                : 'Synchronized Dual View'}
            </div>
          </div>

          {/* Interactive Visualizer Canvas */}
          <div className="relative w-full h-[520px] bg-[#050811] overflow-hidden select-none">
            {viewMode === 'split-slider' ? (
              /* Split Slider Wipe View */
              <div className="relative w-full h-full">
                {/* 1. Underlying POST-EVENT CLASSIFIED WATER MASK (Full width) */}
                <div className="absolute inset-0 bg-[#070b14]">
                  {/* High contrast post-flood classified vector image */}
                  <svg
                    viewBox="0 0 800 500"
                    className="w-full h-full object-cover"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <defs>
                      <pattern id="grid-post" width="40" height="40" patternUnits="userSpaceOnUse">
                        <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" strokeWidth="0.5" />
                      </pattern>
                    </defs>
                    <rect width="800" height="500" fill="#070c18" />
                    <rect width="800" height="500" fill="url(#grid-post)" opacity="0.4" />

                    {/* Pre-Flood Baseline Permanent River Channel (Deep Blue) */}
                    <path
                      d="M 320,30 C 340,90 380,150 410,210 C 450,270 500,340 540,490"
                      stroke="#0369a1"
                      strokeWidth="14"
                      strokeLinecap="round"
                    />

                    {/* Massive Newly Flooded Inundation Extent (Luminous Cyan & Magenta overlay) */}
                    <path
                      d="M 260,70 C 310,90 360,140 400,200 C 440,260 480,310 520,390 C 580,450 560,490 480,480 C 410,470 340,430 290,360 C 230,290 210,210 230,130 Z"
                      fill="#06b6d4"
                      fillOpacity="0.45"
                      stroke="#22d3ee"
                      strokeWidth="2"
                    />
                    <path
                      d="M 350,180 C 420,200 490,230 550,280 C 520,340 450,330 390,270 Z"
                      fill="#f43f5e"
                      fillOpacity="0.35"
                      stroke="#fb7185"
                      strokeWidth="1.5"
                      strokeDasharray="4 2"
                    />

                    {/* Inundated Agricultural Corridors */}
                    <rect x="270" y="220" width="85" height="55" rx="4" fill="#0284c7" fillOpacity="0.35" stroke="#38bdf8" strokeWidth="1" strokeDasharray="3 3" />
                    <rect x="440" y="310" width="95" height="60" rx="4" fill="#0284c7" fillOpacity="0.35" stroke="#38bdf8" strokeWidth="1" strokeDasharray="3 3" />

                    {/* Exposed Settlements Under Threat (Amber) */}
                    <circle cx="365" cy="275" r="7" fill="#f59e0b" stroke="#ffffff" strokeWidth="1.5" />
                    <text x="380" y="280" fill="#fef08a" fontSize="10" fontWeight="bold" fontFamily="sans-serif">
                      Prakashpur Ward 4
                    </text>

                    <circle cx="490" cy="400" r="6" fill="#f59e0b" stroke="#ffffff" strokeWidth="1.5" />
                    <text x="505" y="405" fill="#fef08a" fontSize="9" fontWeight="bold" fontFamily="sans-serif">
                      Bhokraha Narsingh
                    </text>
                  </svg>

                  {/* Post-Event HUD Label */}
                  <div className="absolute top-4 right-4 z-10 px-2.5 py-1 rounded-md bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-mono text-[11px] font-bold">
                    POST-EVENT: CLASSIFIED FLOOD MASK
                  </div>
                </div>

                {/* 2. Top-layered PRE-DISASTER OPTICAL REFERENCE (Clipped by slider width) */}
                <div
                  className="absolute inset-y-0 left-0 overflow-hidden border-r-2 border-cyan-400 shadow-2xl"
                  style={{ width: `${sliderPos}%` }}
                >
                  <div className="w-[800px] h-[520px] max-w-none">
                    <svg
                      viewBox="0 0 800 500"
                      className="w-full h-full object-cover"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <rect width="800" height="500" fill="#09131f" />
                      {/* Normal Riverbed baseline */}
                      <path
                        d="M 320,30 C 340,90 380,150 410,210 C 450,270 500,340 540,490"
                        stroke="#0369a1"
                        strokeWidth="12"
                        strokeLinecap="round"
                      />
                      {/* Agricultural plots normal */}
                      <rect x="270" y="220" width="85" height="55" rx="4" fill="#064e3b" fillOpacity="0.4" stroke="#059669" strokeWidth="0.8" />
                      <rect x="440" y="310" width="95" height="60" rx="4" fill="#064e3b" fillOpacity="0.4" stroke="#059669" strokeWidth="0.8" />

                      {/* Terrain elevation curves */}
                      <path d="M 50,40 Q 200,80 400,60 T 750,90" stroke="#1e293b" strokeWidth="1" strokeDasharray="3 3" />
                      <path d="M 50,380 Q 220,400 480,370 T 750,420" stroke="#1e293b" strokeWidth="1" strokeDasharray="3 3" />
                    </svg>

                    {/* Pre-Event HUD Label */}
                    <div className="absolute top-4 left-4 z-10 px-2.5 py-1 rounded-md bg-slate-950/80 border border-slate-700 text-slate-300 font-mono text-[11px] font-bold">
                      BASELINE: PRE-DISASTER OPTICAL
                    </div>
                  </div>
                </div>

                {/* 3. Slider Handle */}
                <div
                  className="absolute inset-y-0 z-20 flex items-center justify-center pointer-events-none"
                  style={{ left: `${sliderPos}%` }}
                >
                  <div className="w-8 h-8 -ml-4 rounded-full bg-cyan-400 text-slate-950 flex items-center justify-center font-bold text-xs shadow-[0_0_15px_rgba(34,211,238,0.9)] cursor-ew-resize pointer-events-auto border-2 border-white">
                    ⇄
                  </div>
                </div>

                {/* Slider Input Range Controller */}
                <input
                  type="range"
                  min="5"
                  max="95"
                  value={sliderPos}
                  onChange={(e) => setSliderPos(Number(e.target.value))}
                  className="absolute bottom-4 left-1/2 -translate-x-1/2 z-30 w-72 h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                />
              </div>
            ) : (
              /* Side-by-Side Dual View */
              <div className="grid grid-cols-2 h-full divide-x divide-slate-800">
                {/* Panel 1: Pre-Disaster */}
                <div className="relative p-2 flex flex-col justify-between">
                  <div className="text-[10px] font-mono text-slate-300 bg-slate-950/80 px-2 py-0.5 rounded border border-slate-800 self-start">
                    Pre-Disaster Optical Base
                  </div>
                  <div className="flex-1 flex items-center justify-center text-center p-4">
                    <span className="text-xs text-slate-400 font-mono">
                      Baseline Water Body: 18.2 km²
                    </span>
                  </div>
                </div>

                {/* Panel 2: Post-Event Mask */}
                <div className="relative p-2 flex flex-col justify-between bg-cyan-950/20">
                  <div className="text-[10px] font-mono text-cyan-300 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-800 self-start">
                    Post-Event Water Mask (+64.2 km²)
                  </div>
                  <div className="flex-1 flex items-center justify-center text-center p-4">
                    <span className="text-xs text-cyan-300 font-mono">
                      Newly Inundated Extent (MNDWI &gt; -0.05)
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Tactical Coordinates HUD Footer */}
            <div className="absolute bottom-3 left-4 z-10 flex items-center gap-3 text-[10px] font-mono text-slate-400 bg-slate-950/85 px-3 py-1.5 rounded-lg border border-slate-800">
              <span>ORBIT: Sentinel-2 Track 048</span>
              <span>•</span>
              <span className="text-cyan-400 font-bold">EPSG:4326 WGS84</span>
              <span>•</span>
              <span>Koshi Barrage Corridor</span>
            </div>
          </div>

          {/* Legend Bar */}
          <div className="p-3 border-t border-slate-800 bg-slate-950/90 flex flex-wrap items-center justify-between gap-2.5 text-xs">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Classification Legend:
            </span>

            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded bg-[#0369a1]"></span>
                <span className="text-slate-300 text-[11px]">Permanent Water (18.2 km²)</span>
              </div>

              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded bg-cyan-400 shadow-[0_0_6px_rgba(34,211,238,0.6)]"></span>
                <span className="text-cyan-300 font-semibold text-[11px]">
                  Newly Flooded Inundation (64.2 km²)
                </span>
              </div>

              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded bg-rose-500/80"></span>
                <span className="text-rose-300 text-[11px]">High Turbidity / Muddy Surge</span>
              </div>

              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                <span className="text-amber-300 text-[11px]">Exposed Settlements (22 wards)</span>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: AI DETECTION STATISTICS PANEL (4 cols on lg/xl) */}
        <div className="lg:col-span-4 space-y-3.5">
          {/* Surface Area Breakdown Card */}
          <div className="p-4 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] shadow-none space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <span className="font-micro text-[10px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
                  <BrainCircuit className="w-3 h-3 text-white" />
                  WATER EXTRACTION METRICS
                </span>
                <h3 className="font-display text-xs font-bold text-white tracking-wider uppercase mt-0.5">
                  Copernicus Satellite Analysis
                </h3>
              </div>
              <span className="badge-chip font-mono text-[9px]">
                IOU: 89.4%
              </span>
            </div>

            {/* Main Stats Metric */}
            <div className="p-3.5 bg-black border border-[#3a3a3f]">
              <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] block">
                TOTAL NEWLY FLOODED EXTENT
              </span>
              <div className="font-display text-3xl font-bold text-white mt-1 flex items-baseline gap-2">
                {stats.totalNewlyFloodedKm2}
                <span className="font-mono text-xs font-normal text-[#5a5a5f]">KM²</span>
              </div>
              <p className="font-mono text-[10px] text-[#5a5a5f] mt-1 uppercase">
                NET EXPANSION ABOVE PRE-MONSOON RIVERBED
              </p>
            </div>

            {/* Breakdown List */}
            <div className="space-y-2 pt-1 text-xs font-mono">
              {/* Agricultural Land */}
              <div className="p-2.5 bg-black border border-[#3a3a3f] flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block text-[11px] uppercase">
                    SUBMERGED AGRICULTURAL LAND
                  </span>
                  <span className="text-[10px] text-[#5a5a5f] uppercase">
                    PADDY CROPS INUNDATED
                  </span>
                </div>
                <div className="text-right">
                  <span className="font-bold text-white text-sm">
                    {stats.floodedAgriculturalKm2} KM²
                  </span>
                  <span className="text-[10px] text-[#5a5a5f] block uppercase">65% OF TOTAL</span>
                </div>
              </div>

              {/* Submerged Road Network */}
              <div className="p-2.5 bg-black border border-[#3a3a3f] flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block text-[11px] uppercase">
                    SUBMERGED ROAD NETWORK
                  </span>
                  <span className="text-[10px] text-[#5a5a5f] uppercase">
                    SECONDARY CORRIDORS
                  </span>
                </div>
                <div className="text-right">
                  <span className="font-bold text-white text-sm">
                    {stats.submergedRoadsKm} KM
                  </span>
                  <span className="text-[10px] text-[#5a5a5f] block uppercase">TRANSIT CUT</span>
                </div>
              </div>

              {/* Affected Settlements */}
              <div className="p-2.5 bg-black border border-[#3a3a3f] flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block text-[11px] uppercase">
                    EXPOSED SETTLEMENTS
                  </span>
                  <span className="text-[10px] text-[#5a5a5f] uppercase">
                    200M HAZARD BUFFER
                  </span>
                </div>
                <div className="text-right">
                  <span className="font-bold text-white text-sm">
                    {stats.affectedSettlementsCount} WARDS
                  </span>
                  <span className="text-[10px] text-[#5a5a5f] block uppercase">
                    ~{stats.estimatedDisplacedPeople.toLocaleString()} CITIZENS
                  </span>
                </div>
              </div>
            </div>

            {/* Export Actions Buttons: Ghost Pill CTAs */}
            <div className="pt-3 border-t border-[#3a3a3f] space-y-2">
              <button
                onClick={handleDownloadGeoJSON}
                className="btn-ghost-pill w-full text-center justify-center !py-2.5 !text-xs font-mono"
              >
                <Download className="w-3.5 h-3.5" />
                <span>DOWNLOAD GEOJSON FLOOD MASK</span>
              </button>

              <button
                onClick={handleSendToOps}
                className="btn-ghost-pill-subtle w-full text-center justify-center !py-2 !text-xs font-mono"
              >
                <Send className="w-3.5 h-3.5" />
                <span>DISPATCH TO RESPONSE OPERATIONS</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Interactive Action Toast Notification */}
      {notification && (
        <div className="fixed bottom-6 right-6 z-50 p-4 rounded-xl bg-slate-900 border border-cyan-500 text-slate-100 shadow-2xl animate-in slide-in-from-bottom-4 flex items-start gap-3 max-w-md">
          <CheckCircle className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs">
            <h4 className="font-bold text-white">Action Completed</h4>
            <p className="text-slate-300 mt-0.5">{notification}</p>
          </div>
        </div>
      )}
    </div>
  );
};
