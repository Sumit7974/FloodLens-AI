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
      {/* Event Context Strip with Luminous Badges */}
      <div className="rounded-lg bg-gradient-to-r from-[#071326]/90 via-[#0b1e36]/85 to-[#071326]/90 border border-[#1e3a5f]/80 px-4 py-2.5 flex flex-wrap items-center justify-between text-xs font-mono shadow-[0_4px_16px_rgba(0,0,0,0.5)] gap-2">
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="px-2 py-0.5 rounded bg-[#38bdf8]/15 border border-[#38bdf8]/40 text-[#38bdf8] font-bold text-[10px] tracking-wider uppercase">
            EVENT SCENARIO
          </span>
          <span className="text-white font-bold text-xs uppercase tracking-wide">{benchmarkScene.name}</span>
          <span className="text-[#38bdf8]/40">•</span>
          <span className="text-[#94a3b8]">{benchmarkScene.date_range.toUpperCase()}</span>
        </div>
        <div className="flex items-center gap-2">
          <DataStatusBadge status={dataStatus} />
          <span className="px-2.5 py-1 rounded bg-[#e86e25]/20 border border-[#e86e25]/40 text-[#fdba74] font-bold text-[11px] font-mono flex items-center gap-1.5 shadow-[0_0_10px_rgba(232,110,37,0.2)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#e86e25] animate-pulse"></span>
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
            <span className="font-micro text-[10px] uppercase tracking-[1.2px] text-[#38bdf8] font-bold">
              3D GEOSPATIAL TERRAIN COMMAND // KOSHI BASIN
            </span>
            <span className="font-mono text-[10px] text-slate-400">
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
