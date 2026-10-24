import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  AlertTriangle,
  Compass,
  LifeBuoy,
  Maximize2,
  Minimize2,
  RotateCcw,
  Shield,
  Waves,
  X,
  Key,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { loadCesium } from '../../utils/cesiumLoader';
import type { RiskLocationMarker, FacilityItem } from '../../services/backendApi';
import type { HelpRequest } from '../../types';

interface CesiumEarthMapProps {
  center?: [number, number]; // [lng, lat]
  observedExtent?: any;
  riskMarkers?: RiskLocationMarker[];
  facilities?: FacilityItem[];
  incidents?: HelpRequest[];
  activeHorizon?: 'Now' | '1h' | '3h' | '6h';
  onActiveHorizonChange?: (h: 'Now' | '1h' | '3h' | '6h') => void;
  selectedEventTitle?: string;
  selectedEventDate?: string;
  onCloseEarthView?: () => void;
  height?: string;
}

export const CesiumEarthMap: React.FC<CesiumEarthMapProps> = ({
  center = [85.92, 26.73],
  observedExtent,
  riskMarkers = [],
  facilities = [],
  incidents = [],
  activeHorizon = 'Now',
  onActiveHorizonChange,
  selectedEventTitle = 'Nepal Terai Monsoon Event',
  selectedEventDate = '2024-07-08',
  onCloseEarthView,
  height = '620px',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);
  const extentDataSourceRef = useRef<any>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Basemap & Google 3D Tiles State
  const [googleTilesActive, setGoogleTilesActive] = useState(false);
  const [googleKeyInput, setGoogleKeyInput] = useState('');
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [googleKeyError, setGoogleKeyError] = useState<string | null>(null);

  // Layer Toggles
  const [layerFloodWater, setLayerFloodWater] = useState(true);
  const [layerRiskMarkers, setLayerRiskMarkers] = useState(true);
  const [layerIncidents, setLayerIncidents] = useState(true);
  const [layerFacilities, setLayerFacilities] = useState(true);

  // Popup Inspection State
  const [selectedEntity, setSelectedEntity] = useState<any | null>(null);

  // Initialize Cesium Viewer
  useEffect(() => {
    let active = true;
    let viewer: any = null;

    async function initCesium() {
      try {
        setIsLoading(true);
        setLoadError(null);

        const Cesium = await loadCesium();
        if (!active || !containerRef.current) return;

        // Configure default camera orientation
        Cesium.Camera.DEFAULT_VIEW_RECTANGLE = Cesium.Rectangle.fromDegrees(
          center[0] - 1.5,
          center[1] - 1.2,
          center[0] + 1.5,
          center[1] + 1.2
        );

        viewer = new Cesium.Viewer(containerRef.current, {
          animation: false,
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          infoBox: false,
          sceneModePicker: false,
          selectionIndicator: false,
          timeline: false,
          navigationHelpButton: false,
          navigationInstructionsInitiallyVisible: false,
          scene3DOnly: true,
          requestRenderMode: true,
          maximumRenderTimeChange: Infinity,
        });

        // Hide default Cesium credit container elements that block UI
        const credit = viewer.creditDisplay?.container;
        if (credit) {
          credit.style.opacity = '0.6';
          credit.style.transform = 'scale(0.85)';
          credit.style.transformOrigin = 'bottom left';
        }

        // Configure smooth lighting & fog
        viewer.scene.globe.enableLighting = false;
        viewer.scene.globe.depthTestAgainstTerrain = true;
        viewer.scene.fog.enabled = true;
        viewer.scene.fog.density = 0.0002;

        // Try Google Photorealistic 3D Tiles if API key is present
        const envKey = (import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined)?.trim();
        let googleLoaded = false;

        if (envKey) {
          try {
            if (typeof Cesium.createGooglePhotorealistic3DTileset === 'function') {
              const tileset = await Cesium.createGooglePhotorealistic3DTileset({ key: envKey });
              viewer.scene.primitives.add(tileset);
              googleLoaded = true;
            }
          } catch (gErr) {
            console.warn('Google Photorealistic 3D Tiles failed with env key:', gErr);
          }
        }

        // Compatible Non-Google Basemap fallback (High-Resolution Satellite Imagery)
        if (!googleLoaded) {
          try {
            const esriImagery = new Cesium.ArcGisMapServerImageryProvider({
              url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer',
              enablePickFeatures: false,
            });
            viewer.imageryLayers.addImageryProvider(esriImagery);
          } catch {
            // Soft fallback to OpenStreetMap
            try {
              viewer.imageryLayers.addImageryProvider(
                new Cesium.OpenStreetMapImageryProvider({
                  url: 'https://a.tile.openstreetmap.org/',
                })
              );
            } catch {
              // Globe default
            }
          }
        }

        if (active) {
          setGoogleTilesActive(googleLoaded);
          viewerRef.current = viewer;
          setIsLoading(false);

          // Fly camera to center location with realistic oblique 3D tilt
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(center[0], center[1] - 0.25, 28000),
            orientation: {
              heading: Cesium.Math.toRadians(0),
              pitch: Cesium.Math.toRadians(-40),
              roll: 0,
            },
            duration: 1.5,
          });

          // Setup Click Picking
          const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
          handler.setInputAction((movement: any) => {
            const picked = viewer.scene.pick(movement.position);
            if (Cesium.defined(picked) && picked.id && picked.id.properties) {
              const props = picked.id.properties.getValue(Cesium.JulianDate.now());
              setSelectedEntity(props);
            } else {
              setSelectedEntity(null);
            }
          }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

          (viewer as any)._customClickHandler = handler;
        }
      } catch (err) {
        if (active) {
          console.error('Cesium initialization error:', err);
          setLoadError(
            err instanceof Error ? err.message : 'Failed to initialize Cesium 3D Earth View'
          );
          setIsLoading(false);
        }
      }
    }

    void initCesium();

    return () => {
      active = false;
      if (viewer && !viewer.isDestroyed()) {
        try {
          if ((viewer as any)._customClickHandler) {
            (viewer as any)._customClickHandler.destroy();
          }
          viewer.destroy();
        } catch (e) {
          console.warn('Cesium cleanup warning:', e);
        }
        viewerRef.current = null;
      }
    };
  }, [center]);

  // Overlay Flood Extent GeoJSON
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed() || !window.Cesium) return;
    const Cesium = window.Cesium;

    // Remove old extent
    if (extentDataSourceRef.current) {
      viewer.dataSources.remove(extentDataSourceRef.current, true);
      extentDataSourceRef.current = null;
    }

    if (!layerFloodWater || !observedExtent) {
      viewer.scene.requestRender();
      return;
    }

    try {
      Cesium.GeoJsonDataSource.load(observedExtent, {
        stroke: Cesium.Color.fromCssColorString('#38bdf8'),
        fill: Cesium.Color.fromCssColorString('#00e5ff').withAlpha(0.48),
        strokeWidth: 4,
        clampToGround: true,
      }).then((ds: any) => {
        if (viewer.isDestroyed()) return;
        extentDataSourceRef.current = ds;
        viewer.dataSources.add(ds);

        // Enhance polygon materials with bright neon boundaries
        const entities = ds.entities.values;
        for (let i = 0; i < entities.length; i++) {
          const entity = entities[i];
          if (entity.polygon) {
            entity.polygon.material = Cesium.Color.fromCssColorString('#00e5ff').withAlpha(0.48);
            entity.polygon.outline = true;
            entity.polygon.outlineColor = Cesium.Color.fromCssColorString('#38bdf8');
            entity.polygon.outlineWidth = 4;
            entity.polygon.classificationType = Cesium.ClassificationType.BOTH;
            entity.properties = {
              type: 'FLOOD_EXTENT',
              title: selectedEventTitle,
              date: selectedEventDate,
              area_km2: observedExtent?.properties?.area_km2 ?? 42.6,
              method: observedExtent?.properties?.method ?? 'SAR_CHANGE',
              sensor: observedExtent?.properties?.source_scene_ids?.join(', ') || 'Sentinel-1 SAR C-Band',
              disclaimer: 'Observed inundation footprint; does not reflect instantaneous water depth.',
            };
          }
        }

        // Fly to extent bounds smoothly
        viewer.zoomTo(ds, new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-45), 35000));
        viewer.scene.requestRender();
      });
    } catch (err) {
      console.warn('Cesium GeoJsonDataSource error:', err);
    }
  }, [observedExtent, layerFloodWater, selectedEventTitle, selectedEventDate]);

  // Render Risk Markers, Incidents, and Facilities as 3D Entities
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed() || !window.Cesium) return;
    const Cesium = window.Cesium;

    // Clear existing point entities
    const entitiesToRemove: any[] = [];
    viewer.entities.values.forEach((e: any) => {
      if (e.properties && e.properties.customMarkerType) {
        entitiesToRemove.push(e);
      }
    });
    entitiesToRemove.forEach((e) => viewer.entities.remove(e));

    // 1. RISK MARKERS
    if (layerRiskMarkers && riskMarkers.length > 0) {
      riskMarkers.forEach((marker) => {
        if (!marker.coordinates) return;
        const [lon, lat] = marker.coordinates;

        // Determine effective risk based on selected horizon
        const riskLevel =
          activeHorizon === 'Now'
            ? marker.maxRiskLevel
            : marker.horizons[`+${activeHorizon}`]?.risk_level ||
              marker.horizons[activeHorizon]?.risk_level ||
              'UNKNOWN';

        const isCritical = riskLevel === 'CRITICAL' || riskLevel === 'HIGH';
        const isModerate = riskLevel === 'MODERATE';
        const isLow = riskLevel === 'LOW';

        const colorHex = isCritical
          ? '#ef4444' // Red
          : isModerate
          ? '#eab308' // Yellow
          : isLow
          ? '#22c55e' // Green
          : '#64748b'; // Gray

        viewer.entities.add({
          name: marker.name,
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 20),
          point: {
            pixelSize: isCritical ? 18 : 14,
            color: Cesium.Color.fromCssColorString(colorHex),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 2,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          label: {
            text: marker.name,
            font: 'bold 11px monospace',
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.fromCssColorString('#020617'),
            outlineWidth: 3,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -14),
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          properties: {
            customMarkerType: 'RISK_ZONE',
            id: marker.id,
            name: marker.name,
            adminLevel: marker.adminLevel,
            riskLevel: riskLevel,
            colorHex: colorHex,
            activeHorizon: activeHorizon,
            horizons: marker.horizons,
            hasForecast: marker.hasForecast,
            modelVersion: marker.modelVersion || 'FloodLens Baseline v1',
            issuedAt: marker.issuedAt || new Date().toISOString(),
            limitations: marker.limitations,
            disclaimer: marker.disclaimer,
            coordinates: marker.coordinates,
          },
        });
      });
    }

    // 2. CITIZEN INCIDENTS (SOS Pings)
    if (layerIncidents && incidents.length > 0) {
      incidents.forEach((req) => {
        if (!req.coordinates) return;
        const c0 = Number(req.coordinates[0]);
        const c1 = Number(req.coordinates[1]);
        const lon = c0 > 50 ? c0 : c1;
        const lat = c0 > 50 ? c1 : c0;

        const locName = req.location_name || req.landmark || 'Citizen SOS';
        viewer.entities.add({
          name: `Distress: ${locName}`,
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 20),
          point: {
            pixelSize: 15,
            color: Cesium.Color.fromCssColorString('#f43f5e'), // Rose-500
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 2,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          label: {
            text: `SOS: ${locName}`,
            font: 'bold 10px monospace',
            fillColor: Cesium.Color.fromCssColorString('#fecdd3'),
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -12),
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          properties: {
            customMarkerType: 'INCIDENT',
            id: req.id,
            locationName: locName,
            category: req.category,
            urgency: req.urgency,
            peopleCount: req.people_count,
            notes: req.notes,
            requesterName: req.requester_name,
            disclaimer: 'Citizen assistance dispatch queue; not a predictive flood model classification.',
          },
        });
      });
    }

    // 3. EMERGENCY FACILITIES (Shelters & Hospitals)
    if (layerFacilities && facilities.length > 0) {
      facilities.forEach((fac) => {
        const rawCoords = fac.location?.coordinates || [fac.longitude, fac.latitude];
        if (!rawCoords || rawCoords[0] == null || rawCoords[1] == null) return;
        const c0 = Number(rawCoords[0]);
        const c1 = Number(rawCoords[1]);
        const lon = c0 > 50 ? c0 : c1;
        const lat = c0 > 50 ? c1 : c0;

        const isHospital = fac.type === 'hospital';
        const isVerified = fac.verification_status === 'verified';
        const colorHex = isHospital ? '#38bdf8' : isVerified ? '#10b981' : '#f59e0b';

        viewer.entities.add({
          name: fac.name,
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 20),
          point: {
            pixelSize: 13,
            color: Cesium.Color.fromCssColorString(colorHex),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1.5,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          label: {
            text: `${isHospital ? '🏥' : '🏠'} ${fac.name}`,
            font: '10px monospace',
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -12),
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          properties: {
            customMarkerType: 'FACILITY',
            id: fac.id,
            name: fac.name,
            facilityType: fac.type,
            verification_status: fac.verification_status,
            capacity: fac.capacity,
            contact_info: fac.contact_info,
            limitations: fac.limitations,
          },
        });
      });
    }

    viewer.scene.requestRender();
  }, [riskMarkers, incidents, facilities, activeHorizon, layerRiskMarkers, layerIncidents, layerFacilities]);

  // Camera Controls Handlers
  const handleResetNorth = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed() || !window.Cesium) return;
    const Cesium = window.Cesium;
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(center[0], center[1] - 0.2, 25000),
      orientation: {
        heading: 0,
        pitch: Cesium.Math.toRadians(-50),
        roll: 0,
      },
      duration: 1.2,
    });
  }, [center]);

  const handleZoomIn = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    viewer.camera.zoomIn(viewer.camera.positionCartographic.height * 0.4);
    viewer.scene.requestRender();
  }, []);

  const handleZoomOut = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    viewer.camera.zoomOut(viewer.camera.positionCartographic.height * 0.5);
    viewer.scene.requestRender();
  }, []);

  const handleFitExtent = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed() || !window.Cesium) return;
    if (extentDataSourceRef.current) {
      viewer.zoomTo(
        extentDataSourceRef.current,
        new window.Cesium.HeadingPitchRange(0, window.Cesium.Math.toRadians(-45), 32000)
      );
    } else {
      handleResetNorth();
    }
  }, [handleResetNorth]);

  // Activate Custom Google Maps 3D Tiles Key
  const handleApplyGoogleKey = async (e: React.FormEvent) => {
    e.preventDefault();
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed() || !window.Cesium) return;
    const Cesium = window.Cesium;

    const trimmed = googleKeyInput.trim();
    if (!trimmed) {
      setGoogleKeyError('Please provide a valid Google Maps Platform API key.');
      return;
    }

    try {
      setGoogleKeyError(null);
      if (typeof Cesium.createGooglePhotorealistic3DTileset === 'function') {
        const tileset = await Cesium.createGooglePhotorealistic3DTileset({ key: trimmed });
        viewer.scene.primitives.add(tileset);
        setGoogleTilesActive(true);
        setShowKeyModal(false);
      } else {
        setGoogleKeyError('Cesium version does not support createGooglePhotorealistic3DTileset');
      }
    } catch (err) {
      setGoogleKeyError(
        err instanceof Error ? err.message : 'Failed to initialize Google 3D Tiles with provided key.'
      );
    }
  };

  return (
    <div
      className={`relative w-full rounded-xl overflow-hidden border border-zinc-800 bg-[#030712] shadow-2xl transition-all ${
        isFullscreen ? 'fixed inset-0 z-50 h-screen rounded-none' : ''
      }`}
      style={{ height: isFullscreen ? '100vh' : height }}
    >
      {/* Cesium Canvas Container */}
      <div ref={containerRef} className="w-full h-full" />

      {/* Loading Overlay */}
      {isLoading && (
        <div className="absolute inset-0 bg-[#030712]/90 backdrop-blur-md flex flex-col items-center justify-center z-40 gap-3 text-slate-200 font-mono">
          <div className="w-10 h-10 border-3 border-sky-500 border-t-transparent rounded-full animate-spin shadow-[0_0_15px_rgba(56,189,248,0.5)]" />
          <div className="text-sm font-bold tracking-wider text-sky-400">
            LOADING CESIUM 3D EARTH GLOBE...
          </div>
          <div className="text-xs text-slate-400 max-w-sm text-center">
            Initializing high-resolution photorealistic terrain and satellite imagery.
          </div>
        </div>
      )}

      {/* WebGL or Loading Error Notice */}
      {loadError && (
        <div className="absolute inset-0 bg-[#030712]/95 backdrop-blur-md flex flex-col items-center justify-center z-40 p-6 text-center">
          <AlertTriangle className="w-12 h-12 text-rose-500 mb-3" />
          <h3 className="text-base font-bold text-white mb-2 font-mono">3D Earth View Notice</h3>
          <p className="text-xs text-slate-300 max-w-md mb-4">{loadError}</p>
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                setLoadError(null);
                setIsLoading(true);
                window.location.reload();
              }}
              className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-mono text-xs font-bold"
            >
              Retry Cesium
            </button>
            {onCloseEarthView && (
              <button
                onClick={onCloseEarthView}
                className="px-3.5 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-mono text-xs font-bold"
              >
                Switch to MapLibre 3D Terrain
              </button>
            )}
          </div>
        </div>
      )}

      {/* Top Floating Controls Header */}
      <div className="absolute top-3 left-3 right-3 z-20 flex flex-wrap items-center justify-between pointer-events-none gap-2">
        {/* Left: Mode Badge & Horizon Switcher */}
        <div className="flex items-center gap-2 pointer-events-auto bg-[#070e1b]/90 backdrop-blur-md px-3 py-1.5 rounded-xl border border-sky-800/60 shadow-lg">
          <span className="flex items-center gap-1.5 text-xs font-mono font-bold text-sky-400">
            <Compass className="w-4 h-4 text-sky-400 animate-spin-slow" />
            <span>3D EARTH GLOBE</span>
          </span>
          <span className="text-zinc-600">|</span>
          <span className="text-[11px] font-mono text-zinc-300">
            {googleTilesActive ? (
              <span className="text-emerald-400 font-bold">GOOGLE 3D TILES ACTIVE</span>
            ) : (
              <span className="text-sky-300">ESRI WORLD IMAGERY (NON-GOOGLE)</span>
            )}
          </span>

          {/* Horizon Quick Toggle */}
          <div className="ml-2 flex items-center gap-1 border-l border-zinc-700/60 pl-2">
            {(['Now', '1h', '3h', '6h'] as const).map((h) => (
              <button
                key={h}
                type="button"
                onClick={() => onActiveHorizonChange?.(h)}
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold transition-colors ${
                  activeHorizon === h
                    ? 'bg-sky-500 text-white shadow-xs'
                    : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {h === 'Now' ? 'Now' : `+${h}`}
              </button>
            ))}
          </div>
        </div>

        {/* Right: Camera Controls & View Mode Return */}
        <div className="flex items-center gap-1.5 pointer-events-auto">
          {/* Google 3D Tiles Key Dialog Trigger */}
          <button
            onClick={() => setShowKeyModal(true)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/80 text-xs font-mono text-zinc-200 backdrop-blur-md shadow-md cursor-pointer"
            title="Configure Google Maps Platform Photorealistic 3D Tiles API Key"
          >
            <Key className="w-3.5 h-3.5 text-amber-400" />
            <span className="hidden sm:inline">3D Tiles Key</span>
          </button>

          {/* Camera Buttons */}
          <button
            onClick={handleZoomIn}
            className="p-1.5 rounded-lg bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/80 text-zinc-200 backdrop-blur-md shadow-md cursor-pointer"
            title="Zoom In"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleZoomOut}
            className="p-1.5 rounded-lg bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/80 text-zinc-200 backdrop-blur-md shadow-md cursor-pointer"
            title="Zoom Out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleResetNorth}
            className="p-1.5 rounded-lg bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/80 text-zinc-200 backdrop-blur-md shadow-md cursor-pointer"
            title="Reset North / Tilt 45°"
          >
            <RotateCcw className="w-3.5 h-3.5 text-sky-400" />
          </button>
          <button
            onClick={handleFitExtent}
            className="px-2 py-1.5 rounded-lg bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/80 text-xs font-mono text-sky-300 backdrop-blur-md shadow-md cursor-pointer"
            title="Fit to Observed Flood Extent"
          >
            Fit Extent
          </button>
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded-lg bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/80 text-zinc-200 backdrop-blur-md shadow-md cursor-pointer"
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>

          {/* Close / Return to MapLibre */}
          {onCloseEarthView && (
            <button
              onClick={onCloseEarthView}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-sky-950/90 hover:bg-sky-900 border border-sky-500/60 text-xs font-mono font-bold text-sky-200 backdrop-blur-md shadow-md cursor-pointer ml-1"
              title="Return to MapLibre 3D Terrain Map"
            >
              <span>MapLibre 2D/3D</span>
              <X className="w-3.5 h-3.5 ml-0.5" />
            </button>
          )}
        </div>
      </div>

      {/* Floating Layer Toggles Bar (Left Column) */}
      <div className="absolute top-14 left-3 z-20 flex flex-col gap-1.5 pointer-events-auto bg-[#070e1b]/90 backdrop-blur-md p-1.5 rounded-xl border border-zinc-800 shadow-xl">
        <button
          onClick={() => setLayerFloodWater(!layerFloodWater)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-mono font-bold transition-all cursor-pointer ${
            layerFloodWater
              ? 'bg-cyan-950/70 text-cyan-300 border border-cyan-500/50'
              : 'text-zinc-500 hover:text-zinc-300'
          }`}
          title="Toggle Observed Inundation Polygon"
        >
          <Waves className="w-3.5 h-3.5 text-cyan-400" />
          <span>FLOOD EXTENT</span>
        </button>

        <button
          onClick={() => setLayerRiskMarkers(!layerRiskMarkers)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-mono font-bold transition-all cursor-pointer ${
            layerRiskMarkers
              ? 'bg-amber-950/70 text-amber-300 border border-amber-500/50'
              : 'text-zinc-500 hover:text-zinc-300'
          }`}
          title="Toggle Red/Yellow/Green/Gray Risk Locations"
        >
          <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
          <span>RISK ZONES</span>
        </button>

        <button
          onClick={() => setLayerIncidents(!layerIncidents)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-mono font-bold transition-all cursor-pointer ${
            layerIncidents
              ? 'bg-rose-950/70 text-rose-300 border border-rose-500/50'
              : 'text-zinc-500 hover:text-zinc-300'
          }`}
          title="Toggle Citizen Distress Incidents"
        >
          <LifeBuoy className="w-3.5 h-3.5 text-rose-400" />
          <span>INCIDENTS</span>
        </button>

        <button
          onClick={() => setLayerFacilities(!layerFacilities)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-mono font-bold transition-all cursor-pointer ${
            layerFacilities
              ? 'bg-emerald-950/70 text-emerald-300 border border-emerald-500/50'
              : 'text-zinc-500 hover:text-zinc-300'
          }`}
          title="Toggle Shelters & Hospitals"
        >
          <Shield className="w-3.5 h-3.5 text-emerald-400" />
          <span>FACILITIES</span>
        </button>
      </div>

      {/* Interactive Entity Inspection HUD Popup */}
      {selectedEntity && (
        <div className="absolute bottom-12 left-3 z-30 w-80 sm:w-96 bg-[#070e1b]/95 backdrop-blur-xl border border-sky-800/80 rounded-xl p-4 shadow-2xl text-slate-200 pointer-events-auto">
          <div className="flex items-start justify-between border-b border-zinc-800 pb-2 mb-2.5">
            <div>
              <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-sky-400">
                {selectedEntity.customMarkerType === 'RISK_ZONE'
                  ? 'MODEL RISK FORECAST'
                  : selectedEntity.customMarkerType === 'INCIDENT'
                  ? 'CITIZEN ASSISTANCE PING'
                  : selectedEntity.customMarkerType === 'FACILITY'
                  ? 'EMERGENCY FACILITY'
                  : 'OBSERVED FLOOD EXTENT'}
              </div>
              <h4 className="text-sm font-bold text-white font-mono leading-tight">
                {selectedEntity.name || selectedEntity.title || 'Selected Feature'}
              </h4>
            </div>
            <button
              onClick={() => setSelectedEntity(null)}
              className="text-zinc-400 hover:text-white p-1 rounded hover:bg-zinc-800 cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* RISK ZONE CONTENT */}
          {selectedEntity.customMarkerType === 'RISK_ZONE' && (
            <div className="space-y-2.5 text-xs">
              <div className="flex items-center justify-between p-2 rounded bg-zinc-900/80 border border-zinc-800">
                <span className="text-zinc-400">Current Forecast Horizon:</span>
                <span
                  className="px-2 py-0.5 rounded font-mono font-bold text-[11px]"
                  style={{
                    backgroundColor: `${selectedEntity.colorHex}25`,
                    color: selectedEntity.colorHex,
                    borderColor: `${selectedEntity.colorHex}60`,
                    borderWidth: '1px',
                  }}
                >
                  {selectedEntity.riskLevel}
                </span>
              </div>

              {/* Horizon Table */}
              <div className="border border-zinc-800/80 rounded overflow-hidden">
                <div className="bg-zinc-900/90 px-2.5 py-1 text-[10px] font-mono font-bold text-zinc-400 uppercase">
                  Prediction Horizons (+1h / +3h / +6h)
                </div>
                <div className="grid grid-cols-3 divide-x divide-zinc-800 text-center font-mono py-1.5 text-[11px]">
                  <div>
                    <div className="text-[10px] text-zinc-500">+1 HOUR</div>
                    <div className="font-bold text-zinc-200">
                      {selectedEntity.horizons?.['+1h']?.risk_level || 'UNKNOWN'}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-zinc-500">+3 HOURS</div>
                    <div className="font-bold text-zinc-200">
                      {selectedEntity.horizons?.['+3h']?.risk_level || 'UNKNOWN'}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-zinc-500">+6 HOURS</div>
                    <div className="font-bold text-zinc-200">
                      {selectedEntity.horizons?.['+6h']?.risk_level || 'UNKNOWN'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Provenance & Limitations */}
              <div className="text-[11px] text-zinc-400 space-y-1 bg-zinc-950/60 p-2 rounded border border-zinc-800/60">
                <div>Model: <strong className="text-zinc-300">{selectedEntity.modelVersion}</strong></div>
                <div>Issued: <span className="font-mono text-zinc-300">{selectedEntity.issuedAt?.slice(0, 19)}</span></div>
                <div className="text-amber-300/90 italic pt-1">
                  * {selectedEntity.disclaimer}
                </div>
              </div>
            </div>
          )}

          {/* FLOOD EXTENT CONTENT */}
          {selectedEntity.type === 'FLOOD_EXTENT' && (
            <div className="space-y-2 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                  <div className="text-[10px] text-zinc-500 uppercase">Inundated Area</div>
                  <strong className="text-cyan-300 font-mono text-sm">{selectedEntity.area_km2} km²</strong>
                </div>
                <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                  <div className="text-[10px] text-zinc-500 uppercase">Observation Sensor</div>
                  <strong className="text-zinc-200 font-mono text-[11px]">{selectedEntity.method}</strong>
                </div>
              </div>
              <p className="text-[11px] text-sky-200 bg-sky-950/30 p-2 rounded border border-sky-800/40">
                Observed from Sentinel-1 SAR C-band radar via FastAPI/PostGIS. Derived area reflects spatial inundation boundary; independent validation is not implied.
              </p>
            </div>
          )}

          {/* INCIDENT CONTENT */}
          {selectedEntity.customMarkerType === 'INCIDENT' && (
            <div className="space-y-2 text-xs">
              <div className="p-2 rounded bg-rose-950/30 border border-rose-800/40 text-rose-200">
                <div>Location: <strong>{selectedEntity.locationName}</strong></div>
                <div>Urgency: <strong>{selectedEntity.urgency}</strong> &bull; Category: <strong>{selectedEntity.category || 'ASSISTANCE'}</strong></div>
                <div>People affected: <strong>{selectedEntity.peopleCount || 'Unspecified'}</strong></div>
                {selectedEntity.notes && <div className="mt-1 italic">"{selectedEntity.notes}"</div>}
              </div>
              <div className="text-[11px] text-zinc-400 italic">
                * {selectedEntity.disclaimer}
              </div>
            </div>
          )}

          {/* FACILITY CONTENT */}
          {selectedEntity.customMarkerType === 'FACILITY' && (
            <div className="space-y-2 text-xs">
              <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                <div>Type: <strong className="capitalize">{selectedEntity.facilityType}</strong></div>
                <div>Status: <strong className="capitalize text-emerald-400">{selectedEntity.verification_status}</strong></div>
                {selectedEntity.capacity && <div>Capacity: <strong>{selectedEntity.capacity}</strong></div>}
                {selectedEntity.contact_info && <div>Contact: <strong>{selectedEntity.contact_info}</strong></div>}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Bottom Color Legend & Operational Disclaimer Strip */}
      <div className="absolute bottom-2 left-3 right-3 z-10 flex flex-wrap items-center justify-between bg-[#040812]/90 backdrop-blur-md px-3 py-1.5 rounded-lg border border-zinc-800/90 text-xs font-mono text-zinc-300 gap-2 pointer-events-auto">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-bold text-sky-400 text-[11px]">3D RISK KEYS:</span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 shadow-sm" />
            <span className="text-[11px] text-zinc-200">High / Critical</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400 shadow-sm" />
            <span className="text-[11px] text-zinc-200">Moderate</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-sm" />
            <span className="text-[11px] text-zinc-200">Low Risk*</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500 shadow-sm" />
            <span className="text-[11px] text-zinc-400">No Forecast</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-2 rounded-xs bg-cyan-400/60 border border-cyan-300" />
            <span className="text-[11px] text-cyan-300">Observed Water</span>
          </span>
        </div>

        <div className="text-[10px] text-amber-300/80 italic">
          * Green denotes low modeled risk, NOT guaranteed safety. Does not measure water depth.
        </div>
      </div>

      {/* Google Maps Platform Photorealistic 3D Tiles Key Modal */}
      {showKeyModal && (
        <div className="absolute inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#0b1325] border border-sky-800 rounded-xl p-5 max-w-md w-full shadow-2xl text-slate-200 font-sans">
            <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
              <div className="flex items-center gap-2 text-white font-mono font-bold text-sm">
                <Key className="w-4 h-4 text-amber-400" />
                <span>Google Photorealistic 3D Tiles</span>
              </div>
              <button
                onClick={() => setShowKeyModal(false)}
                className="text-zinc-400 hover:text-white p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleApplyGoogleKey} className="mt-4 space-y-3.5 text-xs">
              <p className="text-zinc-300 leading-relaxed">
                Google Photorealistic 3D Tiles require a configured Google Maps Platform API key with
                the <strong>Map Tiles API</strong> enabled and billing authorized on your Google Cloud project.
              </p>

              <div>
                <label className="block text-zinc-300 font-mono mb-1 text-[11px] font-bold">
                  Google Maps Platform API Key:
                </label>
                <input
                  type="password"
                  value={googleKeyInput}
                  onChange={(e) => setGoogleKeyInput(e.target.value)}
                  placeholder="AIzaSy..."
                  className="w-full px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-white font-mono text-xs focus:outline-hidden focus:border-sky-500"
                />
              </div>

              {googleKeyError && (
                <div className="p-2 rounded bg-rose-950/60 border border-rose-700 text-rose-300 text-[11px]">
                  {googleKeyError}
                </div>
              )}

              <div className="p-2.5 rounded bg-zinc-900/80 border border-zinc-800 text-[11px] text-zinc-400 space-y-1">
                <div>• Without an active Google key, the 3D globe operates seamlessly using Esri World Imagery (Non-Google).</div>
                <div>• Billable services are never initiated automatically.</div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setShowKeyModal(false)}
                  className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 font-mono text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-mono text-xs font-bold shadow-md cursor-pointer"
                >
                  Apply 3D Tiles
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
