import React from 'react';
import type { MetricSummary } from '../types';

interface MetricCardsProps {
  metrics: MetricSummary;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ metrics }) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
      {/* 1. Flood Threat Level */}
      <div className="bg-[#0a0a0a] border border-[#27272a] p-4 flex flex-col justify-between h-full space-y-3">
        <span className="font-micro text-[11px] uppercase tracking-[1.2px] text-[#71717a] block">
          SURGE THREAT LEVEL
        </span>
        <div>
          <h3 className="font-display text-3xl font-bold text-white tracking-wider uppercase">
            {metrics.floodThreat.level}
          </h3>
        </div>
        <p className="font-mono text-[11px] text-[#71717a] uppercase pt-2 border-t border-[#1f1f23] truncate">
          Chatara &gt; 8.15m // {metrics.floodThreat.trendLabel.toUpperCase()}
        </p>
      </div>

      {/* 2. Population at Risk */}
      <div className="bg-[#0a0a0a] border border-[#27272a] p-4 flex flex-col justify-between h-full space-y-3">
        <span className="font-micro text-[11px] uppercase tracking-[1.2px] text-[#71717a] block">
          POPULATION AT RISK
        </span>
        <div>
          <h3 className="font-display text-3xl font-bold text-white tracking-wider uppercase">
            {metrics.populationAtRisk.total.toLocaleString()}
          </h3>
        </div>
        <p className="font-mono text-[11px] text-[#71717a] uppercase pt-2 border-t border-[#1f1f23] truncate">
          14 wards threatened // 3 critical reaches
        </p>
      </div>

      {/* 3. Open Assistance Requests */}
      <div className="bg-[#0a0a0a] border border-[#27272a] p-4 flex flex-col justify-between h-full space-y-3">
        <span className="font-micro text-[11px] uppercase tracking-[1.2px] text-[#71717a] block">
          OPEN ASSISTANCE QUEUE
        </span>
        <div>
          <h3 className="font-display text-3xl font-bold text-white tracking-wider uppercase">
            {metrics.openRequests.total} <span className="text-xs font-normal text-[#71717a]">ACTIVE</span>
          </h3>
        </div>
        <p className="font-mono text-[11px] text-[#71717a] uppercase pt-2 border-t border-[#1f1f23] truncate">
          {metrics.openRequests.critical} critical // 7 extraction units
        </p>
      </div>

      {/* 4. Sensor Health */}
      <div className="bg-[#0a0a0a] border border-[#27272a] p-4 flex flex-col justify-between h-full space-y-3">
        <span className="font-micro text-[11px] uppercase tracking-[1.2px] text-[#71717a] block">
          TELEMETRY GAUGES
        </span>
        <div>
          <h3 className="font-display text-3xl font-bold text-white tracking-wider uppercase">
            {metrics.sensorHealth.reporting}/{metrics.sensorHealth.total} <span className="text-xs font-normal text-[#71717a]">ONLINE</span>
          </h3>
        </div>
        <p className="font-mono text-[11px] text-[#71717a] uppercase pt-2 border-t border-[#1f1f23] truncate">
          All feeds nominal // 28ms latency
        </p>
      </div>
    </div>
  );
};

