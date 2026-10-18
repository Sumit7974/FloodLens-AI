import React, { useState } from 'react';
import {
  Compass,
  Crosshair,
} from 'lucide-react';

interface MapPreviewPanelProps {
  onSelectSosItem?: (sosId: string) => void;
}

export const MapPreviewPanel: React.FC<MapPreviewPanelProps> = ({ onSelectSosItem }) => {
  // Layer toggles
  const [layers, setLayers] = useState({
    rainfall: true,
    floodExtent: true,
    shelters: true,
    riverGauges: true,
  });

  // Horizon preview
  const [activeHorizon, setActiveHorizon] = useState<'now' | '+1h' | '+3h' | '+6h'>('now');

  const toggleLayer = (key: keyof typeof layers) => {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="flex flex-col h-full rounded-none bg-[#0a0a0a] border border-[#27272a] overflow-hidden shadow-none">
      {/* Map Control Toolbar */}
      <div className="px-4 py-3 border-b border-[#27272a] bg-[#000000] flex flex-wrap items-center justify-between gap-2.5">
        <div>
          <h3 className="font-display text-xs tracking-[1.4px] uppercase font-bold text-white">
            Tactical Geospatial Overview
          </h3>
          <p className="font-mono text-[10px] text-[#71717a] uppercase mt-0.5">
            KOSHI BASIN SUB-WATERSHED // 26°49′N 87°09′E
          </p>
        </div>

        {/* Horizon selector buttons */}
        <div className="flex items-center gap-1 bg-black p-0.5 border border-[#27272a]">
          {(['now', '+1h', '+3h', '+6h'] as const).map((horizon) => (
            <button
              key={horizon}
              onClick={() => setActiveHorizon(horizon)}
              className={`px-2.5 py-1 text-[10px] font-mono font-bold uppercase transition-all ${
                activeHorizon === horizon
                  ? 'bg-white text-black'
                  : 'text-[#888890] hover:text-white'
              }`}
            >
              {horizon.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Layer Toggles: Sleek Inline Text / Segment Switcher (No Capsules) */}
      <div className="px-4 py-2 border-b border-[#27272a] bg-[#0a0a0a] flex flex-wrap items-center gap-4 text-xs font-mono">
        <span className="font-micro text-[10px] uppercase tracking-[1.2px] text-[#71717a]">
          LAYERS:
        </span>

        {/* Rainfall Layer */}
        <button
          onClick={() => toggleLayer('rainfall')}
          className={`flex items-center gap-1.5 transition-colors uppercase tracking-wider text-[11px] ${
            layers.rainfall
              ? 'text-white font-bold'
              : 'text-[#71717a] hover:text-white'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${layers.rainfall ? 'bg-blue-400' : 'bg-[#27272a]'}`}></span>
          <span>RADAR</span>
        </button>

        {/* Flood Extent */}
        <button
          onClick={() => toggleLayer('floodExtent')}
          className={`flex items-center gap-1.5 transition-colors uppercase tracking-wider text-[11px] ${
            layers.floodExtent
              ? 'text-white font-bold'
              : 'text-[#71717a] hover:text-white'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${layers.floodExtent ? 'bg-cyan-400' : 'bg-[#27272a]'}`}></span>
          <span>EXTENT</span>
        </button>

        {/* Shelters */}
        <button
          onClick={() => toggleLayer('shelters')}
          className={`flex items-center gap-1.5 transition-colors uppercase tracking-wider text-[11px] ${
            layers.shelters
              ? 'text-white font-bold'
              : 'text-[#71717a] hover:text-white'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${layers.shelters ? 'bg-emerald-400' : 'bg-[#27272a]'}`}></span>
          <span>SHELTERS</span>
        </button>

        {/* River Gauges */}
        <button
          onClick={() => toggleLayer('riverGauges')}
          className={`flex items-center gap-1.5 transition-colors uppercase tracking-wider text-[11px] ${
            layers.riverGauges
              ? 'text-white font-bold'
              : 'text-[#71717a] hover:text-white'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${layers.riverGauges ? 'bg-amber-400' : 'bg-[#27272a]'}`}></span>
          <span>GAUGES</span>
        </button>
      </div>

      {/* Main Tactical Map Preview Canvas */}
      <div className="relative flex-1 min-h-[380px] lg:min-h-[460px] bg-[#070b14] overflow-hidden flex items-center justify-center select-none">
        {/* Subtle Map Gridlines & Tactical Reticle */}
        <div
          className="absolute inset-0 opacity-20 pointer-events-none"
          style={{
            backgroundImage: `radial-gradient(rgba(56, 189, 248, 0.2) 1px, transparent 0), linear-gradient(to right, rgba(30, 41, 59, 0.4) 1px, transparent 1px), linear-gradient(to bottom, rgba(30, 41, 59, 0.4) 1px, transparent 1px)`,
            backgroundSize: '32px 32px, 64px 64px, 64px 64px',
          }}
        />

        {/* Compass Rose / HUD Corner */}
        <div className="absolute top-4 left-4 z-10 flex flex-col gap-0.5 p-2 bg-black/90 border border-[#27272a] text-[10px] font-mono text-[#888890]">
          <div className="flex items-center gap-1.5 text-white font-bold">
            <Compass className="w-3.5 h-3.5" />
            <span>GRID: UTM 45N</span>
          </div>
          <div>DATUM: WGS84</div>
          <div className="text-[#71717a]">RES: 10M SENTINEL-2</div>
        </div>

        {/* Top-Right Map Mode Pill */}
        <div className="absolute top-4 right-4 z-10 flex items-center gap-2 p-1.5 bg-black/90 border border-[#27272a] text-[10px] font-mono uppercase">
          <span className="text-white font-bold">
            BENCHMARK REPLAY
          </span>
          <span className="text-[#71717a]">Koshi Basin</span>
        </div>

        {/* Synthetic Vector Map Graphic / River Inundation Visualizer */}
        <svg
          viewBox="0 0 800 500"
          className="w-full h-full object-cover max-h-[520px]"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            {/* Flood Extent Gradient */}
            <radialGradient id="inundationGlow" cx="48%" cy="50%" r="55%">
              <stop offset="0%" stopColor="#0284c7" stopOpacity={layers.floodExtent ? '0.55' : '0.05'} />
              <stop offset="60%" stopColor="#0369a1" stopOpacity={layers.floodExtent ? '0.35' : '0.02'} />
              <stop offset="100%" stopColor="#082f49" stopOpacity="0" />
            </radialGradient>

            <linearGradient id="riverGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#38bdf8" />
              <stop offset="50%" stopColor="#0284c7" />
              <stop offset="100%" stopColor="#0369a1" />
            </linearGradient>

            {/* Radar scanner effect */}
            <linearGradient id="radarSweep" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Contour Lines / Topographic Relief */}
          <path
            d="M 50,40 Q 200,80 400,60 T 750,90"
            stroke="#1e293b"
            strokeWidth="1.2"
            strokeDasharray="4 4"
          />
          <path
            d="M 50,120 Q 250,150 450,130 T 750,160"
            stroke="#1e293b"
            strokeWidth="1.2"
            strokeDasharray="4 4"
          />
          <path
            d="M 50,380 Q 220,400 480,370 T 750,420"
            stroke="#1e293b"
            strokeWidth="1.2"
            strokeDasharray="4 4"
          />

          {/* Rainfall Isohyet Overlay (if enabled) */}
          {layers.rainfall && (
            <g className="animate-pulse" style={{ animationDuration: '4s' }}>
              <ellipse cx="440" cy="220" rx="220" ry="140" fill="#1e3a8a" fillOpacity="0.18" />
              <ellipse cx="420" cy="210" rx="150" ry="90" fill="#2563eb" fillOpacity="0.22" />
              <ellipse cx="400" cy="200" rx="80" ry="50" fill="#3b82f6" fillOpacity="0.25" />
              <text x="370" y="195" fill="#93c5fd" fontSize="10" fontFamily="monospace" opacity="0.8">
                &gt; 25mm/h
              </text>
            </g>
          )}

          {/* Inundation Extent Polygon (Sentinel-1/2 derived) */}
          {layers.floodExtent && (
            <path
              d="M 280,110 C 330,130 380,180 410,230 C 450,290 490,340 520,420 C 460,440 370,410 320,350 C 270,300 240,240 260,180 Z"
              fill="url(#inundationGlow)"
              stroke="#38bdf8"
              strokeWidth="1.8"
              strokeDasharray="3 2"
              className="transition-all duration-700"
            />
          )}

          {/* Main Koshi River Braided Channels */}
          <path
            d="M 290,40 C 310,100 350,160 380,210 C 420,270 470,330 510,480"
            stroke="url(#riverGradient)"
            strokeWidth="10"
            strokeLinecap="round"
          />
          {/* Western Braided Channel */}
          <path
            d="M 320,130 C 290,190 270,250 310,320 C 340,370 420,420 480,480"
            stroke="#0284c7"
            strokeWidth="5"
            strokeLinecap="round"
            opacity="0.85"
          />
          {/* Chatara Canal Offtake */}
          <path
            d="M 380,210 C 430,220 520,240 580,290"
            stroke="#0369a1"
            strokeWidth="3.5"
            strokeDasharray="6 3"
          />

          {/* District Embankment / Levees */}
          <path
            d="M 330,80 L 410,200 L 490,320 L 540,460"
            stroke="#e11d48"
            strokeWidth="2.5"
            strokeDasharray="5 3"
          />
          {/* Critical Breach Point Label */}
          <g transform="translate(415, 205)">
            <circle cx="0" cy="0" r="14" fill="#e11d48" fillOpacity="0.2" className="animate-ping" />
            <circle cx="0" cy="0" r="5" fill="#e11d48" />
            <rect x="10" y="-12" width="130" height="22" rx="4" fill="#0f172a" stroke="#e11d48" strokeWidth="1" />
            <text x="16" y="2" fill="#fda4af" fontSize="9" fontWeight="bold" fontFamily="monospace">
              SPUR km 12+400 (CRITICAL)
            </text>
          </g>

          {/* River Telemetry Gauges (if enabled) */}
          {layers.riverGauges && (
            <>
              {/* Chatara Gauge */}
              <g transform="translate(350, 170)">
                <circle cx="0" cy="0" r="10" fill="#f59e0b" fillOpacity="0.25" className="animate-pulse" />
                <polygon points="0,-7 6,4 -6,4" fill="#f59e0b" />
                <rect x="12" y="-14" width="105" height="26" rx="4" fill="#090d16" stroke="#f59e0b" strokeWidth="1" />
                <text x="18" y="-2" fill="#fef3c7" fontSize="9" fontWeight="bold" fontFamily="sans-serif">
                  Chatara: 8.18m
                </text>
                <text x="18" y="8" fill="#f59e0b" fontSize="8" fontFamily="monospace">
                  +0.38m/h (DANGER)
                </text>
              </g>

              {/* Koshi Barrage Gauge */}
              <g transform="translate(510, 440)">
                <circle cx="0" cy="0" r="10" fill="#ef4444" fillOpacity="0.25" className="animate-pulse" />
                <polygon points="0,-7 6,4 -6,4" fill="#ef4444" />
                <rect x="-120" y="-14" width="112" height="26" rx="4" fill="#090d16" stroke="#ef4444" strokeWidth="1" />
                <text x="-114" y="-2" fill="#fee2e2" fontSize="9" fontWeight="bold" fontFamily="sans-serif">
                  Koshi Barrage
                </text>
                <text x="-114" y="8" fill="#f87171" fontSize="8" fontFamily="monospace">
                  74.85m (Gates Open)
                </text>
              </g>
            </>
          )}

          {/* Verified Shelters (if enabled) */}
          {layers.shelters && (
            <>
              {/* Inaruwa Shelter */}
              <g transform="translate(600, 240)">
                <circle cx="0" cy="0" r="4" fill="#10b981" />
                <rect x="8" y="-9" width="90" height="18" rx="3" fill="#0f172a" stroke="#10b981" strokeWidth="1" />
                <text x="13" y="3" fill="#a7f3d0" fontSize="8" fontWeight="600" fontFamily="sans-serif">
                  Inaruwa Safe Hub
                </text>
              </g>

              {/* Dharan Red Cross Hospital Post */}
              <g transform="translate(480, 80)">
                <circle cx="0" cy="0" r="4" fill="#10b981" />
                <rect x="8" y="-9" width="85" height="18" rx="3" fill="#0f172a" stroke="#10b981" strokeWidth="1" />
                <text x="13" y="3" fill="#a7f3d0" fontSize="8" fontWeight="600" fontFamily="sans-serif">
                  BPKIHS Hospital
                </text>
              </g>
            </>
          )}

          {/* Live SOS Distress Markers */}
          {/* SOS 1: Prakashpur Rooftop */}
          <g
            transform="translate(365, 275)"
            className="cursor-pointer"
            onClick={() => onSelectSosItem && onSelectSosItem('SOS-2026-081')}
          >
            <circle cx="0" cy="0" r="18" fill="#ef4444" fillOpacity="0.25" className="animate-ping" />
            <circle cx="0" cy="0" r="6" fill="#ef4444" stroke="#ffffff" strokeWidth="1.5" />
            <rect x="12" y="-14" width="115" height="24" rx="4" fill="#450a0a" stroke="#ef4444" strokeWidth="1" />
            <text x="17" y="-2" fill="#fecaca" fontSize="9" fontWeight="bold" fontFamily="sans-serif">
              SOS: 5 Trapped (Roof)
            </text>
            <text x="17" y="7" fill="#f87171" fontSize="8" fontFamily="monospace">
              Prakashpur • #081
            </text>
          </g>

          {/* SOS 2: Barahakshetra Medical */}
          <g
            transform="translate(340, 140)"
            className="cursor-pointer"
            onClick={() => onSelectSosItem && onSelectSosItem('SOS-2026-079')}
          >
            <circle cx="0" cy="0" r="16" fill="#ef4444" fillOpacity="0.2" className="animate-ping" />
            <circle cx="0" cy="0" r="5" fill="#ef4444" stroke="#ffffff" strokeWidth="1.5" />
            <rect x="-115" y="-12" width="105" height="22" rx="4" fill="#450a0a" stroke="#ef4444" strokeWidth="1" />
            <text x="-110" y="2" fill="#fecaca" fontSize="8.5" fontWeight="bold" fontFamily="sans-serif">
              SOS: Medical (Oxygen)
            </text>
          </g>
        </svg>

        {/* Tactical Legend Overlay Bottom-Left */}
        <div className="absolute bottom-3 left-3 z-10 p-2.5 bg-[#0a0a0a] border border-[#3a3a3f] text-[10px] space-y-1.5 shadow-none">
          <span className="font-micro uppercase tracking-[0.96px] text-[#5a5a5f] block -mb-0.5">
            SURGE DEPTH KEY
          </span>
          <div className="flex items-center gap-2">
            <span className="w-3 h-2 bg-cyan-600/80"></span>
            <span className="text-[#f0f0fa]">0.5M – 1.2M (MARGINAL)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-2 bg-cyan-400"></span>
            <span className="text-[#f0f0fa]">&gt; 1.5M (HIGH VELOCITY)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping"></span>
            <span className="text-white font-bold">CITIZEN EXTRACTION PT</span>
          </div>
        </div>

        {/* Center Crosshair for EOC target feel */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20">
          <Crosshair className="w-16 h-16 text-white stroke-1" />
        </div>
      </div>

      {/* Map Footer Bar with Telemetry Coordinates */}
      <div className="px-4 py-2 border-t border-[#27272a] bg-[#000000] flex flex-wrap items-center justify-between text-[11px] text-[#5a5a5f] font-mono">
        <div className="flex items-center gap-3">
          <span>COORDINATES: 26°41′15″ N, 87°04′28″ E</span>
          <span className="hidden sm:inline">•</span>
          <span className="text-white hidden sm:inline">ELEV: 78.4M MSL</span>
        </div>
        <div className="flex items-center gap-2 text-[#5a5a5f]">
          <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
          <span>SENTINEL-2 NDWI MASK • CLOUD 4%</span>
        </div>
      </div>
    </div>
  );
};
