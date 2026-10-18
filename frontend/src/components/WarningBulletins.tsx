import React, { useState } from 'react';
import {
  AlertOctagon,
  CheckCircle2,
  MapPin,
  Radio,
  Send,
} from 'lucide-react';
import type { Alert } from '../types';

interface WarningBulletinsProps {
  alerts: Alert[];
  onBroadcastRevision?: (alertId: string) => void;
}

export const WarningBulletins: React.FC<WarningBulletinsProps> = ({
  alerts,
  onBroadcastRevision,
}) => {
  const [activeAlertIndex, setActiveAlertIndex] = useState(0);
  const latestAlert = alerts[activeAlertIndex] || alerts[0];

  return (
    <div className="rounded-none bg-[#0a0a0a] border border-[#27272a] overflow-hidden shadow-none flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#27272a] bg-[#000000] flex items-center justify-between">
        <div>
          <h3 className="font-display text-xs tracking-[1.4px] uppercase font-bold text-white flex items-center gap-2">
            Civil Warning Bulletins
            <span className="font-mono text-[10px] text-[#71717a]">
              // {alerts.length} BROADCAST
            </span>
          </h3>
          <p className="font-mono text-[10px] text-[#71717a] uppercase mt-0.5">
            PUBLIC EMERGENCY DIRECTIVES
          </p>
        </div>

        {/* Tab switchers if multiple alerts */}
        {alerts.length > 1 && (
          <div className="flex items-center gap-1 bg-black p-0.5 border border-[#27272a]">
            {alerts.map((_, idx) => (
              <button
                key={idx}
                onClick={() => setActiveAlertIndex(idx)}
                className={`px-2 py-0.5 text-[10px] font-mono uppercase font-bold transition-colors ${
                  activeAlertIndex === idx
                    ? 'bg-white text-black'
                    : 'text-[#5a5a5f] hover:text-white'
                }`}
              >
                #{idx + 1}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Main Alert Content */}
      <div className="p-3.5 space-y-3 flex-1">
        {/* Severity Banner */}
        <div className="p-3 bg-black border border-[#3a3a3f] flex items-start gap-2.5">
          <AlertOctagon className="w-4 h-4 text-white flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-1 flex-wrap">
              <span className="badge-chip border-rose-600 text-rose-300 text-[10px] font-mono">
                {latestAlert.severity} // {latestAlert.code}
              </span>
              <span className="text-[10px] font-mono text-white flex items-center gap-1 uppercase">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                BROADCAST CONFIRMED
              </span>
            </div>
            <h4 className="font-display text-xs font-bold text-white mt-1.5 leading-snug tracking-wider uppercase">
              {latestAlert.headline}
            </h4>
            <p className="font-mono text-[10px] text-[#f0f0fa] mt-1 leading-relaxed">
              {latestAlert.description}
            </p>
          </div>
        </div>

        {/* Key Dispatch Metadata Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
          {/* Target Geofence */}
          <div className="p-2 bg-black border border-[#3a3a3f] space-y-0.5">
            <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
              <MapPin className="w-3 h-3 text-white" />
              TARGET GEOFENCE
            </span>
            <p className="font-bold text-white text-[11px] uppercase truncate">
              {latestAlert.geofence}
            </p>
          </div>

          {/* Dispatch Time */}
          <div className="p-2 bg-black border border-[#3a3a3f] space-y-0.5">
            <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
              <Radio className="w-3 h-3 text-white" />
              DISPATCH TIMESTAMP
            </span>
            <p className="font-bold text-white text-[11px] uppercase">
              {latestAlert.dispatched_at}
            </p>
          </div>
        </div>

        {/* Channels Broadcasted */}
        <div className="space-y-1 pt-1">
          <span className="font-micro text-[10px] uppercase tracking-[0.96px] text-[#5a5a5f]">
            ACTIVE PROPAGATION CHANNELS:
          </span>
          <div className="flex flex-wrap gap-1.5">
            {latestAlert.channels.map((ch, idx) => (
              <span
                key={idx}
                className="badge-chip border-[#3a3a3f] text-[#f0f0fa] text-[10px] font-mono"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-white"></span>
                {ch}
              </span>
            ))}
          </div>
        </div>

        {/* Footer: Approver & Action Button */}
        <div className="pt-2 border-t border-[#3a3a3f] flex items-center justify-between text-[11px] font-mono">
          <span className="text-[#5a5a5f] truncate max-w-[220px] uppercase">
            AUTHORITY: <strong className="text-white">{latestAlert.approved_by}</strong>
          </span>

          <button
            onClick={() => onBroadcastRevision && onBroadcastRevision(latestAlert.id)}
            className="btn-ghost-pill-subtle text-[10px] !py-1 !px-3 font-mono"
          >
            <Send className="w-3 h-3" />
            DISPATCH REVISION
          </button>
        </div>
      </div>
    </div>
  );
};
