import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  AlertTriangle,
  Compass,
  Layers,
  LifeBuoy,
  Maximize2,
  Minimize2,
  RotateCcw,
  Satellite,
  Shield,
  Waves,
} from 'lucide-react';
import {
  HORIZON_FORECASTS,
  KOSHI_SHELTERS,
  KOSHI_TELEMETRY_GAUGES,
} from '../../data/geospatialData';
import type { HelpRequest } from '../../types';
import {
  DEMO_MODE,
  type ObservedExtentFeature,
  type FacilityItem,
  type RiskLocationMarker,
} from '../../services/backendApi';

export interface GeospatialTerrainMapProps {
  center?: [number, number]; // [lng, lat]
  zoom?: number;
  pitch?: number;
  bearing?: number;
  activeHorizon?: 'Now' | '1h' | '3h' | '6h';
  onActiveHorizonChange?: (horizon: 'Now' | '1h' | '3h' | '6h') => void;
  observedExtent?: ObservedExtentFeature | null;
  riskMarkers?: RiskLocationMarker[];
  selectedRiskMarkerId?: string | null;
  onSelectRiskMarker?: (marker: RiskLocationMarker) => void;
  showInundation?: boolean;
  showRiskMarkers?: boolean;
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
  selectedEventTitle?: string;
  selectedEventDate?: string;
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

// Safe coordinate extractor protecting against flipped lat/lng orders
function getValidLngLat(coords: unknown): [number, number] | null {
  if (!Array.isArray(coords) || coords.length < 2) return null;
  const a = Number(coords[0]);
  const b = Number(coords[1]);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;

  // Nepal longitude is approx 80 - 89, latitude is approx 26 - 31.
  if (a >= 75 && a <= 95 && b >= 20 && b <= 35) {
    return [a, b]; // already [lng, lat]
  }
  if (b >= 75 && b <= 95 && a >= 20 && a <= 35) {
    return [b, a]; // was [lat, lng] -> return [lng, lat]
  }
  if (Math.abs(a) <= 180 && Math.abs(b) <= 90) {
    return [a, b];
  }
  return null;
}

// Extract bounding box [[minLng, minLat], [maxLng, maxLat]] from arbitrary GeoJSON
function extractGeoJsonBounds(feature: any): [[number, number], [number, number]] | null {
  if (!feature?.geometry?.coordinates) return null;
  const pts: [number, number][] = [];
  const walk = (node: any) => {
    if (!Array.isArray(node)) return;
    if (node.length >= 2 && typeof node[0] === 'number' && typeof node[1] === 'number') {
      const p = getValidLngLat(node);
      if (p) pts.push(p);
      return;
    }
    node.forEach(walk);
  };
  walk(feature.geometry.coordinates);
  if (!pts.length) return null;
  const lngs = pts.map((p) => p[0]);
  const lats = pts.map((p) => p[1]);
  return [
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  ];
}

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
          [87.11, 26.608],
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
          [87.14, 26.81],
          [87.125, 26.785],
          [87.108, 26.75],
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
          [86.975, 26.58],
          [86.968, 26.565],
          [86.96, 26.545],
        ],
      },
    },
  ],
};

export const GeospatialTerrainMap: React.FC<GeospatialTerrainMapProps> = ({
  center = [87.05, 26.65],
  zoom = 10.8,
  pitch = 55,
  bearing = -15,
  activeHorizon = '3h',
  onActiveHorizonChange,
  observedExtent = null,
  riskMarkers = [],
  selectedRiskMarkerId: _selectedRiskMarkerId = null,
  onSelectRiskMarker,
  showInundation = true,
  showRiskMarkers = true,
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
  selectedEventTitle = '',
  selectedEventDate = '',
  wipePosition = 50,
  verificationLayers = { tp: true, fp: true, fn: true },
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const lastFlownCenterRef = useRef<string>('');
  const lastFittedExtentRef = useRef<string>('');

  const [is3D, setIs3D] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [basemap, setBasemap] = useState<'dark' | 'satellite'>(
    mode === 'satellite' ? 'satellite' : 'dark'
  );

  // Dynamic Layer Visibility Toggles
  const [layerInundation, setLayerInundation] = useState(showInundation);
  const [layerRiskMarkers, setLayerRiskMarkers] = useState(showRiskMarkers);
  const [layerIncidents, setLayerIncidents] = useState(showIncidents);
  const [layerFacilities, setLayerFacilities] = useState(showShelters);
  const [layerForecast] = useState(showForecast);
  const [currentHorizon, setCurrentHorizon] = useState<'Now' | '1h' | '3h' | '6h'>(activeHorizon);

  const [activePopupData, setActivePopupData] = useState<any | null>(null);

  // Sync prop changes into layer toggles
  useEffect(() => {
    setLayerInundation(showInundation);
  }, [showInundation]);
  useEffect(() => {
    setLayerRiskMarkers(showRiskMarkers);
  }, [showRiskMarkers]);
  useEffect(() => {
    setLayerIncidents(showIncidents);
  }, [showIncidents]);
  useEffect(() => {
    setLayerFacilities(showShelters);
  }, [showShelters]);
  useEffect(() => {
    setCurrentHorizon(activeHorizon);
  }, [activeHorizon]);

  const handleHorizonToggle = (h: 'Now' | '1h' | '3h' | '6h') => {
    setCurrentHorizon(h);
    if (onActiveHorizonChange) onActiveHorizonChange(h);
  };

  // Initialize MapLibre GL
  useEffect(() => {
    if (!mapContainerRef.current) return;

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
          source: 'carto-dark',
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

    map.addControl(
      new maplibregl.NavigationControl({
        visualizePitch: true,
        showCompass: true,
        showZoom: true,
      }),
      'top-right'
    );

    map.on('load', () => {
      // Enable 3D digital elevation model terrain
      try {
        map.setTerrain({ source: 'terrain-dem', exaggeration: 1.5 });
      } catch (err) {
        console.warn('MapLibre terrain warning:', err);
      }

      // Add sky atmosphere
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

      setupMapLayers(map);
      setMapLoaded(true);

      map.on('error', () => {
        // Absorbs tile 404/fetch errors silently
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

  // Setup Map Layers (Inundation Polygons, Horizon Polygons, Road Cuts)
  const setupMapLayers = useCallback((map: maplibregl.Map) => {
    // 1. Observed Flood Inundation Layer (Semi-transparent cyan water + bright blue stroke)
    const demoObservedCoords = toGeoJsonCoords(HORIZON_FORECASTS['1h'].polygonCoords);
    if (!map.getSource('observed-inundation-src')) {
      map.addSource('observed-inundation-src', {
        type: 'geojson',
        data: observedExtent
          ? (observedExtent as any)
          : DEMO_MODE
          ? {
              type: 'Feature',
              properties: { name: 'Illustrative benchmark fixture', area_km2: 28.4 },
              geometry: { type: 'Polygon', coordinates: [demoObservedCoords] },
            }
          : { type: 'FeatureCollection', features: [] },
      });

      // Semi-transparent vibrant cyan fill
      map.addLayer({
        id: 'observed-inundation-fill',
        type: 'fill',
        source: 'observed-inundation-src',
        paint: {
          'fill-color': '#00e5ff',
          'fill-opacity': 0.48,
        },
      });

      // Soft glow contour
      map.addLayer({
        id: 'observed-inundation-glow',
        type: 'line',
        source: 'observed-inundation-src',
        paint: {
          'line-color': '#00e5ff',
          'line-width': 5.5,
          'line-opacity': 0.4,
          'line-blur': 2.5,
        },
      });

      // Bright crisp cyan boundary
      map.addLayer({
        id: 'observed-inundation-stroke',
        type: 'line',
        source: 'observed-inundation-src',
        paint: {
          'line-color': '#38bdf8',
          'line-width': 2.8,
          'line-opacity': 0.95,
        },
      });

      // Click on flood water polygon to see provenance and event telemetry
      map.on('click', 'observed-inundation-fill', (e) => {
        const feat = e.features?.[0];
        if (!feat) return;
        const p = feat.properties || {};
        setActivePopupData({
          type: 'FLOOD_EXTENT',
          title: p.event_id || selectedEventTitle || 'Recorded Flood Inundation Extent',
          area: p.area_km2 ? `${p.area_km2} km²` : 'Measured Inundation Extent',
          observedAt: p.observed_at || 'Observed Sentinel-1/2 pass',
          method: p.method || 'Satellite Observation (SAR/Optical)',
          provenance: p.provenance || (DEMO_MODE ? 'Demo Fixture' : 'PostGIS Extent Polygon'),
          sourceScenes: p.source_scene_ids
            ? String(p.source_scene_ids)
            : 'Copernicus SAR Constellation',
          coords: [e.lngLat.lng, e.lngLat.lat],
        });
      });

      map.on('mouseenter', 'observed-inundation-fill', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'observed-inundation-fill', () => {
        map.getCanvas().style.cursor = '';
      });
    }

    // 2. Predictive Horizon Extent Layer (Dynamic amber/orange/crimson)
    const activeCoords =
      currentHorizon === 'Now'
        ? demoObservedCoords
        : toGeoJsonCoords(
            HORIZON_FORECASTS[currentHorizon as '1h' | '3h' | '6h']?.polygonCoords ||
              demoObservedCoords
          );

    const horizonColor =
      currentHorizon === '6h' ? '#ef4444' : currentHorizon === '3h' ? '#f97316' : '#f59e0b';

    if (!map.getSource('forecast-horizon-src')) {
      map.addSource('forecast-horizon-src', {
        type: 'geojson',
        data: DEMO_MODE
          ? {
              type: 'Feature',
              properties: { horizon: currentHorizon, source: 'illustrative' },
              geometry: { type: 'Polygon', coordinates: [activeCoords] },
            }
          : { type: 'FeatureCollection', features: [] },
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
  }, [currentHorizon, candidateRoute, observedExtent, selectedEventTitle]);

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

  // Update horizon layer dynamically as currentHorizon changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const src = map.getSource('forecast-horizon-src') as maplibregl.GeoJSONSource | undefined;
    if (src) {
      const activeCoords =
        currentHorizon === 'Now'
          ? toGeoJsonCoords(HORIZON_FORECASTS['1h'].polygonCoords)
          : toGeoJsonCoords(
              HORIZON_FORECASTS[currentHorizon as '1h' | '3h' | '6h']?.polygonCoords ||
                HORIZON_FORECASTS['3h'].polygonCoords
            );

      src.setData(
        DEMO_MODE
          ? {
              type: 'Feature',
              properties: { horizon: currentHorizon, source: 'illustrative' },
              geometry: { type: 'Polygon', coordinates: [activeCoords] },
            }
          : { type: 'FeatureCollection', features: [] }
      );

      const horizonColor =
        currentHorizon === '6h' ? '#ef4444' : currentHorizon === '3h' ? '#f97316' : '#f59e0b';

      if (map.getLayer('forecast-horizon-fill')) {
        map.setPaintProperty('forecast-horizon-fill', 'fill-color', horizonColor);
      }
      if (map.getLayer('forecast-horizon-stroke')) {
        map.setPaintProperty('forecast-horizon-stroke', 'line-color', horizonColor);
      }
    }
  }, [currentHorizon, mapLoaded]);

  // Synchronize PostGIS observed extent & automatically fit camera bounds to flood polygons
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const source = map.getSource('observed-inundation-src') as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(
        observedExtent
          ? (observedExtent as any)
          : DEMO_MODE
          ? {
              type: 'Feature',
              properties: { name: 'Illustrative fixture only', area_km2: 28.4 },
              geometry: {
                type: 'Polygon',
                coordinates: [toGeoJsonCoords(HORIZON_FORECASTS['1h'].polygonCoords)],
              },
            }
          : { type: 'FeatureCollection', features: [] }
      );
    }

    if (!observedExtent?.geometry) return;

    // Identify extent by id or event_id to prevent redundant re-fits
    const extentKey = String(observedExtent.id || observedExtent.properties?.event_id || JSON.stringify(observedExtent.geometry.coordinates).slice(0, 50));
    if (lastFittedExtentRef.current === extentKey) return;
    lastFittedExtentRef.current = extentKey;

    const bounds = extractGeoJsonBounds(observedExtent);
    if (bounds) {
      map.fitBounds(bounds, {
        padding: 60,
        maxZoom: 13,
        duration: 1000,
      });
    }
  }, [observedExtent, mapLoaded]);

  // Dynamic layer visibility
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const showFlood = layerInundation && (DEMO_MODE || Boolean(observedExtent));
    if (map.getLayer('observed-inundation-fill')) {
      map.setLayoutProperty('observed-inundation-fill', 'visibility', showFlood ? 'visible' : 'none');
      if (mode === 'satellite') {
        map.setPaintProperty('observed-inundation-fill', 'fill-opacity', (wipePosition / 100) * 0.55);
      }
    }
    if (map.getLayer('observed-inundation-glow')) {
      map.setLayoutProperty('observed-inundation-glow', 'visibility', showFlood ? 'visible' : 'none');
    }
    if (map.getLayer('observed-inundation-stroke')) {
      map.setLayoutProperty('observed-inundation-stroke', 'visibility', showFlood ? 'visible' : 'none');
    }
    if (map.getLayer('forecast-horizon-fill')) {
      map.setLayoutProperty('forecast-horizon-fill', 'visibility', DEMO_MODE && layerForecast ? 'visible' : 'none');
    }
    if (map.getLayer('forecast-horizon-stroke')) {
      map.setLayoutProperty('forecast-horizon-stroke', 'visibility', DEMO_MODE && layerForecast ? 'visible' : 'none');
    }
    if (map.getLayer('road-cuts-lines')) {
      map.setLayoutProperty('road-cuts-lines', 'visibility', DEMO_MODE && showInfrastructure ? 'visible' : 'none');
    }
  }, [layerInundation, layerForecast, showInfrastructure, mode, wipePosition, verificationLayers, observedExtent, mapLoaded]);

  // Manage Interactive Markers (Risk Markers, Incidents, Gauges, Facilities)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    // Clear previous markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    // 1. DATA-GROUNDED RISK MARKERS (Red / Yellow / Green / Gray)
    if (layerRiskMarkers && riskMarkers && riskMarkers.length > 0) {
      riskMarkers.forEach((markerData) => {
        const coords = getValidLngLat(markerData.coordinates);
        if (!coords) return;

        // Determine active risk level for currently selected horizon
        let riskLevel = markerData.activeRiskLevel;
        if (markerData.hasForecast && currentHorizon !== 'Now') {
          const hKey = `+${currentHorizon}`;
          const hData = markerData.horizons[hKey] || markerData.horizons[currentHorizon];
          if (hData?.risk_level) {
            riskLevel = hData.risk_level.toUpperCase() as any;
          }
        }

        // Color coding specification:
        // RED: HIGH or CRITICAL
        // YELLOW: MODERATE
        // GREEN: LOW
        // GRAY: UNKNOWN / NO FORECAST AVAILABLE
        const isCritical = riskLevel === 'CRITICAL' || riskLevel === 'HIGH';
        const isModerate = riskLevel === 'MODERATE';
        const isLow = riskLevel === 'LOW';

        const colorHex = isCritical
          ? '#ef4444'
          : isModerate
          ? '#eab308'
          : isLow
          ? '#22c55e'
          : '#64748b';

        const bgClass = isCritical
          ? 'bg-rose-500'
          : isModerate
          ? 'bg-amber-500'
          : isLow
          ? 'bg-emerald-500'
          : 'bg-slate-600';

        const borderClass = isCritical
          ? 'border-rose-200'
          : isModerate
          ? 'border-amber-200'
          : isLow
          ? 'border-emerald-200'
          : 'border-slate-300';

        const riskLabel = isCritical
          ? `${riskLevel} RISK`
          : isModerate
          ? 'MODERATE RISK'
          : isLow
          ? 'LOW RISK'
          : 'UNASSESSED';

        const el = document.createElement('div');
        el.className = 'group cursor-pointer transform -translate-x-1/2 -translate-y-1/2 transition-transform hover:scale-125 z-30';

        el.innerHTML = `
          <div class="relative flex items-center justify-center">
            ${isCritical ? '<span class="animate-ping absolute inline-flex h-7 w-7 rounded-full bg-rose-500 opacity-60"></span>' : ''}
            ${isModerate ? '<span class="animate-pulse absolute inline-flex h-6 w-6 rounded-full bg-amber-400 opacity-40"></span>' : ''}
            <div class="relative w-6 h-6 rounded-full ${bgClass} border-2 ${borderClass} flex items-center justify-center text-[10px] font-bold text-white shadow-[0_0_12px_rgba(0,0,0,0.8)]">
              ${isCritical ? '▲' : isModerate ? '●' : isLow ? '■' : '?'}
            </div>
            <div class="absolute left-7.5 bg-[#071326]/95 border border-[#1e3a5f] px-2 py-0.5 rounded text-[10px] font-mono font-bold text-white whitespace-nowrap shadow-lg pointer-events-none opacity-90 group-hover:opacity-100 backdrop-blur-md flex items-center gap-1.5">
              <span>${markerData.name.split(' ')[0]}</span>
              <span class="px-1 py-0.2 rounded text-[9px] font-bold" style="background-color: ${colorHex}33; color: ${colorHex}; border: 1px solid ${colorHex}66">
                ${riskLabel}
              </span>
            </div>
          </div>
        `;

        el.addEventListener('click', (e) => {
          e.stopPropagation();
          setActivePopupData({
            type: 'RISK_ZONE',
            id: markerData.id,
            name: markerData.name,
            adminLevel: markerData.adminLevel,
            activeHorizon: currentHorizon,
            riskLevel: riskLevel,
            maxRiskLevel: markerData.maxRiskLevel,
            horizons: markerData.horizons,
            modelVersion: markerData.modelVersion || 'baseline-v1',
            issuedAt: markerData.issuedAt || '2024-07-08T08:00:00Z',
            mode: markerData.mode || 'historical_demo',
            dataQuality: markerData.dataQuality || 'partial',
            limitations: markerData.limitations || [],
            disclaimer: markerData.disclaimer,
            coords: coords,
            hasForecast: markerData.hasForecast,
          });
          if (onSelectRiskMarker) onSelectRiskMarker(markerData);
        });

        const marker = new maplibregl.Marker({ element: el }).setLngLat(coords).addTo(map);
        markersRef.current.push(marker);
      });
    }

    // 2. CITIZEN ASSISTANCE INCIDENTS (SOS Pings)
    if (layerIncidents && incidents.length > 0) {
      incidents.forEach((req) => {
        const coords = getValidLngLat(req.coordinates);
        if (!coords) return;

        const isSelected = selectedIncidentId === req.id;
        const isCritical = req.urgency === 'CRITICAL';
        const isHigh = req.urgency === 'HIGH';
        const badgeColor = isCritical ? '#ef4444' : isHigh ? '#f59e0b' : '#38bdf8';

        const el = document.createElement('div');
        el.className = `cursor-pointer transition-all z-25 ${isSelected ? 'scale-130 z-50' : 'hover:scale-115'}`;

        el.innerHTML = `
          <div class="relative flex items-center justify-center">
            ${isCritical ? '<span class="animate-ping absolute inline-flex h-8 w-8 rounded-full bg-rose-500 opacity-60"></span>' : ''}
            <div class="w-6 h-6 rounded-full border-2 border-white flex items-center justify-center text-[9px] font-mono font-bold text-white shadow-lg" style="background-color: ${badgeColor}; box-shadow: 0 0 10px ${badgeColor}80">
              SOS
            </div>
            <div class="absolute left-7 bg-[#060e1d]/95 border border-[#1e3a5f] px-2 py-0.5 rounded text-[10px] font-mono font-bold text-white whitespace-nowrap shadow-md pointer-events-none opacity-0 group-hover:opacity-100">
              SOS: ${req.category}
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
            coords: coords,
            peopleCount: req.people_count,
            landmark: req.landmark,
            notice: 'Citizen assistance triage ping. Not an AI model flood hazard classification.',
          });
          if (onSelectIncident) onSelectIncident(req.id);
        });

        const marker = new maplibregl.Marker({ element: el }).setLngLat(coords).addTo(map);
        markersRef.current.push(marker);
      });
    }

    // 3. EMERGENCY FACILITIES (Shelters & Hospitals)
    if (layerFacilities && facilities && facilities.length > 0) {
      facilities.forEach((fac) => {
        const rawCoords = fac.location?.coordinates || [fac.longitude, fac.latitude];
        const coords = getValidLngLat(rawCoords);
        if (!coords) return;

        const isHospital = fac.type === 'hospital';
        const isVerified = fac.verification_status === 'verified';
        const isDemo = fac.verification_status === 'demo_labeled';
        const color = isVerified ? 'bg-emerald-500' : isDemo ? 'bg-sky-500' : 'bg-rose-500';
        const borderColor = isVerified ? 'border-emerald-300' : isDemo ? 'border-sky-300' : 'border-rose-300';

        const el = document.createElement('div');
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
            source: fac.source || 'Database Registry',
            limitations: fac.limitations,
            coords: coords,
          });
          if (onSelectFacility) onSelectFacility(fac);
        });

        const marker = new maplibregl.Marker({ element: el }).setLngLat(coords).addTo(map);
        markersRef.current.push(marker);
      });
    } else if (DEMO_MODE && layerFacilities) {
      KOSHI_SHELTERS.forEach((shelter) => {
        const coords = getValidLngLat(shelter.coordinates);
        if (!coords) return;

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
            coords: coords,
          });
        });

        const marker = new maplibregl.Marker({ element: el }).setLngLat(coords).addTo(map);
        markersRef.current.push(marker);
      });
    }

    // 4. HYDROLOGICAL GAUGES (Only in demo/sensor mode)
    if (DEMO_MODE && showGauges) {
      KOSHI_TELEMETRY_GAUGES.forEach((gauge) => {
        const coords = getValidLngLat(gauge.coordinates);
        if (!coords) return;

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
            coords: coords,
          });
          if (onSelectGauge) onSelectGauge(gauge.id);
        });

        const marker = new maplibregl.Marker({ element: el }).setLngLat(coords).addTo(map);
        markersRef.current.push(marker);
      });
    }
  }, [
    mapLoaded,
    layerRiskMarkers,
    riskMarkers,
    currentHorizon,
    layerIncidents,
    incidents,
    selectedIncidentId,
    layerFacilities,
    facilities,
    showGauges,
    onSelectRiskMarker,
    onSelectIncident,
    onSelectFacility,
    onSelectGauge,
  ]);

  // Center on selected incident if provided
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !selectedIncidentId) return;

    const targetReq = incidents.find((r) => r.id === selectedIncidentId);
    if (targetReq) {
      const coords = getValidLngLat(targetReq.coordinates);
      if (coords) {
        map.flyTo({
          center: coords,
          zoom: 12.5,
          duration: 1000,
        });
      }
    }
  }, [selectedIncidentId, incidents, mapLoaded]);

  // Handle external camera moves without redundant loops
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const key = `${center[0].toFixed(4)},${center[1].toFixed(4)},${zoom},${pitch},${bearing}`;
    if (lastFlownCenterRef.current === key) return;
    lastFlownCenterRef.current = key;

    // Only fly if no extent bounds are being actively focused
    if (!observedExtent) {
      map.flyTo({
        center,
        zoom,
        pitch: is3D ? pitch : 0,
        bearing: is3D ? bearing : 0,
        duration: 1200,
        essential: true,
      });
    }
  }, [center, zoom, pitch, bearing, is3D, mapLoaded, observedExtent]);

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

  // Reset View
  const handleResetView = () => {
    const map = mapRef.current;
    if (!map) return;

    if (observedExtent) {
      const bounds = extractGeoJsonBounds(observedExtent);
      if (bounds) {
        map.fitBounds(bounds, { padding: 60, maxZoom: 13, duration: 900 });
        return;
      }
    }

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

      {/* Top Floating Telemetry & Layer Controls Toolbar */}
      <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center bg-zinc-950/90 backdrop-blur-md rounded-xl p-1.5 border border-zinc-800/80 shadow-lg pointer-events-auto gap-1.5 max-w-[calc(100%-60px)]">
        {/* Layer Toggles */}
        <button
          onClick={() => setLayerInundation(!layerInundation)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-bold uppercase transition-all cursor-pointer ${
            layerInundation
              ? 'bg-cyan-950/60 text-cyan-300 border border-cyan-500/40 shadow-xs'
              : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900/60'
          }`}
          title="Toggle Observed Flood-Water Extent (Sentinel-1 SAR / Sentinel-2 GeoJSON)"
        >
          <Waves className="w-3.5 h-3.5 text-cyan-400" />
          <span>FLOOD WATER</span>
        </button>

        <button
          onClick={() => setLayerRiskMarkers(!layerRiskMarkers)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-bold uppercase transition-all cursor-pointer ${
            layerRiskMarkers
              ? 'bg-amber-950/60 text-amber-300 border border-amber-500/40 shadow-xs'
              : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900/60'
          }`}
          title="Toggle Estimated Risk Markers (Red/Yellow/Green/Gray Location Forecasts)"
        >
          <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
          <span>RISK ZONES</span>
        </button>

        <button
          onClick={() => setLayerIncidents(!layerIncidents)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-bold uppercase transition-all cursor-pointer ${
            layerIncidents
              ? 'bg-rose-950/60 text-rose-300 border border-rose-500/40 shadow-xs'
              : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900/60'
          }`}
          title="Toggle Citizen Distress Incidents (SOS Pings)"
        >
          <LifeBuoy className="w-3.5 h-3.5 text-rose-400" />
          <span>INCIDENTS</span>
        </button>

        <button
          onClick={() => setLayerFacilities(!layerFacilities)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-bold uppercase transition-all cursor-pointer ${
            layerFacilities
              ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/40 shadow-xs'
              : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900/60'
          }`}
          title="Toggle Verified Emergency Shelters & Medical Hubs"
        >
          <Shield className="w-3.5 h-3.5 text-emerald-400" />
          <span>FACILITIES</span>
        </button>

        <div className="h-4 w-px bg-zinc-800 mx-0.5" />

        {/* Horizon Forecast Pills */}
        <div className="inline-flex items-center bg-zinc-900/80 rounded-lg p-0.5 border border-zinc-800 text-[11px] font-mono">
          {(['Now', '1h', '3h', '6h'] as const).map((h) => (
            <button
              key={h}
              onClick={() => handleHorizonToggle(h)}
              className={`px-2 py-1 rounded font-bold cursor-pointer transition-all ${
                currentHorizon === h
                  ? h === '6h'
                    ? 'bg-rose-600 text-white shadow-xs'
                    : h === '3h'
                    ? 'bg-amber-600 text-white shadow-xs'
                    : 'bg-cyan-600 text-white shadow-xs'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {h === 'Now' ? 'OBS' : `+${h}`}
            </button>
          ))}
        </div>

        <div className="h-4 w-px bg-zinc-800 mx-0.5" />

        {/* 3D vs 2D Basemap Modes */}
        <button
          onClick={toggle3DMode}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-bold tracking-wider uppercase transition-all cursor-pointer ${
            is3D
              ? 'bg-sky-950/50 text-sky-400 border border-sky-500/30'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
          }`}
          title="Toggle 3D Digital Elevation Model vs 2D Ortho"
        >
          <Layers className="w-3.5 h-3.5" />
          <span>{is3D ? '3D' : '2D'}</span>
        </button>

        <button
          onClick={() => setBasemap((prev) => (prev === 'dark' ? 'satellite' : 'dark'))}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-bold tracking-wider uppercase transition-all cursor-pointer ${
            basemap === 'satellite' || mode === 'satellite'
              ? 'bg-sky-950/50 text-sky-400 border border-sky-500/30'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
          }`}
          title="Toggle CartoDB Dark vs Esri World Imagery Satellite"
        >
          <Satellite className="w-3.5 h-3.5" />
          <span>{basemap === 'satellite' ? 'SAT' : 'DARK'}</span>
        </button>

        {/* Camera Orientation Quick Actions */}
        <button
          onClick={handleResetNorth}
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60 transition-colors cursor-pointer"
          title="Reset Camera Bearing to North"
        >
          <Compass className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={handleResetView}
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60 transition-colors cursor-pointer"
          title="Fit Camera to Flood Extent or Reset View"
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

      {/* Bottom Information Legend & Color Palette */}
      <div className="absolute bottom-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2.5 pointer-events-none">
        {/* Color-Coded Legend Strip */}
        <div className="inline-flex flex-wrap items-center gap-3 px-3 py-1.5 rounded-xl bg-zinc-950/90 border border-zinc-800/80 text-[11px] font-mono text-zinc-200 backdrop-blur-md pointer-events-auto shadow-md">
          {/* Risk Levels */}
          <div className="flex items-center gap-1.5" title="High / Critical Estimated Risk">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.6)]" />
            <span className="font-bold text-rose-300">CRITICAL/HIGH</span>
          </div>

          <div className="flex items-center gap-1.5" title="Moderate Estimated Risk">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.6)]" />
            <span className="font-bold text-amber-300">MODERATE</span>
          </div>

          <div className="flex items-center gap-1.5" title="Low Estimated Risk (Does NOT guarantee complete safety)">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]" />
            <span className="font-bold text-emerald-300">LOW (NOT SAFE)</span>
          </div>

          <div className="flex items-center gap-1.5" title="Unknown / No Forecast Available in Model Run">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500" />
            <span className="font-bold text-slate-400">UNASSESSED</span>
          </div>

          <span className="text-zinc-700 select-none hidden sm:inline">|</span>

          {/* Inundation Water */}
          <div className="flex items-center gap-1.5" title="Observed Flood Extent from Satellite Radar (SAR) or Optical">
            <span className="w-3 h-2 rounded-xs bg-cyan-400/60 border border-cyan-300 inline-block shadow-[0_0_6px_rgba(34,211,238,0.5)]" />
            <span className="font-bold text-cyan-200">
              {observedExtent ? `EXTENT: ${observedExtent.properties?.area_km2 || '42.6'} KM²` : 'FLOOD EXTENT'}
            </span>
          </div>

          {/* Active Event Badge */}
          {selectedEventTitle && (
            <>
              <span className="text-zinc-700 select-none hidden md:inline">|</span>
              <div className="hidden md:flex items-center gap-1.5 text-zinc-400">
                <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
                <span className="truncate max-w-[220px]" title={selectedEventTitle}>
                  {selectedEventTitle} {selectedEventDate ? `(${selectedEventDate})` : ''}
                </span>
              </div>
            </>
          )}
        </div>

        {/* Projection & Accuracy Badge */}
        <div className="px-3 py-1.5 rounded-xl bg-zinc-950/90 border border-zinc-800/80 text-[11px] font-mono text-zinc-300 backdrop-blur-md pointer-events-auto shadow-md font-medium">
          <span>EPSG:4326 · ELEV 1.5X DEM · NOT FOR NAVIGATION</span>
        </div>
      </div>

      {/* Interactive Detail Popup Console */}
      {activePopupData && (
        <div className="absolute top-14 right-3 z-30 w-80 max-w-[calc(100vw-24px)] rounded-xl bg-zinc-950/95 border border-zinc-800 p-4 text-xs font-mono text-white shadow-2xl backdrop-blur-xl animate-in fade-in slide-in-from-top-2">
          {/* Header */}
          <div className="flex items-start justify-between pb-2.5 border-b border-zinc-800">
            <div className="flex items-center gap-2">
              {activePopupData.type === 'RISK_ZONE' ? (
                <AlertTriangle
                  className={`w-4 h-4 ${
                    activePopupData.riskLevel === 'CRITICAL' || activePopupData.riskLevel === 'HIGH'
                      ? 'text-rose-400'
                      : activePopupData.riskLevel === 'MODERATE'
                      ? 'text-amber-400'
                      : activePopupData.riskLevel === 'LOW'
                      ? 'text-emerald-400'
                      : 'text-slate-400'
                  }`}
                />
              ) : activePopupData.type === 'FLOOD_EXTENT' ? (
                <Waves className="w-4 h-4 text-cyan-400" />
              ) : activePopupData.type === 'INCIDENT' ? (
                <LifeBuoy className="w-4 h-4 text-rose-400" />
              ) : (
                <Shield className="w-4 h-4 text-emerald-400" />
              )}
              <div>
                <h4 className="font-bold text-white text-xs uppercase tracking-wider leading-snug">
                  {activePopupData.title || activePopupData.name}
                </h4>
                {activePopupData.adminLevel && (
                  <span className="text-[10px] text-zinc-400">
                    Administrative Level {activePopupData.adminLevel} Location
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={() => setActivePopupData(null)}
              className="text-zinc-400 hover:text-white text-base font-bold leading-none cursor-pointer p-1"
              aria-label="Close popup"
            >
              &times;
            </button>
          </div>

          {/* Body Content */}
          <div className="py-2.5 space-y-2 text-[11px]">
            {/* 1. RISK_ZONE POPUP */}
            {activePopupData.type === 'RISK_ZONE' && (
              <>
                <div className="p-2 rounded bg-zinc-900 border border-zinc-800 space-y-1">
                  <div className="flex justify-between items-center">
                    <span className="text-zinc-400">Active Horizon ({activePopupData.activeHorizon}):</span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                        activePopupData.riskLevel === 'CRITICAL' || activePopupData.riskLevel === 'HIGH'
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                          : activePopupData.riskLevel === 'MODERATE'
                          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                          : activePopupData.riskLevel === 'LOW'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                          : 'bg-slate-700/40 text-slate-400 border border-slate-600'
                      }`}
                    >
                      {activePopupData.riskLevel}
                    </span>
                  </div>
                  <div className="flex justify-between text-[10px]">
                    <span className="text-zinc-500">Max Horizon Severity:</span>
                    <span className="font-bold text-zinc-300">{activePopupData.maxRiskLevel}</span>
                  </div>
                </div>

                {/* Horizon Breakdown Table */}
                {activePopupData.hasForecast && activePopupData.horizons ? (
                  <div className="space-y-1">
                    <div className="text-[10px] font-semibold text-zinc-400 uppercase">
                      Multi-Horizon Predictions:
                    </div>
                    <div className="grid grid-cols-3 gap-1.5 text-center">
                      {(['+1h', '+3h', '+6h'] as const).map((h) => {
                        const hInfo = activePopupData.horizons[h];
                        const r = (hInfo?.risk_level || 'UNKNOWN').toUpperCase();
                        const prob = hInfo?.calibrated_probability;
                        return (
                          <div
                            key={h}
                            className={`p-1.5 rounded border text-[10px] ${
                              r === 'CRITICAL' || r === 'HIGH'
                                ? 'bg-rose-950/40 border-rose-800 text-rose-200'
                                : r === 'MODERATE'
                                ? 'bg-amber-950/40 border-amber-800 text-amber-200'
                                : r === 'LOW'
                                ? 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
                                : 'bg-zinc-900 border-zinc-800 text-zinc-400'
                            }`}
                          >
                            <div className="font-bold">{h}</div>
                            <div className="font-semibold">{r}</div>
                            <div className="text-[9px] text-zinc-400">
                              {typeof prob === 'number' ? `${(prob * 100).toFixed(0)}% prob` : 'Uncalibrated'}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="p-2 rounded bg-zinc-900/80 border border-dashed border-zinc-800 text-zinc-400 text-[10px]">
                    No forecast run currently published for this location in the active database.
                  </div>
                )}

                {/* Provenance & Limitations */}
                <div className="space-y-1 text-[10px] border-t border-zinc-800/80 pt-1.5">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Model:</span>
                    <span className="text-zinc-300">{activePopupData.modelVersion}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Issued:</span>
                    <span className="text-zinc-300">{activePopupData.issuedAt?.slice(0, 16) || '2024-07-08T08:00'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Mode:</span>
                    <span className="text-amber-300 font-semibold uppercase">{activePopupData.mode}</span>
                  </div>
                </div>

                {/* Disclaimer */}
                <div className="p-2 rounded bg-amber-950/30 border border-amber-800/40 text-[9px] text-amber-200/90 leading-tight">
                  {activePopupData.disclaimer}
                </div>
              </>
            )}

            {/* 2. FLOOD EXTENT POPUP */}
            {activePopupData.type === 'FLOOD_EXTENT' && (
              <>
                <div className="p-2 rounded bg-cyan-950/30 border border-cyan-800/40 space-y-1">
                  <div className="flex justify-between">
                    <span className="text-cyan-300 font-bold">Inundated Area:</span>
                    <span className="text-white font-bold">{activePopupData.area}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-400">Sensor Method:</span>
                    <span className="text-cyan-200">{activePopupData.method}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-400">Observed At:</span>
                    <span className="text-zinc-300">{activePopupData.observedAt}</span>
                  </div>
                </div>

                <div className="space-y-1 text-[10px] pt-1">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Provenance:</span>
                    <span className="text-zinc-300">{activePopupData.provenance}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Satellite Scenes:</span>
                    <span className="text-zinc-300 truncate max-w-[170px]" title={activePopupData.sourceScenes}>
                      {activePopupData.sourceScenes}
                    </span>
                  </div>
                </div>

                <div className="p-1.5 rounded bg-zinc-900 border border-zinc-800 text-[9px] text-zinc-400">
                  Geometry rendered from PostGIS Polygon layers. Displays historical satellite observation.
                </div>
              </>
            )}

            {/* 3. INCIDENT POPUP */}
            {activePopupData.type === 'INCIDENT' && (
              <>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Category:</span>
                  <span className="font-bold text-rose-300">{activePopupData.category}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Reported Urgency:</span>
                  <span className="px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 font-bold">
                    {activePopupData.urgency}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Requester:</span>
                  <span className="font-bold text-white">{activePopupData.requester}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">People Impacted:</span>
                  <span className="text-white">{activePopupData.peopleCount || 'Unspecified'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Estimated Depth:</span>
                  <span className="text-sky-300 font-bold">{activePopupData.depth}</span>
                </div>
                <div className="p-1.5 rounded bg-zinc-900 border border-zinc-800 text-[9px] text-zinc-400">
                  {activePopupData.notice}
                </div>
              </>
            )}

            {/* 4. FACILITY POPUP */}
            {activePopupData.type === 'FACILITY' && (
              <>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Facility Type:</span>
                  <span className="font-bold text-white capitalize">{activePopupData.facilityType}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-zinc-400">Verification:</span>
                  <span
                    className={`px-1.5 py-0.2 rounded text-[9px] font-bold uppercase ${
                      activePopupData.verification === 'verified'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                        : activePopupData.verification === 'demo_labeled'
                        ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                        : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                    }`}
                  >
                    {activePopupData.verification}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Recorded Capacity:</span>
                  <span className="text-white font-bold">{activePopupData.capacity}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">Emergency Phone:</span>
                  <span className="text-cyan-300 font-bold">{activePopupData.contact}</span>
                </div>
              </>
            )}

            {/* Coordinates Footer */}
            <div className="pt-2 border-t border-zinc-800/80 text-[10px] text-zinc-500 flex justify-between">
              <span>Coordinates:</span>
              <span>
                {activePopupData.coords?.[0]?.toFixed(4)}°E, {activePopupData.coords?.[1]?.toFixed(4)}°N
              </span>
            </div>
          </div>

          {activePopupData.type === 'INCIDENT' && onSelectIncident && (
            <button
              onClick={() => {
                onSelectIncident(activePopupData.id);
                setActivePopupData(null);
              }}
              className="w-full mt-1.5 py-1.5 px-3 rounded bg-sky-600 hover:bg-sky-500 text-white font-bold text-[10px] tracking-wider uppercase transition-colors text-center cursor-pointer"
            >
              LOCATE IN RESCUE QUEUE
            </button>
          )}
        </div>
      )}
    </div>
  );
};
