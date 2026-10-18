import React, { useState } from 'react';
import {
  MapContainer,
  Polygon,
  TileLayer,
  Tooltip,
} from 'react-leaflet';
import {
  AlertCircle,
  AlertOctagon,
  AlertTriangle,
  BrainCircuit,
  Check,
  CheckCircle,
  CheckCircle2,
  Download,
  GitCommit,
  Layers,
  RefreshCw,
  Rocket,
  Sparkles,
} from 'lucide-react';
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

  // Benchmark dataset selector
  const [datasetBenchmark, setDatasetBenchmark] = useState('koshi-2026-surge');

  // Layer toggles on map
  const [layers, setLayers] = useState({
    predicted: true,
    observed: true,
    falseNegative: true,
    falsePositive: true,
  });

  // Retraining Pipeline simulation state
  const [retrainingState, setRetrainingState] = useState<'READY' | 'RUNNING' | 'COMPLETE'>('COMPLETE');

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
    notify('INITIATED OFFLINE GRADIENT UPDATES & 10-FOLD CV...');
    setTimeout(() => {
      setRetrainingState('COMPLETE');
      notify('RETRAINING COMPLETE: CANDIDATE MODEL v1.3-RC READY (82.4% IOU)');
    }, 2500);
  };

  const handleConfirmDeploy = () => {
    onDeployModel('FloodLens-LSTM-GNN v1.3-RC');
    setShowDeployModal(false);
    notify('MODEL v1.3-RC PROMOTED TO ACTIVE PRODUCTION CHECKPOINT');
  };

  const handleExportReport = () => {
    const reportData = {
      benchmark: 'Nepal Terai Koshi Surge - Event August 2026',
      evaluationTimestamp: new Date().toISOString(),
      productionModel: deployedModelVersion,
      candidateModel: 'FloodLens-LSTM-GNN v1.3-RC',
      metrics: {
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

    notify('MODEL EVALUATION & RETRAINING AUDIT REPORT DOWNLOADED (JSON)');
  };

  // Polygon layers for Spatial Comparison Map
  // 1. Original Predicted Extent (+6h Forecast)
  const predictedPolygon: [number, number][] = [
    [26.90, 87.17],
    [26.85, 87.23],
    [26.78, 87.21],
    [26.70, 87.18],
    [26.62, 87.14],
    [26.54, 87.09],
    [26.46, 87.01],
    [26.44, 86.89],
    [26.51, 86.84],
    [26.64, 86.88],
    [26.73, 86.93],
    [26.82, 87.00],
    [26.90, 87.08],
  ];

  // 2. Actual Observed Flood Extent (Ground Truth from Satellite)
  const observedPolygon: [number, number][] = [
    [26.88, 87.16],
    [26.84, 87.21],
    [26.76, 87.19],
    [26.68, 87.16],
    [26.60, 87.11],
    [26.52, 87.05],
    [26.47, 86.99],
    [26.48, 86.92],
    [26.55, 86.89],
    [26.66, 86.91],
    [26.74, 86.95],
    [26.83, 87.02],
    [26.88, 87.10],
  ];

  // 3. False Negative (Missed Flood Zone near Spur 12+400)
  const falseNegativePolygon: [number, number][] = [
    [26.61, 87.05],
    [26.57, 87.08],
    [26.52, 87.04],
    [26.55, 86.99],
  ];

  // 4. False Positive (Over-predicted Dry Area in East Highlands)
  const falsePositivePolygon: [number, number][] = [
    [26.79, 87.20],
    [26.83, 87.23],
    [26.86, 87.22],
    [26.81, 87.18],
  ];

  return (
    <div className="space-y-4">
      {/* 1. TOP HEADER & MODEL VERSION CONTROLS */}
      <div className="p-4 bg-[#0a0a0a] border border-[#3a3a3f] space-y-3.5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="p-2 border border-[#3a3a3f] bg-black text-white">
              <BrainCircuit className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="font-display text-lg font-bold text-white uppercase tracking-wider">
                  Model Analytics &amp; Closed-Loop AI Retraining
                </h1>
                <span className="badge-chip border-white text-white">
                  EVIDENCE-BASED AUDIT
                </span>
              </div>
              <p className="font-mono text-xs text-[#888890] uppercase tracking-wide mt-0.5">
                Ground-truth spatial alignment &bull; IoU evaluation &bull; Continuous checkpoint deployment
              </p>
            </div>
          </div>

          {/* Model Version Toggle Badges (Ghost Pill Group) */}
          <div className="inline-flex p-1 rounded-full border border-[#3a3a3f] bg-black text-xs">
            <button
              onClick={() => setSelectedModel('prod')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full font-bold uppercase tracking-wider transition-colors ${
                selectedModel === 'prod'
                  ? 'bg-white text-black font-display'
                  : 'text-[#888890] hover:text-white'
              }`}
            >
              <GitCommit className="w-3.5 h-3.5" />
              <span>PRODUCTION ({deployedModelVersion.split(' ')[1] || 'v1.2'})</span>
            </button>

            <button
              onClick={() => setSelectedModel('candidate')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full font-bold uppercase tracking-wider transition-colors ${
                selectedModel === 'candidate'
                  ? 'bg-white text-black font-display'
                  : 'text-[#888890] hover:text-white'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>CANDIDATE: v1.3-RC</span>
            </button>
          </div>
        </div>

        {/* Dataset Benchmark Selector & Calibration Badge */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 pt-3 border-t border-[#3a3a3f] text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-micro uppercase tracking-wider text-[#888890]">
              Evaluation Dataset:
            </span>
            <select
              value={datasetBenchmark}
              onChange={(e) => setDatasetBenchmark(e.target.value)}
              className="bg-black border border-[#3a3a3f] px-3 py-1 text-xs text-white uppercase tracking-wide focus:border-white focus:outline-none font-mono"
            >
              <option value="koshi-2026-surge">
                {currentScene.name} &bull; {currentScene.region} (Ground Truth Calibrated)
              </option>
              <option value="koshi-monsoon-2024">
                Koshi Monsoon Replay - July 2024 (Historical Calibrated)
              </option>
              <option value="narayani-flash-2025">
                Gandaki / Narayani Flash Surge (Cross-Basin Transfer Test)
              </option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <div className="badge-chip border-white text-white">
              <CheckCircle2 className="w-3 h-3 text-white" />
              <span>OBSERVED GROUND TRUTH CALIBRATED // SENTINEL-1 SAR + SENTINEL-2 NDWI</span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. TOP METRICS MATRIX (5 Cards - Pure Monochrome Surfaces) */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {/* Metric 1: IoU */}
        <div className="p-3.5 bg-[#0a0a0a] border border-[#3a3a3f] space-y-1">
          <span className="font-micro uppercase tracking-wider text-[#888890] block">
            Intersection Over Union (IoU)
          </span>
          <div className="font-display text-3xl font-bold text-white tracking-wider flex items-baseline gap-1.5">
            82.4%
            <span className="font-mono text-xs text-white">+9.3%</span>
          </div>
          <p className="font-mono text-[10px] text-[#888890] uppercase">Baseline v1.2: 73.1%</p>
        </div>

        {/* Metric 2: Precision */}
        <div className="p-3.5 bg-[#0a0a0a] border border-[#3a3a3f] space-y-1">
          <span className="font-micro uppercase tracking-wider text-[#888890] block">
            Spatial Precision
          </span>
          <div className="font-display text-3xl font-bold text-white tracking-wider">
            87.6%
          </div>
          <p className="font-mono text-[10px] text-[#888890] uppercase">Low false alarms</p>
        </div>

        {/* Metric 3: Recall */}
        <div className="p-3.5 bg-[#0a0a0a] border border-[#3a3a3f] space-y-1">
          <span className="font-micro uppercase tracking-wider text-[#888890] block">
            Spatial Recall
          </span>
          <div className="font-display text-3xl font-bold text-white tracking-wider">
            89.1%
          </div>
          <p className="font-mono text-[10px] text-[#888890] uppercase">High flood detection</p>
        </div>

        {/* Metric 4: False Alarm Area */}
        <div className="p-3.5 bg-[#0a0a0a] border border-[#3a3a3f] space-y-1">
          <span className="font-micro uppercase tracking-wider text-[#888890] block">
            False Alarm Area
          </span>
          <div className="font-display text-3xl font-bold text-white tracking-wider">
            4.8 <span className="text-xs font-normal text-[#888890]">KM²</span>
          </div>
          <p className="font-mono text-[10px] text-[#888890] uppercase">Over-predicted dry land</p>
        </div>

        {/* Metric 5: Missed Inundation */}
        <div className="p-3.5 bg-[#0a0a0a] border border-[#3a3a3f] space-y-1 col-span-2 md:col-span-1">
          <span className="font-micro uppercase tracking-wider text-[#888890] block">
            Missed Inundation
          </span>
          <div className="font-display text-3xl font-bold text-white tracking-wider">
            5.6 <span className="text-xs font-normal text-[#888890]">KM²</span>
          </div>
          <p className="font-mono text-[10px] text-[#888890] uppercase">Under-predicted fringe</p>
        </div>
      </div>

      {/* 3. MAIN 2-COLUMN LAYOUT: SPATIAL MAP VS RETRAINING ENGINE */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* LEFT COLUMN: PREDICTION VS OBSERVED SPATIAL COMPARISON MAP (7 cols on lg/xl) */}
        <div className="lg:col-span-7 flex flex-col bg-[#0a0a0a] border border-[#3a3a3f] overflow-hidden">
          {/* Map Controls & Layer Toggles Bar */}
          <div className="p-3 border-b border-[#3a3a3f] bg-black flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="font-micro uppercase tracking-wider text-[#888890] flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-white" />
              Spatial Layers:
            </span>

            <div className="flex flex-wrap items-center gap-1.5">
              {/* Predicted Layer */}
              <button
                onClick={() => toggleLayer('predicted')}
                className={`btn-ghost-pill-subtle text-[11px] py-1 px-2.5 flex items-center gap-1.5 ${
                  layers.predicted
                    ? 'border-white text-white bg-white/10'
                    : 'text-[#888890]'
                }`}
              >
                <span className="w-2.5 h-0.5 bg-yellow-400 border-b border-dashed border-white"></span>
                <span>PREDICTED (+6H)</span>
              </button>

              {/* Observed Satellite */}
              <button
                onClick={() => toggleLayer('observed')}
                className={`btn-ghost-pill-subtle text-[11px] py-1 px-2.5 flex items-center gap-1.5 ${
                  layers.observed
                    ? 'border-white text-white bg-white/10'
                    : 'text-[#888890]'
                }`}
              >
                <span className="w-2.5 h-2.5 rounded-full bg-cyan-500 border border-cyan-400"></span>
                <span>OBSERVED (SAR)</span>
              </button>

              {/* Missed Flood Zone (False Negative) */}
              <button
                onClick={() => toggleLayer('falseNegative')}
                className={`btn-ghost-pill-subtle text-[11px] py-1 px-2.5 flex items-center gap-1.5 ${
                  layers.falseNegative
                    ? 'border-white text-white bg-white/10'
                    : 'text-[#888890]'
                }`}
              >
                <span className="w-2.5 h-2.5 rounded-full bg-rose-600 border border-rose-400"></span>
                <span>MISSED (FN)</span>
              </button>

              {/* False Positive (Over-predicted) */}
              <button
                onClick={() => toggleLayer('falsePositive')}
                className={`btn-ghost-pill-subtle text-[11px] py-1 px-2.5 flex items-center gap-1.5 ${
                  layers.falsePositive
                    ? 'border-white text-white bg-white/10'
                    : 'text-[#888890]'
                }`}
              >
                <span className="w-2.5 h-2.5 rounded-full bg-amber-600 border border-amber-400"></span>
                <span>OVER-PREDICTED (FP)</span>
              </button>
            </div>
          </div>

          {/* Leaflet Spatial Comparison Map Canvas */}
          <div className="relative w-full h-[500px] bg-black">
            <MapContainer
              center={[26.68, 87.08]}
              zoom={10}
              scrollWheelZoom={true}
              className="w-full h-full"
            >
              <TileLayer
                attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
                url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
                maxZoom={16}
              />

              {/* 1. Original Predicted Extent (+6h Forecast) - Yellow Dashed Border */}
              {layers.predicted && (
                <Polygon
                  positions={predictedPolygon}
                  pathOptions={{
                    color: '#eab308',
                    fillColor: '#ca8a04',
                    fillOpacity: 0.15,
                    weight: 2,
                    dashArray: '6 6',
                  }}
                >
                  <Tooltip sticky>
                    <div className="p-1 font-mono text-xs">
                      <strong className="text-yellow-400 font-bold block uppercase">Original Predicted Boundary</strong>
                      <span className="text-[10px] text-slate-700">LSTM-GNN BASELINE (+6H HORIZON)</span>
                    </div>
                  </Tooltip>
                </Polygon>
              )}

              {/* 2. Actual Observed Flood Extent from Satellite - Cyan Filled Mask */}
              {layers.observed && (
                <Polygon
                  positions={observedPolygon}
                  pathOptions={{
                    color: '#06b6d4',
                    fillColor: '#0891b2',
                    fillOpacity: 0.45,
                    weight: 1.5,
                  }}
                >
                  <Tooltip sticky>
                    <div className="p-1 font-mono text-xs">
                      <strong className="text-cyan-700 font-bold block uppercase">Observed Satellite Extent</strong>
                      <span className="text-[10px] text-slate-700">SENTINEL-1 SAR + SENTINEL-2 GROUND TRUTH</span>
                    </div>
                  </Tooltip>
                </Polygon>
              )}

              {/* 3. False Negative: Missed Inundation Zone (Red Hatched) */}
              {layers.falseNegative && (
                <Polygon
                  positions={falseNegativePolygon}
                  pathOptions={{
                    color: '#ef4444',
                    fillColor: '#dc2626',
                    fillOpacity: 0.7,
                    weight: 2,
                  }}
                >
                  <Tooltip sticky>
                    <div className="p-1 font-mono text-xs">
                      <strong className="text-rose-700 font-bold block uppercase">Missed Flood Zone (False Negative)</strong>
                      <span className="text-[10px] text-slate-700">AREA: 5.6 KM² &bull; EMBANKMENT BREACH SPILLWAY</span>
                    </div>
                  </Tooltip>
                </Polygon>
              )}

              {/* 4. False Positive: False Alarm Zone (Orange Dashed) */}
              {layers.falsePositive && (
                <Polygon
                  positions={falsePositivePolygon}
                  pathOptions={{
                    color: '#f97316',
                    fillColor: '#ea580c',
                    fillOpacity: 0.65,
                    weight: 2,
                    dashArray: '4 4',
                  }}
                >
                  <Tooltip sticky>
                    <div className="p-1 font-mono text-xs">
                      <strong className="text-amber-700 font-bold block uppercase">False Alarm (False Positive)</strong>
                      <span className="text-[10px] text-slate-700">AREA: 4.8 KM² &bull; ELEVATED LEVEE REMAINED DRY</span>
                    </div>
                  </Tooltip>
                </Polygon>
              )}
            </MapContainer>

            {/* Tactical Legend Floating HUD */}
            <div className="absolute bottom-3 left-3 z-[1000] p-3 bg-black/95 border border-[#3a3a3f] text-[10px] space-y-1.5 shadow-none">
              <span className="font-micro uppercase tracking-wider text-[#888890] block -mb-0.5">
                Evaluation Overlay
              </span>
              <div className="flex items-center gap-2">
                <span className="w-3 h-2 bg-cyan-500/70 border border-cyan-400"></span>
                <span className="font-mono text-[#f0f0fa] uppercase">Match (True Positive: 82.4% IoU)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-2 bg-rose-600 border border-rose-400"></span>
                <span className="font-mono text-[#f0f0fa] uppercase">Missed Inundation (FN: 5.6 km²)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-2 bg-amber-600 border border-amber-400"></span>
                <span className="font-mono text-[#f0f0fa] uppercase">Over-predicted (FP: 4.8 km²)</span>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: ERROR ANALYSIS & RETRAINING ENGINE (5 cols on lg/xl) */}
        <div className="lg:col-span-5 space-y-4">
          {/* Spatial Error Diagnostic Card */}
          <div className="p-4 bg-[#0a0a0a] border border-[#3a3a3f] space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-sm font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-white" />
                Root-Cause Spatial Error Diagnostics
              </h3>
              <span className="font-mono text-[10px] text-[#888890] uppercase">
                2 DISCREPANCIES
              </span>
            </div>

            <div className="space-y-2 text-xs">
              <div className="p-3 bg-black border border-[#3a3a3f] space-y-1">
                <div className="flex items-center gap-1.5 font-bold uppercase text-white font-display text-xs">
                  <AlertOctagon className="w-3.5 h-3.5 text-white" />
                  <span>Embankment Breach at Spur km 12+400</span>
                </div>
                <p className="text-[11px] text-[#a0a0aa] leading-snug">
                  Baseline 1D hydrodynamic model failed to account for levee overtopping breach, causing 5.6 km² of under-predicted inundation across Prakashpur lowlands.
                </p>
                <span className="font-mono text-[10px] text-white block pt-0.5 uppercase">
                  Fix: Coupled shallow-water 2D mesh with breach trigger.
                </span>
              </div>

              <div className="p-3 bg-black border border-[#3a3a3f] space-y-1">
                <div className="flex items-center gap-1.5 font-bold uppercase text-white font-display text-xs">
                  <AlertTriangle className="w-3.5 h-3.5 text-white" />
                  <span>Micro-Topography Culvert Blockage in Ward 7</span>
                </div>
                <p className="text-[11px] text-[#a0a0aa] leading-snug">
                  Unmodeled road embankment culvert obstruction prevented backflow drainage, causing 4.8 km² false alarm discrepancy.
                </p>
                <span className="font-mono text-white text-[10px] block pt-0.5 uppercase">
                  Fix: Ingested high-resolution 5m DEM micro-drainage layer.
                </span>
              </div>
            </div>
          </div>

          {/* Retraining Pipeline Stepper Card */}
          <div className="p-4 bg-[#0a0a0a] border border-[#3a3a3f] space-y-3.5">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-micro uppercase tracking-wider text-[#888890] flex items-center gap-1">
                  <BrainCircuit className="w-3.5 h-3.5 text-white" />
                  Automated Closed-Loop Pipeline
                </span>
                <h3 className="font-display text-sm font-bold text-white uppercase tracking-wider mt-0.5">
                  Candidate Retraining: v1.3-RC Checkpoint
                </h3>
              </div>

              <button
                onClick={handleTriggerRetraining}
                disabled={retrainingState === 'RUNNING'}
                className="btn-ghost-pill-subtle text-[11px] py-1 px-3 flex items-center gap-1.5"
              >
                <RefreshCw className={`w-3 h-3 ${retrainingState === 'RUNNING' ? 'animate-spin' : ''}`} />
                <span>{retrainingState === 'RUNNING' ? 'TRAINING...' : 'RE-RUN RETRAIN'}</span>
              </button>
            </div>

            {/* Stepper Status Indicators */}
            <div className="grid grid-cols-5 gap-1.5 text-[9px] font-mono text-center pt-1 uppercase">
              <div className="p-1.5 border border-[#3a3a3f] bg-black text-[#888890]">
                1. INGEST
              </div>
              <div className="p-1.5 border border-[#3a3a3f] bg-black text-[#888890]">
                2. RE-WEIGHT
              </div>
              <div className="p-1.5 border border-[#3a3a3f] bg-black text-[#888890]">
                3. GRADIENTS
              </div>
              <div className="p-1.5 border border-[#3a3a3f] bg-black text-[#888890]">
                4. 10-FOLD CV
              </div>
              <div className="p-1.5 border border-white bg-black text-white font-bold">
                5. READY
              </div>
            </div>

            {/* Comparative Metric Bars (Baseline vs Candidate) */}
            <div className="space-y-2.5 pt-2 border-t border-[#3a3a3f] text-xs">
              {/* Metric 1: Inundation IoU */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-micro uppercase tracking-wider text-[#888890]">Inundation IoU:</span>
                  <span className="font-mono text-white font-bold">
                    73.1% &rarr; 82.4% (+9.3%)
                  </span>
                </div>
                <div className="w-full h-1.5 bg-black border border-[#3a3a3f] overflow-hidden flex">
                  <div className="bg-[#5a5a5f] h-full" style={{ width: '73.1%' }}></div>
                  <div className="bg-white h-full" style={{ width: '9.3%' }}></div>
                </div>
              </div>

              {/* Metric 2: Peak Crest Arrival Error */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-micro uppercase tracking-wider text-[#888890]">Peak Arrival Error:</span>
                  <span className="font-mono text-white font-bold">
                    &plusmn;45m &rarr; &plusmn;12m
                  </span>
                </div>
                <div className="w-full h-1.5 bg-black border border-[#3a3a3f] overflow-hidden flex">
                  <div className="bg-white h-full" style={{ width: '78%' }}></div>
                </div>
              </div>

              {/* Metric 3: Breach Sensitivity */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-micro uppercase tracking-wider text-[#888890]">Breach Sensitivity:</span>
                  <span className="font-mono text-white font-bold">
                    61% &rarr; 91% (+30%)
                  </span>
                </div>
                <div className="w-full h-1.5 bg-black border border-[#3a3a3f] overflow-hidden flex">
                  <div className="bg-[#5a5a5f] h-full" style={{ width: '61%' }}></div>
                  <div className="bg-white h-full" style={{ width: '30%' }}></div>
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="pt-3 border-t border-[#3a3a3f] space-y-2">
              <button
                onClick={() => setShowDeployModal(true)}
                className="btn-ghost-pill w-full flex items-center justify-center gap-2 py-2 text-xs"
              >
                <Rocket className="w-3.5 h-3.5" />
                <span>Deploy Candidate Model (v1.3-RC) to Production</span>
              </button>

              <button
                onClick={handleExportReport}
                className="btn-ghost-pill-subtle w-full flex items-center justify-center gap-2 py-2 text-xs"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export Full Verification Report (JSON Audit)</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* CONFIRMATION MODAL TO DEPLOY CANDIDATE MODEL */}
      {showDeployModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90">
          <div className="w-full max-w-md bg-[#0a0a0a] border border-white p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 border border-white bg-black text-white">
                <Rocket className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="font-display text-sm font-bold text-white uppercase tracking-wider">
                  Promote Candidate Checkpoint
                </h3>
                <p className="font-mono text-xs text-[#888890] uppercase">
                  FloodLens-LSTM-GNN v1.3-RC
                </p>
              </div>
            </div>

            <div className="p-3.5 bg-black border border-[#3a3a3f] text-xs space-y-1.5 text-[#a0a0aa]">
              <p>
                Promoting this candidate will update the operational multi-horizon inference engine across the <strong className="text-white">Prediction Centre</strong> and <strong className="text-white">Command Overview</strong>.
              </p>
              <div className="font-mono text-white font-bold pt-1">
                &bull; Verified IoU Gain: +9.3% (82.4% overall)
              </div>
              <div className="font-mono text-white font-bold">
                &bull; Embankment Breach Sensitivity: 91%
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowDeployModal(false)}
                className="btn-ghost-pill-subtle text-xs px-4 py-2"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDeploy}
                className="btn-ghost-pill text-xs px-4 py-2 flex items-center gap-1.5"
              >
                <Check className="w-3.5 h-3.5" />
                <span>Confirm Deployment</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Toast Feedback */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 p-4 bg-black border border-white text-white flex items-start gap-3 max-w-md shadow-none animate-in fade-in">
          <CheckCircle className="w-5 h-5 text-white flex-shrink-0 mt-0.5" />
          <div className="text-xs">
            <h4 className="font-display text-xs font-bold uppercase tracking-wider text-white">Model Engine Telemetry</h4>
            <p className="font-mono text-xs text-[#a0a0aa] mt-0.5">{toast}</p>
          </div>
        </div>
      )}
    </div>
  );
};

