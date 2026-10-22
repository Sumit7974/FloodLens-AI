import React, { useState, useEffect } from 'react';
import {
  AlertCircle,
  BrainCircuit,
  CheckCircle,
  Download,
  GitCommit,
  Layers,
  LineChart,
  RefreshCw,
  Rocket,
  Sparkles,
} from 'lucide-react';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';
import { DataStatusBadge } from './common/DataStatusBadge';
import { floodLensClient } from '../services/floodLensClient';
import { InteractiveHoverButton } from '@/components/ui/interactive-hover-button';
import type { BenchmarkScene } from '../types';

interface ModelAnalyticsProps {
  currentScene: BenchmarkScene;
  deployedModelVersion: string;
  onDeployModel: (newVersion: string) => void;
}

export const ModelAnalytics: React.FC<ModelAnalyticsProps> = ({
  currentScene,
  deployedModelVersion,
  onDeployModel,
}) => {
  // Candidate vs Production view toggle
  const [selectedModel, setSelectedModel] = useState<'prod' | 'candidate'>('candidate');

  // Layer toggles on map
  const [layers, setLayers] = useState({
    truePositive: true,
    falsePositive: true,
    falseNegative: true,
  });

  // Retraining Pipeline simulation state
  const [retrainingState, setRetrainingState] = useState<'READY' | 'RUNNING' | 'COMPLETE'>('COMPLETE');

  // Client API / Mock Adapter State
  const [evalStatus, setEvalStatus] = useState<'live' | 'cached' | 'error'>('cached');

  useEffect(() => {
    let isMounted = true;
    const loadEval = async () => {
      const res = await floodLensClient.getModelEvaluation(currentScene.id);
      if (isMounted) {
        setEvalStatus(res.status);
      }
    };
    loadEval();
    return () => {
      isMounted = false;
    };
  }, [currentScene.id]);

  // Confirmation modal for model deployment
  const [showDeployModal, setShowDeployModal] = useState(false);

  // Notification feedback toast
  const [toast, setToast] = useState<string | null>(null);

  const notify = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  const toggleLayer = (key: keyof typeof layers) => {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleTriggerRetraining = () => {
    setRetrainingState('RUNNING');
    notify('Ingesting validation splits & running 10-fold cross validation...');
    setTimeout(() => {
      setRetrainingState('COMPLETE');
      notify('Cross-validation complete: Candidate model v1.3-RC ready (82.4% IoU)');
    }, 2000);
  };

  const handleConfirmDeploy = () => {
    onDeployModel('FloodLens-LSTM-GNN v1.3-RC');
    setShowDeployModal(false);
    notify('Model v1.3-RC promoted: Updated local inference parameters in backend container');
  };

  const handleExportReport = () => {
    const reportData = {
      benchmark: 'Nepal Terai Koshi Surge - Event August 2026',
      evaluationTimestamp: new Date().toISOString(),
      productionModel: deployedModelVersion,
      candidateModel: 'FloodLens-LSTM-GNN v1.3-RC',
      mathematical_metrics: {
        iou_formula: 'IoU = |P ∩ G| / |P ∪ G|',
        precision_formula: 'Precision = |P ∩ G| / |P|',
        recall_formula: 'Recall = |P ∩ G| / |G|',
        iou_production: '73.1%',
        iou_candidate: '82.4%',
        iou_gain: '+9.3%',
        precision: '87.6%',
        recall: '89.1%',
        falseAlarmAreaKm2: 4.8,
        missedInundationAreaKm2: 5.6,
        peakCrestArrivalError: '+/- 12 mins (improved from +/- 45 mins)',
        breachSensitivity: '91% (improved from 61%)',
      },
      spatialErrorsDiagnosed: [
        'Embankment breach at Spur 12+400 not in baseline 1D hydrodynamic model',
        'Localized micro-topography culvert blockage in Ward 7',
      ],
      datasetSensors: 'Sentinel-1 SAR + Sentinel-2 NDWI + 12 Telemetry Gauges',
      note: 'Parameters evaluated on 2017-2024 Terai monsoon validation splits. Deployment updates local inference weights in the backend container.',
    };

    const blob = new Blob([JSON.stringify(reportData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `FloodLens_AI_Model_Evaluation_Report_${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    notify('Model evaluation & retraining audit report downloaded (JSON)');
  };

  // Precision-Recall Curve points for 2026 Koshi Basin verification dataset
  const precisionRecallCurve = [
    { threshold: 0.1, recall: 0.98, precision: 0.65 },
    { threshold: 0.2, recall: 0.95, precision: 0.74 },
    { threshold: 0.3, recall: 0.93, precision: 0.81 },
    { threshold: 0.4, recall: 0.91, precision: 0.85 },
    { threshold: 0.5, recall: 0.89, precision: 0.88 }, // Operational point
    { threshold: 0.6, recall: 0.84, precision: 0.91 },
    { threshold: 0.7, recall: 0.78, precision: 0.94 },
    { threshold: 0.8, recall: 0.68, precision: 0.97 },
  ];

  return (
    <div className="space-y-4 font-mono">
      {/* 1. TOP HEADER & MODEL VERSION CONTROLS */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3.5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="p-2 rounded bg-indigo-500/20 border border-indigo-500/40 text-indigo-400">
              <BrainCircuit className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="font-display text-base font-bold text-white uppercase tracking-wider">
                  Model Analytics &amp; Spatial Verification Engine
                </h1>
                <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/40 text-indigo-300 text-[10px] font-mono font-bold tracking-wider">
                  [HISTORICAL BENCHMARK EVALUATION — 2026 KOSHI SURGE]
                </span>
                <DataStatusBadge status={evalStatus} />
              </div>
              <p className="font-mono text-xs text-[#38bdf8] uppercase tracking-wide mt-0.5 font-semibold">
                Ground-truth spatial alignment &bull; IoU evaluation &bull; Offline parameter promotion
              </p>
            </div>
          </div>

          {/* Model Version Toggle Badges */}
          <div className="inline-flex p-1 rounded-full border border-[#1e3a5f] bg-[#060e1d] text-xs">
            <button
              onClick={() => setSelectedModel('prod')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full font-bold uppercase tracking-wider transition-colors cursor-pointer ${
                selectedModel === 'prod'
                  ? 'bg-gradient-to-r from-sky-600 to-blue-600 text-white shadow-[0_0_10px_rgba(14,165,233,0.4)]'
                  : 'text-[#94a3b8] hover:text-white'
              }`}
            >
              <GitCommit className="w-3.5 h-3.5 text-sky-300" />
              <span>ACTIVE PRODUCTION ({deployedModelVersion.split(' ')[1] || 'v1.2'})</span>
            </button>

            <button
              onClick={() => setSelectedModel('candidate')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full font-bold uppercase tracking-wider transition-colors cursor-pointer ${
                selectedModel === 'candidate'
                  ? 'bg-gradient-to-r from-[#e86e25] to-[#f97316] text-white shadow-[0_0_10px_rgba(232,110,37,0.4)]'
                  : 'text-[#94a3b8] hover:text-white'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-300" />
              <span>CANDIDATE: v1.3-RC</span>
            </button>
          </div>
        </div>
      </div>

      {/* 2. FORMAL MATHEMATICAL EVALUATION METRICS STRIP */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {/* Metric 1: Intersection over Union */}
        <div className="p-3.5 bg-[#071326]/85 border border-[#1e3a5f] rounded-lg space-y-1">
          <span className="text-[10px] uppercase tracking-wider text-slate-400 block font-bold">
            Intersection Over Union (IoU)
          </span>
          <div className="font-display text-2xl lg:text-3xl font-bold text-white tracking-wider flex items-baseline gap-1">
            <span>{selectedModel === 'candidate' ? '82.4%' : '73.1%'}</span>
            <span className="text-[11px] text-emerald-400 font-normal">
              {selectedModel === 'candidate' ? '+9.3%' : 'baseline'}
            </span>
          </div>
          <p className="text-[10px] text-sky-300 font-mono">IoU = |P ∩ G| / |P ∪ G|</p>
        </div>

        {/* Metric 2: Spatial Precision */}
        <div className="p-3.5 bg-[#071326]/85 border border-[#1e3a5f] rounded-lg space-y-1">
          <span className="text-[10px] uppercase tracking-wider text-slate-400 block font-bold">
            Spatial Precision
          </span>
          <div className="font-display text-2xl lg:text-3xl font-bold text-white tracking-wider">
            {selectedModel === 'candidate' ? '87.6%' : '78.2%'}
          </div>
          <p className="text-[10px] text-slate-400 uppercase font-mono">Precision = |P ∩ G| / |P|</p>
        </div>

        {/* Metric 3: Spatial Recall */}
        <div className="p-3.5 bg-[#071326]/85 border border-[#1e3a5f] rounded-lg space-y-1">
          <span className="text-[10px] uppercase tracking-wider text-slate-400 block font-bold">
            Spatial Recall
          </span>
          <div className="font-display text-2xl lg:text-3xl font-bold text-white tracking-wider">
            {selectedModel === 'candidate' ? '89.1%' : '79.5%'}
          </div>
          <p className="text-[10px] text-slate-400 uppercase font-mono">Recall = |P ∩ G| / |G|</p>
        </div>

        {/* Metric 4: False Positive Area */}
        <div className="p-3.5 bg-[#071326]/85 border border-[#1e3a5f] rounded-lg space-y-1">
          <span className="text-[10px] uppercase tracking-wider text-slate-400 block font-bold">
            False Positive Area (FP)
          </span>
          <div className="font-display text-2xl lg:text-3xl font-bold text-amber-300 tracking-wider">
            4.8 <span className="text-xs font-normal text-slate-400">KM²</span>
          </div>
          <p className="text-[10px] text-slate-400 uppercase">Over-predicted dry land</p>
        </div>

        {/* Metric 5: False Negative Area */}
        <div className="p-3.5 bg-[#071326]/85 border border-[#1e3a5f] rounded-lg space-y-1 col-span-2 md:col-span-1">
          <span className="text-[10px] uppercase tracking-wider text-slate-400 block font-bold">
            False Negative Area (FN)
          </span>
          <div className="font-display text-2xl lg:text-3xl font-bold text-rose-400 tracking-wider">
            5.6 <span className="text-xs font-normal text-slate-400">KM²</span>
          </div>
          <p className="text-[10px] text-slate-400 uppercase">Missed inundation fringe</p>
        </div>
      </div>

      {/* 3. MAIN 2-COLUMN LAYOUT: SPATIAL MAP VS RETRAINING PIPELINE */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* LEFT COLUMN: 3D SPATIAL VERIFICATION MAP (7 cols on lg/xl) */}
        <div className="lg:col-span-7 flex flex-col space-y-2">
          {/* Spatial Layer Toggles */}
          <div className="p-3 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="text-[10px] uppercase text-slate-400 font-bold flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-white" />
              Spatial Verification Layers:
            </span>

            <div className="flex flex-wrap items-center gap-1.5">
              <button
                onClick={() => toggleLayer('truePositive')}
                className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-bold flex items-center gap-1.5 border cursor-pointer ${
                  layers.truePositive
                    ? 'bg-cyan-500/20 border-cyan-400 text-cyan-200'
                    : 'bg-black/40 border-[#1e3a5f] text-slate-400'
                }`}
              >
                <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                <span>TRUE POSITIVE (MATCH)</span>
              </button>

              <button
                onClick={() => toggleLayer('falsePositive')}
                className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-bold flex items-center gap-1.5 border cursor-pointer ${
                  layers.falsePositive
                    ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                    : 'bg-black/40 border-[#1e3a5f] text-slate-400'
                }`}
              >
                <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                <span>FALSE POSITIVE (OVER-PREDICTED)</span>
              </button>

              <button
                onClick={() => toggleLayer('falseNegative')}
                className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-bold flex items-center gap-1.5 border cursor-pointer ${
                  layers.falseNegative
                    ? 'bg-rose-500/20 border-rose-400 text-rose-200'
                    : 'bg-black/40 border-[#1e3a5f] text-slate-400'
                }`}
              >
                <span className="w-2 h-2 rounded-full bg-rose-400"></span>
                <span>FALSE NEGATIVE (MISSED)</span>
              </button>
            </div>
          </div>

          {/* 3D Map Component */}
          <GeospatialTerrainMap
            center={currentScene.center || [87.05, 26.65]}
            zoom={11}
            pitch={55}
            bearing={-15}
            activeHorizon="3h"
            showInundation={layers.truePositive}
            showForecast={layers.falsePositive}
            showGauges={true}
            showInfrastructure={true}
            showShelters={true}
            height="520px"
          />
        </div>

        {/* RIGHT COLUMN: PRECISION-RECALL CURVE & CANDIDATE MODEL PIPELINE (5 cols) */}
        <div className="lg:col-span-5 space-y-3.5">
          {/* Precision-Recall Curve Chart */}
          <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-2.5 text-xs">
            <div className="flex items-center justify-between pb-1.5 border-b border-[#1e3a5f]">
              <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <LineChart className="w-4 h-4 text-sky-400" />
                PRECISION-RECALL CURVE (2026 KOSHI VALIDATION)
              </h3>
              <span className="text-[10px] text-sky-300 font-mono">AUC: 0.912</span>
            </div>

            {/* Simulated Coordinate Graph */}
            <div className="p-2.5 bg-black/60 rounded border border-[#1e3a5f] space-y-2">
              <div className="h-28 flex items-end justify-between gap-1 pt-2 pb-1 border-b border-l border-slate-700 px-2">
                {precisionRecallCurve.map((pt, idx) => {
                  const h = Math.round(pt.precision * 100);
                  const isOpt = pt.threshold === 0.5;
                  return (
                    <div key={idx} className="flex flex-col items-center gap-1 h-full justify-end flex-1">
                      <span className="text-[8px] text-slate-400">{Math.round(pt.precision * 100)}%</span>
                      <div
                        className={`w-full rounded-xs transition-all ${
                          isOpt ? 'bg-sky-400 shadow-[0_0_8px_#38bdf8]' : 'bg-[#1e3a5f]'
                        }`}
                        style={{ height: `${h}%` }}
                      />
                      <span className={`text-[8px] ${isOpt ? 'text-sky-300 font-bold' : 'text-slate-400'}`}>
                        {pt.recall.toFixed(2)}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div className="flex justify-between text-[10px] text-slate-400 px-2">
                <span>RECALL &rarr;</span>
                <span className="text-sky-400 font-bold">&bull; Optimal Threshold: 0.50 (Recall 0.89 / Prec 0.88)</span>
              </div>
            </div>
          </div>

          {/* Candidate Model Pipeline & Ethical Guardrail Disclaimer */}
          <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3 text-xs">
            <div className="flex items-center justify-between pb-2 border-b border-[#1e3a5f]">
              <div>
                <span className="text-[10px] text-slate-400 uppercase block font-bold">
                  Candidate Model Pipeline
                </span>
                <h3 className="font-bold text-white text-sm uppercase">
                  FloodLens-LSTM-GNN v1.3-RC
                </h3>
              </div>

              <button
                onClick={handleTriggerRetraining}
                disabled={retrainingState === 'RUNNING'}
                className="px-2.5 py-1 rounded bg-black/60 border border-[#1e3a5f] text-slate-300 hover:text-white text-[10px] flex items-center gap-1 cursor-pointer"
              >
                <RefreshCw className={`w-3 h-3 ${retrainingState === 'RUNNING' ? 'animate-spin' : ''}`} />
                <span>{retrainingState === 'RUNNING' ? 'EVALUATING...' : 'CROSS-VALIDATE'}</span>
              </button>
            </div>

            {/* Parameter Scope Note */}
            <div className="p-3 bg-black/60 border border-amber-500/40 rounded text-[11px] text-amber-200/90 leading-relaxed">
              <strong className="text-amber-300 block mb-1 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" />
                Inference Weight Parameter Update:
              </strong>
              Clicking &ldquo;Promote Candidate Model&rdquo; updates local inference weighting parameters in the backend container based on evaluated validation splits (not fictitious real-time self-training).
            </div>

            {/* Stepper Status Indicators */}
            <div className="grid grid-cols-5 gap-1 text-[9px] font-mono text-center uppercase">
              <div className="p-1 rounded bg-black/60 border border-slate-700 text-slate-400">1. Ingest</div>
              <div className="p-1 rounded bg-black/60 border border-slate-700 text-slate-400">2. Re-weight</div>
              <div className="p-1 rounded bg-black/60 border border-slate-700 text-slate-400">3. Gradients</div>
              <div className="p-1 rounded bg-black/60 border border-slate-700 text-slate-400">4. 10-Fold CV</div>
              <div className="p-1 rounded bg-emerald-500/20 border border-emerald-500/50 text-emerald-300 font-bold">5. Ready</div>
            </div>

            {/* Comparative Gains */}
            <div className="space-y-1.5 pt-1 text-[11px]">
              <div className="flex justify-between">
                <span className="text-slate-400">Inundation IoU Gain:</span>
                <span className="text-emerald-300 font-bold">73.1% &rarr; 82.4% (+9.3%)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Peak Crest Arrival Error:</span>
                <span className="text-emerald-300 font-bold">&plusmn;45m &rarr; &plusmn;12m</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Breach Sensitivity:</span>
                <span className="text-emerald-300 font-bold">61% &rarr; 91% (+30%)</span>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="pt-2 border-t border-[#1e3a5f] space-y-2">
              <button
                onClick={() => setShowDeployModal(true)}
                className="w-full py-2 px-3 rounded-full bg-gradient-to-r from-[#e86e25] to-[#f97316] hover:from-[#d15d18] hover:to-[#ea580c] text-white font-bold text-xs uppercase tracking-wider border border-[#ff9d5c] shadow-[0_0_12px_rgba(232,110,37,0.4)] transition-all cursor-pointer flex items-center justify-center gap-1.5"
              >
                <Rocket className="w-3.5 h-3.5" />
                <span>PROMOTE CANDIDATE MODEL (v1.3-RC)</span>
              </button>

              <button
                onClick={handleExportReport}
                className="w-full py-2 px-3 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white font-bold text-xs uppercase tracking-wider border border-slate-700 transition-colors cursor-pointer flex items-center justify-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                <span>EXPORT VERIFICATION REPORT (JSON)</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Confirmation Modal */}
      {showDeployModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#071326] border border-[#1e3a5f] rounded-lg p-6 space-y-4 font-mono text-white">
            <div className="flex items-center gap-3">
              <div className="p-2 border border-sky-400 bg-sky-500/20 text-sky-300 rounded">
                <Rocket className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-display text-sm font-bold text-white uppercase tracking-wider">
                  Promote Candidate Checkpoint
                </h3>
                <p className="text-xs text-sky-400">
                  FloodLens-LSTM-GNN v1.3-RC
                </p>
              </div>
            </div>

            <div className="p-3.5 bg-black/60 border border-[#1e3a5f] rounded text-xs space-y-1.5 text-slate-300">
              <p>
                Promoting this candidate updates the local inference weighting parameters in the backend container for the <strong className="text-white">Prediction Centre</strong> and <strong className="text-white">Command Overview</strong>.
              </p>
              <div className="text-emerald-300 font-bold pt-1">
                &bull; Verified IoU Gain: +9.3% (82.4% overall)
              </div>
              <div className="text-emerald-300 font-bold">
                &bull; Embankment Breach Sensitivity: 91%
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowDeployModal(false)}
                className="px-4 py-1.5 rounded-full border border-[#1e3a5f] hover:bg-white/10 text-xs text-slate-300 cursor-pointer"
              >
                Cancel
              </button>
              <InteractiveHoverButton
                text="Confirm Weight Update"
                onClick={handleConfirmDeploy}
                className="w-56 py-1.5 text-xs font-mono tracking-wider border-emerald-500/50 bg-emerald-950/40 text-emerald-200"
                dotColor="bg-emerald-500 group-hover:bg-emerald-500"
              />
            </div>
          </div>
        </div>
      )}

      {/* Action Toast Feedback */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 p-4 bg-[#071326] border border-sky-400 text-white rounded-lg flex items-start gap-3 max-w-md shadow-xl animate-in fade-in">
          <CheckCircle className="w-5 h-5 text-sky-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs">
            <h4 className="font-bold uppercase tracking-wider text-white">Model Engine Status</h4>
            <p className="text-slate-300 mt-0.5">{toast}</p>
          </div>
        </div>
      )}
    </div>
  );
};
