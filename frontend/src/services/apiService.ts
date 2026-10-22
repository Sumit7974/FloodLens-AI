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

import { getAccessToken } from './backendApi';

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

      const headers: Record<string, string> = { 'Accept': 'application/json' };
      const token = getAccessToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${API_BASE_URL}/alerts`, {
        signal: controller.signal,
        headers,
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          return { alerts: data, fromBackend: true };
        }
      }
    } catch {
      // Graceful fallback to cached store
    }
    return { alerts: fallbackAlerts, fromBackend: false };
  }

  /**
   * Transmit standardized DEOC handoff packet to backend using supported PATCH /assistance/{id}
   */
  public static async logHandoffToBackend(incidentId: string, payload: any): Promise<boolean> {
    try {
      const headers: Record<string, string> = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      };
      const token = getAccessToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const statusNotes = payload?.status_notes || payload?.notes || (typeof payload === 'string' ? payload : 'Authority DEOC handoff packet acknowledged');

      const res = await fetch(`${API_BASE_URL}/assistance/${encodeURIComponent(incidentId)}`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({
          status: 'acknowledged',
          status_notes: statusNotes,
        }),
      });
      return res.ok;
    } catch {
      return false;
    }
  }
}
