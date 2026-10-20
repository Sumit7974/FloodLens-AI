import React, { useState } from 'react';
import {
  Circle,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from 'react-leaflet';
import L from 'leaflet';
import {
  AlertTriangle,
  Check,
  CheckCircle,
  Clock,
  Compass,
  Copy,
  LifeBuoy,
  MapPin,
  Navigation,
  Phone,
  Search,
  ShieldAlert,
  Truck,
  UserCheck,
  Users,
  Waves,
} from 'lucide-react';
import { KOSHI_INFRASTRUCTURE, KOSHI_SHELTERS } from '../data/geospatialData';
import type { BenchmarkScene, HelpRequest, RequestCategory } from '../types';

interface ResponseOperationsProps {
  currentScene: BenchmarkScene;
  requests: HelpRequest[];
  onUpdateRequestStatus: (requestId: string, status: any, assignedUnit?: string) => void;
}

// Leaflet Recenter Hook
const MapRecenter = ({ lat, lng }: { lat: number; lng: number }) => {
  const map = useMap();
  React.useEffect(() => {
    map.flyTo([lat, lng], 13, { duration: 1.2 });
  }, [lat, lng, map]);
  return null;
};

// Custom DivIcons
const citizenDistressIcon = L.divIcon({
  className: 'custom-distress-marker',
  html: `
    <div class="relative flex items-center justify-center">
      <span class="animate-ping absolute inline-flex h-8 w-8 rounded-full bg-rose-500 opacity-60"></span>
      <div class="relative w-7 h-7 rounded-full bg-rose-600 border-2 border-white flex items-center justify-center text-white text-[10px] font-bold shadow-xl">
        SOS
      </div>
    </div>
  `,
  iconSize: [28, 28],
  iconAnchor: [14, 14],
  popupAnchor: [0, -14],
});

const boatUnitIcon = L.divIcon({
  className: 'custom-boat-marker',
  html: `
    <div class="w-6 h-6 rounded-none bg-black border border-white text-white flex items-center justify-center text-xs shadow-none">
      ⚓
    </div>
  `,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

const shelterIcon = L.divIcon({
  className: 'custom-shelter-marker',
  html: `
    <div class="w-5 h-5 rounded-none bg-white text-black font-bold flex items-center justify-center text-[10px] shadow-none">
      ⌂
    </div>
  `,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

export const ResponseOperations: React.FC<ResponseOperationsProps> = ({
  currentScene,
  requests,
  onUpdateRequestStatus,
}) => {
  // Master-Detail selection
  const [selectedId, setSelectedId] = useState<string>(requests[0]?.id || 'SOS-2026-081');

  // Search & Filter States
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'PENDING' | 'ASSIGNED' | 'RESOLVED'>('ALL');
  const [categoryFilter, setCategoryFilter] = useState<'ALL' | RequestCategory>('ALL');

  // Sub-tab: Queue vs Infrastructure Exposure
  const [activeSubTab, setActiveSubTab] = useState<'triage' | 'infrastructure'>('triage');

  // Toast feedback state
  const [feedback, setFeedback] = useState<string | null>(null);

  const selectedRequest = requests.find((r) => r.id === selectedId) || requests[0];

  // Available rescue units for dispatch
  const availableRescueUnits = [
    { name: 'APF Rapid Swift-Water Boat #04', eta: '8 mins', base: 'Chatara Staging Base' },
    { name: 'Nepal Army Amphibious Unit #02', eta: '14 mins', base: 'Barahakshetra Post' },
    { name: 'Red Cross Motorized Zodiac Alpha', eta: '19 mins', base: 'Inaruwa Hub' },
    { name: 'NDRF Evacuation Squad Charlie', eta: '25 mins', base: 'Prakashpur Depot' },
  ];

  // Filtered requests list
  const filteredRequests = requests.filter((r) => {
    // Search query matching
    const matchesSearch =
      r.requester_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.location_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.landmark.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.id.toLowerCase().includes(searchQuery.toLowerCase());

    // Status matching
    const matchesStatus =
      statusFilter === 'ALL'
        ? true
        : statusFilter === 'PENDING'
        ? r.status === 'OPEN'
        : r.status === statusFilter;

    // Category matching
    const matchesCategory = categoryFilter === 'ALL' || r.category === categoryFilter;

    return matchesSearch && matchesStatus && matchesCategory;
  });

  const notify = (msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(null), 3500);
  };

  const handleAssignUnit = (unitName: string) => {
    onUpdateRequestStatus(selectedRequest.id, 'ASSIGNED', unitName);
    notify(`Assigned ${unitName} to ${selectedRequest.id}`);
  };

  const handleResolve = () => {
    onUpdateRequestStatus(selectedRequest.id, 'RESOLVED');
    notify(`Ticket ${selectedRequest.id} marked as RESOLVED`);
  };

  const handleEscalate = () => {
    notify(`Priority escalated for ${selectedRequest.id} — Flagged to Operations Commander`);
  };

  const copyCoordinates = (coords: [number, number]) => {
    navigator.clipboard?.writeText(`${coords[0]}, ${coords[1]}`);
    notify(`Copied coordinates ${coords[0]}, ${coords[1]} to clipboard`);
  };

  return (
    <div className="space-y-3.5">
      {/* Top Header Bar */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-400">
            <LifeBuoy className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
              Response Operations // Citizen SOS Triage Center
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-[9px] font-mono font-bold tracking-wider">
                LIVE INCIDENT STREAM
              </span>
            </h1>
            <p className="font-mono text-[10px] text-[#38bdf8] uppercase tracking-wider mt-0.5 font-semibold">
              RAPID EXTRACTION COORDINATION // {currentScene.name}
            </p>
          </div>
        </div>

        {/* View Switcher Sub-tabs: Colored Pill Buttons */}
        <div className="flex items-center gap-1.5 p-1 bg-[#060e1d] border border-[#1e3a5f] rounded-full text-xs">
          <button
            onClick={() => setActiveSubTab('triage')}
            className={`flex items-center gap-1.5 px-3 py-1 font-mono font-bold uppercase rounded-full transition-all cursor-pointer ${
              activeSubTab === 'triage'
                ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-[0_0_10px_rgba(16,185,129,0.4)]'
                : 'text-[#94a3b8] hover:text-white'
            }`}
          >
            <LifeBuoy className="w-3.5 h-3.5 text-emerald-300" />
            <span>SOS TRIAGE QUEUE ({requests.length})</span>
          </button>

          <button
            onClick={() => setActiveSubTab('infrastructure')}
            className={`flex items-center gap-1.5 px-3 py-1 font-mono font-bold uppercase rounded-full transition-all cursor-pointer ${
              activeSubTab === 'infrastructure'
                ? 'bg-gradient-to-r from-[#e86e25] to-[#f97316] text-white shadow-[0_0_10px_rgba(232,110,37,0.4)]'
                : 'text-[#94a3b8] hover:text-white'
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5 text-amber-300" />
            <span>INFRASTRUCTURE EXPOSURE (4)</span>
          </button>
        </div>
      </div>

      {activeSubTab === 'infrastructure' ? (
        /* INFRASTRUCTURE EXPOSURE VIEW */
        <div className="p-4 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] shadow-none space-y-3.5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-display text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-white" />
                Inundated Infrastructure &amp; Transportation Corridors
              </h2>
              <p className="font-mono text-[10px] text-[#5a5a5f] uppercase tracking-wider mt-0.5">
                SUBMERGED HIGHWAYS, BREACHED SPURS, AND CRITICAL CHOKEPOINTS
              </p>
            </div>
            <span className="badge-chip border-rose-600 text-rose-300 font-mono text-xs">
              3 CRITICAL CHOKEPOINTS
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono text-[#f0f0fa]">
              <thead className="text-[10px] uppercase font-bold text-[#5a5a5f] bg-black border-b border-[#3a3a3f]">
                <tr>
                  <th className="p-3">INFRASTRUCTURE ASSET</th>
                  <th className="p-3">TYPE</th>
                  <th className="p-3">COORDINATES</th>
                  <th className="p-3">HAZARD STATUS</th>
                  <th className="p-3">IMPACT ON RESCUE ACCESS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#3a3a3f]">
                {KOSHI_INFRASTRUCTURE.map((infra) => (
                  <tr key={infra.id} className="hover:bg-[#141416] transition-colors">
                    <td className="p-3 font-bold text-white uppercase">
                      {infra.name}
                    </td>
                    <td className="p-3">
                      <span className="badge-chip text-[9px]">
                        {infra.type}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-[11px] text-[#5a5a5f]">
                      {infra.coordinates[0].toFixed(3)}, {infra.coordinates[1].toFixed(3)}
                    </td>
                    <td className="p-3">
                      <span
                        className={`badge-chip text-[9px] ${
                          infra.riskLevel === 'CRITICAL'
                            ? 'border-rose-600 text-rose-300'
                            : 'border-amber-600 text-amber-300'
                        }`}
                      >
                        {infra.riskLevel}
                      </span>
                    </td>
                    <td className="p-3 text-[11px] text-[#f0f0fa]">
                      {infra.description}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* 2-COLUMN SOS TRIAGE QUEUE & DETAIL */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
          {/* LEFT COLUMN: TRIAGE QUEUE & FILTERING (5 cols on lg/xl) */}
          <div className="lg:col-span-5 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] overflow-hidden shadow-none flex flex-col">
            {/* Search & Filters */}
            <div className="p-3 border-b border-[#3a3a3f] bg-[#000000] space-y-2">
              {/* Search input */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-[#5a5a5f] absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="SEARCH BY CALLER, LOCATION, OR TICKET #..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-[#0a0a0a] border border-[#3a3a3f] rounded-none pl-9 pr-3 py-1.5 text-xs font-mono text-white placeholder-[#5a5a5f] focus:outline-none focus:border-white uppercase"
                />
              </div>

              {/* Status Filter Tabs */}
              <div className="flex items-center gap-1 overflow-x-auto pb-1 text-[10px] font-mono">
                {(['ALL', 'PENDING', 'ASSIGNED', 'RESOLVED'] as const).map((st) => (
                  <button
                    key={st}
                    onClick={() => setStatusFilter(st)}
                    className={`px-2.5 py-1 uppercase font-bold transition-all whitespace-nowrap ${
                      statusFilter === st
                        ? 'bg-white text-black'
                        : 'bg-black text-[#5a5a5f] hover:text-white border border-[#3a3a3f]'
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>

              {/* Category Filter Pills */}
              <div className="flex items-center gap-1 overflow-x-auto text-[9px] font-mono">
                <span className="text-[#5a5a5f] uppercase font-bold mr-0.5">TYPE:</span>
                {(['ALL', 'TRAPPED', 'MEDICAL', 'ELDERLY_EVAC', 'FOOD_WATER'] as const).map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setCategoryFilter(cat)}
                    className={`badge-chip cursor-pointer text-[9px] !py-0.5 !px-2 whitespace-nowrap transition-colors ${
                      categoryFilter === cat
                        ? 'border-white text-white'
                        : 'border-[#3a3a3f] text-[#5a5a5f] hover:text-white'
                    }`}
                  >
                    {cat.replace('_', ' ')}
                  </button>
                ))}
              </div>
            </div>

            {/* Request Card List */}
            <div className="divide-y divide-[#3a3a3f] max-h-[560px] overflow-y-auto">
              {filteredRequests.length === 0 ? (
                <div className="p-8 text-center text-[#5a5a5f] text-xs font-mono uppercase">
                  NO DISTRESS SIGNALS MATCH CURRENT FILTERS.
                </div>
              ) : (
                filteredRequests.map((req) => {
                  const isSelected = req.id === selectedId;

                  return (
                    <div
                      key={req.id}
                      onClick={() => setSelectedId(req.id)}
                      className={`p-3 transition-colors cursor-pointer ${
                        isSelected
                          ? 'bg-[#141416] border-l-2 border-white'
                          : 'bg-black hover:bg-[#0a0a0a]'
                      }`}
                    >
                      {/* Top Row: Name, Category, Status */}
                      <div className="flex items-start justify-between gap-1">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-display text-xs font-bold text-white tracking-wider uppercase">
                              {req.requester_name}
                            </h3>
                            <span className="badge-chip text-[9px] !py-0.2 !px-1.5 font-mono">
                              {req.category.replace('_', ' ')}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-[10px] text-[#5a5a5f] font-mono mt-0.5 uppercase">
                            <span className="flex items-center gap-1">
                              <Phone className="w-3 h-3 text-[#5a5a5f]" />
                              {req.contact_number}
                            </span>
                            <span>•</span>
                            <span className="flex items-center gap-1">
                              <Clock className="w-3 h-3 text-[#5a5a5f]" />
                              {req.timestamp}
                            </span>
                          </div>
                        </div>

                        {/* Status Badge */}
                        <span
                          className={`badge-chip text-[9px] font-mono ${
                            req.status === 'RESOLVED'
                              ? 'border-emerald-600 text-emerald-400'
                              : req.status === 'ASSIGNED'
                              ? 'border-white text-white'
                              : 'border-rose-600 text-rose-300'
                          }`}
                        >
                          {req.status}
                        </span>
                      </div>

                      {/* Middle: Notes & People Count */}
                      <p className="font-mono text-[10px] text-[#f0f0fa] mt-1.5 line-clamp-2 leading-relaxed">
                        {req.landmark}
                      </p>

                      {/* Bottom Info: Souls & Coordinates */}
                      <div className="mt-2 pt-1.5 border-t border-[#3a3a3f] flex items-center justify-between text-[10px] font-mono">
                        <span className="text-white font-bold flex items-center gap-1 uppercase">
                          <Users className="w-3 h-3" />
                          {req.people_count} SOULS
                        </span>

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            copyCoordinates(req.coordinates);
                          }}
                          className="flex items-center gap-1 px-1.5 py-0.5 bg-black hover:bg-[#1a1a1f] text-[#5a5a5f] hover:text-white border border-[#3a3a3f] transition-colors font-mono uppercase"
                          title="Click to copy coordinates"
                        >
                          <Copy className="w-2.5 h-2.5" />
                          <span>
                            {req.coordinates[0].toFixed(3)}, {req.coordinates[1].toFixed(3)}
                          </span>
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* RIGHT COLUMN: SELECTED REQUEST DETAIL & TACTICAL GEO-CONTEXT (7 cols on lg/xl) */}
          <div className="lg:col-span-7 space-y-3.5">
            {/* Header Details Card */}
            <div className="p-4 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] shadow-none space-y-3.5">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="badge-chip font-mono text-[10px]">
                      TICKET #{selectedRequest.id}
                    </span>
                    <span className="badge-chip text-[10px]">
                      {selectedRequest.category.replace('_', ' ')}
                    </span>
                    <span
                      className={`badge-chip text-[10px] font-mono ${
                        selectedRequest.urgency === 'CRITICAL'
                          ? 'border-rose-600 text-rose-300'
                          : 'border-amber-600 text-amber-300'
                      }`}
                    >
                      {selectedRequest.urgency}
                    </span>
                  </div>

                  <h2 className="font-display text-lg font-bold text-white tracking-wider uppercase mt-1">
                    {selectedRequest.requester_name}
                  </h2>
                  <p className="font-mono text-xs text-[#5a5a5f] uppercase flex items-center gap-1.5 mt-0.5">
                    <MapPin className="w-3.5 h-3.5 text-white" />
                    {selectedRequest.location_name}
                  </p>
                </div>

                {/* Primary Action Buttons: Ghost Pill Style */}
                <div className="flex items-center gap-2">
                  {selectedRequest.status !== 'RESOLVED' && (
                    <button
                      onClick={handleResolve}
                      className="btn-ghost-pill text-xs !py-1.5 !px-4"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>MARK RESOLVED</span>
                    </button>
                  )}
                  <button
                    onClick={handleEscalate}
                    className="btn-ghost-pill-subtle text-xs !py-1.5 !px-3 border-amber-600 text-amber-300 hover:border-white hover:text-white"
                  >
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>ESCALATE</span>
                  </button>
                </div>
              </div>

              {/* Citizen Notes Box */}
              <div className="p-3 bg-black border border-[#3a3a3f] text-xs font-mono space-y-1">
                <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] block">
                  DISTRESS REPORT &amp; LANDMARK:
                </span>
                <p className="text-white leading-relaxed">
                  "{selectedRequest.landmark}"
                </p>
                <div className="pt-1 flex items-center justify-between text-[10px] text-[#5a5a5f]">
                  <span>CONTACT: <strong className="text-white">{selectedRequest.contact_number}</strong></span>
                  <span>BATTERY: <strong className="text-white">{selectedRequest.battery_level}%</strong></span>
                </div>
              </div>

              {/* Water Depth & Tactical Proximity Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs font-mono">
                <div className="p-2.5 bg-black border border-[#3a3a3f] space-y-0.5">
                  <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
                    <Waves className="w-3 h-3 text-white" />
                    WATER DEPTH
                  </span>
                  <div className="font-bold text-sm text-white">
                    {selectedRequest.estimated_water_depth || '1.4M'}
                  </div>
                  <p className="text-[9px] text-[#5a5a5f] uppercase">GROUND FLOOR SUBMERGED</p>
                </div>

                <div className="p-2.5 bg-black border border-[#3a3a3f] space-y-0.5">
                  <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
                    <Navigation className="w-3 h-3 text-white" />
                    SAFE SHELTER
                  </span>
                  <div className="font-bold text-xs text-white uppercase truncate">
                    {selectedRequest.nearest_shelter?.name || 'INARUWA SAFE HUB'}
                  </div>
                  <p className="text-[9px] text-[#5a5a5f] uppercase">
                    DIST: {selectedRequest.nearest_shelter?.distance || '800M'}
                  </p>
                </div>

                <div className="p-2.5 bg-black border border-[#3a3a3f] space-y-0.5">
                  <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
                    <Truck className="w-3 h-3 text-white" />
                    RESCUE BOAT
                  </span>
                  <div className="font-bold text-xs text-white uppercase truncate">
                    {selectedRequest.nearest_boat?.name || 'UNIT ALPHA-3 BOAT'}
                  </div>
                  <p className="text-[9px] text-[#5a5a5f] uppercase">
                    ETA: {selectedRequest.nearest_boat?.eta || '12 MINS'}
                  </p>
                </div>
              </div>
            </div>

            {/* Tactical Leaflet Mini-Map Zoomed onto Distress Point */}
            <div className="rounded-none bg-[#0a0a0a] border border-[#3a3a3f] overflow-hidden shadow-none">
              <div className="p-2.5 border-b border-[#3a3a3f] bg-[#000000] flex items-center justify-between text-xs font-mono">
                <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
                  <Compass className="w-3.5 h-3.5 text-white" />
                  TACTICAL EXTRACTION VICINITY MAP
                </span>
                <span className="text-[10px] text-[#5a5a5f] uppercase">
                  COORDS: {selectedRequest.coordinates[0].toFixed(3)}, {selectedRequest.coordinates[1].toFixed(3)}
                </span>
              </div>

              <div className="relative h-64 w-full bg-black">
                <MapContainer
                  center={selectedRequest.coordinates}
                  zoom={13}
                  scrollWheelZoom={false}
                  className="w-full h-full"
                >
                  <MapRecenter lat={selectedRequest.coordinates[0]} lng={selectedRequest.coordinates[1]} />
                  <TileLayer
                    attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
                    url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
                    maxZoom={16}
                  />

                  {/* Citizen Distress Point Marker */}
                  <Marker position={selectedRequest.coordinates} icon={citizenDistressIcon}>
                    <Popup>
                      <div className="p-1 font-mono text-xs">
                        <strong className="text-white block font-bold uppercase">{selectedRequest.requester_name}</strong>
                        <span>{selectedRequest.location_name}</span>
                        <div className="text-[10px] text-[#5a5a5f] mt-1">
                          DEPTH: {selectedRequest.estimated_water_depth} • {selectedRequest.people_count} SOULS
                        </div>
                      </div>
                    </Popup>
                  </Marker>

                  {/* Inundation Buffer Circle around distress point */}
                  <Circle
                    center={selectedRequest.coordinates}
                    radius={600}
                    pathOptions={{ color: '#ffffff', fillColor: '#ef4444', fillOpacity: 0.35, weight: 1.5 }}
                  />

                  {/* Active Rescue Boat Marker in proximity */}
                  <Marker
                    position={[selectedRequest.coordinates[0] - 0.012, selectedRequest.coordinates[1] + 0.008]}
                    icon={boatUnitIcon}
                  >
                    <Popup>
                      <div className="p-1 font-mono text-xs">
                        <strong className="text-white block font-bold uppercase">
                          {selectedRequest.nearest_boat?.name || 'Unit Alpha-3 (APF Rapid Boat)'}
                        </strong>
                        <div className="text-[10px] text-[#5a5a5f] mt-0.5">
                          ETA: {selectedRequest.nearest_boat?.eta || '12 mins'}
                        </div>
                      </div>
                    </Popup>
                  </Marker>

                  {/* Shelters in vicinity */}
                  {KOSHI_SHELTERS.map((sh) => (
                    <Marker key={sh.id} position={sh.coordinates} icon={shelterIcon}>
                      <Popup>
                        <div className="p-1 font-mono text-xs">
                          <strong className="text-white uppercase">{sh.name}</strong>
                          <div className="text-[10px] text-[#5a5a5f]">CAPACITY: {sh.capacity}</div>
                        </div>
                      </Popup>
                    </Marker>
                  ))}
                </MapContainer>

                {/* Map Floating HUD */}
                <div className="absolute bottom-2 right-2 z-[1000] px-2 py-1 bg-black border border-[#3a3a3f] text-[10px] font-mono text-white">
                  SURGE DEPTH: <strong className="text-white">{selectedRequest.estimated_water_depth || '1.4M'}</strong>
                </div>
              </div>
            </div>

            {/* Assigned Team Card & Dispatch Selection */}
            <div className="p-4 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] shadow-none space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                  <UserCheck className="w-3.5 h-3.5 text-white" />
                  ASSIGNED EXTRACTION SQUAD
                </h3>
                <span className="font-mono text-xs text-[#5a5a5f]">
                  STATUS: <strong className="text-white">{selectedRequest.status}</strong>
                </span>
              </div>

              {selectedRequest.assigned_unit ? (
                <div className="p-3 bg-black border border-[#3a3a3f] flex items-center justify-between font-mono">
                  <div>
                    <span className="text-xs font-bold text-white block uppercase">
                      {selectedRequest.assigned_unit}
                    </span>
                    <span className="text-[10px] text-[#5a5a5f] uppercase">
                      DISPATCHED WITH OUTBOARD MOTOR &amp; LIFE RAFTS
                    </span>
                  </div>
                  <span className="badge-chip border-white text-white text-[10px]">
                    EN ROUTE
                  </span>
                </div>
              ) : (
                <div className="space-y-2">
                  <span className="font-mono text-[10px] text-[#5a5a5f] uppercase block">
                    NO SQUAD ASSIGNED. SELECT FROM STAGING UNITS:
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 font-mono">
                    {availableRescueUnits.map((unit, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleAssignUnit(unit.name)}
                        className="p-2.5 bg-black hover:bg-[#141416] border border-[#3a3a3f] hover:border-white text-left transition-colors"
                      >
                        <div className="text-xs font-bold text-white uppercase truncate">
                          {unit.name}
                        </div>
                        <div className="flex items-center justify-between text-[10px] text-[#5a5a5f] mt-1">
                          <span>{unit.base.toUpperCase()}</span>
                          <span className="text-white font-bold">ETA: {unit.eta.toUpperCase()}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Audit Log / Ticket Activity Timeline */}
              <div className="pt-2 border-t border-[#3a3a3f] space-y-1.5 font-mono">
                <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] block">
                  INCIDENT AUDIT LOG:
                </span>
                <div className="space-y-1 text-xs">
                  {selectedRequest.activity_log?.map((log, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-[10px] text-[#f0f0fa]">
                      <span className="text-[#5a5a5f] w-16 flex-shrink-0">
                        {log.timestamp}
                      </span>
                      <span>&bull;</span>
                      <span className="flex-1 uppercase">{log.action}</span>
                      <span className="text-[#5a5a5f]">({log.author.toUpperCase()})</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Action Toast Notification */}
      {feedback && (
        <div className="fixed bottom-6 right-6 z-50 p-4 rounded-none bg-[#0a0a0a] border border-white text-white shadow-none animate-in slide-in-from-bottom-4 flex items-start gap-3 max-w-md font-mono">
          <CheckCircle className="w-5 h-5 text-white flex-shrink-0 mt-0.5" />
          <div className="text-xs">
            <h4 className="font-bold text-white uppercase">OPERATIONS DISPATCH LOGGED</h4>
            <p className="text-[#f0f0fa] mt-0.5">{feedback}</p>
          </div>
        </div>
      )}
    </div>
  );
};
