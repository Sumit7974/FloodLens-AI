import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Compass,
  Droplets,
  Flame,
  Layers,
  LifeBuoy,
  MapPin,
  Maximize2,
  Minimize2,
  Phone,
  RotateCcw,
  Satellite,
  Send,
  Shield,
  ShieldAlert,
  Users,
  Waves,
} from 'lucide-react';
import {
  HORIZON_FORECASTS,
  KOSHI_SHELTERS,
  KOSHI_TELEMETRY_GAUGES,
} from '../../data/geospatialData';
import type { HelpRequest } from '../../types';
import { DEMO_MODE, type ObservedExtentFeature, type FacilityItem } from '../../services/backendApi';

export interface GeospatialTerrainMapProps {
  center?: [number, number]; // [lng, lat]
  zoom?: number;
  pitch?: number;
  bearing?: number;
  activeHorizon?: 'Now' | '1h' | '3h' | '6h';
  observedExtent?: ObservedExtentFeature | null;
  showInundation?: boolean;
  showForecast?: boolean;
  showGauges?: boolean;
  showIncidents?: boolean;
  showInfrastructure?: boolean;
  showShelters?: boolean;
  candidateRoute?: [number, number][]; // LineString [lng, lat]
  facilities?: FacilityItem[];
  onSelectFacility?: (facility: FacilityItem) => void;
  incidents?: HelpRequest[];
  selectedIncidentId?: string | null;
  onSelectIncident?: (id: string) => void;
  onSelectGauge?: (gaugeId: string) => void;
  onDispatchIncident?: (incidentId: string) => void;
  className?: string;
  height?: string;
  mode?: 'overview' | 'prediction' | 'satellite' | 'coordination' | 'dispatcher' | 'analytics';
  wipePosition?: number; // 0 to 100 for satellite comparison
  verificationLayers?: {
    tp: boolean;
    fp: boolean;
    fn: boolean;
  };
  highlightGeofenceId?: string | null;
  onGeofenceSelect?: (geofenceId: string) => void;
  initialHeatmap?: boolean;
  initialWaterFlow?: boolean;
  initialClustered?: boolean;
}

// Convert [lat, lng] array to GeoJSON [lng, lat] polygon format
const toGeoJsonCoords = (coords: [number, number][]): number[][] => {
  const points = coords.map(([lat, lng]) => [lng, lat]);
  if (points.length > 0) {
    const first = points[0];
    const last = points[points.length - 1];
    if (first[0] !== last[0] || first[1] !== last[1]) {
      points.push([...first]);
    }
  }
  return points;
};

// Road cuts GeoJSON segments along East-West Highway and Canals
const INFRASTRUCTURE_ROAD_CUTS = {
  type: 'FeatureCollection' as const,
  features: [
    {
      type: 'Feature' as const,
      properties: {
        id: 'cut-ew-highway',
        name: 'East-West Highway (Inundated Ch. 42+200 - 45+800)',
        status: 'IMPASSABLE - WATER DEPTH 0.9M',
        hazard: 'CRITICAL',
      },
      geometry: {
        type: 'LineString' as const,
        coordinates: [
          [87.012, 26.618],
          [87.045, 26.615],
          [87.078, 26.612],
          [87.110, 26.608],
        ],
      },
    },
    {
      type: 'Feature' as const,
      properties: {
        id: 'cut-chatara-canal',
        name: 'Chatara Main Canal Dyke Embankment Breach Reach',
        status: 'SCOUR RISK - OVERTOPPING IMMINENT',
        hazard: 'CRITICAL',
      },
      geometry: {
        type: 'LineString' as const,
        coordinates: [
          [87.152, 26.832],
          [87.140, 26.810],
          [87.125, 26.785],
          [87.108, 26.750],
        ],
      },
    },
    {
      type: 'Feature' as const,
      properties: {
        id: 'cut-spur-12',
        name: 'Koshi Embankment Spur 12+400 Riprap Failure Zone',
        status: 'SEVERE HYDRAULIC FORCE',
        hazard: 'CRITICAL',
      },
      geometry: {
        type: 'LineString' as const,
        coordinates: [
          [86.975, 26.580],
          [86.968, 26.565],
          [86.960, 26.545],
        ],
      },
    },
  ],
};

// Settlement centroids for Koshi Basin
const KOSHI_SETTLEMENTS = [
  { name: 'Chatara Hydro Hub', coords: [87.155, 26.839], pop: '14,200', ward: 'Barahakshetra W1' },
  { name: 'Prakashpur Lowlands', coords: [87.051, 26.683], pop: '18,500', ward: 'Barahakshetra W4' },
  { name: 'Inaruwa Municipality', coords: [87.155, 26.602], pop: '42,000', ward: 'District HQ' },
  { name: 'Gobargadha Sandbar Island', coords: [86.995, 26.612], pop: '3,800', ward: 'Hanumannagar W1' },
  { name: 'Belka Confluence', coords: [87.050, 26.785], pop: '11,200', ward: 'Belka W8' },
  { name: 'Bhokraha Narsingh', coords: [87.112, 26.592], pop: '22,400', ward: 'Bhokraha W5' },
];

// Koshi River hydraulic main channels for water discharge and flow vector animations
const KOSHI_MAIN_FLOW_CHANNEL: [number, number][] = [
  [87.168, 26.875], // Barahakshetra Gorge Inflow
  [87.155, 26.839], // Chatara Hydro Hub (13,240 m³/s)
  [87.132, 26.808], // Upper River Bend
  [87.098, 26.765], // Belka Spur Confluence
  [87.072, 26.720], // Mid Basin Braided Stem
  [87.051, 26.683], // Prakashpur Lower Reach (Surge Epicenter)
  [87.025, 26.645], // East Sandbar Inflow
  [86.995, 26.612], // Gobargadha Sandbar Island
  [86.965, 26.570], // Embankment Ch. 38 Reach
  [86.938, 26.540], // Spur 12 Riprap Approach
  [86.915, 26.520], // Koshi International Barrage (12,980 m³/s)
];

const KOSHI_EAST_CANAL_FLOW: [number, number][] = [
  [87.152, 26.832], // Chatara Intake (3,400 m³/s overflow)
  [87.140, 26.810], // Canal Ch. 4+200
  [87.125, 26.785], // Dyke Breach Zone
  [87.108, 26.750], // Embankment Section
  [87.090, 26.705], // Siphon Overpass
  [87.070, 26.660], // Inundated Farm Lands
];

// Depth-stratified sampling points for the dynamic flood depth heatmap
const KOSHI_DEPTH_HEATMAP_POINTS = {
  type: 'FeatureCollection' as const,
  features: [
    // Critical Deep Channel (2.5m - 3.8m depth, intensity 1.0)
    { type: 'Feature', properties: { depth: 3.6, risk: 'critical', surgeLevel: 1.0 }, geometry: { type: 'Point', coordinates: [87.051, 26.683] } },
    { type: 'Feature', properties: { depth: 3.2, risk: 'critical', surgeLevel: 0.95 }, geometry: { type: 'Point', coordinates: [87.042, 26.678] } },
    { type: 'Feature', properties: { depth: 2.9, risk: 'critical', surgeLevel: 0.9 }, geometry: { type: 'Point', coordinates: [87.060, 26.690] } },
    { type: 'Feature', properties: { depth: 3.4, risk: 'critical', surgeLevel: 0.95 }, geometry: { type: 'Point', coordinates: [86.995, 26.612] } },
    { type: 'Feature', properties: { depth: 2.8, risk: 'critical', surgeLevel: 0.85 }, geometry: { type: 'Point', coordinates: [87.155, 26.839] } },
    { type: 'Feature', properties: { depth: 3.1, risk: 'critical', surgeLevel: 0.9 }, geometry: { type: 'Point', coordinates: [86.915, 26.520] } },

    // Moderate Inundation Zones (1.0m - 2.2m depth, intensity 0.6)
    { type: 'Feature', properties: { depth: 1.8, risk: 'medium', surgeLevel: 0.65 }, geometry: { type: 'Point', coordinates: [87.070, 26.715] } },
    { type: 'Feature', properties: { depth: 1.5, risk: 'medium', surgeLevel: 0.6 }, geometry: { type: 'Point', coordinates: [87.030, 26.660] } },
    { type: 'Feature', properties: { depth: 1.7, risk: 'medium', surgeLevel: 0.62 }, geometry: { type: 'Point', coordinates: [87.085, 26.745] } },
    { type: 'Feature', properties: { depth: 1.4, risk: 'medium', surgeLevel: 0.55 }, geometry: { type: 'Point', coordinates: [87.010, 26.635] } },
    { type: 'Feature', properties: { depth: 1.9, risk: 'medium', surgeLevel: 0.7 }, geometry: { type: 'Point', coordinates: [86.980, 26.590] } },
    { type: 'Feature', properties: { depth: 1.3, risk: 'medium', surgeLevel: 0.5 }, geometry: { type: 'Point', coordinates: [87.125, 26.785] } },

    // Shallow / Agricultural Runoff (< 0.9m depth, intensity 0.3)
    { type: 'Feature', properties: { depth: 0.7, risk: 'low', surgeLevel: 0.3 }, geometry: { type: 'Point', coordinates: [87.112, 26.592] } },
    { type: 'Feature', properties: { depth: 0.5, risk: 'low', surgeLevel: 0.25 }, geometry: { type: 'Point', coordinates: [87.135, 26.630] } },
    { type: 'Feature', properties: { depth: 0.8, risk: 'low', surgeLevel: 0.35 }, geometry: { type: 'Point', coordinates: [87.080, 26.620] } },
    { type: 'Feature', properties: { depth: 0.6, risk: 'low', surgeLevel: 0.28 }, geometry: { type: 'Point', coordinates: [87.040, 26.780] } },
    { type: 'Feature', properties: { depth: 0.4, risk: 'low', surgeLevel: 0.2 }, geometry: { type: 'Point', coordinates: [87.150, 26.610] } },
    { type: 'Feature', properties: { depth: 0.75, risk: 'low', surgeLevel: 0.32 }, geometry: { type: 'Point', coordinates: [86.950, 26.540] } },
  ],
};

// Generate approximate circular polygon coordinates for dynamic surge wave ripple
const createRipplePolygon = (centerLng: number, centerLat: number, radiusDegrees: number, steps = 36): number[][] => {
  const coords: number[][] = [];
  for (let i = 0; i <= steps; i++) {
    const angle = (i * 2 * Math.PI) / steps;
    const lng = centerLng + radiusDegrees * Math.cos(angle);
    const lat = centerLat + (radiusDegrees * 0.85) * Math.sin(angle); // slight compression for latitude projection
    coords.push([lng, lat]);
  }
  return coords;
};

// Linear interpolation along a polyline
const interpolatePointAlongPolyline = (polyline: [number, number][], progress: number): { coord: [number, number]; bearing: number } => {
  if (polyline.length < 2) return { coord: polyline[0] || [0, 0], bearing: 180 };
  const totalSegments = polyline.length - 1;
  const scaledProgress = Math.min(Math.max(progress, 0), 1) * totalSegments;
  const segIndex = Math.min(Math.floor(scaledProgress), totalSegments - 1);
  const segFraction = scaledProgress - segIndex;

  const p1 = polyline[segIndex];
  const p2 = polyline[segIndex + 1];

  const lng = p1[0] + (p2[0] - p1[0]) * segFraction;
  const lat = p1[1] + (p2[1] - p1[1]) * segFraction;

  // Bearing in degrees from North
  const dLng = p2[0] - p1[0];
  const dLat = p2[1] - p1[1];
  const angleRad = Math.atan2(dLng, dLat);
  const bearing = (angleRad * (180 / Math.PI) + 360) % 360;

  return { coord: [lng, lat], bearing };
};

// Deterministic initial particle distribution for high-performance 60fps render loop
const INITIAL_FLOW_PARTICLES = Array.from({ length: 32 }, (_, i) => ({
  id: i,
  channel: (i % 4 === 0 ? 'canal' : 'main') as 'main' | 'canal',
  progress: (i / 32) + ((i * 0.037) % 0.05),
  speed: 0.0016 + ((i * 0.00021) % 0.0008),
  size: 4 + (i % 3) * 2,
}));

export const GeospatialTerrainMap: React.FC<GeospatialTerrainMapProps> = ({
  center = [87.05, 26.65],
  zoom = 10.8,
  pitch = 55,
  bearing = -15,
  activeHorizon = '3h',
  observedExtent = null,
  showInundation = true,
  showForecast = true,
  showGauges = true,
  showIncidents = true,
  showInfrastructure = true,
  showShelters = true,
  candidateRoute = [],
  facilities = [],
  onSelectFacility,
  incidents = [],
  selectedIncidentId = null,
  onSelectIncident,
  onSelectGauge,
  onDispatchIncident,
  className = '',
  height = '520px',
  mode = 'overview',
  wipePosition = 50,
  verificationLayers = { tp: true, fp: true, fn: true },
  initialHeatmap = true,
  initialWaterFlow = true,
  initialClustered = true,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const animFrameRef = useRef<number | null>(null);

  // Core Map State
  const [is3D, setIs3D] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [basemap, setBasemap] = useState<'dark' | 'satellite'>(
    mode === 'satellite' ? 'satellite' : 'satellite' // default to satellite base as requested
  );

  // Layer Visibility Controls (Requested UI Toggles)
  const [layerHeatmap, setLayerHeatmap] = useState(initialHeatmap);
  const [layerWaterFlow, setLayerWaterFlow] = useState(initialWaterFlow);
  const [layerClusteredSOS, setLayerClusteredSOS] = useState(initialClustered);

  // Active Tactical Popup & Dispatch Status
  const [activePopupData, setActivePopupData] = useState<any | null>(null);
  const [dispatchedIncidents, setDispatchedIncidents] = useState<Record<string, boolean>>({});

  // Animation particles reference initialized deterministically
  const particlesRef = useRef(INITIAL_FLOW_PARTICLES);

  // Track previous incident IDs to detect incoming SOS beacons in real-time
  const prevIncidentIdsRef = useRef<Set<string>>(new Set());
  const isFirstIncidentSyncRef = useRef<boolean>(true);

  // When a new 'pending' incident arrives, automatically fly to newest coordinate with pulsating beacon
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !incidents || incidents.length === 0) return;

    const currentIds = new Set(incidents.map((i) => i.id));

    if (!isFirstIncidentSyncRef.current) {
      const newPendingIncidents = incidents.filter(
        (i) =>
          !prevIncidentIdsRef.current.has(i.id) &&
          (i.status === 'LOCAL_LOGGED' ||
            i.handoff_status === 'LOCAL_LOGGED' ||
            (i as any).status === 'pending' ||
            !dispatchedIncidents[i.id])
      );

      if (newPendingIncidents.length > 0) {
        const latest = newPendingIncidents[newPendingIncidents.length - 1];
        const [lat, lng] = latest.coordinates;

        map.flyTo({
          center: [lng, lat],
          zoom: Math.max(map.getZoom(), 12.8),
          pitch: 55,
          duration: 1600,
          essential: true,
        });

        if (onSelectIncident) {
          onSelectIncident(latest.id);
        }
      }
    } else {
      isFirstIncidentSyncRef.current = false;
    }

    prevIncidentIdsRef.current = currentIds;
  }, [incidents, mapLoaded, onSelectIncident, dispatchedIncidents]);

  // Convert SOS incidents to GeoJSON FeatureCollection for hardware-accelerated clustering
  const incidentsGeoJson = useMemo<any>(() => {
    return {
      type: 'FeatureCollection',
      features: incidents.map((inc) => ({
        type: 'Feature',
        properties: {
          id: inc.id,
          requester_name: inc.requester_name,
          contact_number: inc.contact_number,
          category: inc.category,
          urgency: inc.urgency,
          people_count: inc.people_count || 1,
          location_name: inc.location_name,
          depth: inc.estimated_water_depth || '1.8m (Fast Current)',
          status: dispatchedIncidents[inc.id] ? 'DISPATCHED_TO_UNIT_ALPHA' : (inc.status || 'LOCAL_LOGGED'),
          timestamp: inc.timestamp,
          landmark: inc.landmark,
          isCritical: inc.urgency === 'CRITICAL' ? 1 : 0,
        },
        geometry: {
          type: 'Point',
          coordinates: [inc.coordinates[1], inc.coordinates[0]], // [lng, lat]
        },
      })),
    };
  }, [incidents, dispatchedIncidents]);

  // Handle local unit dispatch action from popup
  const handleTriggerDispatch = useCallback((incidentId: string) => {
    setDispatchedIncidents((prev) => ({ ...prev, [incidentId]: true }));
    if (onDispatchIncident) {
      onDispatchIncident(incidentId);
    } else if (onSelectIncident) {
      onSelectIncident(incidentId);
    }
  }, [onDispatchIncident, onSelectIncident]);

  // Setup Dynamic Map Layers (Surge pulse, river corridors, depth heatmap, clustered SOS)
  const setupMapLayers = useCallback((map: maplibregl.Map) => {
    // 1. Observed Satellite Inundation Layer
    const observedCoords = toGeoJsonCoords(HORIZON_FORECASTS['1h'].polygonCoords);
    if (!map.getSource('observed-inundation-src')) {
      map.addSource('observed-inundation-src', {
        type: 'geojson',
        data: DEMO_MODE ? {
          type: 'Feature', properties: { name: 'Illustrative fixture only', areaKm2: 28.4 },
          geometry: { type: 'Polygon', coordinates: [observedCoords] },
        } : { type: 'FeatureCollection', features: [] },
      });

      // Animated Surge Pulse Fill Layer
      map.addLayer({
        id: 'observed-inundation-fill',
        type: 'fill',
        source: 'observed-inundation-src',
        paint: {
          'fill-color': '#00e5ff',
          'fill-opacity': 0.45,
        },
      });

      // Neon Surge Glowing Outline
      map.addLayer({
        id: 'observed-inundation-stroke',
        type: 'line',
        source: 'observed-inundation-src',
        paint: {
          'line-color': '#38bdf8',
          'line-width': 3,
          'line-opacity': 0.95,
        },
      });
    }

    // 2. Animated Surge Ripple Wave Layers (Concentric Doppler Waves)
    if (!map.getSource('surge-ripple-src')) {
      const initialRipples = [
        createRipplePolygon(87.051, 26.683, 0.015),
        createRipplePolygon(87.051, 26.683, 0.030),
      ];
      map.addSource('surge-ripple-src', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: initialRipples.map((ringCoords, idx) => ({
            type: 'Feature',
            properties: { ringIndex: idx },
            geometry: { type: 'Polygon', coordinates: [ringCoords] },
          })),
        },
      });

      map.addLayer({
        id: 'surge-ripple-line',
        type: 'line',
        source: 'surge-ripple-src',
        paint: {
          'line-color': '#00f0ff',
          'line-width': 2.5,
          'line-opacity': 0.75,
        },
      });
    }

    // 3. Depth-Gradient Heatmap Layer (Green -> Amber -> Neon Blue -> Red)
    if (!map.getSource('flood-depth-heatmap-src')) {
      map.addSource('flood-depth-heatmap-src', {
        type: 'geojson',
        data: KOSHI_DEPTH_HEATMAP_POINTS,
      });

      map.addLayer({
        id: 'flood-depth-heatmap-layer',
        type: 'heatmap',
        source: 'flood-depth-heatmap-src',
        maxzoom: 16,
        layout: {
          visibility: initialHeatmap ? 'visible' : 'none',
        },
        paint: {
          // Weight by surge level attribute
          'heatmap-weight': ['get', 'surgeLevel'],
          'heatmap-intensity': [
            'interpolate',
            ['linear'],
            ['zoom'],
            9, 0.8,
            12, 1.8,
            15, 3.0,
          ],
          // Color ramp: Green (low) -> Amber (medium) -> Cyan/Neon Blue (surge) -> Crimson Red (critical)
          'heatmap-color': [
            'interpolate',
            ['linear'],
            ['heatmap-density'],
            0, 'rgba(0,0,0,0)',
            0.15, 'rgba(16, 185, 129, 0.55)', // Emerald green: shallow / peripheral
            0.40, 'rgba(245, 158, 11, 0.75)',  // Amber: moderate depth 0.9m - 1.5m
            0.70, 'rgba(6, 182, 212, 0.90)',   // Cyan / Neon Blue: fast channel surge
            0.95, 'rgba(239, 68, 68, 0.98)',   // Pulsing Red: critical > 2.5m surge
          ],
          'heatmap-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            9, 22,
            11, 38,
            14, 65,
          ],
          'heatmap-opacity': 0.72,
        },
      });
    }

    // 4. River Basin Corridors & Directional Water Flow Vector Lines
    if (!map.getSource('water-flow-corridors-src')) {
      map.addSource('water-flow-corridors-src', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              properties: { name: 'Saptakoshi Main Stem (13,240 m³/s)', flowType: 'main' },
              geometry: { type: 'LineString', coordinates: KOSHI_MAIN_FLOW_CHANNEL },
            },
            {
              type: 'Feature',
              properties: { name: 'Chatara Spillway Canal (3,400 m³/s)', flowType: 'canal' },
              geometry: { type: 'LineString', coordinates: KOSHI_EAST_CANAL_FLOW },
            },
          ],
        },
      });

      // Flow corridor casing glow
      map.addLayer({
        id: 'water-flow-casing',
        type: 'line',
        source: 'water-flow-corridors-src',
        layout: {
          visibility: initialWaterFlow ? 'visible' : 'none',
        },
        paint: {
          'line-color': '#0284c7',
          'line-width': 7,
          'line-opacity': 0.35,
          'line-blur': 3,
        },
      });

      // Glowing flow core line
      map.addLayer({
        id: 'water-flow-core',
        type: 'line',
        source: 'water-flow-corridors-src',
        layout: {
          visibility: initialWaterFlow ? 'visible' : 'none',
        },
        paint: {
          'line-color': '#38bdf8',
          'line-width': 2.5,
          'line-opacity': 0.85,
          'line-dasharray': [3, 2],
        },
      });
    }

    // 5. Dynamic Flowing Discharge Particles Source & Layers
    if (!map.getSource('water-flow-particles-src')) {
      map.addSource('water-flow-particles-src', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      // Glowing particle dots
      map.addLayer({
        id: 'water-flow-particles-glow',
        type: 'circle',
        source: 'water-flow-particles-src',
        layout: {
          visibility: initialWaterFlow ? 'visible' : 'none',
        },
        paint: {
          'circle-radius': 6,
          'circle-color': '#00f0ff',
          'circle-opacity': 0.85,
          'circle-blur': 0.6,
        },
      });

      map.addLayer({
        id: 'water-flow-particles-core',
        type: 'circle',
        source: 'water-flow-particles-src',
        layout: {
          visibility: initialWaterFlow ? 'visible' : 'none',
        },
        paint: {
          'circle-radius': 3,
          'circle-color': '#ffffff',
          'circle-opacity': 0.95,
        },
      });
    }

    // 6. Clustered Citizen SOS Requests GeoJSON Source & Layers
    if (!map.getSource('sos-incidents-geojson-src')) {
      map.addSource('sos-incidents-geojson-src', {
        type: 'geojson',
        data: incidentsGeoJson,
        cluster: true,
        clusterMaxZoom: 11,
        clusterRadius: 50,
      });

      // Clustered Node Aura
      map.addLayer({
        id: 'sos-clusters-pulse',
        type: 'circle',
        source: 'sos-incidents-geojson-src',
        filter: ['has', 'point_count'],
        layout: {
          visibility: initialClustered ? 'visible' : 'none',
        },
        paint: {
          'circle-color': '#ef4444',
          'circle-radius': [
            'step',
            ['get', 'point_count'],
            26,
            3, 34,
            5, 42,
          ],
          'circle-opacity': 0.25,
          'circle-blur': 0.5,
        },
      });

      // Clustered Node Tactical Body
      map.addLayer({
        id: 'sos-clusters-body',
        type: 'circle',
        source: 'sos-incidents-geojson-src',
        filter: ['has', 'point_count'],
        layout: {
          visibility: initialClustered ? 'visible' : 'none',
        },
        paint: {
          'circle-color': [
            'step',
            ['get', 'point_count'],
            '#06b6d4',
            3, '#f59e0b',
            5, '#ef4444',
          ],
          'circle-radius': [
            'step',
            ['get', 'point_count'],
            18,
            3, 24,
            5, 30,
          ],
          'circle-stroke-width': 2.5,
          'circle-stroke-color': '#ffffff',
          'circle-opacity': 0.92,
        },
      });

      // Cluster SOS Count Label
      map.addLayer({
        id: 'sos-cluster-count',
        type: 'symbol',
        source: 'sos-incidents-geojson-src',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': '{point_count} SOS',
          'text-font': ['Open Sans Bold'],
          'text-size': 11,
          visibility: initialClustered ? 'visible' : 'none',
        },
        paint: {
          'text-color': '#ffffff',
        },
      });

      // Cluster click zoom interaction
      map.on('click', 'sos-clusters-body', async (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ['sos-clusters-body'] });
        if (!features.length) return;
        const clusterId = features[0].properties?.cluster_id;
        const source = map.getSource('sos-incidents-geojson-src') as any;
        if (source && clusterId != null) {
          try {
            const targetZoom = typeof source.getClusterExpansionZoom === 'function'
              ? await source.getClusterExpansionZoom(clusterId)
              : 12;
            const geom = features[0].geometry as any;
            if (geom && geom.coordinates) {
              map.easeTo({
                center: geom.coordinates as [number, number],
                zoom: (targetZoom || 12) + 0.5,
                duration: 800,
              });
            }
          } catch {
            // Soft fallback
          }
        }
      });
    }

    // 7. Predictive Horizon Extent Layer
    const activeCoords =
      activeHorizon === 'Now'
        ? observedCoords
        : toGeoJsonCoords(HORIZON_FORECASTS[activeHorizon as '1h' | '3h' | '6h']?.polygonCoords || observedCoords);

    const horizonColor =
      activeHorizon === '6h' ? '#ef4444' : activeHorizon === '3h' ? '#f97316' : '#f59e0b';

    if (!map.getSource('forecast-horizon-src')) {
      map.addSource('forecast-horizon-src', {
        type: 'geojson',
        data: DEMO_MODE ? {
          type: 'Feature', properties: { horizon: activeHorizon, source: 'illustrative' },
          geometry: { type: 'Polygon', coordinates: [activeCoords] },
        } : { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'forecast-horizon-fill',
        type: 'fill',
        source: 'forecast-horizon-src',
        paint: {
          'fill-color': horizonColor,
          'fill-opacity': 0.38,
        },
      });

      map.addLayer({
        id: 'forecast-horizon-stroke',
        type: 'line',
        source: 'forecast-horizon-src',
        paint: {
          'line-color': horizonColor,
          'line-width': 2,
          'line-dasharray': [2, 1],
        },
      });
    }

    // 8. Infrastructure & Road Cuts Layer
    if (!map.getSource('road-cuts-src')) {
      map.addSource('road-cuts-src', {
        type: 'geojson',
        data: DEMO_MODE ? INFRASTRUCTURE_ROAD_CUTS : { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'road-cuts-lines',
        type: 'line',
        source: 'road-cuts-src',
        paint: {
          'line-color': '#f43f5e',
          'line-width': 3.5,
          'line-dasharray': [3, 2],
        },
      });
    }

    // 9. Candidate Route LineString Layer
    if (!map.getSource('candidate-route-src')) {
      const hasRoute = candidateRoute && candidateRoute.length >= 2;
      map.addSource('candidate-route-src', {
        type: 'geojson',
        data: hasRoute
          ? {
              type: 'Feature',
              properties: { name: 'Candidate Route' },
              geometry: { type: 'LineString', coordinates: candidateRoute },
            }
          : { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'candidate-route-casing',
        type: 'line',
        source: 'candidate-route-src',
        paint: {
          'line-color': '#000000',
          'line-width': 7,
          'line-opacity': 0.75,
        },
      });

      map.addLayer({
        id: 'candidate-route-line',
        type: 'line',
        source: 'candidate-route-src',
        paint: {
          'line-color': '#f59e0b',
          'line-width': 4,
          'line-dasharray': [2, 1],
        },
      });
    }
  }, [activeHorizon, candidateRoute, initialHeatmap, initialWaterFlow, initialClustered, incidentsGeoJson]);

  // High-Performance Animation Loop: Surge Pulse, Expanding Ripples, and River Flow Particles
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    let rippleRadius1 = 0.008;
    let rippleRadius2 = 0.024;
    let rippleRadius3 = 0.038;
    let lastTime = performance.now();

    const animateFrame = (timestamp: number) => {
      const delta = timestamp - lastTime;
      lastTime = timestamp;

      // 1. Inundation Fill Breathing Pulse (0.35 to 0.65 opacity)
      if (map.getLayer('observed-inundation-fill')) {
        const pulsePhase = Math.sin(timestamp * 0.0035);
        const dynamicOpacity = 0.40 + pulsePhase * 0.20;
        map.setPaintProperty('observed-inundation-fill', 'fill-opacity', dynamicOpacity);
      }

      // 2. Expanding Concentric Surge Ripples
      const surgeSource = map.getSource('surge-ripple-src') as maplibregl.GeoJSONSource | undefined;
      if (surgeSource) {
        rippleRadius1 = (rippleRadius1 + 0.00035 * (delta / 16.6)) % 0.050;
        rippleRadius2 = (rippleRadius2 + 0.00035 * (delta / 16.6)) % 0.050;
        rippleRadius3 = (rippleRadius3 + 0.00035 * (delta / 16.6)) % 0.050;

        const r1 = createRipplePolygon(87.051, 26.683, rippleRadius1);
        const r2 = createRipplePolygon(87.051, 26.683, rippleRadius2);
        const r3 = createRipplePolygon(87.051, 26.683, rippleRadius3);

        surgeSource.setData({
          type: 'FeatureCollection',
          features: [
            { type: 'Feature', properties: { opacity: Math.max(0, 1 - rippleRadius1 / 0.050) }, geometry: { type: 'Polygon', coordinates: [r1] } },
            { type: 'Feature', properties: { opacity: Math.max(0, 1 - rippleRadius2 / 0.050) }, geometry: { type: 'Polygon', coordinates: [r2] } },
            { type: 'Feature', properties: { opacity: Math.max(0, 1 - rippleRadius3 / 0.050) }, geometry: { type: 'Polygon', coordinates: [r3] } },
          ],
        });
      }

      // 3. Flowing Water Discharge Particles
      if (layerWaterFlow) {
        const particleSource = map.getSource('water-flow-particles-src') as maplibregl.GeoJSONSource | undefined;
        if (particleSource) {
          const particleFeatures: any[] = particlesRef.current.map((p) => {
            p.progress = (p.progress + p.speed * (delta / 16.6)) % 1;
            const channel = p.channel === 'canal' ? KOSHI_EAST_CANAL_FLOW : KOSHI_MAIN_FLOW_CHANNEL;
            const { coord, bearing } = interpolatePointAlongPolyline(channel, p.progress);

            return {
              type: 'Feature',
              properties: {
                id: p.id,
                channel: p.channel,
                bearing,
                speedKmh: (p.speed * 12000).toFixed(0),
              },
              geometry: {
                type: 'Point',
                coordinates: coord,
              },
            };
          });

          particleSource.setData({
            type: 'FeatureCollection',
            features: particleFeatures,
          });
        }
      }

      animFrameRef.current = requestAnimationFrame(animateFrame);
    };

    animFrameRef.current = requestAnimationFrame(animateFrame);

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [mapLoaded, layerWaterFlow]);

  // Synchronize GeoJSON sources when incidents data updates
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const src = map.getSource('sos-incidents-geojson-src') as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(incidentsGeoJson);
    }
  }, [incidentsGeoJson, mapLoaded]);

  // Synchronize dynamic layer visibility toggles and operational properties
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    // Depth Heatmap Toggle
    if (map.getLayer('flood-depth-heatmap-layer')) {
      map.setLayoutProperty('flood-depth-heatmap-layer', 'visibility', layerHeatmap ? 'visible' : 'none');
    }

    // Water Flow Vectors Toggle
    const flowVisibility = layerWaterFlow ? 'visible' : 'none';
    if (map.getLayer('water-flow-casing')) map.setLayoutProperty('water-flow-casing', 'visibility', flowVisibility);
    if (map.getLayer('water-flow-core')) map.setLayoutProperty('water-flow-core', 'visibility', flowVisibility);
    if (map.getLayer('water-flow-particles-glow')) map.setLayoutProperty('water-flow-particles-glow', 'visibility', flowVisibility);
    if (map.getLayer('water-flow-particles-core')) map.setLayoutProperty('water-flow-particles-core', 'visibility', flowVisibility);

    // Clustered SOS Toggle
    const sosVisibility = layerClusteredSOS && showIncidents ? 'visible' : 'none';
    if (map.getLayer('sos-clusters-pulse')) map.setLayoutProperty('sos-clusters-pulse', 'visibility', sosVisibility);
    if (map.getLayer('sos-clusters-body')) map.setLayoutProperty('sos-clusters-body', 'visibility', sosVisibility);
    if (map.getLayer('sos-cluster-count')) map.setLayoutProperty('sos-cluster-count', 'visibility', sosVisibility);

    // Observed Inundation and Satellite Wipe Opacity
    if (map.getLayer('observed-inundation-fill')) {
      map.setLayoutProperty('observed-inundation-fill', 'visibility', showInundation && (DEMO_MODE || Boolean(observedExtent)) ? 'visible' : 'none');
      if (mode === 'satellite') {
        map.setPaintProperty('observed-inundation-fill', 'fill-opacity', (wipePosition / 100) * 0.55);
      }
    }
    if (map.getLayer('observed-inundation-stroke')) {
      map.setLayoutProperty('observed-inundation-stroke', 'visibility', showInundation && (DEMO_MODE || Boolean(observedExtent)) ? 'visible' : 'none');
    }

    // Forecast Horizon Extents
    if (map.getLayer('forecast-horizon-fill')) {
      map.setLayoutProperty('forecast-horizon-fill', 'visibility', DEMO_MODE && showForecast ? 'visible' : 'none');
    }
    if (map.getLayer('forecast-horizon-stroke')) {
      map.setLayoutProperty('forecast-horizon-stroke', 'visibility', DEMO_MODE && showForecast ? 'visible' : 'none');
    }

    // Infrastructure Road Cuts
    if (map.getLayer('road-cuts-lines')) {
      map.setLayoutProperty('road-cuts-lines', 'visibility', DEMO_MODE && showInfrastructure ? 'visible' : 'none');
    }
  }, [layerHeatmap, layerWaterFlow, layerClusteredSOS, showIncidents, showInundation, showForecast, showInfrastructure, observedExtent, mode, wipePosition, verificationLayers, mapLoaded]);

  // Initialize MapLibre GL with 100% keyless Esri Satellite & Dark Matter sources
  useEffect(() => {
    if (!mapContainerRef.current) return;

    const darkStyle: maplibregl.StyleSpecification = {
      version: 8,
      sources: {
        'esri-satellite': {
          type: 'raster',
          tiles: [
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          ],
          tileSize: 256,
          attribution: '&copy; Esri &copy; Maxar, Earthstar Geographics',
          maxzoom: 19,
        },
        'carto-dark': {
          type: 'raster',
          tiles: [
            'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
            'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
            'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
          ],
          tileSize: 256,
          attribution: '&copy; CartoDB &copy; OpenStreetMap',
          maxzoom: 19,
        },
        'terrain-dem': {
          type: 'raster-dem',
          tiles: [
            'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
          ],
          encoding: 'terrarium',
          tileSize: 256,
          maxzoom: 15,
        },
      },
      layers: [
        {
          id: 'carto-dark-layer',
          type: 'raster',
          source: 'carto-dark',
          minzoom: 0,
          maxzoom: 20,
          layout: {
            visibility: basemap === 'satellite' ? 'none' : 'visible',
          },
        },
        {
          id: 'esri-satellite-layer',
          type: 'raster',
          source: 'esri-satellite',
          minzoom: 0,
          maxzoom: 20,
          layout: {
            visibility: basemap === 'satellite' ? 'visible' : 'none',
          },
          paint: {
            'raster-opacity': 1.0,
          },
        },
      ],
      glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    };

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: darkStyle,
      center: center,
      zoom: zoom,
      pitch: pitch,
      bearing: bearing,
      maxPitch: 85,
    });

    // Add navigation controls
    map.addControl(
      new maplibregl.NavigationControl({
        visualizePitch: true,
        showCompass: true,
        showZoom: true,
      }),
      'top-right'
    );

    map.on('load', () => {
      try {
        map.setTerrain({ source: 'terrain-dem', exaggeration: 1.5 });
      } catch (err) {
        console.warn('MapLibre terrain warning:', err);
      }

      try {
        map.setSky({
          'sky-color': '#030814',
          'sky-horizon-blend': 0.6,
          'horizon-color': '#091a32',
          'fog-color': '#040d1a',
        } as any);
      } catch {
        // Fallback
      }

      setupMapLayers(map);
      setMapLoaded(true);

      map.on('error', () => {
        // Quietly absorb offline tile errors
      });
    });

    mapRef.current = map;

    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Synchronize basemap selection (Satellite vs Dark Matter)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const showSatellite = basemap === 'satellite';
    if (map.getLayer('esri-satellite-layer')) {
      map.setLayoutProperty('esri-satellite-layer', 'visibility', showSatellite ? 'visible' : 'none');
    }
    if (map.getLayer('carto-dark-layer')) {
      map.setLayoutProperty('carto-dark-layer', 'visibility', showSatellite ? 'none' : 'visible');
    }
  }, [basemap, mapLoaded]);

  // Update camera when center, zoom, pitch change
  const centerLng = center[0];
  const centerLat = center[1];
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;
    map.flyTo({
      center,
      zoom,
      pitch: is3D ? pitch : 0,
      bearing: is3D ? bearing : 0,
      duration: 1200,
    });
  }, [centerLng, centerLat, center, zoom, pitch, bearing, is3D, mapLoaded]);

  // Real PostGIS event-linked extent integration
  useEffect(() => {
    if (DEMO_MODE || !mapLoaded) return;
    const map = mapRef.current;
    const source = map?.getSource('observed-inundation-src') as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    source.setData(observedExtent ? (observedExtent as any) : { type: 'FeatureCollection', features: [] });
    if (!observedExtent?.geometry || !map) return;
    const pairs: number[][] = [];
    const walk = (node: unknown): void => {
      if (!Array.isArray(node)) return;
      if (node.length >= 2 && typeof node[0] === 'number' && typeof node[1] === 'number') {
        const lon = node[0]; const lat = node[1];
        if (Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lon) <= 180 && Math.abs(lat) <= 90) pairs.push([lon, lat]);
        return;
      }
      node.forEach(walk);
    };
    walk(observedExtent.geometry.coordinates);
    if (!pairs.length) return;
    const lons = pairs.map(p => p[0]); const lats = pairs.map(p => p[1]);
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 45, maxZoom: 12, duration: 900 });
  }, [observedExtent, mapLoaded]);

  // Manage Interactive Markers: Unclustered Pulsating SOS Pins, Gauges, Facilities & Shelters
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    // 1. Telemetry Gauges
    if (DEMO_MODE && showGauges) {
      KOSHI_TELEMETRY_GAUGES.forEach((gauge) => {
        const el = document.createElement('div');
        el.className = 'group cursor-pointer transform -translate-x-1/2 -translate-y-1/2 transition-transform hover:scale-110';
        const isCritical = gauge.currentLevel >= gauge.dangerThreshold;
        const color = isCritical ? 'bg-rose-500' : 'bg-amber-500';
        const borderColor = isCritical ? 'border-rose-300' : 'border-amber-300';

        el.innerHTML = `
          <div class="relative flex items-center justify-center">
            <span class="animate-ping absolute inline-flex h-7 w-7 rounded-full ${color} opacity-60"></span>
            <div class="relative w-6 h-6 rounded-full ${color} border-2 ${borderColor} flex items-center justify-center text-[10px] font-bold text-slate-950 shadow-[0_0_12px_rgba(0,0,0,0.8)]">
              ▲
            </div>
            <div class="absolute left-7 bg-[#060e1d]/95 border border-[#1e3a5f] px-2 py-0.5 rounded text-[10px] font-mono font-bold text-white whitespace-nowrap shadow-md pointer-events-none opacity-90 group-hover:opacity-100">
              ${gauge.name.split(' ')[0]}: <span class="${isCritical ? 'text-rose-400' : 'text-amber-400'}">${gauge.currentLevel}m</span>
            </div>
          </div>
        `;

        el.addEventListener('click', (e) => {
          e.stopPropagation();
          setActivePopupData({
            type: 'GAUGE',
            title: gauge.name,
            river: gauge.river,
            current: `${gauge.currentLevel}m`,
            danger: `${gauge.dangerThreshold}m`,
            trend: gauge.trend,
            discharge: `${gauge.flowRate.toLocaleString()} m³/s`,
            coords: [gauge.coordinates[1], gauge.coordinates[0]],
          });
          if (onSelectGauge) onSelectGauge(gauge.id);
        });

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([gauge.coordinates[1], gauge.coordinates[0]])
          .addTo(map);

        markersRef.current.push(marker);
      });
    }

    // 2. Interactive Pulsating Citizen SOS Pins (Displayed on map zoom in or when unclustered)
    if (showIncidents && incidents.length > 0) {
      incidents.forEach((req) => {
        const isSelected = selectedIncidentId === req.id;
        const isCritical = req.urgency === 'CRITICAL';
        const isHigh = req.urgency === 'HIGH';
        const isDispatched = Boolean(dispatchedIncidents[req.id]);

        const badgeColor = isDispatched ? '#10b981' : isCritical ? '#ef4444' : isHigh ? '#f59e0b' : '#06b6d4';
        const pulseColor = isDispatched ? 'bg-emerald-500' : isCritical ? 'bg-rose-500' : 'bg-cyan-500';

        const el = document.createElement('div');
        el.className = `cursor-pointer transition-all duration-300 ${isSelected ? 'scale-125 z-50' : 'hover:scale-115'}`;

        // Custom Cyber-Tactical SVG Pin with Concentric Pulsating Radar Beacon Rings
        el.innerHTML = `
          <div class="relative flex items-center justify-center group">
            <span class="animate-ping absolute inline-flex h-12 w-12 rounded-full ${pulseColor} opacity-70"></span>
            <span class="animate-ping absolute inline-flex h-8 w-8 rounded-full ${pulseColor} opacity-90" style="animation-duration: 1.5s; animation-delay: 0.3s"></span>
            <div class="relative w-8 h-8 rounded-full border-2 ${isSelected ? 'border-amber-300 ring-4 ring-amber-400/50 scale-110' : 'border-white/90'} flex items-center justify-center text-[10px] font-mono font-bold text-white shadow-2xl backdrop-blur-sm transition-transform"
                 style="background: radial-gradient(circle, ${badgeColor} 40%, #030712 100%); box-shadow: 0 0 ${isSelected ? '22px #f59e0b' : '14px ' + badgeColor + '99'}">
              <svg class="w-4 h-4 text-white drop-shadow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
            </div>
            <div class="absolute -top-8 left-1/2 -translate-x-1/2 bg-black/95 border ${isSelected ? 'border-amber-400 text-amber-300' : 'border-cyan-500/40 text-cyan-300'} px-2 py-0.5 rounded text-[9px] font-mono font-bold whitespace-nowrap shadow-lg ${isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity pointer-events-none z-30">
              ${req.requester_name} (${req.people_count || 1} souls) &bull; ${req.urgency}
            </div>
          </div>
        `;

        el.addEventListener('click', (e) => {
          e.stopPropagation();
          setActivePopupData({
            type: 'INCIDENT',
            id: req.id,
            requester: req.requester_name,
            phone: req.contact_number,
            location: req.location_name,
            category: req.category,
            urgency: req.urgency,
            depth: req.estimated_water_depth || '1.8m (Fast Current)',
            status: dispatchedIncidents[req.id] ? 'DISPATCHED_TO_UNIT_ALPHA' : (req.status || req.handoff_status || 'LOCAL_LOGGED'),
            timestamp: req.timestamp || '4 mins ago',
            coords: [req.coordinates[1], req.coordinates[0]],
            peopleCount: req.people_count || 1,
            landmark: req.landmark || 'Concrete rooftop refuge',
            notes: req.notes,
          });
          if (onSelectIncident) onSelectIncident(req.id);
        });

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([req.coordinates[1], req.coordinates[0]])
          .addTo(map);

        markersRef.current.push(marker);
      });
    }

    // 3. Emergency Facilities (Hospitals & Shelters)
    if (facilities && facilities.length > 0) {
      facilities.forEach((fac) => {
        if (fac.longitude == null || fac.latitude == null) return;
        const el = document.createElement('div');
        const isHospital = fac.type === 'hospital';
        const isVerified = fac.verification_status === 'verified';
        const isDemo = fac.verification_status === 'demo_labeled';
        const color = isVerified ? 'bg-emerald-500' : isDemo ? 'bg-sky-500' : 'bg-rose-500';
        const borderColor = isVerified ? 'border-emerald-300' : isDemo ? 'border-sky-300' : 'border-rose-300';
        el.className = 'cursor-pointer group transform -translate-x-1/2 -translate-y-1/2 hover:scale-125 transition-transform z-20';
        el.innerHTML = `
          <div class="relative flex items-center justify-center">
            <div class="w-6 h-6 rounded-full ${color} border-2 ${borderColor} flex items-center justify-center text-[10px] font-bold text-white shadow-lg">
              ${isHospital ? 'H' : 'S'}
            </div>
            <div class="absolute left-7 bg-[#060e1d]/95 border border-[#1e3a5f] px-2 py-0.5 rounded text-[10px] font-mono font-bold text-white whitespace-nowrap shadow-md pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-30">
              ${fac.name} (${fac.type})
            </div>
          </div>
        `;

        el.addEventListener('click', (e) => {
          e.stopPropagation();
          setActivePopupData({
            type: 'FACILITY',
            title: fac.name,
            facilityType: fac.type,
            verification: fac.verification_status,
            capacity: fac.capacity ? `${fac.capacity} (${isHospital ? 'beds' : 'persons'})` : 'Unrecorded',
            contact: fac.contact_info || 'None recorded',
            source: fac.source || 'Database',
            limitations: fac.limitations,
            coords: [fac.longitude, fac.latitude],
          });
          if (onSelectFacility) onSelectFacility(fac);
        });

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([fac.longitude, fac.latitude])
          .addTo(map);

        markersRef.current.push(marker);
      });
    } else if (DEMO_MODE && showShelters) {
      KOSHI_SHELTERS.forEach((shelter) => {
        const el = document.createElement('div');
        el.className = 'cursor-pointer group transform -translate-x-1/2 -translate-y-1/2 hover:scale-110';
        el.innerHTML = `
          <div class="w-5 h-5 rounded bg-emerald-600 border border-emerald-300 flex items-center justify-center text-[10px] text-white shadow-md">
            ⌂
          </div>
        `;

        el.addEventListener('click', (e) => {
          e.stopPropagation();
          setActivePopupData({
            type: 'SHELTER',
            title: shelter.name,
            capacity: shelter.capacity,
            occupancy: shelter.currentOccupancy,
            elevation: `${shelter.elevationMsl}m MSL`,
            contact: shelter.contact,
            coords: [shelter.coordinates[1], shelter.coordinates[0]],
          });
        });

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([shelter.coordinates[1], shelter.coordinates[0]])
          .addTo(map);

        markersRef.current.push(marker);
      });
    }

    // 4. Settlement Labels
    if (DEMO_MODE) {
      KOSHI_SETTLEMENTS.forEach((settlement) => {
        const el = document.createElement('div');
        el.className = 'pointer-events-none transform -translate-x-1/2 -translate-y-1/2';
        el.innerHTML = `
          <div class="flex items-center gap-1 px-1.5 py-0.5 rounded bg-black/75 border border-[#1e3a5f]/60 text-[9px] font-mono text-slate-300 whitespace-nowrap shadow-sm backdrop-blur-xs">
            <span class="w-1.5 h-1.5 rounded-full bg-sky-400"></span>
            <span>${settlement.name}</span>
          </div>
        `;

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat(settlement.coords as [number, number])
          .addTo(map);

        markersRef.current.push(marker);
      });
    }
  }, [mapLoaded, showGauges, showIncidents, showShelters, facilities, onSelectFacility, incidents, selectedIncidentId, onSelectIncident, onSelectGauge, dispatchedIncidents]);

  // Center on selected incident if requested externally
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !selectedIncidentId) return;

    const targetReq = incidents.find((r) => r.id === selectedIncidentId);
    if (targetReq) {
      map.flyTo({
        center: [targetReq.coordinates[1], targetReq.coordinates[0]],
        zoom: 12.5,
        duration: 1200,
      });
    }
  }, [selectedIncidentId, incidents, mapLoaded]);

  // Toggle 3D Terrain Elevation vs 2D Ortho
  const toggle3DMode = () => {
    const map = mapRef.current;
    if (!map) return;

    const next3D = !is3D;
    setIs3D(next3D);

    if (next3D) {
      map.setTerrain({ source: 'terrain-dem', exaggeration: 1.5 });
      map.easeTo({ pitch: 55, bearing: -15, duration: 800 });
    } else {
      map.setTerrain(null);
      map.easeTo({ pitch: 0, bearing: 0, duration: 800 });
    }
  };

  // Reset View to Center & Elevation Angle
  const handleResetView = () => {
    const map = mapRef.current;
    if (!map) return;
    map.flyTo({
      center,
      zoom,
      pitch: is3D ? 55 : 0,
      bearing: is3D ? -15 : 0,
      duration: 1000,
    });
  };

  // Reset Bearing to North
  const handleResetNorth = () => {
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({ bearing: 0, duration: 500 });
  };

  return (
    <div
      className={`relative w-full rounded-xl overflow-hidden border border-cyan-500/30 bg-[#030712] shadow-[0_0_35px_rgba(0,0,0,0.8)] ${className} ${
        isFullscreen ? 'fixed inset-0 z-50 h-screen w-screen rounded-none' : ''
      }`}
      style={{ height: isFullscreen ? '100vh' : height }}
    >
      {/* Map Canvas Container */}
      <div ref={mapContainerRef} className="w-full h-full" />

      {/* Top-Left Floating Tactical Telemetry HUD */}
      <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center bg-zinc-950/85 backdrop-blur-xl rounded-xl p-1.5 border border-zinc-800/80 shadow-2xl pointer-events-auto gap-1.5">
        {/* 3D Terrain Switcher */}
        <button
          onClick={toggle3DMode}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-bold tracking-wider uppercase transition-all cursor-pointer ${
            is3D
              ? 'bg-cyan-950/70 text-cyan-300 border border-cyan-500/40 shadow-[0_0_10px_rgba(6,182,212,0.25)]'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
          }`}
          title="Toggle 3D Digital Elevation Model vs 2D Orthographic View"
        >
          <Layers className="w-3.5 h-3.5" />
          <span>{is3D ? '3D TERRAIN' : '2D ORTHO'}</span>
        </button>

        <div className="h-4 w-px bg-zinc-800 mx-0.5" />

        {/* Camera Orientation Quick Actions */}
        <button
          onClick={handleResetNorth}
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60 transition-colors cursor-pointer"
          title="Reset Camera Bearing to True North"
        >
          <Compass className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={handleResetView}
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60 transition-colors cursor-pointer"
          title="Reset Camera Center & Zoom"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={() => setIsFullscreen(!isFullscreen)}
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60 transition-colors cursor-pointer"
          title={isFullscreen ? 'Exit Fullscreen' : 'Expand Geospatial Canvas'}
        >
          {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Top-Right Dedicated Interactive Layer Control Toolbar (Requirement 4) */}
      <div className="absolute top-3 right-14 z-10 flex flex-wrap items-center bg-zinc-950/90 backdrop-blur-xl rounded-xl p-1.5 border border-cyan-500/30 shadow-2xl pointer-events-auto gap-1">
        {/* Toggle 1: Satellite Base Imagery */}
        <button
          onClick={() => setBasemap((prev) => (prev === 'satellite' ? 'dark' : 'satellite'))}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-mono font-bold tracking-wider uppercase transition-all cursor-pointer ${
            basemap === 'satellite'
              ? 'bg-cyan-950/70 text-cyan-300 border border-cyan-500/40 shadow-[0_0_10px_rgba(6,182,212,0.25)]'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
          }`}
          title="Toggle Esri High-Resolution Satellite Base Imagery"
        >
          <Satellite className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">SATELLITE BASE</span>
        </button>

        {/* Toggle 2: Depth-Gradient Flood Heatmap */}
        <button
          onClick={() => setLayerHeatmap((prev) => !prev)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-mono font-bold tracking-wider uppercase transition-all cursor-pointer ${
            layerHeatmap
              ? 'bg-amber-950/60 text-amber-300 border border-amber-500/40 shadow-[0_0_10px_rgba(245,158,11,0.25)]'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
          }`}
          title="Toggle Depth-Gradient Inundation Heatmap (Green -> Amber -> Red)"
        >
          <Flame className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">FLOOD HEATMAP</span>
        </button>

        {/* Toggle 3: Water Flow Discharge Vectors */}
        <button
          onClick={() => setLayerWaterFlow((prev) => !prev)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-mono font-bold tracking-wider uppercase transition-all cursor-pointer ${
            layerWaterFlow
              ? 'bg-sky-950/70 text-sky-300 border border-sky-500/40 shadow-[0_0_10px_rgba(56,189,248,0.25)]'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
          }`}
          title="Toggle Animated Basin Water Discharge & Directional Vector Flow"
        >
          <Waves className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">WATER FLOW</span>
        </button>

        {/* Toggle 4: Clustered SOS Incident Markers */}
        <button
          onClick={() => setLayerClusteredSOS((prev) => !prev)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-mono font-bold tracking-wider uppercase transition-all cursor-pointer ${
            layerClusteredSOS
              ? 'bg-rose-950/60 text-rose-300 border border-rose-500/40 shadow-[0_0_10px_rgba(244,63,94,0.25)]'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
          }`}
          title="Toggle Clustered Citizen Emergency SOS Requests"
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">SOS CLUSTERS</span>
        </button>
      </div>

      {/* Bottom Information Legend & Telemetry Bar */}
      <div className="absolute bottom-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2.5 pointer-events-none">
        {/* Layer Legend */}
        <div className="inline-flex items-center gap-3.5 px-3.5 py-2 rounded-xl bg-zinc-950/90 border border-zinc-800/80 text-xs font-mono text-zinc-200 backdrop-blur-xl pointer-events-auto shadow-xl">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-500"></span>
            </span>
            <span className="text-xs font-semibold text-cyan-200">
              {DEMO_MODE ? 'ANIMATED SURGE PULSE' : observedExtent ? 'OBSERVED SATELLITE EXTENT' : 'NO SATELLITE EXTENT'}
            </span>
          </div>

          <span className="text-zinc-700 select-none">|</span>

          {/* Depth Gradient Heatmap Legend Indicator */}
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block"></span>
            <span className="text-[10px] text-zinc-400">&lt;0.5m</span>
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block ml-1"></span>
            <span className="text-[10px] text-zinc-400">1.2m</span>
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block ml-1"></span>
            <span className="text-[10px] text-zinc-400">&gt;2.5m</span>
          </div>

          <span className="text-zinc-700 select-none hidden sm:inline">|</span>

          <div className="hidden sm:flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-sky-400 inline-block shadow-[0_0_6px_rgba(56,189,248,0.7)]" />
            <span className="text-xs font-semibold text-sky-200">13,240 M³/S DISCHARGE</span>
          </div>
        </div>

        {/* Projection & Elevation Spec */}
        <div className="px-3.5 py-2 rounded-xl bg-zinc-950/90 border border-zinc-800/80 text-xs font-mono text-zinc-300 backdrop-blur-xl pointer-events-auto shadow-xl font-medium">
          <span>ESRI WORLD IMAGERY · KOSHI DEM 30M // WGS84</span>
        </div>
      </div>

      {/* Sleek Dark-Themed Tactical Incident & Telemetry Popup (Requirement 3) */}
      {activePopupData && (
        <div className="absolute top-16 right-3 z-30 w-80 rounded-2xl bg-zinc-950/95 border border-cyan-500/40 p-4 text-xs font-mono text-white shadow-[0_0_35px_rgba(6,182,212,0.2)] backdrop-blur-2xl animate-in fade-in slide-in-from-top-3">
          {/* Header */}
          <div className="flex items-start justify-between pb-2.5 border-b border-zinc-800/80">
            <div className="flex items-center gap-2">
              {activePopupData.type === 'INCIDENT' ? (
                <div className="relative">
                  <span className="animate-ping absolute inline-flex h-4 w-4 rounded-full bg-rose-500 opacity-60"></span>
                  <LifeBuoy className="w-4 h-4 text-rose-400 relative" />
                </div>
              ) : activePopupData.type === 'GAUGE' ? (
                <Activity className="w-4 h-4 text-amber-400" />
              ) : (
                <Shield className="w-4 h-4 text-emerald-400" />
              )}
              <div>
                <span className="font-bold uppercase tracking-wider text-white text-xs block">
                  {activePopupData.type === 'INCIDENT'
                    ? `INCIDENT #${activePopupData.id}`
                    : activePopupData.title}
                </span>
                {activePopupData.type === 'INCIDENT' && (
                  <span className="text-[10px] text-cyan-400 font-mono flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5" /> Reported {activePopupData.timestamp}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={() => setActivePopupData(null)}
              className="text-zinc-400 hover:text-white text-lg font-bold leading-none cursor-pointer p-0.5"
            >
              &times;
            </button>
          </div>

          {/* Body Content */}
          <div className="py-3 space-y-2 text-[11px]">
            {activePopupData.type === 'INCIDENT' && (
              <>
                <div className="flex justify-between items-center bg-zinc-900/60 px-2 py-1.5 rounded-lg border border-zinc-800">
                  <span className="text-zinc-400 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                    Priority:
                  </span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                    activePopupData.urgency === 'CRITICAL'
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-[0_0_8px_rgba(244,63,94,0.3)]'
                      : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  }`}>
                    {activePopupData.urgency} SURGE PRIORITY
                  </span>
                </div>

                <div className="flex justify-between">
                  <span className="text-zinc-400">Requester:</span>
                  <span className="font-bold text-white">{activePopupData.requester}</span>
                </div>

                {activePopupData.phone && (
                  <div className="flex justify-between">
                    <span className="text-zinc-400 flex items-center gap-1">
                      <Phone className="w-3 h-3 text-cyan-400" /> Contact:
                    </span>
                    <span className="text-cyan-300 font-bold">{activePopupData.phone}</span>
                  </div>
                )}

                <div className="flex justify-between">
                  <span className="text-zinc-400 flex items-center gap-1">
                    <Users className="w-3 h-3 text-amber-400" /> Souls at Risk:
                  </span>
                  <span className="text-amber-300 font-bold">{activePopupData.peopleCount} Persons</span>
                </div>

                <div className="flex justify-between">
                  <span className="text-zinc-400 flex items-center gap-1">
                    <Droplets className="w-3 h-3 text-sky-400" /> Water Depth:
                  </span>
                  <span className="text-sky-300 font-bold">{activePopupData.depth}</span>
                </div>

                <div className="flex justify-between">
                  <span className="text-zinc-400">Location:</span>
                  <span className="text-zinc-200 text-right truncate max-w-[170px]" title={activePopupData.location}>
                    {activePopupData.location}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-zinc-400">Triage Status:</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                    activePopupData.status === 'DISPATCHED_TO_UNIT_ALPHA'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : 'bg-zinc-800 text-zinc-300'
                  }`}>
                    {activePopupData.status}
                  </span>
                </div>
              </>
            )}

            {activePopupData.type === 'GAUGE' && (
              <>
                <div className="flex justify-between">
                  <span className="text-zinc-400">River Basin:</span>
                  <span className="text-zinc-200">{activePopupData.river}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Current Level:</span>
                  <span className="text-rose-400 font-bold">{activePopupData.current}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Danger Mark:</span>
                  <span className="text-zinc-300">{activePopupData.danger}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Discharge Flow:</span>
                  <span className="text-cyan-300 font-bold">{activePopupData.discharge}</span>
                </div>
              </>
            )}

            {activePopupData.type === 'SHELTER' && (
              <>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Elevation:</span>
                  <span className="text-emerald-300 font-bold">{activePopupData.elevation}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Capacity:</span>
                  <span className="text-white">
                    {activePopupData.occupancy} / {activePopupData.capacity} souls
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Emergency Phone:</span>
                  <span className="text-zinc-300">{activePopupData.contact}</span>
                </div>
              </>
            )}

            {activePopupData.type === 'FACILITY' && (
              <>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Facility Type:</span>
                  <span className="font-bold text-white capitalize">{activePopupData.facilityType}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-zinc-400">Verification:</span>
                  <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold uppercase ${
                    activePopupData.verification === 'verified'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                  }`}>
                    {activePopupData.verification}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Recorded Capacity:</span>
                  <span className="text-white font-bold">{activePopupData.capacity}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Contact:</span>
                  <span className="text-cyan-300 font-bold">{activePopupData.contact}</span>
                </div>
              </>
            )}

            <div className="pt-2 border-t border-zinc-800/80 text-[10px] text-zinc-400 flex items-center justify-between">
              <span className="flex items-center gap-1">
                <MapPin className="w-3 h-3 text-cyan-400" /> Coords:
              </span>
              <span>{activePopupData.coords?.[1]?.toFixed(4)}°N, {activePopupData.coords?.[0]?.toFixed(4)}°E</span>
            </div>
          </div>

          {/* Direct "DISPATCH UNIT" Trigger Button (Requirement 3) */}
          {activePopupData.type === 'INCIDENT' && (
            <div className="mt-2 pt-2 border-t border-zinc-800/80 space-y-1.5">
              <button
                onClick={() => handleTriggerDispatch(activePopupData.id)}
                className={`w-full py-2.5 px-3 rounded-xl font-mono font-bold text-xs tracking-wider uppercase transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer shadow-lg ${
                  dispatchedIncidents[activePopupData.id]
                    ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/50 shadow-[0_0_15px_rgba(16,185,129,0.3)]'
                    : 'bg-gradient-to-r from-cyan-600 to-sky-600 hover:from-cyan-500 hover:to-sky-500 text-white border border-cyan-400/40 shadow-[0_0_15px_rgba(6,182,212,0.3)] hover:scale-[1.02]'
                }`}
              >
                {dispatchedIncidents[activePopupData.id] ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>UNIT ALPHA DISPATCHED</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5 text-white animate-pulse" />
                    <span>DISPATCH RESCUE UNIT</span>
                  </>
                )}
              </button>

              {onSelectIncident && (
                <button
                  onClick={() => {
                    onSelectIncident(activePopupData.id);
                    setActivePopupData(null);
                  }}
                  className="w-full py-1.5 px-3 rounded-lg bg-zinc-900/80 hover:bg-zinc-800 text-zinc-300 hover:text-white font-mono text-[10px] tracking-wider uppercase transition-colors text-center border border-zinc-700/60 cursor-pointer"
                >
                  VIEW FULL DOSSIER
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
