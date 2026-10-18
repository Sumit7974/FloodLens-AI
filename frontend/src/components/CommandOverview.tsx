import React from 'react';
import type { Alert, BenchmarkScene, HelpRequest, MetricSummary } from '../types';
import { MapPreviewPanel } from './MapPreviewPanel';
import { MetricCards } from './MetricCards';
import { SosQueue } from './SosQueue';
import { WarningBulletins } from './WarningBulletins';

interface CommandOverviewProps {
  metrics: MetricSummary;
  benchmarkScene: BenchmarkScene;
  requests: HelpRequest[];
  alerts: Alert[];
  onAssignRequest: (requestId: string, unitName: string) => void;
  onBroadcastRevision: (alertId: string) => void;
}

export const CommandOverview: React.FC<CommandOverviewProps> = ({
  metrics,
  benchmarkScene,
  requests,
  alerts,
  onAssignRequest,
  onBroadcastRevision,
}) => {
  return (
    <div className="space-y-3.5">
      {/* Event Context Strip */}
      <div className="px-3.5 py-2 bg-[#0a0a0a] border border-[#27272a] flex flex-wrap items-center justify-between text-xs font-mono text-[#71717a]">
        <div className="flex items-center gap-2">
          <span className="font-bold text-white uppercase">BENCHMARK:</span>
          <span className="text-white uppercase">{benchmarkScene.name}</span>
          <span className="text-[#3a3a3f]">•</span>
          <span>{benchmarkScene.date_range.toUpperCase()}</span>
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <span>PEAK DISCHARGE: <strong className="text-white">{benchmarkScene.peak_discharge_m3s.toLocaleString()} M³/S</strong></span>
        </div>
      </div>

      {/* 4 Top Metric Cards */}
      <MetricCards metrics={metrics} />

      {/* Main Grid: 2-Column EOC Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* Left Column: Tactical Map Preview Panel */}
        <div className="lg:col-span-7 xl:col-span-7 h-full">
          <MapPreviewPanel />
        </div>

        {/* Right Column: Live Feeds */}
        <div className="lg:col-span-5 xl:col-span-5 space-y-3.5">
          {/* Urgent SOS Triage Queue (Top 3) */}
          <SosQueue requests={requests} onAssignRequest={onAssignRequest} />

          {/* Active Warning Bulletins */}
          <WarningBulletins alerts={alerts} onBroadcastRevision={onBroadcastRevision} />
        </div>
      </div>
    </div>
  );
};
