import React, { useState } from 'react';
import {
  CheckCircle,
  Eye,
  FileText,
  Send,
  X
} from 'lucide-react';
import type { HelpRequest } from '../types';

interface SosQueueProps {
  requests: HelpRequest[];
  onSelectIncident?: (requestId: string) => void;
  onHandoffToDeoc?: (requestId: string) => void;
  onAssignRequest?: (requestId: string, unitName: string) => void; // backwards compat
}

export const SosQueue: React.FC<SosQueueProps> = ({
  requests,
  onSelectIncident,
  onHandoffToDeoc,
  onAssignRequest,
}) => {
  const [activeDossierRequest, setActiveDossierRequest] = useState<HelpRequest | null>(null);
  const [handoffSuccessMsg, setHandoffSuccessMsg] = useState<string | null>(null);

  // Top 3 emergency requests
  const topRequests = requests.slice(0, 3);

  const handleOpenDossier = (req: HelpRequest) => {
    setActiveDossierRequest(req);
    if (onSelectIncident) {
      onSelectIncident(req.id);
    }
  };

  const handleTriggerHandoff = (reqId: string) => {
    if (onHandoffToDeoc) {
      onHandoffToDeoc(reqId);
    } else if (onAssignRequest) {
      onAssignRequest(reqId, 'DEOC Sunsari District Operations');
    }

    setHandoffSuccessMsg(`Incident #${reqId} transmitted to District Emergency Operations Center (DEOC)`);
    setTimeout(() => {
      setHandoffSuccessMsg(null);
      setActiveDossierRequest(null);
    }, 2500);
  };

  const getStatusBadge = (status: string) => {
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
    <>
      <div className="rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 overflow-hidden shadow-[0_4px_20px_rgba(0,0,0,0.5)] flex flex-col backdrop-blur-xl">
        {/* Header with Emergency Triage Accents */}
        <div className="px-4 py-3 border-b border-[#1e3a5f]/80 bg-[#091a32]/85 flex items-center justify-between">
          <div>
            <h3 className="font-display text-xs tracking-[1.4px] uppercase font-bold text-white flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#ef4444] animate-ping"></span>
              Citizen Assistance Queue
            </h3>
            <p className="font-mono text-[10px] text-[#38bdf8] uppercase mt-0.5 font-semibold">
              AUTHORITY TRIAGE &amp; HANDOFF PIPELINE
            </p>
          </div>

          <span className="px-2.5 py-0.5 rounded-full bg-[#ef4444]/20 border border-[#ef4444]/40 text-[#fca5a5] text-[10px] font-mono font-bold flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse"></span>
            TOP 3 CRITICAL
          </span>
        </div>

        {/* SOS Request List */}
        <div className="p-3 space-y-2 flex-1">
          {topRequests.map((req) => {
            return (
              <div
                key={req.id}
                className="rounded-md p-3 bg-[#0c1c38]/75 border border-[#1e3a5f]/70 hover:border-[#38bdf8]/60 transition-all duration-200 flex items-center justify-between gap-3 shadow-sm"
              >
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="font-display text-sm font-bold text-white tracking-wider uppercase truncate">
                      {req.requester_name}
                    </h4>
                    <span className="px-2 py-0.5 rounded bg-[#0284c7]/25 border border-[#0284c7]/50 text-[#38bdf8] font-mono text-[11px] font-semibold">
                      {req.estimated_water_depth || '1.8M DEPTH'}
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-[#e86e25]/20 border border-[#e86e25]/40 text-[#fed7aa] font-mono text-[10px] font-bold">
                      {req.category}
                    </span>
                  </div>
                  <p className="font-mono text-[10px] text-[#94a3b8] uppercase truncate flex items-center gap-1">
                    <span>📍</span> {req.location_name}
                  </p>
                  <div className="pt-0.5">
                    {getStatusBadge(req.handoff_status || req.status)}
                  </div>
                </div>

                <div className="relative flex-shrink-0">
                  <button
                    onClick={() => handleOpenDossier(req)}
                    className="px-3.5 py-1.5 rounded-full bg-gradient-to-r from-sky-600 to-blue-600 hover:from-sky-500 hover:to-blue-500 text-white text-[11px] font-bold font-mono uppercase tracking-wider border border-sky-400/60 shadow-[0_0_12px_rgba(56,189,248,0.35)] hover:scale-105 active:scale-95 transition-all cursor-pointer flex items-center gap-1.5"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>VIEW INCIDENT</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Incident Review Dossier Modal / Drawer */}
      {activeDossierRequest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-xl rounded-lg bg-[#071326] border border-[#1e3a5f] p-5 shadow-[0_12px_48px_rgba(0,0,0,0.85)] space-y-4 font-mono text-white">
            {/* Header */}
            <div className="flex items-start justify-between pb-3 border-b border-[#1e3a5f]">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded bg-sky-500/20 border border-sky-500/40 text-sky-400">
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-display text-sm font-bold text-white tracking-wider uppercase">
                    INCIDENT DOSSIER // #{activeDossierRequest.id}
                  </h3>
                  <p className="text-[10px] text-[#38bdf8] uppercase tracking-wider">
                    DECISION-SUPPORT INTELLIGENCE &bull; ANONYMIZED
                  </p>
                </div>
              </div>
              <button
                onClick={() => setActiveDossierRequest(null)}
                className="text-slate-400 hover:text-white text-lg font-bold p-1 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Success Message Banner */}
            {handoffSuccessMsg && (
              <div className="p-3 rounded bg-emerald-500/20 border border-emerald-500/50 text-emerald-300 text-xs font-bold flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                <span>{handoffSuccessMsg}</span>
              </div>
            )}

            {/* Dossier Body */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded bg-black/60 border border-[#1e3a5f]/70 space-y-1">
                <span className="text-[10px] text-slate-400 uppercase block">Citizen Contact:</span>
                <span className="font-bold text-white text-sm block">
                  {activeDossierRequest.requester_name}
                </span>
                <span className="text-[10px] text-slate-400">
                  Phone: {activeDossierRequest.contact_number}
                </span>
              </div>

              <div className="p-3 rounded bg-black/60 border border-[#1e3a5f]/70 space-y-1">
                <span className="text-[10px] text-slate-400 uppercase block">Verified Coordinates:</span>
                <span className="font-bold text-sky-300 text-xs block">
                  {activeDossierRequest.coordinates[0].toFixed(4)}°N, {activeDossierRequest.coordinates[1].toFixed(4)}°E
                </span>
                <span className="text-[10px] text-slate-400">
                  Elapsed: {activeDossierRequest.report_elapsed_time || activeDossierRequest.timestamp}
                </span>
              </div>

              <div className="p-3 rounded bg-black/60 border border-[#1e3a5f]/70 space-y-1 sm:col-span-2">
                <span className="text-[10px] text-slate-400 uppercase block">Location &amp; Landmark:</span>
                <span className="font-bold text-white text-xs block">
                  📍 {activeDossierRequest.location_name}
                </span>
                <p className="text-[11px] text-slate-300 mt-1">
                  {activeDossierRequest.landmark}
                </p>
              </div>

              <div className="p-3 rounded bg-black/60 border border-[#1e3a5f]/70 space-y-1 sm:col-span-2">
                <span className="text-[10px] text-slate-400 uppercase block">Reported Needs &amp; Surrounding Inundation:</span>
                <p className="text-[11px] text-amber-200">
                  {activeDossierRequest.notes}
                </p>
                <div className="pt-2 flex flex-wrap gap-2 text-[10px]">
                  <span className="px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/40">
                    Depth: {activeDossierRequest.estimated_water_depth || '1.8m DEM Estimate'}
                  </span>
                  <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40">
                    Souls: {activeDossierRequest.people_count}
                  </span>
                  <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40">
                    Category: {activeDossierRequest.category}
                  </span>
                </div>
              </div>

              <div className="p-3 rounded bg-black/60 border border-[#1e3a5f]/70 space-y-1 sm:col-span-2">
                <span className="text-[10px] text-slate-400 uppercase block">High Ground &amp; Medical Facilities:</span>
                <div className="text-[11px] space-y-1 text-slate-300">
                  <div>
                    &bull; Nearest Refuge:{' '}
                    <strong className="text-white">
                      {activeDossierRequest.nearest_shelter?.name || 'Inaruwa Safe Hub'}
                    </strong>{' '}
                    ({activeDossierRequest.nearest_shelter?.distance || '650m'})
                  </div>
                  {activeDossierRequest.nearest_highground && (
                    <div>
                      &bull; Dry High-Ground Spur:{' '}
                      <strong className="text-white">{activeDossierRequest.nearest_highground.name}</strong>{' '}
                      ({activeDossierRequest.nearest_highground.distance})
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Footer Actions */}
            <div className="flex items-center justify-between pt-3 border-t border-[#1e3a5f] flex-wrap gap-2">
              <div className="text-[10px] text-slate-400">
                Current Status: {getStatusBadge(activeDossierRequest.handoff_status || activeDossierRequest.status)}
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setActiveDossierRequest(null)}
                  className="px-3 py-1.5 rounded-full border border-[#1e3a5f] hover:bg-white/10 text-xs text-slate-300 transition-colors cursor-pointer"
                >
                  CLOSE
                </button>

                <button
                  onClick={() => handleTriggerHandoff(activeDossierRequest.id)}
                  disabled={!!handoffSuccessMsg}
                  className="px-4 py-1.5 rounded-full bg-gradient-to-r from-[#e86e25] to-[#f97316] hover:from-[#d15d18] hover:to-[#ea580c] text-white text-xs font-bold tracking-wider uppercase border border-[#ff9d5c] shadow-[0_0_12px_rgba(232,110,37,0.4)] transition-all cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>PREPARE AUTHORITY HANDOFF</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
