import React, { useState, useEffect } from 'react';
import type { Alert, BenchmarkScene, HelpRequest, MetricSummary } from '../types';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';
import { MetricCards } from './MetricCards';
import { SosQueue } from './SosQueue';
import { WarningBulletins } from './WarningBulletins';
import { DataStatusBadge } from './common/DataStatusBadge';
import { floodLensClient } from '../services/floodLensClient';
import { DEMO_MODE, listHistoricalEvents, getObservedExtent, getSettlementExposure, getAssetExposure, type FloodEventRecord, type ObservedExtentFeature, type SettlementExposureResponse, type AssetExposureResponse } from '../services/backendApi';

interface CommandOverviewProps {
  metrics: MetricSummary;
  benchmarkScene: BenchmarkScene;
  requests: HelpRequest[];
  alerts: Alert[];
  onHandoffRequest?: (requestId: string) => Promise<boolean> | boolean;
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
  const [backendEvents, setBackendEvents] = useState<FloodEventRecord[]>([]);
  const [selectedEventId, setSelectedEventId] = useState('');
  const [observedExtent, setObservedExtent] = useState<ObservedExtentFeature | null>(null);
  const [settlements, setSettlements] = useState<SettlementExposureResponse | null>(null);
  const [assets, setAssets] = useState<AssetExposureResponse | null>(null);
  const [backendEventError, setBackendEventError] = useState('');
  const [extentError, setExtentError] = useState('');

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

  useEffect(() => {
    if (DEMO_MODE) return;
    let active = true;
    listHistoricalEvents().then(events => {
      if (!active) return;
      setBackendEvents(events);
      setSelectedEventId(prev => events.some(e => e.id === prev) ? prev : (events[0]?.id || ''));
      setBackendEventError(events.length === 0 ? 'No historical/test flood events have been imported into FastAPI yet.' : '');
    }).catch(error => {
      if (active) setBackendEventError(error instanceof Error ? error.message : 'Could not list backend events');
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (DEMO_MODE || !selectedEventId) {
      setObservedExtent(null);
      setSettlements(null);
      setAssets(null);
      return;
    }
    let active = true;
    setObservedExtent(null);
    setSettlements(null);
    setAssets(null);
    setExtentError('');
    Promise.allSettled([
      getObservedExtent(selectedEventId),
      getSettlementExposure(selectedEventId),
      getAssetExposure(selectedEventId),
    ]).then(([extentResult, settlementResult, assetResult]) => {
      if (!active) return;
      if (extentResult.status === 'fulfilled') setObservedExtent(extentResult.value);
      else setExtentError(extentResult.reason instanceof Error ? extentResult.reason.message : 'No observed extent is available for this event');
      if (settlementResult.status === 'fulfilled') setSettlements(settlementResult.value);
      if (assetResult.status === 'fulfilled') setAssets(assetResult.value);
    });
    return () => { active = false; };
  }, [selectedEventId]);

  const selectedBackendEvent = backendEvents.find(event => event.id === selectedEventId);

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
          {DEMO_MODE && (
            <span className="text-zinc-200 font-bold text-xs sm:text-sm font-mono flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse shadow-[0_0_8px_rgba(245,158,11,0.6)]" />
              <span>DEMO PEAK DISCHARGE: {benchmarkScene.peak_discharge_m3s.toLocaleString()} M³/S</span>
            </span>
          )}
        </div>
      </div>

      {!DEMO_MODE && (
        <section aria-label="Backend historical event evidence" className="space-y-2 rounded-lg border border-sky-800/60 bg-slate-950/80 p-3 text-sm text-slate-200">
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="backend-event-selector" className="font-semibold">FastAPI historical event:</label>
            <select
              id="backend-event-selector"
              value={selectedEventId}
              onChange={event => setSelectedEventId(event.target.value)}
              className="min-w-56 max-w-full rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-slate-100"
            >
              {backendEvents.length === 0 && <option value="">No imported historical events</option>}
              {backendEvents.map(event => <option key={event.id} value={event.id}>{event.name} · {event.start_at.slice(0, 10)}</option>)}
            </select>
            <span className="text-xs text-slate-400">This selector uses database event IDs, not built-in benchmark scene IDs.</span>
          </div>
          {backendEventError && <p role="status" className="text-amber-300">{backendEventError}</p>}
          {selectedBackendEvent && (
            <p className="text-xs text-slate-400">
              Region: {selectedBackendEvent.region_id} · Event: {selectedBackendEvent.start_at} · Mode: {selectedBackendEvent.mode}
            </p>
          )}
          {extentError && <p role="status" className="text-amber-300">Flood extent unavailable: {extentError}</p>}
          <div className="grid gap-2 sm:grid-cols-4">
            <div className="rounded border border-slate-800 p-2"><div className="text-slate-500 text-[11px] uppercase">Mapped flood area</div><strong>{observedExtent ? `${observedExtent.properties.area_km2} km²` : 'Unavailable'}</strong></div>
            <div className="rounded border border-slate-800 p-2"><div className="text-slate-500 text-[11px] uppercase">Intersecting settlements</div><strong>{settlements?.status === 'completed' ? settlements.total_settlements_affected : 'Unavailable'}</strong></div>
            <div className="rounded border border-slate-800 p-2"><div className="text-slate-500 text-[11px] uppercase">Roads exposed</div><strong>{assets?.status === 'completed' ? `${assets.roads_exposed_km} km` : 'Unavailable'}</strong></div>
            <div className="rounded border border-slate-800 p-2"><div className="text-slate-500 text-[11px] uppercase">Structures exposed</div><strong>{assets?.status === 'completed' ? assets.structures_exposed_count : 'Unavailable'}</strong></div>
          </div>
          {observedExtent && (
            <p className="text-xs text-sky-200">
              Flood extent loaded from PostGIS via FastAPI · Observation: {observedExtent.properties.observed_at}
              · Method: {observedExtent.properties.method}
              · Satellite scene IDs: {observedExtent.properties.source_scene_ids?.join(', ') || 'Not provided'}.
              Derived area and confidence are source claims; independent validation is not implied.
            </p>
          )}
        </section>
      )}

      {/* Demo metrics are illustrative and must not masquerade as FastAPI measurements. */}
      {DEMO_MODE && <MetricCards metrics={metrics} />}

      {!DEMO_MODE && <p className="text-xs text-amber-300">Live hydrological gauges, verified flood-depth prediction and operational evacuation routes are not available. Map overlays without verified backend records stay hidden.</p>}
      {/* Main Grid: 2-Column EOC Tactical Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* Left Column: Reusable 3D Geospatial Terrain Map (7 cols on lg, 7 cols on xl) */}
        <div className="lg:col-span-7 xl:col-span-7 flex flex-col space-y-2">
          <div className="flex items-center justify-between px-1">
            <span className="font-micro text-xs uppercase tracking-[1.4px] text-[#38bdf8] font-bold">
              3D GEOSPATIAL TERRAIN COMMAND // {DEMO_MODE ? 'KOSHI BENCHMARK' : 'HISTORICAL EVENT'}
            </span>
            <span className="font-mono text-xs text-slate-300 font-medium">
              DEM TERRAIN 1.5X &bull; {DEMO_MODE ? 'ILLUSTRATIVE SETTLEMENTS' : 'EVENT-LINKED POSTGIS OBSERVATIONS'}
            </span>
          </div>

          <GeospatialTerrainMap
            center={benchmarkScene.center || [87.05, 26.65]}
            zoom={benchmarkScene.zoom || 10.8}
            pitch={benchmarkScene.pitch || 55}
            bearing={benchmarkScene.bearing || -15}
            activeHorizon="3h"
            observedExtent={observedExtent}
            showInundation={DEMO_MODE || Boolean(observedExtent)}
            showForecast={DEMO_MODE}
            showGauges={DEMO_MODE}
            showIncidents={true}
            showInfrastructure={DEMO_MODE}
            showShelters={DEMO_MODE}
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
