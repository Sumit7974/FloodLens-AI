import React, { useState } from 'react';
import {
  CheckCircle,
  FileText,
  X
} from 'lucide-react';
import type { HelpRequest } from '../types';
import { InteractiveHoverButton } from '@/components/ui/interactive-hover-button';

interface SosQueueProps {
  requests: HelpRequest[];
  onSelectIncident?: (requestId: string) => void;
  onHandoffToDeoc?: (requestId: string) => Promise<boolean> | boolean;
  onAssignRequest?: (requestId: string, unitName: string) => Promise<boolean> | boolean | void; // backwards compat
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

  const handleTriggerHandoff = async (reqId: string) => {
    if (!onHandoffToDeoc && !onAssignRequest) {
      setHandoffSuccessMsg('No approved backend handoff action is configured.');
      return;
    }
    try {
      const result = onHandoffToDeoc
        ? await onHandoffToDeoc(reqId)
        : await onAssignRequest?.(reqId, 'DEMO - authority review');
      if (result === false) {
        setHandoffSuccessMsg(`NOT SAVED: ${reqId}. Please check backend authentication and logs.`);
        return;
      }
      setHandoffSuccessMsg(`Demo/test acknowledgement recorded for ${reqId}. No external responder dispatch.`);
      setTimeout(() => {
        setHandoffSuccessMsg(null);
        setActiveDossierRequest(null);
      }, 3000);
    } catch (err) {
      setHandoffSuccessMsg(`NOT SAVED: ${err instanceof Error ? err.message : 'Backend update failed'}`);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'TRANSMITTED_TO_DEOC':
        return (
          <span className="px-3 py-1 rounded-full bg-sky-500/20 border border-sky-500/50 text-sky-300 text-xs font-mono font-bold tracking-wider">
            TRANSMITTED TO DEOC
          </span>
        );
      case 'SIMULATED_AUTHORITY_ACK':
      case 'ACKNOWLEDGED_BY_AUTHORITY':
        return (
          <span className="px-3 py-1 rounded-full bg-emerald-500/20 border border-emerald-500/50 text-emerald-300 text-xs font-mono font-bold tracking-wider">
            SIMULATED AUTHORITY ACK
          </span>
        );
      case 'RESOLVED':
        return (
          <span className="px-3 py-1 rounded-full bg-slate-500/20 border border-slate-500/50 text-slate-300 text-xs font-mono font-bold tracking-wider">
            RESOLVED
          </span>
        );
      default:
        return (
          <span className="px-3 py-1 rounded-full bg-rose-500/20 border border-rose-500/50 text-rose-300 text-xs font-mono font-bold tracking-wider">
            LOCAL LOGGED
          </span>
        );
    }
  };

  return (
    <>
      <div className="rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 overflow-hidden shadow-[0_4px_20px_rgba(0,0,0,0.5)] flex flex-col backdrop-blur-xl">
        {/* Header with Emergency Triage Accents */}
        <div className="px-4 py-3.5 border-b border-[#1e3a5f]/80 bg-[#091a32]/85 flex items-center justify-between">
          <div>
            <h3 className="font-display text-sm sm:text-base tracking-[1.4px] uppercase font-bold text-white flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#ef4444] animate-ping"></span>
              Citizen Assistance Queue
            </h3>
            <p className="font-mono text-xs text-[#38bdf8] uppercase mt-0.5 font-bold tracking-wider">
              AUTHORITY TRIAGE &amp; HANDOFF PIPELINE
            </p>
          </div>

          <span className="px-3 py-1 rounded-full bg-[#ef4444]/20 border border-[#ef4444]/40 text-[#fca5a5] text-xs font-mono font-bold flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse"></span>
            TOP 3 CRITICAL
          </span>
        </div>

        {/* SOS Request List */}
        <div className="p-3.5 space-y-2.5 flex-1">
          {topRequests.length === 0 ? (
            <div className="p-5 rounded-md bg-[#0a1b33]/60 border border-[#1e3a5f]/60 text-center flex flex-col items-center justify-center gap-2">
              <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">
                NO PENDING CITIZEN SOS BEACONS
              </span>
              <p className="font-mono text-[11px] text-slate-500 max-w-xs">
                Civilian queue is currently clear. Real-time beacons from mobile field clients will populate here automatically.
              </p>
            </div>
          ) : (
            topRequests.map((req) => {
            return (
              <div
                key={req.id}
                className="rounded-md p-3.5 bg-[#0c1c38]/75 border border-[#1e3a5f]/70 hover:border-[#38bdf8]/60 transition-all duration-200 flex items-center justify-between gap-3.5 shadow-sm"
              >
                <div className="space-y-1.5 min-w-0">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <h4 className="font-display text-base font-bold text-white tracking-wider uppercase truncate">
                      {req.requester_name}
                    </h4>
                    <span className="px-2.5 py-0.5 rounded bg-[#0284c7]/25 border border-[#0284c7]/50 text-[#38bdf8] font-mono text-xs font-bold">
                      {req.estimated_water_depth || 'DEPTH UNKNOWN'}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-[#e86e25]/20 border border-[#e86e25]/40 text-[#fed7aa] font-mono text-xs font-bold">
                      {req.category}
                    </span>
                  </div>
                  <p className="font-mono text-xs text-[#94a3b8] uppercase truncate flex items-center gap-1.5">
                    <span>📍</span> {req.location_name}
                  </p>
                  <div className="pt-1">
                    {getStatusBadge(req.handoff_status || req.status)}
                  </div>
                </div>

                <div className="relative flex-shrink-0">
                  <InteractiveHoverButton
                    text="VIEW INCIDENT"
                    onClick={() => handleOpenDossier(req)}
                    className="w-40 py-2 text-xs font-mono font-bold tracking-wider border-sky-500/50 bg-sky-950/40 text-sky-200 shadow-[0_0_10px_rgba(14,165,233,0.2)]"
                    dotColor="bg-sky-500 group-hover:bg-sky-500"
                  />
                </div>
              </div>
            );
          }))}
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
                  <h3 className="font-display text-base sm:text-lg font-bold text-white tracking-wider uppercase">
                    INCIDENT DOSSIER // #{activeDossierRequest.id}
                  </h3>
                  <p className="text-xs text-[#38bdf8] uppercase tracking-wider font-semibold">
                    DECISION-SUPPORT INTELLIGENCE &bull; ANONYMIZED
                  </p>
                </div>
              </div>
              <button
                onClick={() => setActiveDossierRequest(null)}
                className="text-slate-400 hover:text-white text-xl font-bold p-1 cursor-pointer"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            {/* Success Message Banner */}
            {handoffSuccessMsg && (
              <div className="p-3.5 rounded bg-emerald-500/20 border border-emerald-500/50 text-emerald-300 text-sm font-bold flex items-center gap-2.5">
                <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                <span>{handoffSuccessMsg}</span>
              </div>
            )}

            {/* Dossier Body */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 text-sm">
              <div className="p-3.5 rounded bg-black/60 border border-[#1e3a5f]/70 space-y-1.5">
                <span className="text-xs text-slate-300 font-bold uppercase block">Citizen Contact:</span>
                <span className="font-bold text-white text-base block">
                  {activeDossierRequest.requester_name}
                </span>
                <span className="text-xs text-slate-300">
                  Phone: {activeDossierRequest.contact_number}
                </span>
              </div>

              <div className="p-3.5 rounded bg-black/60 border border-[#1e3a5f]/70 space-y-1.5">
                <span className="text-xs text-slate-300 font-bold uppercase block">Verified Coordinates:</span>
                <span className="font-bold text-sky-300 text-sm block">
                  {activeDossierRequest.coordinates[0].toFixed(4)}°N, {activeDossierRequest.coordinates[1].toFixed(4)}°E
                </span>
                <span className="text-xs text-slate-300">
                  Elapsed: {activeDossierRequest.report_elapsed_time || activeDossierRequest.timestamp}
                </span>
              </div>

              <div className="p-3.5 rounded bg-black/60 border border-[#1e3a5f]/70 space-y-1.5 sm:col-span-2">
                <span className="text-xs text-slate-300 font-bold uppercase block">Location &amp; Landmark:</span>
                <span className="font-bold text-white text-sm block">
                  📍 {activeDossierRequest.location_name}
                </span>
                <p className="text-xs sm:text-sm text-slate-200 mt-1 leading-relaxed">
                  {activeDossierRequest.landmark}
                </p>
              </div>

              <div className="p-3.5 rounded bg-black/60 border border-[#1e3a5f]/70 space-y-1.5 sm:col-span-2">
                <span className="text-xs text-slate-300 font-bold uppercase block">Reported Needs &amp; Surrounding Inundation:</span>
                <p className="text-xs sm:text-sm text-amber-200 leading-relaxed">
                  {activeDossierRequest.notes}
                </p>
                <div className="pt-2 flex flex-wrap gap-2 text-xs">
                  <span className="px-3 py-1 rounded bg-sky-500/20 text-sky-300 border border-sky-500/40 font-bold">
                    Depth: {activeDossierRequest.estimated_water_depth || '1.8m DEM Estimate'}
                  </span>
                  <span className="px-3 py-1 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 font-bold">
                    Souls: {activeDossierRequest.people_count}
                  </span>
                  <span className="px-3 py-1 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40 font-bold">
                    Category: {activeDossierRequest.category}
                  </span>
                </div>
              </div>

              <div className="p-3.5 rounded bg-black/60 border border-[#1e3a5f]/70 space-y-1.5 sm:col-span-2">
                <span className="text-xs text-slate-300 font-bold uppercase block">High Ground &amp; Medical Facilities:</span>
                <div className="text-xs sm:text-sm space-y-1.5 text-slate-200">
                  <div>
                    &bull; Nearest Refuge:{' '}
                    <strong className="text-white font-bold">
                      {activeDossierRequest.nearest_shelter?.name || 'Inaruwa Safe Hub'}
                    </strong>{' '}
                    ({activeDossierRequest.nearest_shelter?.distance || '650m'})
                  </div>
                  {activeDossierRequest.nearest_highground && (
                    <div>
                      &bull; Dry High-Ground Spur:{' '}
                      <strong className="text-white font-bold">{activeDossierRequest.nearest_highground.name}</strong>{' '}
                      ({activeDossierRequest.nearest_highground.distance})
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Footer Actions */}
            <div className="flex items-center justify-between pt-3.5 border-t border-[#1e3a5f] flex-wrap gap-3">
              <div className="text-xs text-slate-300 font-mono">
                Current Status: {getStatusBadge(activeDossierRequest.handoff_status || activeDossierRequest.status)}
              </div>

              <div className="flex items-center gap-2.5">
                <button
                  onClick={() => setActiveDossierRequest(null)}
                  className="px-4 py-2 rounded-full border border-[#1e3a5f] hover:bg-white/10 text-xs sm:text-sm font-semibold text-slate-200 transition-colors cursor-pointer"
                >
                  CLOSE
                </button>

                <InteractiveHoverButton
                  text="PREPARE HANDOFF"
                  onClick={() => handleTriggerHandoff(activeDossierRequest.id)}
                  disabled={!!handoffSuccessMsg}
                  className="w-52 py-2 text-xs sm:text-sm font-mono font-bold tracking-wider border-orange-500/50 bg-orange-950/40 text-orange-200"
                  dotColor="bg-orange-500 group-hover:bg-orange-500"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
