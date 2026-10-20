import React, { useState } from 'react';
import type { HelpRequest } from '../types';

interface SosQueueProps {
  requests: HelpRequest[];
  onAssignRequest?: (requestId: string, unitName: string) => void;
}

export const SosQueue: React.FC<SosQueueProps> = ({ requests, onAssignRequest }) => {
  const [assigningId, setAssigningId] = useState<string | null>(null);
  const [assignedUnits, setAssignedUnits] = useState<Record<string, string>>({});

  // Top 3 emergency requests as per requirement
  const topRequests = requests.slice(0, 3);

  const availableUnits = [
    'Motorized Rapid Boat Unit #02 (Chatara Base)',
    'NDRF Alpha Water Rescue Squad',
    'Nepal Army Amphibious Unit #05',
    'Armed Police Force (APF) Swift Boat',
    'Red Cross Emergency Medical Evac Van',
  ];

  const handleAssign = (requestId: string, unit: string) => {
    setAssignedUnits((prev) => ({ ...prev, [requestId]: unit }));
    setAssigningId(null);
    if (onAssignRequest) {
      onAssignRequest(requestId, unit);
    }
  };

  return (
    <div className="rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 overflow-hidden shadow-[0_4px_20px_rgba(0,0,0,0.5)] flex flex-col backdrop-blur-xl">
      {/* Header with Emergency Triage Accents */}
      <div className="px-4 py-3 border-b border-[#1e3a5f]/80 bg-[#091a32]/85 flex items-center justify-between">
        <div>
          <h3 className="font-display text-xs tracking-[1.4px] uppercase font-bold text-white flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#ef4444] animate-ping"></span>
            Citizen SOS Triage
          </h3>
          <p className="font-mono text-[10px] text-[#38bdf8] uppercase mt-0.5 font-semibold">
            AWAITING EXTRACTION UNIT ASSIGNMENT
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
          const currentUnit = assignedUnits[req.id] || req.assigned_unit;
          const isAssigned = !!currentUnit;

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
              </div>

              <div className="relative flex-shrink-0">
                {isAssigned ? (
                  <button
                    onClick={() => setAssigningId(assigningId === req.id ? null : req.id)}
                    className="px-2.5 py-1 rounded-full bg-[#10b981]/20 border border-[#10b981]/50 text-[#34d399] hover:bg-[#10b981]/30 text-[11px] font-mono font-bold transition-colors cursor-pointer"
                  >
                    REASSIGN
                  </button>
                ) : (
                  <button
                    onClick={() => setAssigningId(assigningId === req.id ? null : req.id)}
                    className="px-3.5 py-1.5 rounded-full bg-gradient-to-r from-[#e86e25] to-[#f97316] hover:from-[#d15d18] hover:to-[#ea580c] text-white text-[11px] font-bold font-mono uppercase tracking-wider border border-[#ff9d5c] shadow-[0_0_12px_rgba(232,110,37,0.4)] hover:scale-105 active:scale-95 transition-all cursor-pointer"
                  >
                    ASSIGN UNIT
                  </button>
                )}

                {/* Unit Selection Dropdown Popup */}
                {assigningId === req.id && (
                  <>
                    <div
                      className="fixed inset-0 z-30"
                      onClick={() => setAssigningId(null)}
                    />
                    <div className="absolute right-0 bottom-full mb-1 w-64 z-40 bg-[#0a0a0a] border border-[#27272a] p-2 shadow-2xl animate-in fade-in">
                      <div className="font-micro text-[10px] uppercase tracking-[1px] text-[#71717a] px-2 py-1 border-b border-[#27272a]">
                        DISPATCH RESCUE SQUAD
                      </div>
                      <div className="mt-1 space-y-1">
                        {availableUnits.map((unit) => (
                          <button
                            key={unit}
                            onClick={() => handleAssign(req.id, unit)}
                            className="w-full text-left px-2 py-1.5 text-[11px] font-mono text-[#f0f0fa] hover:text-white hover:bg-[#141416] transition-colors truncate block uppercase"
                          >
                            • {unit}
                          </button>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

