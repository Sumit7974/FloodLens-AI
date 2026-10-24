import React, { useState, useEffect, useMemo } from 'react';
import type { Alert, BenchmarkScene, HelpRequest, MetricSummary } from '../types';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';
import { CesiumEarthMap } from './map/CesiumEarthMap';
import { Globe, Map as MapIcon } from 'lucide-react';
import { MetricCards } from './MetricCards';
import { SosQueue } from './SosQueue';
import { WarningBulletins } from './WarningBulletins';
import { DataStatusBadge } from './common/DataStatusBadge';
import { floodLensClient } from '../services/floodLensClient';
import {
  DEMO_MODE,
  listHistoricalEvents,
  getObservedExtent,
  getSettlementExposure,
  getAssetExposure,
  getRiskLocationMarkers,
  getShelters,
  getHospitals,
  type FloodEventRecord,
  type ObservedExtentFeature,
  type SettlementExposureResponse,
  type AssetExposureResponse,
  type RiskLocationMarker,
  type FacilityItem,
} from '../services/backendApi';

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

  // Location-linked backend risk forecasts & emergency facilities
  const [riskMarkers, setRiskMarkers] = useState<RiskLocationMarker[]>([]);
  const [facilities, setFacilities] = useState<FacilityItem[]>([]);
  const [activeHorizon, setActiveHorizon] = useState<'Now' | '1h' | '3h' | '6h'>('Now');
  const [isRiskLoading, setIsRiskLoading] = useState(false);
  const [riskError, setRiskError] = useState<string | null>(null);
  const [viewEngine, setViewEngine] = useState<'maplibre' | 'cesium'>('maplibre');

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

  useEffect(() => {
    let active = true;
    setIsRiskLoading(true);
    setRiskError(null);

    Promise.allSettled([
      getRiskLocationMarkers(),
      getShelters().catch(() => ({ count: 0, shelters: [], data_notes: '' })),
      getHospitals().catch(() => ({ count: 0, hospitals: [], data_notes: '' })),
    ]).then(([riskRes, shelterRes, hospitalRes]) => {
      if (!active) return;
      setIsRiskLoading(false);

      if (riskRes.status === 'fulfilled') {
        setRiskMarkers(riskRes.value);
      } else {
        setRiskError(riskRes.reason instanceof Error ? riskRes.reason.message : 'Unable to load location forecasts');
      }

      const items: FacilityItem[] = [];
      if (shelterRes.status === 'fulfilled' && shelterRes.value?.shelters) {
        items.push(...shelterRes.value.shelters);
      }
      if (hospitalRes.status === 'fulfilled' && hospitalRes.value?.hospitals) {
        items.push(...hospitalRes.value.hospitals);
      }
      setFacilities(items);
    });

    return () => { active = false; };
  }, [selectedEventId]);

  const selectedBackendEvent = backendEvents.find(event => event.id === selectedEventId);

  const defaultCenter = useMemo((): [number, number] => {
    if (selectedEventId === 'evt_2024_terai_monsoon') {
      return [85.92, 26.73];
    }
    if (selectedEventId === 'event_nepal_koshi_2017') {
      return [87.05, 26.65];
    }
    const firstPredicted = riskMarkers.find(m => m.hasForecast && m.coordinates);
    if (firstPredicted) {
      return firstPredicted.coordinates;
    }
    return benchmarkScene.center || [85.92, 26.73];
  }, [selectedEventId, riskMarkers, benchmarkScene.center]);

  const riskStats = useMemo(() => {
    let criticalOrHigh = 0;
    let moderate = 0;
    let low = 0;
    let unknown = 0;

    for (const m of riskMarkers) {
      const risk = activeHorizon === 'Now' 
        ? m.maxRiskLevel 
        : (m.horizons[`+${activeHorizon}`]?.risk_level || m.horizons[activeHorizon]?.risk_level || 'UNKNOWN');
      
      const normalized = risk.toUpperCase();
      if (normalized === 'CRITICAL' || normalized === 'HIGH') {
        criticalOrHigh++;
      } else if (normalized === 'MODERATE') {
        moderate++;
      } else if (normalized === 'LOW') {
        low++;
      } else {
        unknown++;
      }
    }

    return { criticalOrHigh, moderate, low, unknown, total: riskMarkers.length };
  }, [riskMarkers, activeHorizon]);

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

      {/* Tactical Flood Risk Intelligence Summary Bar */}
      <div className="rounded-lg border border-slate-800 bg-[#070d16] p-3 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-micro uppercase tracking-wider font-bold text-sky-400">
              TACTICAL RISK SUMMARY
            </span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-300">
              Horizon: <strong className="text-sky-300">{activeHorizon === 'Now' ? 'Current Run (Max)' : `+${activeHorizon}`}</strong>
            </span>
            {isRiskLoading && <span className="text-amber-400 animate-pulse text-[11px]">Loading forecasts...</span>}
            {riskError && <span className="text-rose-400 text-[11px]">Notice: {riskError}</span>}
          </div>

          {/* Horizon Selection Buttons */}
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500 text-[11px] font-mono mr-1">PREDICTION HORIZON:</span>
            {(['Now', '1h', '3h', '6h'] as const).map(h => (
              <button
                key={h}
                type="button"
                onClick={() => setActiveHorizon(h)}
                className={`px-2 py-0.5 rounded text-[11px] font-mono font-bold transition-colors ${
                  activeHorizon === h
                    ? 'bg-sky-500 text-white shadow-sm'
                    : 'bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700'
                }`}
              >
                {h === 'Now' ? 'Now' : `+${h}`}
              </button>
            ))}
          </div>
        </div>

        {/* Risk Level Tally Badges */}
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-rose-950/40 border border-rose-500/50 text-rose-300 font-mono">
            <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
            <span className="font-bold">{riskStats.criticalOrHigh}</span>
            <span className="text-[11px] uppercase">High / Critical</span>
          </div>

          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-950/40 border border-amber-500/50 text-amber-300 font-mono">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span className="font-bold">{riskStats.moderate}</span>
            <span className="text-[11px] uppercase">Moderate</span>
          </div>

          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-950/40 border border-emerald-500/50 text-emerald-300 font-mono">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="font-bold">{riskStats.low}</span>
            <span className="text-[11px] uppercase">Low Risk</span>
          </div>

          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-900 border border-slate-700 text-slate-400 font-mono">
            <span className="w-2 h-2 rounded-full bg-slate-500" />
            <span className="font-bold">{riskStats.unknown}</span>
            <span className="text-[11px] uppercase">No Forecast / Unassessed</span>
          </div>

          <div className="ml-auto text-[11px] text-amber-300/80 italic">
            * Green markers denote low modeled risk, NOT guaranteed safety.
          </div>
        </div>
      </div>

      {/* Main Grid: 2-Column EOC Tactical Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* Left Column: Reusable 3D Geospatial Terrain Map (7 cols on lg, 7 cols on xl) */}
        <div className="lg:col-span-7 xl:col-span-7 flex flex-col space-y-2">
          <div className="flex flex-wrap items-center justify-between px-1 gap-2">
            <div className="flex items-center gap-2">
              <span className="font-micro text-xs uppercase tracking-[1.4px] text-[#38bdf8] font-bold">
                {viewEngine === 'cesium' ? '3D EARTH GLOBE VIEW // CESIUMJS' : '3D GEOSPATIAL TERRAIN COMMAND // MAPLIBRE'}
              </span>
              <span className="font-mono text-[11px] text-slate-400 font-medium hidden sm:inline">
                &bull; {DEMO_MODE ? 'ILLUSTRATIVE SETTLEMENTS' : 'EVENT-LINKED POSTGIS OBSERVATIONS'}
              </span>
            </div>

            {/* View Engine Toggle Buttons */}
            <div className="flex items-center gap-1 bg-zinc-950 p-0.5 rounded-lg border border-zinc-800">
              <button
                type="button"
                onClick={() => setViewEngine('maplibre')}
                className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-mono font-bold transition-all cursor-pointer ${
                  viewEngine === 'maplibre'
                    ? 'bg-sky-500 text-white shadow-xs'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
                title="Standard High-Performance MapLibre 3D Terrain"
              >
                <MapIcon className="w-3.5 h-3.5" />
                <span>MapLibre 3D</span>
              </button>

              <button
                type="button"
                onClick={() => setViewEngine('cesium')}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono font-bold transition-all cursor-pointer ${
                  viewEngine === 'cesium'
                    ? 'bg-cyan-500 text-slate-950 shadow-xs'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
                title="Optional Google Earth-Style 3D Globe with Photorealistic 3D Tiles & Esri Satellite"
              >
                <Globe className="w-3.5 h-3.5" />
                <span>3D Earth View</span>
              </button>
            </div>
          </div>

          {viewEngine === 'cesium' ? (
            <CesiumEarthMap
              center={defaultCenter}
              observedExtent={observedExtent}
              riskMarkers={riskMarkers}
              facilities={facilities}
              incidents={requests}
              activeHorizon={activeHorizon}
              onActiveHorizonChange={setActiveHorizon}
              selectedEventTitle={selectedBackendEvent ? selectedBackendEvent.name : benchmarkScene.name}
              selectedEventDate={selectedBackendEvent ? selectedBackendEvent.start_at.slice(0, 10) : benchmarkScene.date_range}
              onCloseEarthView={() => setViewEngine('maplibre')}
              height="580px"
            />
          ) : (
            <GeospatialTerrainMap
              center={defaultCenter}
              zoom={benchmarkScene.zoom || 10.8}
              pitch={benchmarkScene.pitch || 55}
              bearing={benchmarkScene.bearing || -15}
              activeHorizon={activeHorizon}
              onActiveHorizonChange={setActiveHorizon}
              observedExtent={observedExtent}
              riskMarkers={riskMarkers}
              facilities={facilities}
              selectedEventTitle={selectedBackendEvent ? selectedBackendEvent.name : benchmarkScene.name}
              selectedEventDate={selectedBackendEvent ? selectedBackendEvent.start_at.slice(0, 10) : benchmarkScene.date_range}
              showInundation={true}
              showRiskMarkers={true}
              showForecast={true}
              showGauges={DEMO_MODE}
              showIncidents={true}
              showInfrastructure={DEMO_MODE}
              showShelters={true}
              incidents={requests}
              selectedIncidentId={selectedIncidentId}
              onSelectIncident={(id) => setSelectedIncidentId(id)}
              height="580px"
            />
          )}
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
