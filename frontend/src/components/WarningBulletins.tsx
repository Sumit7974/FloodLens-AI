import React, { useState } from 'react';
import {
  AlertOctagon,
  CheckCircle2,
  MapPin,
  Radio,
} from 'lucide-react';
import type { Alert } from '../types';
import { InteractiveHoverButton } from '@/components/ui/interactive-hover-button';

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
    <div className="rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 overflow-hidden shadow-[0_4px_20px_rgba(0,0,0,0.5)] flex flex-col backdrop-blur-xl">
      {/* Header with Directive Accents */}
      <div className="px-4 py-3.5 border-b border-[#1e3a5f]/80 bg-[#091a32]/85 flex items-center justify-between">
        <div>
          <h3 className="font-display text-sm sm:text-base tracking-[1.4px] uppercase font-bold text-white flex items-center gap-2.5">
            <Radio className="w-4 h-4 text-[#e86e25] animate-pulse" />
            Civil Warning Bulletins
            <span className="font-mono text-xs text-[#38bdf8] font-bold">
              // {alerts.length} BROADCAST
            </span>
          </h3>
          <p className="font-mono text-xs text-[#94a3b8] uppercase mt-0.5 font-bold tracking-wider">
            PUBLIC EMERGENCY DIRECTIVES
          </p>
        </div>

        {/* Tab switchers if multiple alerts */}
        {alerts.length > 1 && (
          <div className="flex items-center gap-1.5 bg-[#060e1d] p-1 border border-[#1e3a5f] rounded-md">
            {alerts.map((_, idx) => (
              <button
                key={idx}
                onClick={() => setActiveAlertIndex(idx)}
                className={`px-2.5 py-1 text-xs font-mono uppercase font-bold transition-all rounded ${
                  activeAlertIndex === idx
                    ? 'bg-[#e86e25] text-white shadow-sm'
                    : 'text-[#94a3b8] hover:text-white'
                }`}
              >
                #{idx + 1}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Main Alert Content */}
      <div className="p-4 space-y-3.5 flex-1">
        {/* Severity Banner with Vibrant Emergency Gradient */}
        <div className="p-4 rounded-md bg-gradient-to-br from-[#2a0e10]/85 via-[#1b152d]/80 to-[#0c1628]/90 border border-rose-500/50 shadow-[0_0_15px_rgba(244,63,94,0.18)] flex items-start gap-3.5">
          <AlertOctagon className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5 animate-pulse" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="px-3 py-1 rounded-full bg-rose-500/25 border border-rose-500/50 text-rose-200 text-xs font-mono font-bold tracking-wider uppercase">
                {latestAlert.severity} // {latestAlert.code}
              </span>
              <span className="text-xs font-mono text-emerald-300 flex items-center gap-1.5 uppercase font-bold bg-emerald-500/15 px-2.5 py-1 rounded border border-emerald-500/30">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                SIMULATED BROADCAST LOGGED
              </span>
            </div>
            <h4 className="font-display text-base font-bold text-white mt-2 leading-snug tracking-wider uppercase">
              {latestAlert.headline}
            </h4>
            <p className="font-mono text-sm text-[#cbd5e1] mt-1.5 leading-relaxed">
              {latestAlert.description}
            </p>
          </div>
        </div>

        {/* Key Dispatch Metadata Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs font-mono">
          {/* Target Geofence */}
          <div className="p-3 rounded bg-[#0c1d38]/75 border border-[#1e3a5f]/70 space-y-1">
            <span className="font-micro text-xs uppercase tracking-[1px] text-[#38bdf8] font-bold flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 text-[#38bdf8]" />
              TARGET GEOFENCE
            </span>
            <p className="font-bold text-white text-xs sm:text-sm uppercase truncate">
              {latestAlert.geofence}
            </p>
          </div>

          {/* Dispatch Time */}
          <div className="p-3 rounded bg-[#0c1d38]/75 border border-[#1e3a5f]/70 space-y-1">
            <span className="font-micro text-xs uppercase tracking-[1px] text-[#34d399] font-bold flex items-center gap-1.5">
              <Radio className="w-3.5 h-3.5 text-[#34d399]" />
              DISPATCH TIMESTAMP
            </span>
            <p className="font-bold text-white text-xs sm:text-sm uppercase">
              {latestAlert.dispatched_at}
            </p>
          </div>
        </div>

        {/* Channels Broadcasted */}
        <div className="space-y-1.5 pt-1">
          <span className="font-micro text-xs uppercase tracking-[1px] text-[#94a3b8] font-bold">
            ACTIVE PROPAGATION CHANNELS:
          </span>
          <div className="flex flex-wrap gap-2">
            {latestAlert.channels.map((ch, idx) => (
              <span
                key={idx}
                className="px-2.5 py-1 rounded-full bg-[#0284c7]/20 border border-[#0284c7]/40 text-[#7dd3fc] text-xs font-mono font-bold flex items-center gap-1.5"
              >
                <span className="w-2 h-2 rounded-full bg-[#38bdf8]"></span>
                {ch}
              </span>
            ))}
          </div>
        </div>

        {/* Footer: Approver & Action Button */}
        <div className="pt-2.5 border-t border-[#1e3a5f]/80 flex items-center justify-between text-xs font-mono">
          <span className="text-[#94a3b8] truncate max-w-[220px] uppercase font-medium">
            AUTHORITY: <strong className="text-white font-bold">{latestAlert.approved_by}</strong>
          </span>

          <InteractiveHoverButton
            text="DRAFT REVISION"
            onClick={() => onBroadcastRevision && onBroadcastRevision(latestAlert.id)}
            className="w-40 py-2 text-xs font-mono font-bold tracking-wider border-sky-500/50 bg-sky-950/40 text-sky-200 shadow-[0_0_10px_rgba(14,165,233,0.2)]"
            dotColor="bg-sky-500 group-hover:bg-sky-500"
          />
        </div>
      </div>
    </div>
  );
};
