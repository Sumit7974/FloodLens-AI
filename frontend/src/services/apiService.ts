/**
 * FloodLens AI EOC Backend Integration Service
 * Provides resilient communication with FastAPI backend endpoints:
 * - /api/v1/health
 * - /api/v1/alerts
 * - /api/v1/assistance
 * - /api/v1/monitoring
 *
 * Automatically falls back to local typed benchmark stores when backend is offline
 * or during standalone review while exposing connection status.
 */

const rawBackendUrl = import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_BASE_URL = String(rawBackendUrl).replace(/\/+$/, '').endsWith('/api/v1')
  ? String(rawBackendUrl).replace(/\/+$/, '')
  : `${String(rawBackendUrl).replace(/\/+$/, '')}/api/v1`;

export interface BackendHealthResponse {
  status: string;
  timestamp: string;
  database?: {
    connected: boolean;
  };
}

export class ApiService {
  private static isConnected: boolean = false;
  private static lastCheck: number = 0;

  /**
   * Check backend health and readiness
   */
  public static async checkHealth(): Promise<boolean> {
    const now = Date.now();
    if (now - this.lastCheck < 10000 && this.isConnected) {
      return this.isConnected;
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2500);

      const res = await fetch(`${API_BASE_URL}/health`, {
        signal: controller.signal,
        headers: { 'Accept': 'application/json' },
      });
      clearTimeout(timeoutId);

      this.isConnected = res.ok;
      this.lastCheck = now;
      return this.isConnected;
    } catch {
      this.isConnected = false;
      this.lastCheck = now;
      return false;
    }
  }

  /**
   * Fetch active alerts with fallback
   */
  public static async fetchAlerts(fallbackAlerts: any[]): Promise<{ alerts: any[]; fromBackend: boolean }> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);

      const res = await fetch(`${API_BASE_URL}/alerts`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          return { alerts: data, fromBackend: true };
        }
      }
    } catch {
      // Graceful fallback to cached store
    }
    return { alerts: fallbackAlerts, fromBackend: false };
  }

  /**
   * Transmit standardized DEOC handoff packet to backend
   */
  public static async logHandoffToBackend(incidentId: string, payload: any): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE_URL}/assistance/${incidentId}/handoff`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      return res.ok;
    } catch {
      return false;
    }
  }
}
