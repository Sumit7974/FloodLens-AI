import React, { useState } from 'react';
import {
  BrainCircuit,
  LifeBuoy,
  Satellite,
  Send,
  TrendingUp,
  Waves,
} from 'lucide-react';
import type { Alert, BenchmarkScene, HelpRequest, NavigationItemId } from '../types';

interface PlaceholderViewsProps {
  tab: NavigationItemId;
  currentScene: BenchmarkScene;
  requests: HelpRequest[];
  alerts: Alert[];
}

export const PlaceholderViews: React.FC<PlaceholderViewsProps> = ({
  tab,
  currentScene,
  requests,
  alerts,
}) => {
  const [horizon, setHorizon] = useState<'1h' | '3h' | '6h'>('3h');

  if (tab === 'prediction-centre') {
    return (
      <div className="space-y-4">
        {/* Top Control Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 rounded-xl bg-slate-900 border border-slate-800 gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-cyan-400" />
                Multi-Horizon Flood Risk Prediction Centre
              </h2>
              <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800/40">
                {currentScene.region}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Hydrological runoff modeling calibrated with Koshi upstream rain gauges &amp; elevation models
            </p>
          </div>

          {/* Horizon Toggle */}
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
            {(['1h', '3h', '6h'] as const).map((h) => (
              <button
                key={h}
                onClick={() => setHorizon(h)}
                className={`px-3 py-1.5 text-xs font-mono font-bold rounded-md transition-all ${
                  horizon === h
                    ? 'bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                +{h} HORIZON
              </button>
            ))}
          </div>
        </div>

        {/* Prediction Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
            <span className="text-[10px] font-bold uppercase text-slate-400">
              Projected River Stage ({horizon})
            </span>
            <div className="text-2xl font-mono font-bold text-rose-400">
              {horizon === '1h' ? '8.32 m' : horizon === '3h' ? '8.54 m' : '8.78 m'}
            </div>
            <p className="text-[11px] text-slate-400">
              Threshold: 7.50m (Danger). Peak predicted at +4.5h from Arun outflow.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
            <span className="text-[10px] font-bold uppercase text-slate-400">
              Estimated Inundation Area
            </span>
            <div className="text-2xl font-mono font-bold text-cyan-400">
              {horizon === '1h' ? '38.4 km²' : horizon === '3h' ? '46.8 km²' : '58.2 km²'}
            </div>
            <p className="text-[11px] text-slate-400">
              Overbank progression affecting low-lying agricultural floodplains.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
            <span className="text-[10px] font-bold uppercase text-slate-400">
              Model Calibration Metadata
            </span>
            <div className="text-sm font-mono font-bold text-emerald-400">
              LSTM-GNN v1.2
            </div>
            <p className="text-[11px] text-slate-400">
              Trained on 2017–2024 Terai Monsoons | Calibrated against telemetry gauges.
            </p>
          </div>
        </div>

        {/* Detailed Horizon Matrix */}
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
          <h3 className="text-xs font-bold uppercase text-white tracking-wide">
            Settlement Exposure Projection Table ({horizon})
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="text-[10px] uppercase font-bold text-slate-400 bg-slate-950/70 border-b border-slate-800">
                <tr>
                  <th className="p-2.5">Settlement / Ward</th>
                  <th className="p-2.5">Projected Water Depth</th>
                  <th className="p-2.5">Population Impact</th>
                  <th className="p-2.5">Recommended Action</th>
                  <th className="p-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                <tr>
                  <td className="p-2.5 font-semibold text-white">Prakashpur (Ward 4)</td>
                  <td className="p-2.5 font-mono text-rose-400">1.8m – 2.4m</td>
                  <td className="p-2.5 font-mono">4,120 citizens</td>
                  <td className="p-2.5 text-rose-300">Mandatory Evacuation Enacted</td>
                  <td className="p-2.5">
                    <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 text-[10px] font-bold uppercase">
                      High Hazard
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="p-2.5 font-semibold text-white">Barahakshetra (Ward 2)</td>
                  <td className="p-2.5 font-mono text-amber-400">0.9m – 1.4m</td>
                  <td className="p-2.5 font-mono">2,850 citizens</td>
                  <td className="p-2.5 text-amber-300">Move to Elevated Shelters</td>
                  <td className="p-2.5">
                    <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px] font-bold uppercase">
                      Moderate
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="p-2.5 font-semibold text-white">Gobargadha Sandbar</td>
                  <td className="p-2.5 font-mono text-rose-400">2.1m – 2.9m</td>
                  <td className="p-2.5 font-mono">1,400 citizens</td>
                  <td className="p-2.5 text-rose-300">Highland Evacuation Triage Underway</td>
                  <td className="p-2.5">
                    <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 text-[10px] font-bold uppercase">
                      Critical
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  if (tab === 'satellite-intel') {
    return (
      <div className="space-y-4">
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Satellite className="w-5 h-5 text-cyan-400" />
              Earth Observation &amp; Satellite Intelligence
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Copernicus Sentinel-2 Optical (NDWI/MNDWI) &amp; Sentinel-1 Synthetic Aperture Radar (SAR)
            </p>
          </div>
          <span className="px-2.5 py-1 text-xs font-mono font-semibold rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
            Latest Orbit Pass: 3h 12m ago
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                Pre-Flood Baseline Scene
              </h3>
              <span className="text-[10px] font-mono text-slate-400">Sentinel-2A • 10m Ground Res</span>
            </div>
            <div className="h-56 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-center relative overflow-hidden">
              <div className="text-center p-4">
                <Satellite className="w-8 h-8 text-cyan-400/50 mx-auto mb-2" />
                <span className="text-xs font-bold text-slate-300 block">Baseline Surface Water Extent</span>
                <span className="text-[11px] text-slate-400 font-mono mt-1 block">
                  Reference MNDWI Threshold: -0.12 • Normal Riverbed: 18.2 km²
                </span>
              </div>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                Post-Event Inundation Detection
              </h3>
              <span className="text-[10px] font-mono text-rose-400">Sentinel-1 SAR VH/VV Backscatter</span>
            </div>
            <div className="h-56 rounded-lg bg-slate-950 border border-rose-900/50 flex items-center justify-center relative overflow-hidden">
              <div className="text-center p-4">
                <Waves className="w-8 h-8 text-rose-400/60 mx-auto mb-2 animate-pulse" />
                <span className="text-xs font-bold text-slate-200 block">Detected Flood Polygon: 46.8 km²</span>
                <span className="text-[11px] text-rose-300 font-mono mt-1 block">
                  Net Increase: +28.6 km² inundated area
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (tab === 'response-ops') {
    return (
      <div className="space-y-4">
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <LifeBuoy className="w-5 h-5 text-rose-400" />
              Response Operations &amp; Citizen SOS Dispatch
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Live incoming distress queue from citizen Android applications &amp; emergency SMS gateway
            </p>
          </div>
          <span className="px-2.5 py-1 text-xs font-mono font-bold rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
            {requests.length} Total Requests Active
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {requests.map((req) => (
            <div key={req.id} className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="text-xs font-bold text-white">{req.requester_name}</h4>
                  <span className="text-[10px] font-mono text-slate-400">{req.id} • {req.timestamp}</span>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  {req.category}
                </span>
              </div>
              <p className="text-xs text-slate-300">{req.location_name}</p>
              <p className="text-[11px] text-slate-400 italic">"{req.landmark}"</p>
              <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-xs">
                <span className="font-mono text-cyan-400 font-semibold">{req.people_count} people</span>
                <span className="text-[11px] text-emerald-400 font-semibold">{req.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (tab === 'alert-dispatcher') {
    return (
      <div className="space-y-4">
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Send className="w-5 h-5 text-amber-400" />
              Emergency Alert Dispatcher &amp; Broadcast Hub
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Draft, verify, authorize, and multi-cast emergency warnings (Common Alerting Protocol CAP v1.2)
            </p>
          </div>
          <button className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-xs font-semibold text-white shadow-md">
            + Draft New Warning
          </button>
        </div>

        <div className="space-y-3">
          {alerts.map((alert) => (
            <div key={alert.id} className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2.5">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                      {alert.severity}
                    </span>
                    <h3 className="text-sm font-bold text-white">{alert.headline}</h3>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{alert.description}</p>
                </div>
                <span className="text-xs font-mono text-emerald-400 font-semibold">{alert.status}</span>
              </div>
              <div className="text-xs text-slate-300 font-mono">
                Geofence: <span className="text-cyan-300">{alert.geofence}</span>
              </div>
              <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs">
                <span className="text-slate-400">Approved by: {alert.approved_by}</span>
                <span className="text-slate-400 font-mono">{alert.dispatched_at}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Model Analytics & Retraining
  return (
    <div className="space-y-4">
      <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <BrainCircuit className="w-5 h-5 text-purple-400" />
            AI Model Analytics &amp; Continuous Retraining
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Post-event validation, IoU flood mask alignment, and reproducible candidate checkpoint auditing
          </p>
        </div>
        <button className="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-xs font-semibold text-white shadow-md">
          Trigger Offline Retraining Run
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-1">
          <span className="text-[10px] font-bold uppercase text-slate-400">Mask IoU Accuracy</span>
          <div className="text-2xl font-mono font-bold text-cyan-400">89.4%</div>
          <p className="text-[11px] text-slate-400">Comparison vs Copernicus Emergency Reference Mask</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-1">
          <span className="text-[10px] font-bold uppercase text-slate-400">Lead Time Gain</span>
          <div className="text-2xl font-mono font-bold text-emerald-400">+2.8 hrs</div>
          <p className="text-[11px] text-slate-400">Earlier evacuation warning threshold trigger</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-1">
          <span className="text-[10px] font-bold uppercase text-slate-400">Model Checkpoint</span>
          <div className="text-2xl font-mono font-bold text-purple-300">v2.4-koshi-prod</div>
          <p className="text-[11px] text-slate-400">Deterministic seeds, weights audited for EOC operations</p>
        </div>
      </div>
    </div>
  );
};
