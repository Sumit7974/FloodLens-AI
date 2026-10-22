import React, { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  AlertTriangle,
  CloudRain,
  Layers,
  RefreshCw,
  ShieldAlert,
  Waves,
} from 'lucide-react';
import {
  DEMO_MODE,
  getWeatherMonitoring,
  getRiverMonitoring,
  getDamMonitoring,
  type GaugeStationRecord,
  type WeatherMonitoringResponse,
  type DamMonitoringResponse,
} from '../services/backendApi';
import type { BenchmarkScene } from '../types';

interface EnvironmentalMonitoringProps {
  currentScene: BenchmarkScene;
}

export const EnvironmentalMonitoring: React.FC<EnvironmentalMonitoringProps> = ({ currentScene }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);

  const [weatherData, setWeatherData] = useState<WeatherMonitoringResponse | null>(null);
  const [riverStations, setRiverStations] = useState<GaugeStationRecord[]>([]);
  const [damData, setDamData] = useState<DamMonitoringResponse | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    if (DEMO_MODE) {
      // In demo mode, use the verified demonstration fixtures representing Koshi Basin baseline
      setWeatherData({
        status: 'active',
        providers: ['DHM Nepal (Hydrology & Meteorology)', 'ECMWF IFS-HRES', 'Open-Meteo Global SE-Asia'],
        readings: [],
        note: 'Baseline demonstration configuration. Live API telemetry disabled in DEMO_MODE.',
      });
      setRiverStations([
        {
          station_id: 'gauge-chatara',
          name: 'Chatara Hydro-Station',
          river: 'Saptakoshi Main Stem',
          coordinates: [87.163, 26.871],
          current_level: 8.18,
          warning_level: 7.0,
          danger_level: 8.0,
          discharge_rate: 14250,
          trend: 'RISING',
          last_reported_at: 'Historical scenario reference (Chatara Flood Marker)',
          battery_level: 98,
          status: 'CRITICAL',
        },
        {
          station_id: 'gauge-barrage',
          name: 'Koshi Barrage Control',
          river: 'Koshi Main Channel',
          coordinates: [86.918, 26.522],
          current_level: 74.85,
          warning_level: 74.0,
          danger_level: 75.0,
          discharge_rate: 12980,
          trend: 'RISING',
          last_reported_at: 'Historical scenario reference (Barrage Sluice Registry)',
          battery_level: 94,
          status: 'WARNING',
        },
        {
          station_id: 'gauge-mulghat',
          name: 'Mulghat Station',
          river: 'Tamor River',
          coordinates: [87.332, 26.935],
          current_level: 4.62,
          warning_level: 5.0,
          danger_level: 6.5,
          discharge_rate: 3150,
          trend: 'RISING',
          last_reported_at: 'Historical scenario reference (Tamor Inflow Sensor)',
          battery_level: 91,
          status: 'NORMAL',
        },
        {
          station_id: 'gauge-rabuwaghat',
          name: 'Rabuwaghat Station',
          river: 'Dudh Koshi',
          coordinates: [86.654, 27.268],
          current_level: 5.12,
          warning_level: 5.5,
          danger_level: 7.0,
          discharge_rate: 2840,
          trend: 'STABLE',
          last_reported_at: 'Historical scenario reference (Dudh Koshi Outflow)',
          battery_level: 88,
          status: 'NORMAL',
        },
      ]);
      setDamData({
        notices: [],
        verified_count: 0,
        note: 'Only verified dam notices are displayed by authority systems.',
      });
      setLastRefreshedAt(new Date().toLocaleTimeString());
      setLoading(false);
      return;
    }

    try {
      const [w, r, d] = await Promise.all([
        getWeatherMonitoring().catch((err) => {
          console.warn('Weather monitoring fetch failed:', err);
          return { status: 'offline', providers: [], readings: [], note: err instanceof Error ? err.message : 'Error fetching weather' };
        }),
        getRiverMonitoring(currentScene.id).catch((err) => {
          console.warn('River monitoring fetch failed:', err);
          return { status: 'offline', stations: [], readings: [], count: 0 };
        }),
        getDamMonitoring().catch((err) => {
          console.warn('Dam monitoring fetch failed:', err);
          return { notices: [], verified_count: 0, note: err instanceof Error ? err.message : 'Error fetching dams' };
        }),
      ]);

      setWeatherData(w);
      setRiverStations(r.stations || []);
      setDamData(d);
      setLastRefreshedAt(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to query FastAPI monitoring routes.');
    } finally {
      setLoading(false);
    }
  }, [currentScene.id]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  return (
    <div className="space-y-4">
      {/* Disclaimer Banner: Demo Fixtures Caution */}
      <div className="p-3.5 rounded-lg bg-amber-500/10 border-2 border-amber-500/50 text-amber-200 text-xs font-mono flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
          <span>
            <strong>DATA PROVENANCE NOTICE:</strong> Backend river gauge records are pre-configured demonstration fixtures. They represent hydrological baseline references, not live-streamed sensor telemetry.
          </span>
        </div>
        <span className="px-2 py-0.5 rounded bg-black/60 border border-amber-400/40 text-[10px] text-amber-300 font-bold">
          {DEMO_MODE ? 'DEMO MODE FIXTURES' : 'FASTAPI DEMONSTRATION RECORD'}
        </span>
      </div>

      {/* Header Bar */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded bg-cyan-500/20 border border-cyan-500/40 text-cyan-400">
            <Activity className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
              Environmental Monitoring // Hydro-Meteorological Observatories
              <span className="px-2 py-0.5 rounded-full bg-cyan-500/15 border border-cyan-500/40 text-cyan-300 text-[9px] font-mono font-bold tracking-wider">
                API V1 MONITORING
              </span>
            </h1>
            <p className="font-mono text-[10px] text-cyan-300 uppercase tracking-wider mt-0.5 font-semibold">
              STATIONS &bull; {currentScene.name} ({currentScene.district})
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {lastRefreshedAt && (
            <span className="text-[10px] font-mono text-slate-400">
              Queried: <strong className="text-white">{lastRefreshedAt}</strong>
            </span>
          )}
          <button
            onClick={() => void fetchData()}
            disabled={loading}
            className="px-3.5 py-1.5 rounded-md bg-[#0f2442] hover:bg-[#16355e] border border-[#2b4c7e] text-xs font-mono font-bold text-white flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${loading ? 'animate-spin' : ''}`} />
            <span>{loading ? 'Refreshing…' : 'Refresh Telemetry'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
          <span>Backend monitoring query failed: {error}</span>
        </div>
      )}

      {/* Main Grid: Weather Providers + Dam Releases */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Weather Providers Card */}
        <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3 font-mono text-xs">
          <div className="flex items-center justify-between pb-2 border-b border-[#1e3a5f]">
            <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
              <CloudRain className="w-4 h-4 text-cyan-400" />
              Meteorological Providers
            </h3>
            <span className="px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/30 text-[10px] font-bold uppercase">
              {weatherData?.status || 'Active'}
            </span>
          </div>

          <div className="space-y-2">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-bold">
              Configured Weather Sources:
            </span>
            {weatherData?.providers && weatherData.providers.length > 0 ? (
              <ul className="space-y-1.5">
                {weatherData.providers.map((p, idx) => (
                  <li key={idx} className="p-2 rounded bg-black/40 border border-[#1e3a5f] text-slate-200 flex items-center justify-between">
                    <span className="font-semibold text-white">{p}</span>
                    <span className="text-[9px] text-emerald-400 uppercase tracking-wider font-bold">Configured</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="p-3 rounded bg-black/40 border border-[#1e3a5f] text-slate-400 text-xs">
                No configured external weather observation providers in database.
              </div>
            )}
          </div>

          {/* Actual Readings State */}
          <div className="pt-2 border-t border-[#1e3a5f]/60 text-slate-400 space-y-1">
            <div className="flex items-center justify-between text-[11px]">
              <span>Active Precipitation Ingest:</span>
              <span className="text-amber-300 font-bold">No verified readings available</span>
            </div>
            <p className="text-[10px] text-slate-500 italic">
              {weatherData?.note || 'Weather monitoring skeleton endpoint active. Precipitation fields are not fabricated without sensor link.'}
            </p>
          </div>
        </div>

        {/* Dam Releases & Reservoir Safety Card */}
        <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3 font-mono text-xs">
          <div className="flex items-center justify-between pb-2 border-b border-[#1e3a5f]">
            <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
              <Layers className="w-4 h-4 text-indigo-400" />
              Verified Dam Release Notices
            </h3>
            <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-[10px] font-bold">
              {damData?.verified_count ?? 0} VERIFIED
            </span>
          </div>

          <div className="space-y-2">
            {damData?.notices && damData.notices.length > 0 ? (
              <div className="space-y-2">
                {damData.notices.map((n, idx) => (
                  <div key={idx} className="p-2.5 rounded bg-black/40 border border-[#1e3a5f] space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white">{n.dam_name || 'Dam Release Point'}</span>
                      <span className="text-amber-400 text-[10px] font-bold">{n.warning_level || 'ADVISORY'}</span>
                    </div>
                    <div className="text-[11px] text-slate-300">
                      Discharge: {n.discharge_m3s ? `${n.discharge_m3s} m³/s` : 'Not reported'}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-4 rounded bg-black/40 border border-[#1e3a5f] text-center space-y-1.5">
                <span className="text-slate-300 font-semibold block">No verified dam release notices</span>
                <p className="text-[11px] text-slate-400">
                  {damData?.note || 'Only verified dam release schedules published by authorities are displayed.'}
                </p>
              </div>
            )}
          </div>

          <div className="pt-2 border-t border-[#1e3a5f]/60 text-[10px] text-slate-400">
            Dam spillway operations are regulated by regional river commissions. FloodLens does not synthesize automated reservoir warnings.
          </div>
        </div>

        {/* Observatory Summary Card */}
        <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3 font-mono text-xs">
          <div className="flex items-center justify-between pb-2 border-b border-[#1e3a5f]">
            <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
              <Waves className="w-4 h-4 text-emerald-400" />
              Basin Hydro Stations
            </h3>
            <span className="text-emerald-400 text-[10px] font-bold">
              {riverStations.length} STATIONS
            </span>
          </div>

          <div className="space-y-2">
            <div className="p-2.5 rounded bg-black/40 border border-[#1e3a5f] flex items-center justify-between">
              <span className="text-slate-400 text-[11px]">Reporting Coverage:</span>
              <span className="text-white font-bold">{riverStations.length} of 4 Basin Gauges</span>
            </div>
            <div className="p-2.5 rounded bg-black/40 border border-[#1e3a5f] flex items-center justify-between">
              <span className="text-slate-400 text-[11px]">Critical Stage Exceeded:</span>
              <span className="text-rose-400 font-bold">
                {riverStations.filter((s) => s.status === 'CRITICAL').length} Stations
              </span>
            </div>
            <div className="p-2.5 rounded bg-black/40 border border-[#1e3a5f] flex items-center justify-between">
              <span className="text-slate-400 text-[11px]">Provenance Mode:</span>
              <span className="text-amber-300 font-bold">Example Demonstration Fixture</span>
            </div>
          </div>

          <div className="pt-2 border-t border-[#1e3a5f]/60 text-[10px] text-slate-400">
            Values are historical reference thresholds calibrated against DHM Koshi river cross-sections.
          </div>
        </div>
      </div>

      {/* River Gauges Directory & Water-Level Table */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3 font-mono text-xs">
        <div className="flex items-center justify-between pb-2 border-b border-[#1e3a5f]">
          <div>
            <h2 className="font-display text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <Waves className="w-4 h-4 text-cyan-400" />
              River Telemetry Gauge Stations
            </h2>
            <p className="text-[10px] text-slate-400 mt-0.5">
              Hydrological water stages, danger thresholds, and estimated discharge rates.
            </p>
          </div>
          <span className="px-2.5 py-1 rounded bg-black/60 border border-[#1e3a5f] text-[10px] text-cyan-300 font-bold">
            SOURCE: /api/v1/monitoring/gauges
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-black/60 text-[10px] text-slate-400 uppercase tracking-wider border-b border-[#1e3a5f]">
                <th className="p-2.5">Station ID</th>
                <th className="p-2.5">Station &amp; Waterway</th>
                <th className="p-2.5">Coordinates (Lng, Lat)</th>
                <th className="p-2.5 text-right">Water Stage</th>
                <th className="p-2.5 text-right">Warning / Danger</th>
                <th className="p-2.5 text-right">Discharge</th>
                <th className="p-2.5 text-center">Trend</th>
                <th className="p-2.5 text-center">Sensor Status</th>
                <th className="p-2.5">Reference Provenance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e3a5f]/60">
              {riverStations.map((station) => {
                const isCritical = station.status === 'CRITICAL' || station.current_level >= station.danger_level;
                const isWarning = station.status === 'WARNING' || station.current_level >= station.warning_level;

                return (
                  <tr key={station.station_id} className="hover:bg-white/[0.03] transition-colors">
                    <td className="p-2.5 font-bold text-slate-300 text-[11px] whitespace-nowrap">
                      {station.station_id}
                    </td>
                    <td className="p-2.5">
                      <div className="font-bold text-white">{station.name}</div>
                      <div className="text-[10px] text-slate-400">{station.river}</div>
                    </td>
                    <td className="p-2.5 text-[11px] text-slate-300 font-mono whitespace-nowrap">
                      {station.coordinates ? `${station.coordinates[0]?.toFixed(3)}, ${station.coordinates[1]?.toFixed(3)}` : 'N/A'}
                    </td>
                    <td className="p-2.5 text-right font-mono font-bold whitespace-nowrap">
                      <span className={isCritical ? 'text-rose-400' : isWarning ? 'text-amber-400' : 'text-emerald-400'}>
                        {station.current_level?.toFixed(2)} m
                      </span>
                    </td>
                    <td className="p-2.5 text-right font-mono text-slate-400 text-[11px] whitespace-nowrap">
                      <span className="text-amber-300">{station.warning_level?.toFixed(2)}m</span>
                      {' / '}
                      <span className="text-rose-300">{station.danger_level?.toFixed(2)}m</span>
                    </td>
                    <td className="p-2.5 text-right font-mono text-white text-[11px] whitespace-nowrap">
                      {station.discharge_rate ? `${station.discharge_rate.toLocaleString()} m³/s` : 'N/A'}
                    </td>
                    <td className="p-2.5 text-center whitespace-nowrap">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                          station.trend === 'RISING'
                            ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                            : station.trend === 'FALLING'
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            : 'bg-slate-500/20 text-slate-300 border border-slate-500/40'
                        }`}
                      >
                        {station.trend || 'STABLE'}
                      </span>
                    </td>
                    <td className="p-2.5 text-center whitespace-nowrap">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[9px] font-bold ${
                          station.status === 'CRITICAL'
                            ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                            : station.status === 'WARNING'
                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                            : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                        }`}
                      >
                        {station.status}
                      </span>
                    </td>
                    <td className="p-2.5 text-[10px] text-slate-400 max-w-xs">
                      <span className="text-amber-300 font-semibold block text-[11px]">Example Demo Fixture</span>
                      <span className="text-[9px] text-slate-500 italic block">
                        {station.last_reported_at?.includes('Historical')
                          ? station.last_reported_at
                          : `Simulated record (${station.last_reported_at}) — Not live sensor`}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
