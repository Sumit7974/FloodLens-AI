import type { Geometry } from './api';

export type LatLng = { latitude: number; longitude: number };
export type Rings = LatLng[];
export type Bounds = { minLat: number; maxLat: number; minLon: number; maxLon: number };

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
  const points: Rings = [];
  for (let i = 0; i < unknownRing.length; i++) {
    const p = unknownRing[i];
    if (Array.isArray(p) && p.length >= 2 && validCoordinate(p[0], p[1])) {
      points.push({ longitude: p[0], latitude: p[1] });
    }
  }
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
    const result: Rings[] = [];
    for (let i = 0; i < c.length; i++) {
      const polygon = c[i];
      if (Array.isArray(polygon)) {
        const ring = parseRing(polygon[0]);
        if (ring.length > 0) result.push(ring);
      }
    }
    return result;
  }
  return [];
}

export function ringsBounds(rings: Rings[]): Bounds | null {
  let minLat = Infinity, maxLat = -Infinity;
  let minLon = Infinity, maxLon = -Infinity;
  let hasPoints = false;

  for (let r = 0; r < rings.length; r++) {
    const ring = rings[r];
    for (let p = 0; p < ring.length; p++) {
      const pt = ring[p];
      if (pt.latitude < minLat) minLat = pt.latitude;
      if (pt.latitude > maxLat) maxLat = pt.latitude;
      if (pt.longitude < minLon) minLon = pt.longitude;
      if (pt.longitude > maxLon) maxLon = pt.longitude;
      hasPoints = true;
    }
  }

  if (!hasPoints) return null;
  return { minLat, maxLat, minLon, maxLon };
}

export function geometryCenter(geometryOrRings: Geometry | Rings[] | null | undefined): LatLng | null {
  if (!geometryOrRings) return null;

  if (!Array.isArray(geometryOrRings) && geometryOrRings.type === 'Point' && Array.isArray(geometryOrRings.coordinates)) {
    const c = geometryOrRings.coordinates;
    if (validCoordinate(c[0], c[1])) return { longitude: c[0], latitude: c[1] };
  }

  const rings = Array.isArray(geometryOrRings) ? geometryOrRings : exteriorRings(geometryOrRings);
  const bounds = ringsBounds(rings);
  if (!bounds) return null;

  return {
    longitude: (bounds.minLon + bounds.maxLon) / 2,
    latitude: (bounds.minLat + bounds.maxLat) / 2,
  };
}

export function pointFromFacility(lat: number | null, lon: number | null): LatLng | null {
  return validCoordinate(lon, lat) ? { latitude: lat!, longitude: lon! } : null;
}
