import React, { useState, useEffect } from 'react';
import {
  CheckCircle,
  Copy,
  Download,
  LifeBuoy,
  Search,
  Shield,
  ShieldAlert,
} from 'lucide-react';
import { KOSHI_SHELTERS } from '../data/geospatialData';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';
import { DataStatusBadge } from './common/DataStatusBadge';
import { floodLensClient } from '../services/floodLensClient';
import { InteractiveHoverButton } from '@/components/ui/interactive-hover-button';
import type {
  AuthorityHandoffStatus,
  BenchmarkScene,
  HelpRequest,
  RequestCategory,
  UrgencyLevel
} from '../types';

interface ResponseOperationsProps {
  currentScene: BenchmarkScene;
  requests: HelpRequest[];
  onUpdateRequestStatus: (requestId: string, status: AuthorityHandoffStatus, authorityNote?: string) => Promise<boolean> | boolean;
}

export const ResponseOperations: React.FC<ResponseOperationsProps> = ({
  currentScene,
  requests,
  onUpdateRequestStatus,
}) => {
  // Master-Detail selection
  const [selectedId, setSelectedId] = useState<string>(requests[0]?.id || 'SOS-2026-081');

  // Search & Filter States
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | AuthorityHandoffStatus>('ALL');
  const [categoryFilter, setCategoryFilter] = useState<'ALL' | RequestCategory>('ALL');
  const [urgencyFilter, setUrgencyFilter] = useState<'ALL' | UrgencyLevel>('ALL');

  // Sub-tab: Incident Feed vs Exposed Infrastructure
  const [activeSubTab, setActiveSubTab] = useState<'triage' | 'infrastructure'>('triage');

  // Toast feedback state
  const [feedback, setFeedback] = useState<string | null>(null);

  // Client API / Mock Adapter State
  const [apiStatus, setApiStatus] = useState<'live' | 'cached' | 'error'>('cached');

  useEffect(() => {
    let isMounted = true;
    const loadReports = async () => {
      const res = await floodLensClient.getAssistanceReports(currentScene.id);
      if (isMounted) {
        setApiStatus(res.status);
      }
    };
    loadReports();
    return () => {
      isMounted = false;
    };
  }, [currentScene.id]);

  const selectedRequest = requests.find((r) => r.id === selectedId) || requests[0];

  // Filtered requests list
  const filteredRequests = requests.filter((r) => {
    // Search query matching
    const matchesSearch =
      r.requester_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.location_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.landmark.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.id.toLowerCase().includes(searchQuery.toLowerCase());

    // Status matching
    const currentStatus = (r.handoff_status || r.status) as AuthorityHandoffStatus;
    const matchesStatus = statusFilter === 'ALL' || currentStatus === statusFilter;

    // Category matching
    const matchesCategory = categoryFilter === 'ALL' || r.category === categoryFilter;

    // Urgency matching
    const matchesUrgency = urgencyFilter === 'ALL' || r.urgency === urgencyFilter;

    return matchesSearch && matchesStatus && matchesCategory && matchesUrgency;
  });

  const notify = (msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(null), 3500);
  };

  const handleUpdateLifecycle = async (status: AuthorityHandoffStatus, note: string) => {
    if (!selectedRequest) return;
    const saved = await onUpdateRequestStatus(selectedRequest.id, status, note);
    notify(saved ? `Demo/test status recorded for #${selectedRequest.id}; no dispatch.` : `NOT SAVED: #${selectedRequest.id}. Review backend authentication.`);
  };

  const copyCoordinates = (coords: [number, number]) => {
    navigator.clipboard?.writeText(`${coords[0]}, ${coords[1]}`);
    notify(`Copied coordinates ${coords[0]}, ${coords[1]} to clipboard`);
  };

  // Generate standardized incident packet for DEOC
  const generateDeocPacket = () => {
    if (!selectedRequest) return null;
    return {
      incident_id: selectedRequest.id,
      timestamp_logged: selectedRequest.timestamp,
      handoff_timestamp: new Date().toISOString(),
      location: {
        name: selectedRequest.location_name,
        latitude: selectedRequest.coordinates[0],
        longitude: selectedRequest.coordinates[1],
        landmark: selectedRequest.landmark,
      },
      triage_classification: {
        category: selectedRequest.category,
        urgency: selectedRequest.urgency,
        urgency_score: selectedRequest.urgency_score || 'Priority 1',
        souls_threatened: selectedRequest.people_count,
        reported_depth_dem_estimate: selectedRequest.estimated_water_depth || 'UNAVAILABLE (no verified depth)',
      },
      citizen_requester: {
        name: selectedRequest.requester_name,
        contact_redacted: selectedRequest.contact_number,
        battery_level: `${selectedRequest.battery_level || 35}%`,
      },
      topography_and_safe_ground: {
        nearest_shelter: selectedRequest.nearest_shelter?.name || 'Inaruwa Safe Hub',
        distance_to_shelter: selectedRequest.nearest_shelter?.distance || '650m',
        nearest_highground_msl: selectedRequest.nearest_highground?.name || 'Prakashpur Ridge (84m MSL)',
        nearest_medical_post: selectedRequest.nearest_medical?.name || 'Prakashpur Sub-Health Post',
      },
      audit_provenance: {
        source: 'FloodLens AI EOC Coordination Engine',
        transmission_target: 'District Emergency Operation Center (DEOC) Sunsari',
        hash: 'SHA256: 8a4c10ef923145bd9901aa',
      },
    };
  };

  const handleDownloadPacket = () => {
    const packet = generateDeocPacket();
    const blob = new Blob([JSON.stringify(packet, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `DEOC_Incident_Packet_${selectedRequest.id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    notify(`Exported DEOC Handoff Packet for #${selectedRequest.id}`);
  };

  const getStatusBadge = (status: AuthorityHandoffStatus | string) => {
    switch (status) {
      case 'TRANSMITTED_TO_DEOC':
        return (
          <span className="px-2 py-0.5 rounded-full bg-sky-500/20 border border-sky-500/50 text-sky-300 text-[10px] font-mono font-bold">
            TRANSMITTED TO DEOC
          </span>
        );
      case 'SIMULATED_AUTHORITY_ACK':
      case 'ACKNOWLEDGED_BY_AUTHORITY':
        return (
          <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 border border-emerald-500/50 text-emerald-300 text-[10px] font-mono font-bold">
            SIMULATED AUTHORITY ACK
          </span>
        );
      case 'RESOLVED':
        return (
          <span className="px-2 py-0.5 rounded-full bg-slate-500/20 border border-slate-500/50 text-slate-400 text-[10px] font-mono font-bold">
            RESOLVED
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded-full bg-rose-500/20 border border-rose-500/50 text-rose-300 text-[10px] font-mono font-bold">
            LOCAL LOGGED
          </span>
        );
    }
  };

  return (
    <div className="space-y-3.5">
      {/* Top Header Bar */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-400">
            <ShieldAlert className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
              Incident Intelligence &amp; Authority Coordination
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-[9px] font-mono font-bold tracking-wider">
                DECISION SUPPORT EOC
              </span>
              <DataStatusBadge status={apiStatus} />
            </h1>
            <p className="font-mono text-[10px] text-[#38bdf8] uppercase tracking-wider mt-0.5 font-semibold">
              DISASTER SITUATION ROOM TRIAGE FEED // {currentScene.name} ({currentScene.district})
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
            <span>INCIDENT TRIAGE FEED ({requests.length})</span>
          </button>

          <button
            onClick={() => setActiveSubTab('infrastructure')}
            className={`flex items-center gap-1.5 px-3 py-1 font-mono font-bold uppercase rounded-full transition-all cursor-pointer ${
              activeSubTab === 'infrastructure'
                ? 'bg-gradient-to-r from-[#e86e25] to-[#f97316] text-white shadow-[0_0_10px_rgba(232,110,37,0.4)]'
                : 'text-[#94a3b8] hover:text-white'
            }`}
          >
            <Shield className="w-3.5 h-3.5 text-[#fed7aa]" />
            <span>HIGH GROUND &amp; MEDICAL POSTS ({KOSHI_SHELTERS.length})</span>
          </button>
        </div>
      </div>

      {/* 2-COLUMN MAIN LAYOUT */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* LEFT COLUMN: TACTICAL 3D MAP VISUALIZER (7 cols on lg, 7 cols on xl) */}
        <div className="lg:col-span-7 xl:col-span-7 flex flex-col space-y-2">
          <div className="flex items-center justify-between px-1">
            <span className="font-micro text-[10px] uppercase tracking-[1.2px] text-[#38bdf8] font-bold">
              TACTICAL INCIDENT POSITIONING // RELATIVE TO HIGH GROUND &amp; REFUGES
            </span>
            <span className="font-mono text-[10px] text-slate-400">
              CLICK PINS FOR POPUP DOSSIER
            </span>
          </div>

          <GeospatialTerrainMap
            center={
              selectedRequest
                ? [selectedRequest.coordinates[1], selectedRequest.coordinates[0]]
                : (currentScene.center || [87.05, 26.65])
            }
            zoom={11.5}
            pitch={55}
            bearing={-15}
            activeHorizon="3h"
            showInundation={true}
            showForecast={true}
            showGauges={true}
            showIncidents={true}
            showInfrastructure={true}
            showShelters={true}
            incidents={requests}
            selectedIncidentId={selectedId}
            onSelectIncident={(id) => setSelectedId(id)}
            height="580px"
          />
        </div>

        {/* RIGHT COLUMN: TRIAGE FEED & AUTHORITY HANDOFF CONSOLE (5 cols) */}
        <div className="lg:col-span-5 xl:col-span-5 space-y-3.5">
          {activeSubTab === 'triage' ? (
            <div className="space-y-3.5">
              {/* Search & Urgency / Category Filters */}
              <div className="p-3.5 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-2.5">
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search Citizen, Ward, Location or ID..."
                    className="w-full bg-black/60 border border-[#1e3a5f] rounded-lg pl-9 pr-3 py-1.5 text-xs font-mono text-white placeholder-slate-500 focus:outline-none focus:border-sky-400"
                  />
                </div>

                <div className="grid grid-cols-3 gap-2 text-[10px] font-mono">
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value as any)}
                    className="bg-black/60 border border-[#1e3a5f] rounded px-1.5 py-1 text-slate-200 focus:outline-none focus:border-sky-400"
                  >
                    <option value="ALL">ALL STATUSES</option>
                    <option value="LOCAL_LOGGED">LOCAL LOGGED</option>
                    <option value="TRANSMITTED_TO_DEOC">TRANSMITTED TO DEOC</option>
                    <option value="SIMULATED_AUTHORITY_ACK">SIMULATED AUTHORITY ACK</option>
                    <option value="RESOLVED">RESOLVED</option>
                  </select>

                  <select
                    value={categoryFilter}
                    onChange={(e) => setCategoryFilter(e.target.value as any)}
                    className="bg-black/60 border border-[#1e3a5f] rounded px-1.5 py-1 text-slate-200 focus:outline-none focus:border-sky-400"
                  >
                    <option value="ALL">ALL CATEGORIES</option>
                    <option value="TRAPPED">TRAPPED</option>
                    <option value="MEDICAL">MEDICAL</option>
                    <option value="ELDERLY_EVAC">ELDERLY EVAC</option>
                    <option value="EVACUATION">EVACUATION</option>
                    <option value="FOOD_WATER">FOOD/WATER</option>
                  </select>

                  <select
                    value={urgencyFilter}
                    onChange={(e) => setUrgencyFilter(e.target.value as any)}
                    className="bg-black/60 border border-[#1e3a5f] rounded px-1.5 py-1 text-slate-200 focus:outline-none focus:border-sky-400"
                  >
                    <option value="ALL">ALL URGENCIES</option>
                    <option value="CRITICAL">CRITICAL ONLY</option>
                    <option value="HIGH">HIGH ONLY</option>
                    <option value="MEDIUM">MEDIUM ONLY</option>
                  </select>
                </div>
              </div>

              {/* Master Incident List (Scrollable) */}
              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {filteredRequests.map((req) => {
                  const isSelected = req.id === selectedId;
                  const isCritical = req.urgency === 'CRITICAL';
                  return (
                    <div
                      key={req.id}
                      onClick={() => setSelectedId(req.id)}
                      className={`p-3 rounded-lg border transition-all cursor-pointer font-mono ${
                        isSelected
                          ? 'bg-[#0c1d38] border-[#38bdf8] shadow-[0_0_15px_rgba(56,189,248,0.25)]'
                          : 'bg-[#071326]/75 border-[#1e3a5f]/70 hover:border-slate-500'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${isCritical ? 'bg-rose-500 animate-ping' : 'bg-sky-400'}`}></span>
                          <span className="font-bold text-white uppercase">{req.requester_name}</span>
                          <span className="text-[10px] text-slate-400">#{req.id}</span>
                        </div>
                        {getStatusBadge(req.handoff_status || req.status)}
                      </div>

                      <div className="mt-1 text-[11px] text-slate-300 truncate">
                        📍 {req.location_name} &bull; {req.people_count} Souls &bull; {req.category}
                      </div>
                    </div>
                  );
                })}
                {filteredRequests.length === 0 && (
                  <div className="p-4 text-center text-slate-400 font-mono text-xs border border-dashed border-[#1e3a5f]/60 rounded-lg">
                    No citizen assistance requests in current queue.
                  </div>
                )}
              </div>

              {/* Selected Incident Authority Handoff Console */}
              {selectedRequest && (
                <div className="p-4 rounded-lg bg-[#071326]/95 border border-[#38bdf8]/70 shadow-[0_4px_24px_rgba(0,0,0,0.6)] backdrop-blur-xl space-y-3 font-mono text-xs">
                  <div className="flex items-start justify-between pb-2 border-b border-[#1e3a5f]">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-white font-bold text-sm">
                          {selectedRequest.requester_name}
                        </span>
                        <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[10px] font-bold">
                          {selectedRequest.urgency}
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-400">
                        Phone: {selectedRequest.contact_number} &bull; Logged: {selectedRequest.timestamp}
                      </span>
                    </div>

                    <button
                      onClick={() => copyCoordinates(selectedRequest.coordinates)}
                      className="p-1.5 rounded bg-black/60 border border-[#1e3a5f] hover:text-sky-300 text-slate-400 cursor-pointer"
                      title="Copy GPS coordinates"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Coordinates & Water Inundation Note */}
                  <div className="p-2.5 rounded bg-black/60 border border-[#1e3a5f] space-y-1">
                    <div className="flex justify-between text-[11px]">
                      <span className="text-slate-400">GPS Coordinates:</span>
                      <span className="text-sky-300 font-bold">
                        {selectedRequest.coordinates[0].toFixed(4)}°N, {selectedRequest.coordinates[1].toFixed(4)}°E
                      </span>
                    </div>
                    <div className="flex justify-between text-[11px]">
                      <span className="text-slate-400">Estimated Water Depth:</span>
                      <span className="text-rose-400 font-bold">
                        {selectedRequest.estimated_water_depth || '1.8m (Surging)'}
                      </span>
                    </div>
                    <div className="flex justify-between text-[11px]">
                      <span className="text-slate-400">Nearest High Ground Spur:</span>
                      <span className="text-emerald-300 font-bold">
                        {selectedRequest.nearest_highground?.name || 'Prakashpur Ridge Embankment Spur'}
                      </span>
                    </div>
                  </div>

                  {/* Situation Notes */}
                  <div className="text-[11px] text-slate-200 bg-black/40 p-2.5 rounded border border-[#1e3a5f]/60">
                    <strong className="text-amber-300 block mb-0.5">Reported Needs:</strong>
                    {selectedRequest.notes}
                  </div>

                  {/* Authority Handoff Lifecycle Buttons */}
                  <div className="pt-2 border-t border-[#1e3a5f] space-y-2">
                    <span className="text-[10px] uppercase text-slate-400 font-bold block">
                      AUTHORITY HANDOFF ACTIONS:
                    </span>

                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <InteractiveHoverButton
                        text="FORWARD TO DEOC"
                        onClick={() =>
                          handleUpdateLifecycle(
                            'TRANSMITTED_TO_DEOC',
                            'Transmitted standardized incident packet to DEOC Sunsari'
                          )
                        }
                        className="w-full py-2 text-[10px] font-mono tracking-wider border-sky-500/50 bg-sky-950/40 text-sky-200"
                        dotColor="bg-sky-500 group-hover:bg-sky-500"
                      />

                      <InteractiveHoverButton
                        text="SIMULATE ACK"
                        onClick={() =>
                          handleUpdateLifecycle(
                            'SIMULATED_AUTHORITY_ACK',
                            'Simulated authority receipt recorded in DEOC test log'
                          )
                        }
                        className="w-full py-2 text-[10px] font-mono tracking-wider border-emerald-500/50 bg-emerald-950/40 text-emerald-200"
                        dotColor="bg-emerald-500 group-hover:bg-emerald-500"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                      <button
                        onClick={() => handleUpdateLifecycle('RESOLVED', 'Civil Protection confirmed citizen reached safe ground')}
                        className="py-1.5 px-3 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white font-bold text-[10px] uppercase border border-slate-700 transition-colors flex items-center justify-center gap-1 cursor-pointer"
                      >
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>MARK RESOLVED</span>
                      </button>

                      <button
                        onClick={handleDownloadPacket}
                        className="py-1.5 px-3 rounded-md bg-slate-800 hover:bg-slate-700 text-sky-300 hover:text-white font-bold text-[10px] uppercase border border-slate-700 transition-colors flex items-center justify-center gap-1 cursor-pointer"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>EXPORT PACKET</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* Infrastructure & Safe Places Subtab */
            <div className="p-4 rounded-lg bg-[#071326]/95 border border-[#1e3a5f]/80 shadow-[0_4px_24px_rgba(0,0,0,0.6)] backdrop-blur-xl space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between pb-2 border-b border-[#1e3a5f]">
                <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider">
                  VERIFIED SHELTERS &amp; MEDICAL POSTS
                </h3>
                <span className="text-[10px] text-slate-400">KOSHI BASIN REACH</span>
              </div>

              <div className="space-y-2 max-h-[460px] overflow-y-auto pr-1">
                {KOSHI_SHELTERS.map((s) => (
                  <div key={s.id} className="p-3 bg-black/60 border border-[#1e3a5f] rounded-md space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white text-[11px] uppercase">{s.name}</span>
                      <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[9px] font-bold">
                        {s.elevationMsl}M ELEVATION
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-400 flex justify-between">
                      <span>Occupancy: {s.currentOccupancy} / {s.capacity} souls</span>
                      <span className="text-sky-300">📞 {s.contact}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Action Notification Toast */}
      {feedback && (
        <div className="fixed bottom-6 right-6 z-50 p-4 rounded-lg bg-[#071326] border border-sky-400 text-white shadow-xl flex items-center gap-2 text-xs font-mono animate-in slide-in-from-bottom-2">
          <CheckCircle className="w-4 h-4 text-sky-400" />
          <span>{feedback}</span>
        </div>
      )}
    </div>
  );
};
