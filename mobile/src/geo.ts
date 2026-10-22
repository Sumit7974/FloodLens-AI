import type { Geometry } from './api';

export type LatLng = { latitude: number; longitude: number };
export type Rings = LatLng[];

/**
 * RFC 7946 GeoJSON stores [longitude, latitude]. React Native Maps stores
 * {latitude, longitude}. Do not reverse arrays twice.
 */
export function validCoordinate(lon: unknown, lat: unknown): lon is number {
  return typeof lon === 'number' && Number.isFinite(lon)
    && typeof lat === 'number' && Number.isFinite(lat)
    && lon >= -180 && lon <= 180 && lat >= -90 && lat <= 90;
}
function parseRing(unknownRing: unknown): Rings {
  if (!Array.isArray(unknownRing)) return [];
  const points = unknownRing.filter((p): p is number[] =>
    Array.isArray(p) && p.length >= 2 && validCoordinate(p[0], p[1]))
    .map(p => ({ longitude: p[0], latitude: p[1] }));
  return points.length >= 3 ? points : [];
}
/** Return every polygon's exterior ring; interior holes are not drawn by this basic viewer. */
export function exteriorRings(geometry: Geometry | null | undefined): Rings[] {
  if (!geometry || !Array.isArray(geometry.coordinates)) return [];
  const c = geometry.coordinates;
  if (geometry.type === 'Polygon') {
    const ring = parseRing(c[0]);
    return ring.length ? [ring] : [];
  }
  if (geometry.type === 'MultiPolygon') {
    return c.map((polygon: unknown) =>
      Array.isArray(polygon) ? parseRing(polygon[0]) : [])
      .filter((ring: Rings) => ring.length > 0);
  }
  return [];
}
export function geometryCenter(geometry: Geometry | null | undefined): LatLng | null {
  if (geometry?.type === 'Point' && Array.isArray(geometry.coordinates)) {
    const c = geometry.coordinates;
    if (validCoordinate(c[0], c[1])) return { longitude: c[0], latitude: c[1] };
  }
  const rings = exteriorRings(geometry);
  const points = rings.flat();
  if (!points.length) return null;
  const lons = points.map(p => p.longitude);
  const lats = points.map(p => p.latitude);
  return {
    longitude: (Math.min(...lons) + Math.max(...lons)) / 2,
    latitude: (Math.min(...lats) + Math.max(...lats)) / 2,
  };
}
export function pointFromFacility(lat: number | null, lon: number | null): LatLng | null {
  return validCoordinate(lon, lat) ? { latitude: lat!, longitude: lon! } : null;
}
