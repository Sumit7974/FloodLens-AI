import React, { useState, useEffect } from 'react';
import type { Alert, BenchmarkScene, HelpRequest, MetricSummary } from '../types';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';
import { MetricCards } from './MetricCards';
import { SosQueue } from './SosQueue';
import { WarningBulletins } from './WarningBulletins';
import { DataStatusBadge } from './common/DataStatusBadge';
import { floodLensClient } from '../services/floodLensClient';

interface CommandOverviewProps {
  metrics: MetricSummary;
  benchmarkScene: BenchmarkScene;
  requests: HelpRequest[];
  alerts: Alert[];
  onHandoffRequest?: (requestId: string) => void;
  onAssignRequest?: (requestId: string, unitName: string) => void; // backwards compat
  onBroadcastRevision: (alertId: string) => void;
}

export const CommandOverview: React.FC<CommandOverviewProps> = ({
  metrics,
  benchmarkScene,
  requests,
  alerts,
  onHandoffRequest,
  onAssignRequest,
  onBroadcastRevision,
}) => {
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [dataStatus, setDataStatus] = useState<'live' | 'cached' | 'error'>('cached');

  useEffect(() => {
    let isMounted = true;
    floodLensClient.getEventDetail(benchmarkScene.id).then((res) => {
      if (isMounted && res.status) {
        setDataStatus(res.status);
      }
    });
    return () => {
      isMounted = false;
    };
  }, [benchmarkScene.id]);

  return (
    <div className="space-y-3.5">
      {/* Event Context Strip with Sleek Minimalist Dividers */}
      <div className="rounded-xl bg-[#0a0a0a] border border-zinc-800 px-5 py-3 flex flex-wrap items-center justify-between text-sm font-mono shadow-sm gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-zinc-900 border border-zinc-700 text-zinc-300 uppercase tracking-wider">
            EVENT SCENARIO
          </span>
          <span className="text-white font-bold text-sm sm:text-base tracking-normal">{benchmarkScene.name}</span>
          <span className="text-zinc-600 select-none">·</span>
          <span className="text-zinc-300 font-medium text-xs sm:text-sm">{benchmarkScene.date_range.toUpperCase()}</span>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <DataStatusBadge status={dataStatus} />
          <span className="text-zinc-600 select-none">|</span>
          <span className="text-zinc-200 font-bold text-xs sm:text-sm font-mono flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse shadow-[0_0_8px_rgba(245,158,11,0.6)]" />
            <span>PEAK DISCHARGE: {benchmarkScene.peak_discharge_m3s.toLocaleString()} M³/S</span>
          </span>
        </div>
      </div>

      {/* 4 Top Clean Decision Metrics Cards */}
      <MetricCards metrics={metrics} />

      {/* Main Grid: 2-Column EOC Tactical Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* Left Column: Reusable 3D Geospatial Terrain Map (7 cols on lg, 7 cols on xl) */}
        <div className="lg:col-span-7 xl:col-span-7 flex flex-col space-y-2">
          <div className="flex items-center justify-between px-1">
            <span className="font-micro text-xs uppercase tracking-[1.4px] text-[#38bdf8] font-bold">
              3D GEOSPATIAL TERRAIN COMMAND // KOSHI BASIN
            </span>
            <span className="font-mono text-xs text-slate-300 font-medium">
              DEM TERRAIN 1.5X &bull; REAL SETTLEMENTS MAPPED
            </span>
          </div>

          <GeospatialTerrainMap
            center={benchmarkScene.center || [87.05, 26.65]}
            zoom={benchmarkScene.zoom || 10.8}
            pitch={benchmarkScene.pitch || 55}
            bearing={benchmarkScene.bearing || -15}
            activeHorizon="3h"
            showInundation={true}
            showForecast={true}
            showGauges={true}
            showIncidents={true}
            showInfrastructure={true}
            showShelters={true}
            incidents={requests}
            selectedIncidentId={selectedIncidentId}
            onSelectIncident={(id) => setSelectedIncidentId(id)}
            height="560px"
          />
        </div>

        {/* Right Column: Live Incident Intelligence & Warning Bulletins */}
        <div className="lg:col-span-5 xl:col-span-5 space-y-3.5">
          {/* Urgent Citizen Assistance Queue (Top 3) */}
          <SosQueue
            requests={requests}
            onSelectIncident={(id) => setSelectedIncidentId(id)}
            onHandoffToDeoc={onHandoffRequest}
            onAssignRequest={onAssignRequest}
          />

          {/* Active Warning Bulletins */}
          <WarningBulletins alerts={alerts} onBroadcastRevision={onBroadcastRevision} />
        </div>
      </div>
    </div>
  );
};
