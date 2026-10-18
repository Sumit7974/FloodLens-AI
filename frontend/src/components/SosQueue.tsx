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
    <div className="rounded-none bg-[#0a0a0a] border border-[#27272a] overflow-hidden shadow-none flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#27272a] bg-[#000000] flex items-center justify-between">
        <div>
          <h3 className="font-display text-xs tracking-[1.4px] uppercase font-bold text-white">
            Citizen SOS Triage
          </h3>
          <p className="font-mono text-[10px] text-[#71717a] uppercase mt-0.5">
            AWAITING EXTRACTION UNIT ASSIGNMENT
          </p>
        </div>

        <span className="font-mono text-[10px] text-[#71717a] uppercase">
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
              className="p-3 bg-black border border-[#27272a] hover:border-[#3a3a3f] transition-colors flex items-center justify-between gap-3"
            >
              <div className="space-y-0.5 min-w-0">
                <div className="flex items-center gap-2">
                  <h4 className="font-display text-sm font-bold text-white tracking-wider uppercase truncate">
                    {req.requester_name}
                  </h4>
                  <span className="font-mono text-xs text-[#a0a0aa]">
                    // {req.estimated_water_depth || '1.8M DEPTH'}
                  </span>
                </div>
                <p className="font-mono text-[10px] text-[#71717a] uppercase truncate">
                  {req.location_name}
                </p>
              </div>

              <div className="relative flex-shrink-0">
                {isAssigned ? (
                  <button
                    onClick={() => setAssigningId(assigningId === req.id ? null : req.id)}
                    className="btn-ghost-pill-subtle text-[10px] !py-1 !px-2.5 font-mono"
                  >
                    REASSIGN
                  </button>
                ) : (
                  <button
                    onClick={() => setAssigningId(assigningId === req.id ? null : req.id)}
                    className="btn-ghost-pill text-[11px] !py-1.5 !px-3 font-mono"
                  >
                    ASSIGN
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

