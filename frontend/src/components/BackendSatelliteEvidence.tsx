import { useEffect, useState } from 'react';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';
import {
  getAssetExposure, getObservedExtent, getSettlementExposure, listHistoricalEvents,
  type AssetExposureResponse, type FloodEventRecord, type ObservedExtentFeature,
  type SettlementExposureResponse,
} from '../services/backendApi';

/**
 * Historical satellite/GIS evidence panel. Never exports invented geometry:
 * it downloads exactly the event-linked GeoJSON returned by FastAPI/PostGIS.
 */
export function BackendSatelliteEvidence() {
  const [events, setEvents] = useState<FloodEventRecord[]>([]);
  const [eventId, setEventId] = useState('');
  const [feature, setFeature] = useState<ObservedExtentFeature | null>(null);
  const [settlements, setSettlements] = useState<SettlementExposureResponse | null>(null);
  const [assets, setAssets] = useState<AssetExposureResponse | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    listHistoricalEvents().then(items => {
      if (!active) return;
      setEvents(items);
      setEventId(old => items.some(i => i.id === old) ? old : (items[0]?.id || ''));
      if (!items.length) setError('No historical/test event records available yet. Member 2 must import a matching event and geospatial data.');
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : 'Failed to list historical events'); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!eventId) return;
    let active = true;
    setBusy(true);
    setError('');
    setFeature(null);
    setSettlements(null);
    setAssets(null);
    Promise.allSettled([
      getObservedExtent(eventId),
      getSettlementExposure(eventId),
      getAssetExposure(eventId),
    ]).then(([extent, settlement, asset]) => {
      if (!active) return;
      if (extent.status === 'fulfilled') setFeature(extent.value);
      else setError(extent.reason instanceof Error ? extent.reason.message : 'No PostGIS flood polygon exists for this event');
      if (settlement.status === 'fulfilled') setSettlements(settlement.value);
      if (asset.status === 'fulfilled') setAssets(asset.value);
      setBusy(false);
    });
    return () => { active = false; };
  }, [eventId]);

  const selectedEvent = events.find(item => item.id === eventId);

  function downloadObservedGeoJSON() {
    if (!feature) return;
    const json = JSON.stringify(feature, null, 2);
    const url = URL.createObjectURL(new Blob([json], { type: 'application/geo+json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `floodlens-observed-${eventId.replace(/[^a-zA-Z0-9_-]/g, '_')}.geojson`;
    link.click();
    URL.revokeObjectURL(url);
    setNotice('Downloaded the exact GeoJSON feature returned by the historical FastAPI endpoint. Not independently ground-validated.');
  }

  return (
    <section className="space-y-4 rounded-xl border border-slate-700 bg-slate-950/80 p-4 text-sm text-white" aria-label="Historical satellite and GIS evidence">
      <div>
        <h2 className="font-semibold text-lg">Satellite / GIS · PostGIS historical evidence</h2>
        <p className="text-slate-400 text-xs mt-1">
          Historic data replay only. Flood polygons are derived observations, not guaranteed ground truth. No fabricated satellite export, depth or evacuation safety claims.
        </p>
      </div>
      <div className="flex flex-wrap gap-3 items-center">
        <label htmlFor="historical-gis-event">Recorded event</label>
        <select
          id="historical-gis-event"
          value={eventId}
          onChange={e => setEventId(e.target.value)}
          className="bg-slate-900 border border-slate-600 rounded px-3 py-2"
        >
          {!events.length && <option value="">No imported historical events</option>}
          {events.map(e => <option value={e.id} key={e.id}>{e.name} · {e.start_at.slice(0, 10)}</option>)}
        </select>
        <button
          type="button"
          disabled={!feature}
          onClick={downloadObservedGeoJSON}
          className="bg-cyan-950 border border-cyan-700 rounded px-3 py-2 text-cyan-100 disabled:opacity-40"
        >Export backend GeoJSON</button>
      </div>
      {selectedEvent && <p className="text-xs text-slate-400">Event ID: {selectedEvent.id} · Region: {selectedEvent.region_id} · Mode: {selectedEvent.mode}</p>}
      {busy && <p role="status" className="text-sky-300">Retrieving event-linked PostGIS evidence…</p>}
      {error && <p role="status" className="text-amber-300">{error}</p>}
      {notice && <p role="status" className="text-sky-300">{notice}</p>}
      <div className="grid gap-3 sm:grid-cols-4 text-sm">
        <div className="p-3 rounded border border-slate-800"><p className="text-slate-400 text-xs">Mapped inundation area</p><strong>{feature ? `${feature.properties.area_km2} km²` : 'Not available'}</strong></div>
        <div className="p-3 rounded border border-slate-800"><p className="text-slate-400 text-xs">Affected settlements</p><strong>{settlements?.status === 'completed' ? settlements.total_settlements_affected : 'Not available'}</strong></div>
        <div className="p-3 rounded border border-slate-800"><p className="text-slate-400 text-xs">Exposed roads</p><strong>{assets?.status === 'completed' ? `${assets.roads_exposed_km} km` : 'Not available'}</strong></div>
        <div className="p-3 rounded border border-slate-800"><p className="text-slate-400 text-xs">Exposed structures</p><strong>{assets?.status === 'completed' ? assets.structures_exposed_count : 'Not available'}</strong></div>
      </div>
      <GeospatialTerrainMap
        observedExtent={feature}
        showInundation={Boolean(feature)}
        showForecast={false}
        showInfrastructure={false}
        showGauges={false}
        showShelters={false}
        showIncidents={false}
        mode="satellite"
        height="490px"
      />
      {feature && (
        <div className="text-xs text-slate-300 space-y-1">
          <p>Observed at: {feature.properties.observed_at} · Method: {feature.properties.method} · Extent ID: {feature.id}</p>
          <p>Satellite scene IDs: {feature.properties.source_scene_ids?.join(', ') || 'Not provided'} · Confidence field: {feature.properties.confidence ?? 'Not provided'}</p>
          <p className="text-amber-200">Source metrics and classifications are unverified until Member 2 supplies repeatable reference validation and satellite provenance.</p>
        </div>
      )}
    </section>
  );
}
