import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  Activity,
  Compass,
  Layers,
  LifeBuoy,
  Maximize2,
  Minimize2,
  RotateCcw,
  Satellite,
  Shield,
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
  className = '',
  height = '520px',
  mode = 'overview',
  wipePosition = 50,
  verificationLayers = { tp: true, fp: true, fn: true },
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const [is3D, setIs3D] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [basemap, setBasemap] = useState<'dark' | 'satellite'>(
    mode === 'satellite' ? 'satellite' : 'dark'
  );
  const [activePopupData, setActivePopupData] = useState<any | null>(null);

  // Initialize MapLibre GL with 100% free, keyless tile endpoints
  useEffect(() => {
    if (!mapContainerRef.current) return;

    // Free keyless vector/raster tiles style with aerospace dark matter and Esri satellite options
    const darkStyle: maplibregl.StyleSpecification = {
      version: 8,
      sources: {
        'esri-dark': {
          type: 'raster',
          tiles: [
            'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
          ],
          tileSize: 256,
          attribution: '&copy; Esri &copy; OpenStreetMap contributors',
          maxzoom: 16,
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
        'esri-satellite': {
          type: 'raster',
          tiles: [
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          ],
          tileSize: 256,
          attribution: '&copy; Esri &copy; Maxar, Earthstar Geographics',
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
          id: 'base-dark-layer',
          type: 'raster',
          source: 'esri-dark',
          minzoom: 0,
          maxzoom: 20,
          layout: {
            visibility: mode === 'satellite' ? 'none' : 'visible',
          },
        },
        {
          id: 'esri-satellite-layer',
          type: 'raster',
          source: 'esri-satellite',
          minzoom: 0,
          maxzoom: 20,
          layout: {
            visibility: mode === 'satellite' ? 'visible' : 'none',
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
      // Enable 3D terrain by default
      try {
        map.setTerrain({ source: 'terrain-dem', exaggeration: 1.5 });
      } catch (err) {
        console.warn('MapLibre terrain initialization warning:', err);
      }

      // Add Sky atmosphere
      try {
        map.setSky({
          'sky-color': '#030814',
          'sky-horizon-blend': 0.6,
          'horizon-color': '#091a32',
          'fog-color': '#040d1a',
        } as any);
      } catch {
        // Soft fallback
      }

      // Setup dynamic GeoJSON sources for Flood Extents
      setupMapLayers(map);
      setMapLoaded(true);

      // Gracefully handle tile network errors in detached/offline demo mode
      map.on('error', () => {
        // Absorbs tile 404/fetch errors silently when running detached from external tile servers
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

  // Synchronize basemap selection with map layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const showSatellite = basemap === 'satellite' || mode === 'satellite';
    if (map.getLayer('esri-satellite-layer')) {
      map.setLayoutProperty('esri-satellite-layer', 'visibility', showSatellite ? 'visible' : 'none');
    }
    if (map.getLayer('base-dark-layer')) {
      map.setLayoutProperty('base-dark-layer', 'visibility', showSatellite ? 'none' : 'visible');
    }
  }, [basemap, mode, mapLoaded]);

  // Update center/pitch/bearing when props change
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
  }, [center, zoom, pitch, bearing, is3D, mapLoaded]);

  // Setup Map Layers (Inundation Polygons, Horizon Polygons, Road Cuts)
  const setupMapLayers = useCallback((map: maplibregl.Map) => {
    // 1. Observed Satellite Inundation Layer (Sentinel-1/2 deep cyan)
    const observedCoords = toGeoJsonCoords(HORIZON_FORECASTS['1h'].polygonCoords);
    if (!map.getSource('observed-inundation-src')) {
      map.addSource('observed-inundation-src', {
        type: 'geojson',
        data: DEMO_MODE ? {
          type: 'Feature', properties: { name: 'Illustrative fixture only', areaKm2: 28.4 },
          geometry: { type: 'Polygon', coordinates: [observedCoords] },
        } : { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'observed-inundation-fill',
        type: 'fill',
        source: 'observed-inundation-src',
        paint: {
          'fill-color': '#00e5ff',
          'fill-opacity': 0.42,
        },
      });

      map.addLayer({
        id: 'observed-inundation-stroke',
        type: 'line',
        source: 'observed-inundation-src',
        paint: {
          'line-color': '#38bdf8',
          'line-width': 2.5,
          'line-opacity': 0.9,
        },
      });
    }

    // 2. Predictive Horizon Extent Layer (Dynamic amber/orange/crimson)
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

    // 3. Infrastructure & Road Cuts Layer (Dashed warning red)
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

    // 4. Candidate Route LineString Layer
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
  }, [activeHorizon, candidateRoute]);

  // Update candidate route line dynamically
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const src = map.getSource('candidate-route-src') as maplibregl.GeoJSONSource | undefined;
    if (src) {
      const hasRoute = candidateRoute && candidateRoute.length >= 2;
      src.setData(
        hasRoute
          ? {
              type: 'Feature',
              properties: { name: 'Candidate Route' },
              geometry: { type: 'LineString', coordinates: candidateRoute },
            }
          : { type: 'FeatureCollection', features: [] }
      );
      if (hasRoute) {
        const lons = candidateRoute.map((p) => p[0]);
        const lats = candidateRoute.map((p) => p[1]);
        map.fitBounds(
          [
            [Math.min(...lons), Math.min(...lats)],
            [Math.max(...lons), Math.max(...lats)],
          ],
          { padding: 50, maxZoom: 13, duration: 800 }
        );
      }
    }
  }, [candidateRoute, mapLoaded]);

  // Update horizon layer dynamically as activeHorizon changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const src = map.getSource('forecast-horizon-src') as maplibregl.GeoJSONSource | undefined;
    if (src) {
      const activeCoords =
        activeHorizon === 'Now'
          ? toGeoJsonCoords(HORIZON_FORECASTS['1h'].polygonCoords)
          : toGeoJsonCoords(HORIZON_FORECASTS[activeHorizon as '1h' | '3h' | '6h']?.polygonCoords || HORIZON_FORECASTS['3h'].polygonCoords);

      src.setData(DEMO_MODE ? { type: 'Feature', properties: { horizon: activeHorizon, source: 'illustrative' }, geometry: { type: 'Polygon', coordinates: [activeCoords] } } : { type: 'FeatureCollection', features: [] });

      const horizonColor =
        activeHorizon === '6h' ? '#ef4444' : activeHorizon === '3h' ? '#f97316' : '#f59e0b';

      if (map.getLayer('forecast-horizon-fill')) {
        map.setPaintProperty('forecast-horizon-fill', 'fill-color', horizonColor);
      }
      if (map.getLayer('forecast-horizon-stroke')) {
        map.setPaintProperty('forecast-horizon-stroke', 'line-color', horizonColor);
      }
    }
  }, [activeHorizon, mapLoaded]);

  // Real PostGIS event-linked extent replaces illustration in backend mode.
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

  // Dynamic layer visibility, wipe opacity, and verification layer styles
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    if (map.getLayer('observed-inundation-fill')) {
      map.setLayoutProperty('observed-inundation-fill', 'visibility', showInundation && (DEMO_MODE || Boolean(observedExtent)) ? 'visible' : 'none');
      if (mode === 'satellite') {
        map.setPaintProperty('observed-inundation-fill', 'fill-opacity', (wipePosition / 100) * 0.55);
      }
    }
    if (map.getLayer('observed-inundation-stroke')) {
      map.setLayoutProperty('observed-inundation-stroke', 'visibility', showInundation && (DEMO_MODE || Boolean(observedExtent)) ? 'visible' : 'none');
    }
    if (map.getLayer('forecast-horizon-fill')) {
      map.setLayoutProperty('forecast-horizon-fill', 'visibility', DEMO_MODE && showForecast ? 'visible' : 'none');
    }
    if (map.getLayer('forecast-horizon-stroke')) {
      map.setLayoutProperty('forecast-horizon-stroke', 'visibility', DEMO_MODE && showForecast ? 'visible' : 'none');
    }
    if (map.getLayer('road-cuts-lines')) {
      map.setLayoutProperty('road-cuts-lines', 'visibility', DEMO_MODE && showInfrastructure ? 'visible' : 'none');
    }
  }, [showInundation, showForecast, showInfrastructure, mode, wipePosition, verificationLayers, observedExtent, mapLoaded]);

  // Manage Interactive Markers (Gauges, Incidents, Shelters, Settlements)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    // Clear existing HTML markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    // 1. Gauges
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

    // 2. Citizen Assistance Reports / Incidents
    if (showIncidents && incidents.length > 0) {
      incidents.forEach((req) => {
        const isSelected = selectedIncidentId === req.id;
        const isCritical = req.urgency === 'CRITICAL';
        const isHigh = req.urgency === 'HIGH';
        const badgeColor = isCritical ? '#ef4444' : isHigh ? '#f59e0b' : '#38bdf8';

        const el = document.createElement('div');
        el.className = `cursor-pointer transition-all ${isSelected ? 'scale-125 z-50' : 'hover:scale-115'}`;

        el.innerHTML = `
          <div class="relative flex items-center justify-center">
            ${isCritical ? '<span class="animate-ping absolute inline-flex h-8 w-8 rounded-full bg-rose-500 opacity-60"></span>' : ''}
            <div class="w-6 h-6 rounded-full border-2 border-white flex items-center justify-center text-[9px] font-mono font-bold text-white shadow-lg" style="background-color: ${badgeColor}; box-shadow: 0 0 10px ${badgeColor}80">
              SOS
            </div>
          </div>
        `;

        el.addEventListener('click', (e) => {
          e.stopPropagation();
          setActivePopupData({
            type: 'INCIDENT',
            id: req.id,
            requester: req.requester_name,
            location: req.location_name,
            category: req.category,
            urgency: req.urgency,
            depth: req.estimated_water_depth || 'Not measured',
            status: req.status || req.handoff_status,
            coords: [req.coordinates[1], req.coordinates[0]],
            peopleCount: req.people_count,
            landmark: req.landmark,
          });
          if (onSelectIncident) onSelectIncident(req.id);
        });

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([req.coordinates[1], req.coordinates[0]])
          .addTo(map);

        markersRef.current.push(marker);
      });
    }

    // 3. Emergency Facilities (Shelters & Hospitals)
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
    if (DEMO_MODE) KOSHI_SETTLEMENTS.forEach((settlement) => {
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
  }, [mapLoaded, showGauges, showIncidents, showShelters, facilities, onSelectFacility, incidents, selectedIncidentId, onSelectIncident, onSelectGauge]);

  // Center on selected incident if provided
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

  // Camera flyTo when center, zoom, pitch, or bearing change externally (e.g. benchmark scene selector)
  const centerLng = center[0];
  const centerLat = center[1];
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;
    map.flyTo({
      center,
      zoom,
      pitch,
      bearing,
      duration: 1500,
      essential: true,
    });
  }, [centerLng, centerLat, center, zoom, pitch, bearing, mapLoaded]);

  // Toggle 3D Terrain / 2D Ortho Mode
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

  // Reset View to North and default elevation angle
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
      className={`relative w-full rounded-lg overflow-hidden border border-[#1e3a5f]/80 bg-[#040914] shadow-[0_4px_24px_rgba(0,0,0,0.6)] ${className} ${
        isFullscreen ? 'fixed inset-0 z-50 h-screen w-screen rounded-none' : ''
      }`}
      style={{ height: isFullscreen ? '100vh' : height }}
    >
      {/* Map Canvas Container */}
      <div ref={mapContainerRef} className="w-full h-full" />

      {/* Top Floating Telemetry HUD: Docked Segmented Toolbar */}
      <div className="absolute top-3 left-3 z-10 inline-flex items-center bg-zinc-950/80 backdrop-blur-md rounded-xl p-1 border border-zinc-800/80 shadow-md pointer-events-auto gap-1">
        {/* Terrain Mode Switcher */}
        <button
          onClick={toggle3DMode}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-semibold tracking-wider uppercase transition-all cursor-pointer ${
            is3D
              ? 'bg-cyan-950/40 text-cyan-400 shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
          }`}
          title="Toggle 3D Digital Elevation Model vs 2D Orthographic View"
        >
          <Layers className="w-3.5 h-3.5" />
          <span>{is3D ? '3D TERRAIN' : '2D ORTHO'}</span>
        </button>

        {/* Keyless Basemap Switcher: Carto Dark vs Esri Satellite */}
        <button
          onClick={() => setBasemap((prev) => (prev === 'dark' ? 'satellite' : 'dark'))}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-semibold tracking-wider uppercase transition-all cursor-pointer ${
            basemap === 'satellite' || mode === 'satellite'
              ? 'bg-cyan-950/40 text-cyan-400 shadow-sm'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
          }`}
          title="Toggle between CartoDB Dark Matter and Esri World Imagery Satellite"
        >
          <Satellite className="w-3.5 h-3.5" />
          <span>{basemap === 'satellite' || mode === 'satellite' ? 'ESRI SATELLITE' : 'CARTO DARK'}</span>
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

        {/* Fullscreen Expand */}
        <button
          onClick={() => setIsFullscreen(!isFullscreen)}
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60 transition-colors cursor-pointer"
          title={isFullscreen ? 'Exit Fullscreen' : 'Expand Geospatial Canvas'}
        >
          {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Bottom Information Legend & Coordinates Bar */}
      <div className="absolute bottom-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        {/* Layer Legend in a Single Clean Strip */}
        <div className="inline-flex items-center gap-3 px-3 py-1.5 rounded-xl bg-zinc-950/80 border border-zinc-800/80 text-xs font-mono text-zinc-300 backdrop-blur-md pointer-events-auto shadow-sm">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400 inline-block" />
            <span className="text-[11px] text-zinc-300">{DEMO_MODE ? 'DEMO FLOOD MASK' : observedExtent ? 'BACKEND OBSERVED EXTENT' : 'NO OBSERVED EXTENT'}</span>
          </div>

          <span className="text-zinc-700 select-none">|</span>

          <div className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full inline-block"
              style={{
                backgroundColor:
                  activeHorizon === '6h' ? '#ef4444' : activeHorizon === '3h' ? '#f97316' : '#f59e0b',
              }}
            />
            <span className="text-[11px] text-zinc-300">+{activeHorizon} ILLUSTRATION</span>
          </div>

          <span className="text-zinc-700 select-none hidden sm:inline">|</span>

          <div className="hidden sm:flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 bg-rose-500 inline-block" />
            <span className="text-[11px] text-rose-300">ROAD CUTS / DYKES</span>
          </div>
        </div>

        {/* Projection Spec */}
        <div className="px-3 py-1.5 rounded-xl bg-zinc-950/80 border border-zinc-800/80 text-[11px] font-mono text-zinc-400 backdrop-blur-md pointer-events-auto shadow-sm">
          <span>{DEMO_MODE ? 'DEMO EPSG:4326 · TERRAIN BASEMAP' : 'BACKEND EPSG:4326 · NOT FOR NAVIGATION'}</span>
        </div>
      </div>

      {/* Contextual Tactical Detail Popup */}
      {activePopupData && (
        <div className="absolute top-14 right-3 z-20 w-72 rounded-xl bg-zinc-950/90 border border-zinc-800/80 p-3.5 text-xs font-mono text-white shadow-2xl backdrop-blur-xl animate-in fade-in slide-in-from-top-2">
          <div className="flex items-start justify-between pb-2 border-b border-zinc-800">
            <div className="flex items-center gap-1.5">
              {activePopupData.type === 'INCIDENT' ? (
                <LifeBuoy className="w-4 h-4 text-rose-400" />
              ) : activePopupData.type === 'GAUGE' ? (
                <Activity className="w-4 h-4 text-amber-400" />
              ) : (
                <Shield className="w-4 h-4 text-emerald-400" />
              )}
              <span className="font-bold uppercase tracking-wider text-white">
                {activePopupData.type === 'INCIDENT'
                  ? `INCIDENT #${activePopupData.id}`
                  : activePopupData.title}
              </span>
            </div>
            <button
              onClick={() => setActivePopupData(null)}
              className="text-slate-400 hover:text-white text-sm font-bold leading-none cursor-pointer"
            >
              &times;
            </button>
          </div>

          <div className="py-2.5 space-y-1.5 text-[11px]">
            {activePopupData.type === 'INCIDENT' && (
              <>
                <div className="flex justify-between">
                  <span className="text-slate-400">Requester:</span>
                  <span className="font-bold text-white">{activePopupData.requester}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Location:</span>
                  <span className="text-slate-200 text-right truncate max-w-[150px]">
                    {activePopupData.location}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Inundation:</span>
                  <span className="text-sky-300 font-bold">{activePopupData.depth}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Status:</span>
                  <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px] font-bold">
                    {activePopupData.status}
                  </span>
                </div>
              </>
            )}

            {activePopupData.type === 'GAUGE' && (
              <>
                <div className="flex justify-between">
                  <span className="text-slate-400">River Basin:</span>
                  <span className="text-slate-200">{activePopupData.river}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Current Level:</span>
                  <span className="text-rose-400 font-bold">{activePopupData.current}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Danger Mark:</span>
                  <span className="text-slate-300">{activePopupData.danger}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Discharge:</span>
                  <span className="text-white">{activePopupData.discharge}</span>
                </div>
              </>
            )}

            {activePopupData.type === 'SHELTER' && (
              <>
                <div className="flex justify-between">
                  <span className="text-slate-400">Elevation:</span>
                  <span className="text-emerald-300 font-bold">{activePopupData.elevation}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Capacity:</span>
                  <span className="text-white">
                    {activePopupData.occupancy} / {activePopupData.capacity} souls
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Emergency Phone:</span>
                  <span className="text-slate-300">{activePopupData.contact}</span>
                </div>
              </>
            )}

            {activePopupData.type === 'FACILITY' && (
              <>
                <div className="flex justify-between">
                  <span className="text-slate-400">Facility Type:</span>
                  <span className="font-bold text-white capitalize">{activePopupData.facilityType}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Verification:</span>
                  <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold uppercase ${
                    activePopupData.verification === 'verified'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : activePopupData.verification === 'demo_labeled'
                      ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                      : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                  }`}>
                    {activePopupData.verification}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Recorded Capacity:</span>
                  <span className="text-white font-bold">{activePopupData.capacity}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Contact liaison:</span>
                  <span className="text-cyan-300 font-bold">{activePopupData.contact}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Source:</span>
                  <span className="text-slate-300 truncate max-w-[130px]" title={activePopupData.source}>
                    {activePopupData.source}
                  </span>
                </div>
              </>
            )}

            <div className="pt-1.5 border-t border-[#1e3a5f]/60 text-[10px] text-slate-400">
              Coordinates: {activePopupData.coords?.[1].toFixed(4)}°N, {activePopupData.coords?.[0].toFixed(4)}°E
            </div>
          </div>

          {activePopupData.type === 'INCIDENT' && onSelectIncident && (
            <button
              onClick={() => {
                onSelectIncident(activePopupData.id);
                setActivePopupData(null);
              }}
              className="w-full mt-1 py-1.5 px-3 rounded bg-sky-600 hover:bg-sky-500 text-white font-bold text-[10px] tracking-wider uppercase transition-colors text-center cursor-pointer"
            >
              REVIEW INCIDENT DOSSIER
            </button>
          )}
        </div>
      )}
    </div>
  );
};
