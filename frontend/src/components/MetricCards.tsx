import React from 'react';
import { AlertTriangle, Users, LifeBuoy, Activity } from 'lucide-react';
import type { MetricSummary } from '../types';

interface MetricCardsProps {
  metrics: MetricSummary;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ metrics }) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-4">
      {/* 1. Flood Threat Level */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md p-4 sm:p-5 h-full flex flex-col justify-between transition-colors shadow-sm">
        {/* Header Section */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <span className="text-xs font-semibold tracking-wider uppercase text-zinc-400 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />
            <span>SURGE THREAT LEVEL</span>
          </span>
          <span className="flex h-2 w-2 relative shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
          </span>
        </div>

        {/* Value Section */}
        <div className="my-auto py-1">
          <div className="text-3xl sm:text-4xl font-extrabold tracking-tight font-mono text-white uppercase">
            {metrics.floodThreat.level}
          </div>
        </div>

        {/* Footer Section */}
        <div className="text-[11px] font-medium text-zinc-400 tracking-wide mt-2 pt-2 border-t border-zinc-800/40 flex items-center justify-between">
          <span className="whitespace-nowrap truncate" title={metrics.floodThreat.description}>
            Chatara: 8.18m / Danger: 8.00m — Elevated
          </span>
        </div>
      </div>

      {/* 2. Population at Risk */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md p-4 sm:p-5 h-full flex flex-col justify-between transition-colors shadow-sm">
        {/* Header Section */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <span className="text-xs font-semibold tracking-wider uppercase text-zinc-400 flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            <span>EXPOSED POPULATION</span>
          </span>
          <span className="w-2 h-2 rounded-full bg-cyan-400 shrink-0" />
        </div>

        {/* Value Section */}
        <div className="my-auto py-1">
          <div className="text-3xl sm:text-4xl font-extrabold tracking-tight font-mono text-white">
            ~{metrics.populationAtRisk.total.toLocaleString()}
          </div>
        </div>

        {/* Footer Section */}
        <div className="text-[11px] font-medium text-zinc-400 tracking-wide mt-2 pt-2 border-t border-zinc-800/40 flex items-center justify-between">
          <span className="whitespace-nowrap truncate" title="Calculated from overlay of DEM flood envelope onto ward settlement census">
            DEM flood envelope overlay onto census
          </span>
        </div>
      </div>

      {/* 3. Open Assistance Requests */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md p-4 sm:p-5 h-full flex flex-col justify-between transition-colors shadow-sm">
        {/* Header Section */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <span className="text-xs font-semibold tracking-wider uppercase text-zinc-400 flex items-center gap-1.5">
            <LifeBuoy className="w-3.5 h-3.5 text-rose-400 shrink-0" />
            <span>ASSISTANCE REPORTS</span>
          </span>
          <span className="text-[10px] font-mono font-medium text-rose-400 shrink-0">
            {metrics.openRequests.critical > 0 ? `${metrics.openRequests.critical} CRITICAL` : 'ACTIVE'}
          </span>
        </div>

        {/* Value Section */}
        <div className="my-auto py-1">
          <div className="text-3xl sm:text-4xl font-extrabold tracking-tight font-mono text-white flex items-baseline gap-2">
            <span>{metrics.openRequests.total}</span>
            <span className="text-sm font-sans font-semibold text-zinc-400 uppercase">LOGGED</span>
          </div>
        </div>

        {/* Footer Section */}
        <div className="text-[11px] font-medium text-zinc-400 tracking-wide mt-2 pt-2 border-t border-zinc-800/40 flex items-center justify-between">
          <span className="whitespace-nowrap truncate">
            {metrics.openRequests.total} Reports · {metrics.openRequests.critical} Critical Risk
          </span>
        </div>
      </div>

      {/* 4. Telemetry Health */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md p-4 sm:p-5 h-full flex flex-col justify-between transition-colors shadow-sm">
        {/* Header Section */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <span className="text-xs font-semibold tracking-wider uppercase text-zinc-400 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>TELEMETRY UPLINK</span>
          </span>
          <span className="inline-flex items-center gap-1 text-[10px] font-mono text-emerald-400 font-medium shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            ONLINE
          </span>
        </div>

        {/* Value Section */}
        <div className="my-auto py-1">
          <div className="text-3xl sm:text-4xl font-extrabold tracking-tight font-mono text-white flex items-baseline gap-2">
            <span>{metrics.sensorHealth.reporting}/{metrics.sensorHealth.total}</span>
            <span className="text-sm font-sans font-semibold text-zinc-400 uppercase">ACTIVE</span>
          </div>
        </div>

        {/* Footer Section */}
        <div className="text-[11px] font-medium text-zinc-400 tracking-wide mt-2 pt-2 border-t border-zinc-800/40 flex items-center justify-between">
          <span className="whitespace-nowrap truncate" title="12/12 Gauges Online [LoRa/Gov Hydro]">
            12/12 Gauges Online · LoRa &amp; Gov Hydro
          </span>
        </div>
      </div>
    </div>
  );
};

