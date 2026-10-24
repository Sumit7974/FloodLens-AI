/**
 * FloodLens Mobile Client Configuration
 * Synchronized with the deployed FastAPI production backend on Render.
 */

export const CONFIG = {
  API_BASE_URL: (process.env.EXPO_PUBLIC_API_URL || 'https://floodlens-backend-4pt5.onrender.com').replace(/\/+$/, ''),
  TIMEOUT_MS: 20000,
  DEFAULT_COORDINATES: {
    latitude: 26.7258,
    longitude: 85.9250,
    region: 'Koshi Basin, Nepal (Terai Flood Corridor)',
  },
  ENDPOINTS: {
    HEALTH: '/health',
    API_V1_HEALTH: '/api/v1/health',
    AUTH_LOGIN: '/api/v1/auth/login',
    AUTH_REGISTER: '/api/v1/auth/register',
    ASSISTANCE_SOS: '/api/v1/assistance',
    MONITORING_GAUGES: '/api/v1/monitoring/gauges',
    ALERTS: '/api/v1/alerts',
    FACILITIES_SHELTERS: '/api/v1/facilities/shelters',
  },
} as const;

export default CONFIG;
