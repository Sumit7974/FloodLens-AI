import React, { useState, useEffect, useMemo } from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  Compass,
  FileCode,
  Layers,
  MapPin,
  Play,
  Route,
  ShieldAlert,
} from 'lucide-react';
import {
  DEMO_MODE,
  assessRoute,
  listHistoricalEvents,
  type FloodEventRecord,
  type RouteAssessRequest,
  type RouteAssessResponse,
} from '../services/backendApi';
import type { BenchmarkScene } from '../types';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';

interface RouteAssessmentProps {
  currentScene: BenchmarkScene;
}

const PRESET_CANDIDATE_ROUTES = [
  {
    id: 'route-prakashpur-inaruwa',
    name: 'Prakashpur to Inaruwa Elevated Levee Bypass',
    description: 'Paved secondary arterial route along elevated floodplain levee towards Inaruwa Safe Hub.',
    buffer_meters: 50,
    coordinates: [
      [87.085, 26.705],
      [87.112, 26.680],
      [87.135, 26.645],
      [87.155, 26.602],
    ] as [number, number][],
  },
  {
    id: 'route-gobargadha-channel',
    name: 'Gobargadha Alluvial Island Sandbar Track (High Hazard Risk)',
    description: 'Unpaved riverine sandbar track intersecting Koshi braided alluvial channels.',
    buffer_meters: 100,
    coordinates: [
      [86.980, 26.620],
      [87.010, 26.635],
      [87.045, 26.650],
      [87.085, 26.705],
    ] as [number, number][],
  },
  {
    id: 'route-barahakshetra-chatara',
    name: 'Barahakshetra Confluence Foothill Reach',
    description: 'Foothill transit route along Saptakoshi main stem towards Chatara hydro station.',
    buffer_meters: 35,
    coordinates: [
      [87.135, 26.845],
      [87.150, 26.855],
      [87.163, 26.871],
    ] as [number, number][],
  },
];

export const RouteAssessment: React.FC<RouteAssessmentProps> = ({ currentScene }) => {
  const [events, setEvents] = useState<FloodEventRecord[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string>(currentScene.id);
  const [selectedPresetId, setSelectedPresetId] = useState<string>(PRESET_CANDIDATE_ROUTES[0].id);
  const [bufferMeters, setBufferMeters] = useState<number>(50);
  const [rawCoordinatesJson, setRawCoordinatesJson] = useState<string>(
    JSON.stringify(PRESET_CANDIDATE_ROUTES[0].coordinates, null, 2)
  );
  const [validationError, setValidationError] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [assessmentResult, setAssessmentResult] = useState<RouteAssessResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Compute parsed coordinates for interactive map rendering
  const candidateCoordinates = useMemo<[number, number][]>(() => {
    try {
      const parsed = JSON.parse(rawCoordinatesJson);
      if (Array.isArray(parsed) && parsed.length >= 2) {
        return parsed.filter(
          (pt): pt is [number, number] =>
            Array.isArray(pt) &&
            pt.length >= 2 &&
            typeof pt[0] === 'number' &&
            typeof pt[1] === 'number'
        );
      }
    } catch {
      // ignore
    }
    return PRESET_CANDIDATE_ROUTES[0].coordinates;
  }, [rawCoordinatesJson]);

  // Load available events for historical assessment
  useEffect(() => {
    if (DEMO_MODE) {
      setEvents([
        {
          id: 'koshi-basin-primary',
          name: '2026 Monsoon Surge — Koshi Basin Reach',
          region_id: 'koshi-basin',
          start_at: '2026-10-17T18:00:00Z',
          end_at: '2026-10-19T12:00:00Z',
          mode: 'historical_demo',
          source_refs: { copernicus_sar: 'S1A_20261018' },
          description: 'Saptakoshi monsoon flood surge event with active extent polygons.',
          created_at: '2026-10-18T00:00:00Z',
        },
      ]);
      return;
    }

    listHistoricalEvents()
      .then((evs) => {
        setEvents(evs);
        if (evs.length > 0 && !selectedEventId) {
          setSelectedEventId(evs[0].id);
        }
      })
      .catch((err) => {
        console.warn('Could not fetch historical events:', err);
      });
  }, [selectedEventId]);

  const handleSelectPreset = (presetId: string) => {
    setSelectedPresetId(presetId);
    const preset = PRESET_CANDIDATE_ROUTES.find((r) => r.id === presetId);
    if (preset) {
      setBufferMeters(preset.buffer_meters);
      setRawCoordinatesJson(JSON.stringify(preset.coordinates, null, 2));
      setValidationError(null);
      setAssessmentResult(null);
    }
  };

  const handleAssess = async () => {
    setValidationError(null);
    setError(null);

    // Validate coordinates JSON
    let parsedCoords: [number, number][];
    try {
      const parsed = JSON.parse(rawCoordinatesJson);
      if (!Array.isArray(parsed) || parsed.length < 2) {
        throw new Error('Candidate route must contain at least 2 coordinate pairs [[lon, lat], ...].');
      }
      for (let i = 0; i < parsed.length; i++) {
        const pt = parsed[i];
        if (!Array.isArray(pt) || pt.length < 2) {
          throw new Error(`Vertex at index ${i} is not a valid [lon, lat] pair.`);
        }
        const [lon, lat] = pt;
        if (typeof lon !== 'number' || typeof lat !== 'number') {
          throw new Error(`Vertex at index ${i} contains non-numeric coordinates.`);
        }
        if (lon < -180 || lon > 180) {
          throw new Error(`Longitude at index ${i} (${lon}) is out of bounds [-180, 180]. Must be [longitude, latitude].`);
        }
        if (lat < -90 || lat > 90) {
          throw new Error(`Latitude at index ${i} (${lat}) is out of bounds [-90, 90]. Must be [longitude, latitude].`);
        }
        // Coordinate order verification: In Koshi/Terai region, longitude is ~86-88°E, latitude is ~26-28°N.
        if (lon >= 20 && lon <= 35 && lat >= 75 && lat <= 95) {
          throw new Error(`Coordinate order error at index ${i}: [${lon}, ${lat}] appears reversed ([latitude, longitude]). EPSG:4326 GeoJSON strictly requires [longitude, latitude] (e.g. [${lat}, ${lon}]).`);
        }
      }
      parsedCoords = parsed as [number, number][];
    } catch (err) {
      setValidationError(err instanceof Error ? err.message : 'Invalid GeoJSON coordinates.');
      return;
    }

    const requestPayload: RouteAssessRequest = {
      route: {
        type: 'LineString',
        coordinates: parsedCoords,
      },
      event_id: selectedEventId || undefined,
      buffer_meters: bufferMeters,
      evaluation_time: new Date().toISOString(),
      evaluation_context: {
        screening_agency: 'FloodLens AI EOC Technical Screening Tool',
        operator_role: 'authority',
      },
    };

    setLoading(true);

    if (DEMO_MODE) {
      // In demo mode, simulate realistic spatial screening result
      const isHighHazard = selectedPresetId === 'route-gobargadha-channel';

      const demoResponse: RouteAssessResponse = {
        route_status: isHighHazard ? 'hazards_detected' : 'no_known_hazards_detected',
        assessment_status: isHighHazard ? 'HAZARDS_INTERSECTED' : 'NO_KNOWN_INTERSECTIONS',
        hazards_detected: isHighHazard
          ? [
              {
                hazard_id: 'extent-koshi-sar-01',
                hazard_type: 'observed_flood_extent',
                source_layer: 'flood_extent',
                status: 'active',
                observed_at: '2026-10-18T05:00:00Z',
                source: 'Sentinel-1 SAR VV Backscatter Detection',
                confidence: 0.94,
                match_type: 'direct_intersection',
                proximity_distance_meters: 0.0,
                notes: 'Route directly intersects 46.8 km² Sentinel-1 satellite water mask.',
              },
              {
                hazard_id: 'hazard-road-belka-02',
                hazard_type: 'submerged',
                source_layer: 'road_hazard',
                status: 'active',
                observed_at: '2026-10-18T06:15:00Z',
                source: 'Authority Field Inspection Report',
                confidence: 0.98,
                match_type: 'proximity_warning',
                proximity_distance_meters: 18.5,
                notes: 'Culvert bypass approach inundated to 1.2m depth.',
              },
            ]
          : [],
        event_id: selectedEventId,
        evaluation_time: new Date().toISOString(),
        cutoff_time_applied: '2026-10-18T06:30:00Z',
        total_hazards_screened: 6,
        hazards_intersected_count: isHighHazard ? 2 : 0,
        limitations: [
          'EVIDENCE CAVEAT: Absence of detected hazard intersections does NOT imply physical route safety, clear bridges, or road viability.',
          'Satellite SAR detection cannot penetrate tree canopies or dense urban structures.',
          'This panel provides historical decision-support screening and must NEVER be published as automated citizen evacuation instructions.',
        ],
        provenance: {
          engine: 'FastAPI Spatial Intersection Engine (PostGIS ST_Intersects / ST_DWithin)',
          crs: 'EPSG:4326 (WGS 84)',
        },
      };

      setAssessmentResult(demoResponse);
      setLoading(false);
      return;
    }

    try {
      const res = await assessRoute(requestPayload);
      setAssessmentResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'FastAPI route assessment failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Mandatory Regulatory Warning: Not Public Navigation */}
      <div className="p-3.5 rounded-lg bg-rose-500/10 border-2 border-rose-500/50 text-rose-200 text-xs font-mono flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <AlertOctagon className="w-5 h-5 text-rose-400 shrink-0" />
          <span>
            <strong>AUTHORITY CANDIDATE ROUTE SCREENING TOOL ONLY:</strong> Never label a candidate route &quot;safe&quot; simply because no intersections were detected. Automated public evacuation navigation is strictly forbidden.
          </span>
        </div>
        <span className="px-2 py-0.5 rounded bg-black/60 border border-rose-400/40 text-[10px] text-rose-300 font-bold">
          RESTRICTED &bull; DECISION-SUPPORT
        </span>
      </div>

      {/* Header Bar */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded bg-amber-500/20 border border-amber-500/40 text-amber-400">
            <Route className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
              Candidate Route Hazard Assessment // PostGIS Screening
              <span className="px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/40 text-amber-300 text-[9px] font-mono font-bold tracking-wider">
                POST /api/v1/routes/assess
              </span>
            </h1>
            <p className="font-mono text-[10px] text-amber-300 uppercase tracking-wider mt-0.5 font-semibold">
              SPATIAL INTERSECTION ANALYZER &bull; {currentScene.name}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={handleAssess}
            disabled={loading}
            className="px-4 py-1.5 rounded-md bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600 text-white text-xs font-mono font-bold tracking-wider uppercase border border-amber-400 shadow-[0_0_12px_rgba(245,158,11,0.3)] flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
          >
            <Play className={`w-3.5 h-3.5 fill-current ${loading ? 'animate-pulse' : ''}`} />
            <span>{loading ? 'Screening LineString…' : 'Screen Route'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
          <span>Route assessment request failed: {error}</span>
        </div>
      )}

      {/* Main Form & Configuration */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Form: Event Selection, Preset Route & Coordinate Editor */}
        <div className="lg:col-span-5 space-y-4">
          <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3 font-mono text-xs">
            <h2 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5 pb-2 border-b border-[#1e3a5f]">
              <Compass className="w-4 h-4 text-amber-400" />
              Route Configuration Parameters
            </h2>

            {/* Event Selector */}
            <div className="space-y-1">
              <label className="text-[10px] text-slate-400 uppercase font-bold block">
                Target Historical Flood Event:
              </label>
              <select
                value={selectedEventId}
                onChange={(e) => setSelectedEventId(e.target.value)}
                className="w-full px-2.5 py-1.5 rounded bg-black/50 border border-[#1e3a5f] text-white text-xs focus:outline-none focus:border-amber-500"
              >
                {events.map((ev) => (
                  <option key={ev.id} value={ev.id}>
                    {ev.name} ({ev.id})
                  </option>
                ))}
                {events.length === 0 && (
                  <option value="koshi-basin-primary">2026 Monsoon Surge — Koshi Basin (Default)</option>
                )}
              </select>
            </div>

            {/* Preset Selector */}
            <div className="space-y-1">
              <label className="text-[10px] text-slate-400 uppercase font-bold block">
                Candidate Corridor Presets:
              </label>
              <div className="space-y-1.5">
                {PRESET_CANDIDATE_ROUTES.map((preset) => (
                  <button
                    key={preset.id}
                    onClick={() => handleSelectPreset(preset.id)}
                    className={`w-full text-left p-2 rounded border transition-colors cursor-pointer text-xs ${
                      selectedPresetId === preset.id
                        ? 'bg-amber-500/15 border-amber-500/60 text-white'
                        : 'bg-black/30 border-[#1e3a5f]/60 text-slate-400 hover:text-white hover:border-[#1e3a5f]'
                    }`}
                  >
                    <div className="font-bold">{preset.name}</div>
                    <div className="text-[10px] text-slate-400 mt-0.5">{preset.description}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Proximity Buffer Distance */}
            <div className="space-y-1 pt-1">
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-slate-400 font-bold uppercase">Proximity Buffer Radius:</span>
                <span className="text-amber-300 font-bold">{bufferMeters} meters</span>
              </div>
              <input
                type="range"
                min="10"
                max="500"
                step="10"
                value={bufferMeters}
                onChange={(e) => setBufferMeters(Number(e.target.value))}
                className="w-full accent-amber-500 cursor-pointer"
              />
              <span className="text-[9px] text-slate-500 block">
                ST_DWithin proximity buffer around candidate line to screen adjacent flood inundation.
              </span>
            </div>

            {/* GeoJSON LineString Coordinate Editor */}
            <div className="space-y-1 pt-1">
              <div className="flex items-center justify-between">
                <label className="text-[10px] text-slate-400 uppercase font-bold flex items-center gap-1">
                  <FileCode className="w-3.5 h-3.5 text-cyan-400" />
                  LineString Vertices [longitude, latitude]:
                </label>
                <span className="text-[9px] text-slate-400">EPSG:4326 WGS84</span>
              </div>
              <textarea
                rows={6}
                value={rawCoordinatesJson}
                onChange={(e) => setRawCoordinatesJson(e.target.value)}
                className="w-full p-2.5 rounded bg-black/60 border border-[#1e3a5f] text-cyan-300 font-mono text-[11px] leading-relaxed focus:outline-none focus:border-amber-500 resize-none"
              />
              {validationError && (
                <div className="p-2 rounded bg-rose-500/15 border border-rose-500/40 text-rose-300 text-[10px] flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  <span>{validationError}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Section: Screening Results & Map Preview */}
        <div className="lg:col-span-7 space-y-4">
          {/* Assessment Output Card */}
          <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between pb-2 border-b border-[#1e3a5f]">
              <h2 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-cyan-400" />
                Spatial Screening Evaluation Output
              </h2>
              {assessmentResult && (
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                    assessmentResult.assessment_status === 'HAZARDS_INTERSECTED'
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      : assessmentResult.assessment_status === 'INCOMPLETE_DATA'
                      ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                      : assessmentResult.assessment_status === 'NOT_EVALUATED'
                      ? 'bg-slate-500/20 text-slate-300 border border-slate-500/40'
                      : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  }`}
                >
                  {assessmentResult.assessment_status}
                </span>
              )}
            </div>

            {assessmentResult ? (
              <div className="space-y-3">
                {/* Status Callout */}
                <div
                  className={`p-3 rounded border space-y-1 ${
                    assessmentResult.assessment_status === 'HAZARDS_INTERSECTED'
                      ? 'bg-rose-500/10 border-rose-500/40 text-rose-200'
                      : assessmentResult.assessment_status === 'INCOMPLETE_DATA'
                      ? 'bg-purple-500/10 border-purple-500/40 text-purple-200'
                      : assessmentResult.assessment_status === 'NOT_EVALUATED'
                      ? 'bg-slate-500/10 border-slate-500/40 text-slate-200'
                      : 'bg-amber-500/10 border-amber-500/40 text-amber-200'
                  }`}
                >
                  <div className="font-bold text-white flex items-center gap-1.5 text-xs">
                    {assessmentResult.assessment_status === 'HAZARDS_INTERSECTED' ? (
                      <AlertOctagon className="w-4 h-4 text-rose-400" />
                    ) : assessmentResult.assessment_status === 'INCOMPLETE_DATA' ? (
                      <ShieldAlert className="w-4 h-4 text-purple-400" />
                    ) : assessmentResult.assessment_status === 'NOT_EVALUATED' ? (
                      <ShieldAlert className="w-4 h-4 text-slate-400" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-amber-400" />
                    )}
                    <span>
                      {assessmentResult.assessment_status === 'HAZARDS_INTERSECTED'
                        ? 'CRITICAL HAZARDS DETECTED ALONG CANDIDATE ROUTE'
                        : assessmentResult.assessment_status === 'INCOMPLETE_DATA'
                        ? 'INCOMPLETE DATA: HAZARD SCREENING INCONCLUSIVE'
                        : assessmentResult.assessment_status === 'NOT_EVALUATED'
                        ? 'NOT EVALUATED: MODEL SCREENING NOT EXECUTED'
                        : 'NO KNOWN HAZARDS DETECTED IN RECORDED SATELLITE LAYERS'}
                    </span>
                  </div>
                  <p className="text-[11px] leading-relaxed">
                    {assessmentResult.assessment_status === 'HAZARDS_INTERSECTED'
                      ? `Candidate route intersects ${assessmentResult.hazards_intersected_count} detected hazard(s) within a ${bufferMeters}m proximity buffer. Route is compromised by inundated surface extent or road closure.`
                      : assessmentResult.assessment_status === 'INCOMPLETE_DATA'
                      ? `The screening engine reported incomplete data: active hazard polygons or observation layers for this event are missing or have unverified geometry. Never treat this route as safe.`
                      : assessmentResult.assessment_status === 'NOT_EVALUATED'
                      ? `The candidate corridor was not evaluated against verified flood hazard models.`
                      : `The spatial screening engine found 0 intersections among ${assessmentResult.total_hazards_screened} active layers. THIS DOES NOT GUARANTEE SAFETY: unseen washed-out bridges, rapid surge currents, unrecorded debris, or cloud-occluded water may exist.`}
                  </p>
                </div>

                {/* Detected Hazards List */}
                {assessmentResult.hazards_detected && assessmentResult.hazards_detected.length > 0 && (
                  <div className="space-y-2">
                    <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider block">
                      Intersecting Hazard Features ({assessmentResult.hazards_detected.length}):
                    </span>
                    <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                      {assessmentResult.hazards_detected.map((hz, idx) => (
                        <div key={idx} className="p-2.5 rounded bg-black/40 border border-[#1e3a5f] space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-white text-xs">{hz.hazard_id}</span>
                            <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30 uppercase">
                              {hz.hazard_type}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-300 flex items-center justify-between">
                            <span>Layer: {hz.source_layer}</span>
                            <span className="text-amber-300">
                              {hz.match_type === 'direct_intersection' ? 'Direct Intersection' : `Proximity: ~${hz.proximity_distance_meters?.toFixed(1)}m`}
                            </span>
                          </div>
                          <p className="text-[10px] text-slate-400 italic">{hz.notes || hz.source}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Limitations & Provenance */}
                <div className="p-3 bg-black/40 border border-[#1e3a5f]/60 rounded space-y-1.5 text-[10px] text-slate-400">
                  <div className="flex items-center justify-between text-slate-300 font-bold">
                    <span>EVALUATED AT: {assessmentResult.evaluation_time}</span>
                    <span>BUFFER: {bufferMeters}m</span>
                  </div>
                  <ul className="list-disc list-inside space-y-0.5 text-slate-400">
                    {assessmentResult.limitations.map((lim, idx) => (
                      <li key={idx}>{lim}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <div className="p-8 text-center text-slate-400 space-y-2">
                <Route className="w-8 h-8 text-slate-600 mx-auto" />
                <p className="text-xs">No route assessment executed yet.</p>
                <p className="text-[11px] text-slate-500">
                  Select a candidate corridor or enter GeoJSON LineString coordinates and click &quot;Screen Route&quot;.
                </p>
              </div>
            )}
          </div>

          {/* Interactive Map Visualizer */}
          <div className="space-y-1">
            <div className="flex items-center justify-between px-1">
              <span className="font-micro text-[10px] uppercase tracking-[1.2px] text-amber-300 font-bold flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-amber-400" />
                GEOSPATIAL TERRAIN OVERVIEW // {currentScene.name}
              </span>
              <span className="font-mono text-[10px] text-slate-400">
                SRTM 30m Elevation &bull; Koshi Basin
              </span>
            </div>

            <GeospatialTerrainMap
              center={candidateCoordinates[0] || currentScene.center || [87.05, 26.65]}
              zoom={11}
              pitch={50}
              bearing={-10}
              activeHorizon="3h"
              showInundation={true}
              showForecast={true}
              showGauges={true}
              showInfrastructure={true}
              showShelters={true}
              candidateRoute={candidateCoordinates}
              height="300px"
            />
          </div>
        </div>
      </div>
    </div>
  );
};
