import React, { useMemo } from 'react';
import { StyleSheet, View, Text } from 'react-native';
import { WebView } from 'react-native-webview';
import type { LatLng, Rings } from './geo';
import { C } from './ui';

export type MapMarker = {
  id?: string;
  coordinate: LatLng;
  title?: string;
  description?: string;
  color?: string;
};

export type MapPolygon = {
  coordinates: Rings;
  strokeColor?: string;
  fillColor?: string;
  strokeWidth?: number;
};

interface Props {
  center?: LatLng | null;
  zoom?: number;
  polygons?: MapPolygon[];
  markers?: MapMarker[];
  style?: object;
}

export function MapViewFallback({ center, zoom = 11, polygons = [], markers = [], style }: Props) {
  const htmlContent = useMemo(() => {
    const lat = center?.latitude ?? 26.65;
    const lon = center?.longitude ?? 87.05;

    // Sanitize and simplify polygons for leaflet
    const polyData = polygons.map(p => ({
      coords: p.coordinates.map(pt => [pt.latitude, pt.longitude]),
      stroke: p.strokeColor || C.aqua,
      fill: p.fillColor || 'rgba(20,179,191,0.3)',
      weight: p.strokeWidth || 2,
    }));

    const markerData = markers.map(m => ({
      lat: m.coordinate.latitude,
      lon: m.coordinate.longitude,
      title: m.title ? m.title.replace(/['"<>\\]/g, '') : '',
      desc: m.description ? m.description.replace(/['"<>\\]/g, '') : '',
      color: m.color || C.yellow,
    }));

    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map { margin: 0; padding: 0; width: 100%; height: 100%; background: #0b151b; font-family: -apple-system, Roboto, sans-serif; }
    .leaflet-popup-content-wrapper { background: #0d1e27; color: #f1f5f9; border: 1px solid #1e3a47; border-radius: 8px; }
    .leaflet-popup-tip { background: #0d1e27; }
    .custom-dot { border-radius: 50%; border: 2px solid #ffffff; box-shadow: 0 0 6px rgba(0,0,0,0.6); }
    .leaflet-container { background-color: #0b151b !important; }
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    try {
      var map = L.map('map', {
        center: [${lat}, ${lon}],
        zoom: ${zoom},
        zoomControl: false,
        attributionControl: false
      });

      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 19,
        subdomains: 'abcd'
      }).addTo(map);

      var polyLayers = [];
      var polys = ${JSON.stringify(polyData)};
      polys.forEach(function(p) {
        if (p.coords && p.coords.length > 0) {
          var layer = L.polygon(p.coords, {
            color: p.stroke,
            fillColor: p.fill,
            fillOpacity: 0.35,
            weight: p.weight
          }).addTo(map);
          polyLayers.push(layer);
        }
      });

      var markers = ${JSON.stringify(markerData)};
      markers.forEach(function(m) {
        var icon = L.divIcon({
          className: 'custom-dot',
          html: '<div style="width:12px; height:12px; background:' + m.color + '; border-radius:50%;"></div>',
          iconSize: [16, 16],
          iconAnchor: [8, 8]
        });
        var marker = L.marker([m.lat, m.lon], { icon: icon }).addTo(map);
        if (m.title || m.desc) {
          marker.bindPopup('<b>' + m.title + '</b><br/><small>' + m.desc + '</small>');
        }
      });

      if (polyLayers.length > 0) {
        var group = new L.featureGroup(polyLayers);
        map.fitBounds(group.getBounds().pad(0.1));
      }
    } catch (e) {
      document.body.innerHTML = '<div style="color:#94a3b8;padding:20px;text-align:center;">Interactive map loaded offline. Coordinates: ${lat.toFixed(4)}, ${lon.toFixed(4)}</div>';
    }
  </script>
</body>
</html>`;
  }, [center, zoom, polygons, markers]);

  return (
    <View style={[styles.container, style]}>
      <WebView
        originWhitelist={['*']}
        source={{ html: htmlContent }}
        style={styles.webview}
        javaScriptEnabled={true}
        domStorageEnabled={true}
        startInLoadingState={true}
        renderLoading={() => (
          <View style={styles.loadingContainer}>
            <Text style={styles.loadingText}>Rendering interactive flood map…</Text>
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    height: '100%',
    backgroundColor: C.surface,
  },
  webview: {
    backgroundColor: 'transparent',
  },
  loadingContainer: {
    ...StyleSheet.absoluteFill,
    backgroundColor: C.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    color: C.muted,
    fontSize: 12,
  },
});
