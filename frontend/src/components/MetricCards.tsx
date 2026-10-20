import React from 'react';
import { AlertTriangle, Users, LifeBuoy, Activity } from 'lucide-react';
import type { MetricSummary } from '../types';

interface MetricCardsProps {
  metrics: MetricSummary;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ metrics }) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3.5">
      {/* 1. Flood Threat Level: Vibrant Safety Orange & Emergency Ruby Theme */}
      <div className="rounded-lg bg-gradient-to-br from-[#1c0d0a]/90 via-[#10192b]/85 to-[#081020]/90 border border-[#e86e25]/50 hover:border-[#e86e25] p-4 flex flex-col justify-between h-full space-y-3 shadow-[0_4px_20px_rgba(232,110,37,0.18)] transition-all duration-200 hover:shadow-[0_4px_25px_rgba(232,110,37,0.3)]">
        <div className="flex items-center justify-between">
          <span className="font-micro text-[11px] uppercase tracking-[1.2px] text-[#fb923c] font-bold flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-[#e86e25]" />
            SURGE THREAT LEVEL
          </span>
          <span className="w-2 h-2 rounded-full bg-[#e86e25] animate-ping"></span>
        </div>
        <div>
          <h3 className="font-display text-3xl font-bold text-white tracking-wider uppercase flex items-baseline gap-2">
            <span>{metrics.floodThreat.level}</span>
            <span className="text-xs px-2 py-0.5 rounded bg-[#e86e25]/25 border border-[#e86e25]/60 text-[#fed7aa] font-mono font-semibold">
              HIGH
            </span>
          </h3>
        </div>
        <p className="font-mono text-[11px] text-[#fdba74] uppercase pt-2 border-t border-[#e86e25]/25 truncate">
          Chatara &gt; 8.15m // {metrics.floodThreat.trendLabel.toUpperCase()}
        </p>
      </div>

      {/* 2. Population at Risk: Electric Cyan & Deep Ocean Hydro Theme */}
      <div className="rounded-lg bg-gradient-to-br from-[#061e33]/90 via-[#0a1e35]/85 to-[#081020]/90 border border-[#0ea5e9]/50 hover:border-[#0ea5e9] p-4 flex flex-col justify-between h-full space-y-3 shadow-[0_4px_20px_rgba(14,165,233,0.18)] transition-all duration-200 hover:shadow-[0_4px_25px_rgba(14,165,233,0.3)]">
        <div className="flex items-center justify-between">
          <span className="font-micro text-[11px] uppercase tracking-[1.2px] text-[#38bdf8] font-bold flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5 text-[#0ea5e9]" />
            POPULATION AT RISK
          </span>
          <span className="w-2 h-2 rounded-full bg-[#0ea5e9]"></span>
        </div>
        <div>
          <h3 className="font-display text-3xl font-bold text-white tracking-wider uppercase">
            {metrics.populationAtRisk.total.toLocaleString()}
          </h3>
        </div>
        <p className="font-mono text-[11px] text-[#7dd3fc] uppercase pt-2 border-t border-[#0ea5e9]/25 truncate">
          14 wards threatened // 3 critical reaches
        </p>
      </div>

      {/* 3. Open Assistance Requests: Amber Warning & Rescue Beacon Theme */}
      <div className="rounded-lg bg-gradient-to-br from-[#211707]/90 via-[#181d2d]/85 to-[#081020]/90 border border-[#f59e0b]/50 hover:border-[#f59e0b] p-4 flex flex-col justify-between h-full space-y-3 shadow-[0_4px_20px_rgba(245,158,11,0.18)] transition-all duration-200 hover:shadow-[0_4px_25px_rgba(245,158,11,0.3)]">
        <div className="flex items-center justify-between">
          <span className="font-micro text-[11px] uppercase tracking-[1.2px] text-[#fbbf24] font-bold flex items-center gap-1.5">
            <LifeBuoy className="w-3.5 h-3.5 text-[#f59e0b]" />
            OPEN ASSISTANCE QUEUE
          </span>
          <span className="px-2 py-0.5 rounded-full bg-[#f59e0b]/20 border border-[#f59e0b]/50 text-[#fde68a] text-[10px] font-mono font-bold">
            ACTIVE
          </span>
        </div>
        <div>
          <h3 className="font-display text-3xl font-bold text-white tracking-wider uppercase">
            {metrics.openRequests.total} <span className="text-xs font-semibold text-[#fde68a]">QUEUED</span>
          </h3>
        </div>
        <p className="font-mono text-[11px] text-[#fde68a] uppercase pt-2 border-t border-[#f59e0b]/25 truncate">
          {metrics.openRequests.critical} critical // 7 extraction units
        </p>
      </div>

      {/* 4. Sensor Health: Luminous Emerald & Vital Nominal Status Theme */}
      <div className="rounded-lg bg-gradient-to-br from-[#06241a]/90 via-[#0a1f29]/85 to-[#081020]/90 border border-[#10b981]/50 hover:border-[#10b981] p-4 flex flex-col justify-between h-full space-y-3 shadow-[0_4px_20px_rgba(16,185,129,0.18)] transition-all duration-200 hover:shadow-[0_4px_25px_rgba(16,185,129,0.3)]">
        <div className="flex items-center justify-between">
          <span className="font-micro text-[11px] uppercase tracking-[1.2px] text-[#34d399] font-bold flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-[#10b981]" />
            TELEMETRY GAUGES
          </span>
          <span className="px-2 py-0.5 rounded-full bg-[#10b981]/20 border border-[#10b981]/50 text-[#a7f3d0] text-[10px] font-mono font-bold flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            LIVE
          </span>
        </div>
        <div>
          <h3 className="font-display text-3xl font-bold text-white tracking-wider uppercase">
            {metrics.sensorHealth.reporting}/{metrics.sensorHealth.total} <span className="text-xs font-semibold text-[#a7f3d0]">REPORTING</span>
          </h3>
        </div>
        <p className="font-mono text-[11px] text-[#a7f3d0] uppercase pt-2 border-t border-[#10b981]/25 truncate">
          All feeds nominal // 28ms latency
        </p>
      </div>
    </div>
  );
};

