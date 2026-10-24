import React, { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle,
  Building2,
  Calendar,
  Database,
  Download,
  FileCode,
  FileSpreadsheet,
  FileText,
  History,
  Layers,
  MapPin,
  RefreshCw,
  ShieldAlert,
  Waves,
} from 'lucide-react';
import {
  DEMO_MODE,
  getFloodReport,
  downloadFloodReportExport,
  listHistoricalEvents,
  type FloodEventRecord,
  type FloodReportResponse,
} from '../services/backendApi';
import type { BenchmarkScene } from '../types';

interface HistoricalReportsProps {
  currentScene: BenchmarkScene;
}

export const HistoricalReports: React.FC<HistoricalReportsProps> = ({ currentScene }) => {
  const [events, setEvents] = useState<FloodEventRecord[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string>('');
  const [report, setReport] = useState<FloodReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloadingFormat, setDownloadingFormat] = useState<'json' | 'csv' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);

  // Load historical events list
  useEffect(() => {
    if (DEMO_MODE) {
      const demoEvents: FloodEventRecord[] = [
        {
          id: 'koshi-basin-primary',
          name: '2026 Monsoon Surge — Koshi Basin Reach',
          region_id: 'koshi-basin',
          start_at: '2026-10-17T18:00:00Z',
          end_at: '2026-10-19T12:00:00Z',
          mode: 'historical_demo',
          source_refs: { copernicus_sar: 'S1A_20261018', dhm_gauges: 12 },
          description: 'Saptakoshi monsoon flood surge event with active extent polygons.',
          created_at: '2026-10-18T00:00:00Z',
        },
        {
          id: 'terai-flood-2024',
          name: '2024 Terai Flood Surge Benchmark',
          region_id: 'sunsari-morang',
          start_at: '2024-08-12T00:00:00Z',
          end_at: '2024-08-16T18:00:00Z',
          mode: 'historical_demo',
          source_refs: { sensor: 'Sentinel-1A SAR' },
          description: 'Historical monsoon benchmark with recorded settlement inundation.',
          created_at: '2024-08-17T00:00:00Z',
        },
      ];
      setEvents(demoEvents);
      setSelectedEventId((prev) => (prev && demoEvents.some((e) => e.id === prev) ? prev : demoEvents[0].id));
      return;
    }

    listHistoricalEvents()
      .then((evs) => {
        setEvents(evs);
        if (evs.length > 0) {
          setSelectedEventId((prev) => {
            const match = evs.find((e) => e.id === prev);
            return match ? match.id : evs[0].id;
          });
        }
      })
      .catch((err) => {
        console.warn('Could not load flood events for reports view:', err);
      });
  }, []);

  // Synchronize selectedEventId if currentScene matches a registered event
  useEffect(() => {
    if (events.length > 0 && currentScene?.id) {
      const match = events.find((e) => e.id === currentScene.id);
      if (match) {
        setSelectedEventId(match.id);
      }
    }
  }, [currentScene.id, events]);

  // Fetch synthesized impact report for selected event
  const fetchReport = useCallback(async () => {
    if (!selectedEventId) return;

    setLoading(true);
    setError(null);
    setExportError(null);

    if (DEMO_MODE) {
      // In demo mode, construct verified demo report matching Koshi Basin benchmark scenario
      const is2024 = selectedEventId === 'terai-flood-2024';
      const demoReport: FloodReportResponse = {
        event_id: selectedEventId,
        event_name: is2024 ? '2024 Terai Flood Surge Benchmark' : '2026 Monsoon Surge — Koshi Basin Reach',
        region_id: is2024 ? 'sunsari-morang' : 'koshi-basin',
        mode: 'historical_demo',
        extent_observed_at: is2024 ? '2024-08-14T06:00:00Z' : '2026-10-18T05:00:00Z',
        extent_area_km2: is2024 ? 38.2 : 46.8,
        total_settlements_affected: is2024 ? 2 : 3,
        settlements_evaluated: is2024 ? 8 : 12,
        settlements_data_status: 'completed',
        roads_exposed_km: is2024 ? 14.2 : 18.4,
        structures_exposed_count: is2024 ? 98 : 142,
        cropland_exposed_ha: is2024 ? 245.0 : 320.5,
        assets_data_status: 'completed',
        report_generated_at: new Date().toISOString(),
        status: 'summary_available',
        data_limitations: [
          'Physical exposure indicates spatial intersection with satellite water mask; exposure does not equal verified structural damage.',
          'Settlement population counts reflect census figures, not verified casualties or displaced persons.',
          'Sentinel-1 SAR C-Band radar cannot penetrate dense vegetation canopy or high-density urban shadows.',
        ],
        data_provenance: {
          extent_id: is2024 ? 'ext_terai_2024_01' : 'ext_koshi_sar_01',
          export_available: true,
          export_endpoint: `/api/v1/flood-events/${selectedEventId}/report/export`,
          satellite_source: 'Copernicus Sentinel-1A SAR VV backscatter',
        },
      };

      setReport(demoReport);
      setLastRefreshedAt(new Date().toLocaleTimeString());
      setLoading(false);
      return;
    }

    try {
      const res = await getFloodReport(selectedEventId);
      setReport(res);
      setLastRefreshedAt(new Date().toLocaleTimeString());
    } catch (err: any) {
      // If the selectedEventId is not found (404) and we have other valid events, gracefully switch to the first valid event
      if (err?.status === 404 && events.length > 0 && selectedEventId !== events[0].id) {
        setSelectedEventId(events[0].id);
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to query FastAPI flood report summary.');
    } finally {
      setLoading(false);
    }
  }, [selectedEventId, events]);

  useEffect(() => {
    void fetchReport();
  }, [fetchReport]);

  const handleDownload = async (format: 'json' | 'csv') => {
    if (!selectedEventId) return;
    setDownloadingFormat(format);
    setExportError(null);

    try {
      await downloadFloodReportExport(selectedEventId, format);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : `Failed to download ${format.toUpperCase()} report.`);
    } finally {
      setDownloadingFormat(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Disclaimer Banner: Archival Decision Support Record */}
      <div className="p-3.5 rounded-lg bg-indigo-500/10 border-2 border-indigo-500/50 text-indigo-200 text-xs font-mono flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <History className="w-4 h-4 text-indigo-400 shrink-0" />
          <span>
            <strong>HISTORICAL IMPACT REPORTING MODULE:</strong> Synthesized post-disaster evaluation records combining Copernicus satellite extents with regional GIS exposure layers. This tool provides archival audit records, not active emergency dispatches.
          </span>
        </div>
        <span className="px-2 py-0.5 rounded bg-black/60 border border-indigo-400/40 text-[10px] text-indigo-300 font-bold">
          FASTAPI /flood-events/{'{event_id}'}/report
        </span>
      </div>

      {/* Header Bar */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded bg-indigo-500/20 border border-indigo-500/40 text-indigo-400">
            <FileText className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
              Historical Flood Reports // Evidence &amp; Exposure Synthesis
              <span className="px-2 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/40 text-indigo-300 text-[9px] font-mono font-bold tracking-wider">
                API V1 FLOOD-EVENTS
              </span>
            </h1>
            <p className="font-mono text-[10px] text-indigo-300 uppercase tracking-wider mt-0.5 font-semibold">
              SYNTHESIZED IMPACT SUMMARY &bull; {currentScene.name}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {lastRefreshedAt && (
            <span className="text-[10px] font-mono text-slate-400">
              Fetched: <strong className="text-white">{lastRefreshedAt}</strong>
            </span>
          )}
          <button
            onClick={() => void fetchReport()}
            disabled={loading}
            className="px-3.5 py-1.5 rounded-md bg-[#0f2442] hover:bg-[#16355e] border border-[#2b4c7e] text-xs font-mono font-bold text-white flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-indigo-400 ${loading ? 'animate-spin' : ''}`} />
            <span>{loading ? 'Fetching…' : 'Refresh Report'}</span>
          </button>
        </div>
      </div>

      {/* Event Selector Card */}
      <div className="p-3.5 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 font-mono text-xs">
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-cyan-400" />
          <label className="text-slate-300 font-bold uppercase text-[11px]">
            Target Historical Flood Episode:
          </label>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={selectedEventId}
            onChange={(e) => setSelectedEventId(e.target.value)}
            className="px-3 py-1.5 rounded-md bg-black/60 border border-[#1e3a5f] text-white text-xs font-mono focus:outline-none focus:border-indigo-500 min-w-[280px]"
          >
            {events.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.name} ({ev.id})
              </option>
            ))}
            {events.length === 0 && (
              <option value="koshi-basin-primary">2026 Monsoon Surge — Koshi Basin (Default)</option>
            )}
          </select>
        </div>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
          <span>Report query failed: {error}</span>
        </div>
      )}

      {exportError && (
        <div className="p-3.5 rounded-lg bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>Export generation error: {exportError}</span>
        </div>
      )}

      {report && (
        <div className="space-y-4 font-mono text-xs">
          {/* Key Indicators Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Event Scope */}
            <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-2">
              <div className="flex items-center justify-between pb-1 border-b border-[#1e3a5f]">
                <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">
                  Event Scope
                </span>
                <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 uppercase">
                  {report.mode}
                </span>
              </div>
              <div>
                <h3 className="font-bold text-white text-sm leading-tight">{report.event_name}</h3>
                <div className="text-[10px] text-slate-400 mt-1 flex items-center gap-1">
                  <MapPin className="w-3 h-3 text-cyan-400" />
                  Region: {report.region_id}
                </div>
              </div>
              <div className="pt-2 border-t border-[#1e3a5f]/60 text-[10px] flex items-center justify-between">
                <span className="text-slate-400">Synthesis Status:</span>
                <span className="text-emerald-400 font-bold uppercase">{report.status}</span>
              </div>
            </div>

            {/* Mapped Flood Area */}
            <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-2">
              <div className="flex items-center justify-between pb-1 border-b border-[#1e3a5f]">
                <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">
                  Mapped Inundation
                </span>
                <Waves className="w-3.5 h-3.5 text-cyan-400" />
              </div>
              <div className="space-y-1">
                <div className="text-2xl font-bold font-mono text-cyan-400">
                  {report.extent_area_km2 != null ? `${report.extent_area_km2.toFixed(1)} km²` : 'Pending'}
                </div>
                <div className="text-[10px] text-slate-400">
                  Observation: {report.extent_observed_at ? new Date(report.extent_observed_at).toLocaleString() : 'No extent observation'}
                </div>
              </div>
              <div className="pt-2 border-t border-[#1e3a5f]/60 text-[10px] text-slate-400">
                Derived via Sentinel-1 SAR VV backscatter thresholding
              </div>
            </div>

            {/* Affected Settlements */}
            <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-2">
              <div className="flex items-center justify-between pb-1 border-b border-[#1e3a5f]">
                <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">
                  Settlements Exposed
                </span>
                <Building2 className="w-3.5 h-3.5 text-amber-400" />
              </div>
              <div className="space-y-1">
                <div className="text-2xl font-bold font-mono text-amber-400">
                  {report.total_settlements_affected}
                  <span className="text-xs text-slate-400 ml-1">/ {report.settlements_evaluated} evaluated</span>
                </div>
                <div className="text-[10px] text-slate-400">
                  Coverage: {report.settlements_data_status || 'completed'}
                </div>
              </div>
              <div className="pt-2 border-t border-[#1e3a5f]/60 text-[10px] text-slate-400">
                Census boundary centroids intersected by SAR polygon
              </div>
            </div>

            {/* Infrastructure & Assets */}
            <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-2">
              <div className="flex items-center justify-between pb-1 border-b border-[#1e3a5f]">
                <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">
                  Asset Exposure
                </span>
                <Database className="w-3.5 h-3.5 text-rose-400" />
              </div>
              <div className="space-y-1 text-[11px]">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Roads Inundated:</span>
                  <span className="font-bold text-white">{report.roads_exposed_km?.toFixed(1) || '0.0'} km</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Structures Exposed:</span>
                  <span className="font-bold text-white">{report.structures_exposed_count ?? 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Cropland Flooded:</span>
                  <span className="font-bold text-emerald-400">{report.cropland_exposed_ha?.toFixed(1) || '0.0'} ha</span>
                </div>
              </div>
              <div className="pt-2 border-t border-[#1e3a5f]/60 text-[10px] text-slate-400">
                Status: {report.assets_data_status || 'completed'}
              </div>
            </div>
          </div>

          {/* Detailed Synthesis Summary & Evidence Boundaries */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Left 8 Cols: Limitations & Provenance */}
            <div className="lg:col-span-8 p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-[#1e3a5f]">
                <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-cyan-400" />
                  Evidence Limitations &amp; Decision-Support Boundaries
                </h3>
                <span className="px-2 py-0.5 rounded bg-black/50 border border-[#1e3a5f] text-[9px] text-slate-400">
                  POSTGIS SYNTHESIS
                </span>
              </div>

              <div className="space-y-2">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-bold">
                  System Caveats:
                </span>
                <ul className="space-y-1.5">
                  {report.data_limitations && report.data_limitations.length > 0 ? (
                    report.data_limitations.map((lim, idx) => (
                      <li key={idx} className="p-2.5 rounded bg-black/40 border border-[#1e3a5f] text-slate-200 flex items-start gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                        <span className="text-[11px] leading-relaxed">{lim}</span>
                      </li>
                    ))
                  ) : (
                    <li className="p-2.5 rounded bg-black/40 border border-[#1e3a5f] text-slate-400 text-xs">
                      No explicit limitations recorded for this dataset.
                    </li>
                  )}
                </ul>
              </div>

              {report.data_provenance && (
                <div className="pt-2 border-t border-[#1e3a5f]/60 text-[10px] text-slate-400 space-y-1">
                  <div className="flex items-center justify-between text-slate-300 font-bold">
                    <span>PROVENANCE RECORD:</span>
                    <span>FASTAPI POSTGIS SPATIAL ENGINE</span>
                  </div>
                  <pre className="p-2 rounded bg-black/50 border border-[#1e3a5f] text-slate-400 text-[10px] overflow-x-auto">
                    {JSON.stringify(report.data_provenance, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Right 4 Cols: Real Exports Panel */}
            <div className="lg:col-span-4 p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-[#1e3a5f]">
                <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                  <Download className="w-4 h-4 text-emerald-400" />
                  Export Artifacts
                </h3>
                <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[9px] font-bold">
                  VERIFIED FORMATS
                </span>
              </div>

              <div className="space-y-2 text-slate-300 text-xs">
                <p className="text-[11px] leading-relaxed text-slate-400">
                  Export physical data files generated directly by the FastAPI backend impact synthesis engine.
                </p>

                {/* Real JSON Download */}
                <button
                  onClick={() => void handleDownload('json')}
                  disabled={downloadingFormat !== null}
                  className="w-full p-3 rounded-md bg-[#0f2442] hover:bg-[#16355e] border border-[#2b4c7e] text-left transition-colors cursor-pointer flex items-center justify-between disabled:opacity-50"
                >
                  <div className="flex items-center gap-2.5">
                    <FileCode className="w-5 h-5 text-cyan-400" />
                    <div>
                      <div className="font-bold text-white text-xs">Export Report (JSON)</div>
                      <div className="text-[10px] text-slate-400">RFC 8259 structured payload with full metadata</div>
                    </div>
                  </div>
                  {downloadingFormat === 'json' ? (
                    <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4 text-slate-400 hover:text-white" />
                  )}
                </button>

                {/* Real CSV Download */}
                <button
                  onClick={() => void handleDownload('csv')}
                  disabled={downloadingFormat !== null}
                  className="w-full p-3 rounded-md bg-[#0f2442] hover:bg-[#16355e] border border-[#2b4c7e] text-left transition-colors cursor-pointer flex items-center justify-between disabled:opacity-50"
                >
                  <div className="flex items-center gap-2.5">
                    <FileSpreadsheet className="w-5 h-5 text-emerald-400" />
                    <div>
                      <div className="font-bold text-white text-xs">Export Summary (CSV)</div>
                      <div className="text-[10px] text-slate-400">Tabular summary row for spreadsheet audit</div>
                    </div>
                  </div>
                  {downloadingFormat === 'csv' ? (
                    <RefreshCw className="w-4 h-4 text-emerald-400 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4 text-slate-400 hover:text-white" />
                  )}
                </button>
              </div>

              {/* Explicit Architecture Boundary Notice: No fake PDF / Shapefile */}
              <div className="p-2.5 rounded bg-black/60 border border-[#1e3a5f]/60 text-[10px] text-slate-400 space-y-1">
                <span className="font-bold uppercase tracking-wider text-[9px] text-amber-300 block">
                  ARCHITECTURE COMPLIANCE:
                </span>
                <p>
                  Only verified CSV and JSON exports are implemented in the FloodLens FastAPI architecture. PDF and Shapefile formats are not implemented in the backend and cannot be downloaded.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
