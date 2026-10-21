import React, { useState, useEffect } from 'react';
import {
  AlertOctagon,
  CheckCircle,
  Clock,
  FileText,
  Hash,
  Languages,
  Send,
  X
} from 'lucide-react';
import { KOSHI_SHELTERS } from '../data/geospatialData';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';
import type { Alert, AlertSeverity, BenchmarkScene } from '../types';
import { DataStatusBadge } from './common/DataStatusBadge';
import { floodLensClient } from '../services/floodLensClient';

interface AlertDispatcherProps {
  currentScene: BenchmarkScene;
  activeAlerts: Alert[];
  onBroadcastAlert: (newAlert: Alert) => void;
  onCancelAlert: (alertId: string) => void;
  initialPayload?: {
    horizon?: string;
    threatLevel?: string;
    population?: number;
    wards?: string[];
  } | null;
}

// Preset Geofences for Koshi Basin
const TARGET_GEOFENCES = [
  {
    id: 'sunsari-sec3',
    name: 'Sunsari Floodplain Sector 3 (Prakashpur Reach)',
    estimatedPopulation: 14200,
    areaKm2: 42.5,
    polygon: [
      [26.78, 87.16],
      [26.72, 87.19],
      [26.65, 87.14],
      [26.58, 87.08],
      [26.53, 87.02],
      [26.58, 86.96],
      [26.67, 87.02],
      [26.75, 87.09],
    ] as [number, number][],
  },
  {
    id: 'koshi-embankment',
    name: 'Koshi Embankment Reach & Gobargadha Island',
    estimatedPopulation: 8900,
    areaKm2: 31.8,
    polygon: [
      [26.68, 87.02],
      [26.62, 87.04],
      [26.55, 86.98],
      [26.50, 86.91],
      [26.56, 86.87],
      [26.64, 86.91],
    ] as [number, number][],
  },
  {
    id: 'belka-confluence',
    name: 'Belka Confluence Corridor (Wards 8 & 9)',
    estimatedPopulation: 6400,
    areaKm2: 24.2,
    polygon: [
      [26.88, 87.12],
      [26.83, 87.17],
      [26.76, 87.11],
      [26.80, 87.04],
      [26.86, 87.07],
    ] as [number, number][],
  },
];

// Preset Bilingual Templates
const PRESET_TEMPLATES = [
  {
    id: 'evac-order',
    name: 'Immediate Evacuation Advisory (Rising Surge)',
    severity: 'EMERGENCY' as AlertSeverity,
    headline_en: 'EMERGENCY ADVISORY: Immediate Koshi River Crest Overbank Threat',
    headline_ne: 'अति जरुरी सूचना: कोशी नदीको बहाव तीव्र गतिमा बढ्दै, तत्काल सुरक्षित उच्च स्थानमा जानुहोस्',
    message_en: 'River discharge has exceeded critical danger thresholds (Chatara > 8.18m). All residents in low-lying riverside wards are advised to move to designated high ground shelters immediately. Avoid inundated roads.',
    message_ne: 'चतारा जलमापन केन्द्रमा पानीको सतह खतराको तह (८.०० मिटर) नाघेको छ। तटीय वडाका बासिन्दाहरू तुरुन्त तोकिएको सुरक्षित आश्रयस्थलमा सर्नुहोस्। डुबान भएका सडक पार नगर्नुहोस्।',
  },
  {
    id: 'boil-water',
    name: 'Drinking Water Contamination Advisory',
    severity: 'WARNING' as AlertSeverity,
    headline_en: 'HEALTH ADVISORY: Drinking Water Tube-Wells Submerged',
    headline_ne: 'स्वास्थ्य सतर्कता: खानेपानीको मुहान दूषित भएको सूचना',
    message_en: 'Floodwaters have inundated municipal tube-wells and local distribution points. Boil all drinking water or use chlorine purification tablets supplied at relief checkpoints.',
    message_ne: 'बाढीको पानीले खानेपानीका मुहानहरू दूषित बनाएकाले पिउने पानी अनिवार्य रूपमा उमालेर वा शुद्धीकरण गरेर मात्र प्रयोग गर्नुहोस्।',
  },
  {
    id: 'shelter-route',
    name: 'Evacuation Corridor Guidance Notice',
    severity: 'ADVISORY' as AlertSeverity,
    headline_en: 'CIVIL NOTICE: Verified High Ground Corridor Open to Inaruwa Safe Hub',
    headline_ne: 'यातायात सूचना: इनरुवा सुरक्षित आश्रयस्थल जाने बाटो खुला',
    message_en: 'The elevated secondary bypass from Prakashpur Ward 2 towards Inaruwa Municipality is currently dry and monitored by civil protection volunteers. Proceed orderly before nightfall.',
    message_ne: 'प्रकाशपुर वडा २ बाट इनरुवा नगरपालिका जाने सुरक्षित बाटो खुला छ। सुरक्षित रूपमा तोकिएको आश्रयस्थलमा जानुहोस्।',
  },
];

export const AlertDispatcher: React.FC<AlertDispatcherProps> = ({
  currentScene,
  activeAlerts,
  onBroadcastAlert,
  onCancelAlert,
  initialPayload,
}) => {
  // Target Zone selection
  const [selectedZoneId, setSelectedZoneId] = useState(TARGET_GEOFENCES[0].id);

  // Severity selector
  const [severity, setSeverity] = useState<AlertSeverity>('EMERGENCY');

  // Multi-channel simulation checklist
  const [channels, setChannels] = useState({
    push: true,
    sms: true,
    siren: true,
    cap: true,
  });

  // Bilingual Content Editor (English & Nepali)
  const [headlineEn, setHeadlineEn] = useState(PRESET_TEMPLATES[0].headline_en);
  const [headlineNe, setHeadlineNe] = useState(PRESET_TEMPLATES[0].headline_ne);
  const [messageEn, setMessageEn] = useState(PRESET_TEMPLATES[0].message_en);
  const [messageNe, setMessageNe] = useState(PRESET_TEMPLATES[0].message_ne);

  // Language Preview toggle
  const [previewLanguage, setPreviewLanguage] = useState<'EN' | 'NE'>('EN');

  // Shelter Attachment
  const [selectedShelter, setSelectedShelter] = useState(KOSHI_SHELTERS[0].name);

  // Confirmation Modal state
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  // Notification Toast state
  const [toast, setToast] = useState<string | null>(null);

  // Client Data Status state
  const [dataStatus, setDataStatus] = useState<'live' | 'cached' | 'error'>('cached');

  // Handle incoming pre-filled payload from PredictionCentre
  useEffect(() => {
    if (initialPayload) {
      if (initialPayload.threatLevel?.includes('Level 4') || initialPayload.threatLevel?.includes('Severe')) {
        setSeverity('EMERGENCY');
      } else {
        setSeverity('WARNING');
      }
      setHeadlineEn(`FLOOD CREST ADVISORY (+${initialPayload.horizon || '3h'} Horizon)`);
      setMessageEn(
        `Hydrological models predict elevated overbank surge affecting ~${
          initialPayload.population ? initialPayload.population.toLocaleString() : '18,420'
        } citizens in ${initialPayload.wards?.join(', ') || 'Prakashpur & low-lying reaches'}. Move to designated high ground.`
      );
      setToast(`Pre-filled technical advisory loaded from Prediction Centre (+${initialPayload.horizon || '3h'})`);
      setTimeout(() => setToast(null), 4000);
    }
  }, [initialPayload]);

  const activeZone = TARGET_GEOFENCES.find((z) => z.id === selectedZoneId) || TARGET_GEOFENCES[0];

  const handleApplyTemplate = (tmpl: typeof PRESET_TEMPLATES[0]) => {
    setSeverity(tmpl.severity);
    setHeadlineEn(tmpl.headline_en);
    setHeadlineNe(tmpl.headline_ne);
    setMessageEn(tmpl.message_en);
    setMessageNe(tmpl.message_ne);
    setToast(`Applied template: "${tmpl.name}"`);
    setTimeout(() => setToast(null), 3000);
  };

  const handleToggleChannel = (key: keyof typeof channels) => {
    setChannels((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const generateSha256Audit = () => {
    const chars = '0123456789abcdef';
    let hash = '';
    for (let i = 0; i < 32; i++) {
      hash += chars[Math.floor(Math.random() * chars.length)];
    }
    return `SHA-256: ${hash}`;
  };

  const handleConfirmBroadcast = async () => {
    const selectedChannelList: string[] = [];
    if (channels.push) selectedChannelList.push('Citizen Android Push [Simulated Drill]');
    if (channels.sms) selectedChannelList.push('Emergency Cell Broadcast SMS [Simulated Drill]');
    if (channels.siren) selectedChannelList.push('Community Siren Array [Simulated Tone]');
    if (channels.cap) selectedChannelList.push('CAP v1.2 Relay [Audit Logged]');

    // Transmit through unified service adapter
    const res = await floodLensClient.postSimulatedAlert({
      geofence_id: activeZone.id,
      severity: severity,
      channels: selectedChannelList,
      headline: headlineEn,
      message: messageEn,
      headline_ne: headlineNe,
      message_ne: messageNe,
      issued_by: 'Authorized EOC Duty Commander (Drill Simulation)',
      simulated_reach: activeZone.estimatedPopulation,
    });

    if (res.status) {
      setDataStatus(res.status);
    }

    const auditHash = res.data?.audit_hash || generateSha256Audit();

    const newAlert: Alert = {
      id: res.data?.id || `ALT-KOSHI-2026-0${activeAlerts.length + 5}`,
      code: `${severity === 'EMERGENCY' ? 'RED-ALERT' : severity === 'WARNING' ? 'AMBER-WATCH' : 'YELLOW-ADVISORY'}-0${activeAlerts.length + 5}`,
      headline: headlineEn,
      headline_ne: headlineNe,
      description: messageEn,
      description_ne: messageNe,
      severity: severity,
      risk_level: severity === 'EMERGENCY' ? 'EXTREME' : severity === 'WARNING' ? 'HIGH' : 'MODERATE',
      geofence: activeZone.name,
      population_affected: activeZone.estimatedPopulation,
      status: 'DISPATCHED',
      issued_at: new Date().toISOString(),
      dispatched_at: 'Just now (Simulated Drill)',
      expires_at: new Date(Date.now() + 6 * 3600 * 1000).toISOString(),
      channels: selectedChannelList,
      approved_by: 'Authorized EOC Duty Commander (Drill Simulation)',
      evacuation_notice: severity === 'EMERGENCY',
      safe_shelter: selectedShelter,
      read_rate: 88,
      reach_count: activeZone.estimatedPopulation,
      audit_hash: auditHash,
      is_drill_simulation: true,
    };

    onBroadcastAlert(newAlert);
    setShowConfirmModal(false);
    setToast('Simulated Broadcast Logged (Audit Record Created)');
    setTimeout(() => setToast(null), 4000);
  };

  const getSeverityPillColor = (sev: AlertSeverity) => {
    switch (sev) {
      case 'EMERGENCY':
        return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
      case 'WARNING':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
      default:
        return 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40';
    }
  };

  return (
    <div className="space-y-4">
      {/* Permanent High-Visibility Mandatory Simulation & Drill Banner */}
      <div className="p-3.5 rounded-lg bg-amber-500/15 border-2 border-amber-500/80 text-amber-200 text-xs font-mono font-bold tracking-wider uppercase flex items-center justify-between gap-3 shadow-[0_0_24px_rgba(245,158,11,0.25)] flex-wrap">
        <div className="flex items-center gap-2.5">
          <AlertOctagon className="w-5 h-5 text-amber-400 animate-pulse flex-shrink-0" />
          <span>[SIMULATION &amp; DRILL ENVIRONMENT — NO ACTUAL BROADCAST TRANSMITTED]</span>
        </div>
        <span className="px-2.5 py-1 rounded bg-black/60 border border-amber-400/50 text-[10px] text-amber-300">
          EOC DRILL &bull; AUDIT LOGGED
        </span>
      </div>

      {/* Top Header */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded bg-rose-500/20 border border-rose-500/40 text-rose-400">
            <Send className="w-4 h-4 text-rose-400" />
          </div>
          <div>
            <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
              Alert Dispatcher // Simulation &amp; Drill Authorization Interface
              <span className="px-2 py-0.5 rounded-full bg-[#38bdf8]/15 border border-[#38bdf8]/40 text-[#38bdf8] text-[9px] font-mono font-bold tracking-wider">
                CAP V1.2 PROTOCOL
              </span>
            </h1>
            <p className="font-mono text-[10px] text-[#38bdf8] uppercase tracking-wider mt-0.5 font-semibold">
              AUTHORITY WARNING STUDIO // {currentScene.name} ({currentScene.district})
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <DataStatusBadge status={dataStatus} />
          <span className="px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 font-mono text-xs font-bold flex items-center gap-1.5 shadow-[0_0_10px_rgba(16,185,129,0.2)]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            DRILL AUDIT READY
          </span>
        </div>
      </div>

      {/* 2-COLUMN LAYOUT: CONFIGURATION STUDIO + 3D GEOSPATIAL MAP */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* LEFT COLUMN: ALERT CREATION STUDIO (6 cols on lg/xl) */}
        <div className="lg:col-span-6 space-y-3.5">
          <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3.5 font-mono text-xs">
            {/* Quick Templates Bar */}
            <div className="space-y-1.5">
              <span className="font-micro text-[10px] uppercase tracking-[0.96px] text-slate-400 flex items-center gap-1 font-bold">
                <FileText className="w-3.5 h-3.5 text-white" />
                PRESET WARNING TEMPLATES:
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-1.5">
                {PRESET_TEMPLATES.map((tmpl) => (
                  <button
                    key={tmpl.id}
                    onClick={() => handleApplyTemplate(tmpl)}
                    className="p-2 bg-black/60 hover:bg-[#0c1d38] text-left border border-[#1e3a5f] hover:border-sky-400 transition-colors rounded cursor-pointer"
                  >
                    <span className="text-[10px] font-bold text-white block uppercase truncate">
                      {tmpl.name}
                    </span>
                    <span
                      className={`text-[9px] font-bold uppercase ${
                        tmpl.severity === 'EMERGENCY'
                          ? 'text-rose-400'
                          : tmpl.severity === 'WARNING'
                          ? 'text-amber-400'
                          : 'text-white'
                      }`}
                    >
                      {tmpl.severity}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Target Geofence Selector */}
            <div className="space-y-1">
              <label className="font-micro text-[10px] uppercase tracking-[0.96px] text-slate-400 block font-bold">
                TARGET FLOODPLAIN SECTOR GEOFENCE:
              </label>
              <select
                value={selectedZoneId}
                onChange={(e) => setSelectedZoneId(e.target.value)}
                className="w-full bg-black/60 border border-[#1e3a5f] rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-sky-400 uppercase cursor-pointer"
              >
                {TARGET_GEOFENCES.map((zone) => (
                  <option key={zone.id} value={zone.id}>
                    {zone.name.toUpperCase()} (~{zone.estimatedPopulation.toLocaleString()} POPULATION • {zone.areaKm2} KM²)
                  </option>
                ))}
              </select>
            </div>

            {/* Severity Level Selector */}
            <div className="space-y-1">
              <label className="font-micro text-[10px] uppercase tracking-[0.96px] text-slate-400 block font-bold">
                ALERT SEVERITY TIER:
              </label>
              <div className="grid grid-cols-3 gap-2">
                {(['ADVISORY', 'WATCH', 'EMERGENCY'] as const).map((sev) => {
                  const isSelected = severity === sev;
                  return (
                    <button
                      key={sev}
                      onClick={() => setSeverity(sev)}
                      className={`py-2 px-3 text-center text-xs font-bold uppercase rounded border transition-all cursor-pointer ${
                        isSelected
                          ? sev === 'EMERGENCY'
                            ? 'bg-rose-600 text-white border-rose-400 shadow-[0_0_12px_rgba(244,63,94,0.4)]'
                            : sev === 'WATCH'
                            ? 'bg-amber-600 text-white border-amber-400 shadow-[0_0_12px_rgba(245,158,11,0.4)]'
                            : 'bg-sky-600 text-white border-sky-400 shadow-[0_0_12px_rgba(14,165,233,0.4)]'
                          : 'bg-black/60 border-[#1e3a5f] text-slate-400 hover:text-white'
                      }`}
                    >
                      {sev}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Multi-Channel Simulation Checklist */}
            <div className="space-y-1.5 pt-1">
              <span className="font-micro text-[10px] uppercase tracking-[0.96px] text-slate-400 block font-bold">
                DISPATCH CHANNELS &bull; [SIMULATED DRILL OUTPUT]:
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                <label className="flex items-center gap-2 p-2 bg-black/60 border border-[#1e3a5f] rounded cursor-pointer hover:border-slate-400">
                  <input
                    type="checkbox"
                    checked={channels.push}
                    onChange={() => handleToggleChannel('push')}
                    className="accent-sky-500"
                  />
                  <span>Citizen Android Push (Simulated)</span>
                </label>

                <label className="flex items-center gap-2 p-2 bg-black/60 border border-[#1e3a5f] rounded cursor-pointer hover:border-slate-400">
                  <input
                    type="checkbox"
                    checked={channels.sms}
                    onChange={() => handleToggleChannel('sms')}
                    className="accent-sky-500"
                  />
                  <span>Cell Broadcast SMS (Simulated)</span>
                </label>

                <label className="flex items-center gap-2 p-2 bg-black/60 border border-[#1e3a5f] rounded cursor-pointer hover:border-slate-400">
                  <input
                    type="checkbox"
                    checked={channels.siren}
                    onChange={() => handleToggleChannel('siren')}
                    className="accent-sky-500"
                  />
                  <span>Community Siren Relay (Drill)</span>
                </label>

                <label className="flex items-center gap-2 p-2 bg-black/60 border border-[#1e3a5f] rounded cursor-pointer hover:border-slate-400">
                  <input
                    type="checkbox"
                    checked={channels.cap}
                    onChange={() => handleToggleChannel('cap')}
                    className="accent-sky-500"
                  />
                  <span>CAP v1.2 Relay (Audit Trail)</span>
                </label>
              </div>
            </div>

            {/* Bilingual Message Studio: English & Nepali */}
            <div className="space-y-2 pt-2 border-t border-[#1e3a5f]">
              <div className="flex items-center justify-between">
                <span className="font-micro text-[10px] uppercase tracking-[0.96px] text-slate-400 block font-bold flex items-center gap-1">
                  <Languages className="w-3.5 h-3.5 text-sky-400" />
                  BILINGUAL MESSAGE STUDIO (ENGLISH &amp; नेपाली):
                </span>
                <div className="flex gap-1 text-[10px]">
                  <button
                    onClick={() => setPreviewLanguage('EN')}
                    className={`px-2 py-0.5 rounded cursor-pointer ${
                      previewLanguage === 'EN' ? 'bg-sky-600 text-white font-bold' : 'text-slate-400'
                    }`}
                  >
                    EN
                  </button>
                  <button
                    onClick={() => setPreviewLanguage('NE')}
                    className={`px-2 py-0.5 rounded cursor-pointer ${
                      previewLanguage === 'NE' ? 'bg-sky-600 text-white font-bold' : 'text-slate-400'
                    }`}
                  >
                    नेपाली
                  </button>
                </div>
              </div>

              {previewLanguage === 'EN' ? (
                <div className="space-y-2">
                  <input
                    type="text"
                    value={headlineEn}
                    onChange={(e) => setHeadlineEn(e.target.value)}
                    placeholder="Headline in English..."
                    className="w-full bg-black/60 border border-[#1e3a5f] rounded p-2 text-xs text-white focus:outline-none focus:border-sky-400 uppercase"
                  />
                  <textarea
                    rows={3}
                    value={messageEn}
                    onChange={(e) => setMessageEn(e.target.value)}
                    placeholder="Message text in English..."
                    className="w-full bg-black/60 border border-[#1e3a5f] rounded p-2 text-xs text-white focus:outline-none focus:border-sky-400"
                  />
                </div>
              ) : (
                <div className="space-y-2">
                  <input
                    type="text"
                    value={headlineNe}
                    onChange={(e) => setHeadlineNe(e.target.value)}
                    placeholder="Headline in Nepali..."
                    className="w-full bg-black/60 border border-[#1e3a5f] rounded p-2 text-xs text-white focus:outline-none focus:border-sky-400"
                  />
                  <textarea
                    rows={3}
                    value={messageNe}
                    onChange={(e) => setMessageNe(e.target.value)}
                    placeholder="Message text in Nepali..."
                    className="w-full bg-black/60 border border-[#1e3a5f] rounded p-2 text-xs text-white focus:outline-none focus:border-sky-400"
                  />
                </div>
              )}
            </div>

            {/* Designated Shelter Attachment */}
            <div className="space-y-1 pt-1">
              <label className="font-micro text-[10px] uppercase text-slate-400 block font-bold">
                DESIGNATED EVACUATION SHELTER ATTACHMENT:
              </label>
              <select
                value={selectedShelter}
                onChange={(e) => setSelectedShelter(e.target.value)}
                className="w-full bg-black/60 border border-[#1e3a5f] rounded p-2 text-xs text-white uppercase focus:outline-none focus:border-sky-400"
              >
                {KOSHI_SHELTERS.map((s) => (
                  <option key={s.id} value={s.name}>
                    {s.name} ({s.elevationMsl}m MSL &bull; {s.capacity} souls cap)
                  </option>
                ))}
              </select>
            </div>

            {/* Trigger Button */}
            <div className="pt-2">
              <button
                onClick={() => setShowConfirmModal(true)}
                className="w-full py-2.5 px-4 rounded-full bg-gradient-to-r from-rose-600 via-red-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white font-mono font-bold text-xs uppercase tracking-wider border border-rose-400 shadow-[0_0_15px_rgba(244,63,94,0.4)] transition-all cursor-pointer flex items-center justify-center gap-2"
              >
                <Send className="w-3.5 h-3.5" />
                <span>AUTHORIZE SIMULATION DRILL DISPATCH</span>
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: 3D MAP & RECENT DISPATCH AUDIT LOG (6 cols) */}
        <div className="lg:col-span-6 space-y-3.5">
          {/* 3D Map Visualizer with Target Geofence */}
          <div className="space-y-1">
            <div className="flex items-center justify-between px-1">
              <span className="font-micro text-[10px] uppercase tracking-[1.2px] text-[#38bdf8] font-bold">
                TARGET GEOFENCE BOUNDS // {activeZone.name}
              </span>
              <span className="font-mono text-[10px] text-slate-400">
                EST. POPULATION: ~{activeZone.estimatedPopulation.toLocaleString()}
              </span>
            </div>

            <GeospatialTerrainMap
              center={currentScene.center || [87.05, 26.65]}
              zoom={11}
              pitch={55}
              bearing={-15}
              activeHorizon="3h"
              showInundation={true}
              showForecast={true}
              showGauges={true}
              showInfrastructure={true}
              showShelters={true}
              height="340px"
            />
          </div>

          {/* Audit Metrics & Recent Dispatched Bulletins Table */}
          <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between pb-2 border-b border-[#1e3a5f]">
              <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-white" />
                SIMULATION DISPATCH AUDIT LOG
              </h3>
              <span className="text-[10px] text-emerald-400 font-bold">
                SHA-256 AUDIT VERIFIED
              </span>
            </div>

            <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
              {activeAlerts.map((alert) => (
                <div key={alert.id} className="p-3 bg-black/60 border border-[#1e3a5f] rounded space-y-1.5">
                  <div className="flex items-start justify-between gap-1">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${getSeverityPillColor(alert.severity)}`}>
                          {alert.severity}
                        </span>
                        <h4 className="font-bold text-white uppercase text-[11px] truncate max-w-[280px]">
                          {alert.headline}
                        </h4>
                      </div>
                      <span className="text-[10px] text-slate-400 block mt-0.5">
                        {alert.dispatched_at} &bull; Geofence: {alert.geofence}
                      </span>
                    </div>

                    <button
                      onClick={() => onCancelAlert(alert.id)}
                      className="px-2 py-0.5 rounded text-[9px] border border-rose-500/50 text-rose-300 hover:bg-rose-500/20 cursor-pointer"
                    >
                      SUPERSEDE
                    </button>
                  </div>

                  <div className="flex items-center justify-between pt-1 border-t border-[#1e3a5f]/60 text-[10px]">
                    <span className="text-slate-300">
                      Estimated Population in Geofence: ~{alert.population_affected.toLocaleString()} (Census Overlay)
                    </span>
                    <span className="text-sky-300 flex items-center gap-1 font-mono">
                      <Hash className="w-3 h-3 text-sky-400" />
                      {alert.audit_hash || 'SHA-256 Verified'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Confirmation Modal to Prevent Unintentional Dispatch */}
      {showConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-lg rounded-lg bg-[#071326] border border-[#1e3a5f] p-6 shadow-2xl space-y-4 font-mono text-white">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded bg-amber-500/20 border border-amber-500/40 text-amber-400">
                  <AlertOctagon className="w-5 h-5 text-amber-400" />
                </div>
                <div>
                  <h3 className="font-display text-sm font-bold text-white uppercase tracking-wider">
                    SIMULATION DRILL AUTHORIZATION
                  </h3>
                  <p className="font-micro text-[10px] text-slate-400 uppercase">
                    EOC DECISION-SUPPORT AUDIT RECORD
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowConfirmModal(false)}
                className="text-slate-400 hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3.5 bg-black/60 border border-[#1e3a5f] rounded text-xs space-y-2">
              <div>
                <span className="text-[10px] text-slate-400 uppercase block font-bold">TARGET SECTOR:</span>
                <span className="font-bold text-white uppercase">{activeZone.name}</span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 uppercase block font-bold">ESTIMATED POPULATION:</span>
                <span className="text-white font-bold">
                  ~{activeZone.estimatedPopulation.toLocaleString()} CITIZENS WITHIN GEOFENCE
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 uppercase block font-bold">PAYLOAD HEADLINE:</span>
                <span className="text-sky-300">{headlineEn}</span>
              </div>
              <div className="pt-1 text-[10px] text-amber-300">
                &bull; Simulation Dispatch Status: Recorded in EOC Audit Log
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowConfirmModal(false)}
                className="px-4 py-1.5 rounded-full border border-[#1e3a5f] hover:bg-white/10 text-xs text-slate-300 transition-colors cursor-pointer"
              >
                CANCEL &amp; EDIT
              </button>
              <button
                onClick={handleConfirmBroadcast}
                className="px-5 py-1.5 rounded-full bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-bold font-mono tracking-wider uppercase border border-rose-400 shadow-[0_0_12px_rgba(244,63,94,0.4)] transition-all cursor-pointer flex items-center gap-1.5"
              >
                <Send className="w-3.5 h-3.5" />
                <span>CONFIRM SIMULATION LOG</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Toast Notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 p-4 rounded-lg bg-[#071326] border border-emerald-400 text-white shadow-2xl flex items-center gap-2 text-xs font-mono animate-in slide-in-from-bottom-2">
          <CheckCircle className="w-4 h-4 text-emerald-400" />
          <span>{toast}</span>
        </div>
      )}
    </div>
  );
};
