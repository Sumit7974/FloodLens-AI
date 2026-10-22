import { useEffect, useState } from 'react';
import {
  getPredictedRiskZones, listResearchModels, listHistoricalEvents, getEventEvaluations,
  type PredictionMapResponse, type ModelResearchRecord, type FloodEventRecord, type EventEvaluations,
} from '../services/backendApi';

function ExplainDataScope() {
  return (
    <p className="text-xs text-amber-200 border border-amber-800/50 rounded p-3 bg-amber-950/20">
      Historical replay and offline research only. Proxy-data models are not validated operational flood forecasts.
      No actual water depth, rescue dispatch or guaranteed evacuation guidance is supplied.
    </p>
  );
}

export function BackendPredictionPanel() {
  const [prediction, setPrediction] = useState<PredictionMapResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getPredictedRiskZones().then(data => { if (active) setPrediction(data); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Failed to load forecast data'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-950/80 p-5 space-y-4 text-white" aria-label="Historical prediction research data">
      <h2 className="font-semibold text-lg">Prediction Centre · actual FastAPI forecast records</h2>
      <ExplainDataScope />
      {loading && <p role="status" className="text-sky-300">Loading forecast records…</p>}
      {error && <p role="alert" className="text-rose-300">Backend unavailable: {error}</p>}
      {prediction && (
        <>
          <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div><dt className="text-slate-400">Data state</dt><dd className="font-semibold">{prediction.status}</dd></div>
            <div><dt className="text-slate-400">Forecast issue time</dt><dd>{prediction.issued_at || 'Not available'}</dd></div>
            <div><dt className="text-slate-400">Model version</dt><dd>{prediction.model_version || 'Not available'}</dd></div>
            <div><dt className="text-slate-400">Zones with records</dt><dd>{prediction.total_zones}</dd></div>
          </dl>
          <p className="text-xs text-slate-400">
            Data quality: {prediction.data_quality || 'unknown'} · Mode: {prediction.mode || 'not provided'}.
            Predictions are backend-held research records, not live hydro-meteorological readings.
          </p>
          {prediction.status === 'no_data' || prediction.features.length === 0
            ? <p className="text-amber-300 p-4 border border-amber-800 rounded">
                No forecast records are loaded. Member 3 must provide an evaluated +1h/+3h/+6h forecast for the selected shared historical event and Member 1 must ingest it.
              </p>
            : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[600px] text-left text-xs">
                  <thead className="bg-slate-900 text-slate-300"><tr><th className="p-3">Backend location</th><th className="p-3">+1h</th><th className="p-3">+3h</th><th className="p-3">+6h</th><th className="p-3">Quality</th></tr></thead>
                  <tbody>
                    {prediction.features.map(feature => {
                      const hs = feature.properties?.horizons || {};
                      const label = (key: string) => {
                        const h = hs[key];
                        return h ? `${h.risk_level}${h.calibrated_probability == null ? '' : ` · ${Math.round(h.calibrated_probability * 100)}% (model estimate)`}` : 'No data';
                      };
                      return <tr className="border-b border-slate-800" key={feature.id}>
                        <td className="p-3">{feature.properties?.location_name || feature.id}</td>
                        <td className="p-3">{label('+1h')}</td>
                        <td className="p-3">{label('+3h')}</td>
                        <td className="p-3">{label('+6h')}</td>
                        <td className="p-3">{feature.properties?.data_quality || 'Not provided'}</td>
                      </tr>;
                    })}
                  </tbody>
                </table>
              </div>
            )}
        </>
      )}
    </section>
  );
}

export function BackendAnalyticsPanel() {
  const [models, setModels] = useState<ModelResearchRecord[]>([]);
  const [events, setEvents] = useState<FloodEventRecord[]>([]);
  const [selected, setSelected] = useState('');
  const [evaluation, setEvaluation] = useState<EventEvaluations | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    Promise.all([listResearchModels(), listHistoricalEvents()])
      .then(([m, e]) => {
        if (!active) return;
        setModels(m);
        setEvents(e);
        setSelected(e[0]?.id || '');
      })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Backend analytics unavailable'); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selected) { setEvaluation(null); return; }
    let active = true;
    setEvaluation(null);
    getEventEvaluations(selected)
      .then(data => { if (active) { setEvaluation(data); setError(''); } })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Could not load event evaluation'); });
    return () => { active = false; };
  }, [selected]);

  return (
    <section className="rounded-xl border border-slate-700 bg-slate-950/80 p-5 space-y-4 text-white" aria-label="Backend ML evaluation evidence">
      <h2 className="font-semibold text-lg">Model Analytics · verified backend records only</h2>
      <ExplainDataScope />
      <p className="text-xs text-slate-400">Online retraining and model deployment are not implemented. Local demo graphs are not evidence of validated prediction skill.</p>
      {error && <p role="alert" className="text-rose-300">{error}</p>}
      <div className="grid gap-3 md:grid-cols-2">
        {models.map(model => <article className="rounded border border-slate-800 p-3 space-y-2 text-xs" key={model.version}>
          <div className="text-sm font-semibold text-sky-300">{model.version} · {model.status.replace(/_/g, ' ')}</div>
          <p className="text-slate-300">{model.description}</p>
          <div className="text-slate-400">Horizon(s): {model.horizons.map(h => `+${h}h`).join(', ') || 'Not listed'}</div>
          {model.limitations.map((limitation, index) => <p key={index} className="text-amber-200">{limitation}</p>)}
        </article>)}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="eval-event-id" className="font-semibold text-sm">Historical event evaluation</label>
        <select id="eval-event-id" value={selected} onChange={event => setSelected(event.target.value)} className="rounded bg-slate-900 border border-slate-700 p-2 text-sm">
          {!events.length && <option value="">No event imported</option>}
          {events.map(e => <option key={e.id} value={e.id}>{e.name} · {e.start_at.slice(0, 10)}</option>)}
        </select>
      </div>
      {evaluation && (
        <div className="space-y-3">
          <p className="text-sm">Status: <strong>{evaluation.status}</strong> · Recorded evaluations: {evaluation.evaluations_count}</p>
          {evaluation.data_limitations.map((limitation,index) => <p className="text-amber-200 text-xs" key={index}>{limitation}</p>)}
          {evaluation.results.length === 0
            ? <p className="text-slate-300 text-sm">No evaluation records for this historical event. Model performance cannot be claimed as validated.</p>
            : evaluation.results.map(item => (
              <article className="border border-slate-800 rounded p-3 text-xs space-y-2" key={item.id}>
                <h3 className="font-semibold text-slate-100">{item.target_type} · {item.baseline_version} vs {item.candidate_version || 'No candidate'}</h3>
                <p className="text-slate-400">Reference: {item.reference_id || 'Not provided'} · Recorded: {item.created_at}</p>
                <pre className="whitespace-pre-wrap break-words font-mono text-sky-200">{JSON.stringify(item.metrics, null, 2)}</pre>
                {item.notes && <p className="text-amber-200">{item.notes}</p>}
              </article>
            ))}
        </div>
      )}
    </section>
  );
}
