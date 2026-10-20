import React, { useState, useEffect } from 'react';
import {
  MapContainer,
  Polygon,
  TileLayer,
  Tooltip,
} from 'react-leaflet';
import {
  AlertOctagon,
  BellRing,
  CheckCircle,
  Clock,
  FileText,
  Languages,
  MapPin,
  MessageSquare,
  Radio,
  Send,
  Smartphone,
  Volume2,
  X,
} from 'lucide-react';
import { KOSHI_SHELTERS } from '../data/geospatialData';
import type { Alert, AlertSeverity, BenchmarkScene } from '../types';

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
    name: 'Sunsari Floodplain - Sector 3 (Prakashpur Reach)',
    estimatedDevices: 14250,
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
    id: 'koshi-west-embankment',
    name: 'Koshi Western Embankment & Gobargadha Island',
    estimatedDevices: 8900,
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
    id: 'belka-wards',
    name: 'Belka Confluence Corridor (Wards 8 & 9)',
    estimatedDevices: 6400,
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

// Preset Templates
const PRESET_TEMPLATES = [
  {
    id: 'evac-order',
    name: 'Immediate Evacuation Order (Rising Surge)',
    severity: 'EMERGENCY' as AlertSeverity,
    headline_en: 'EMERGENCY EVACUATION ORDER: Immediate Koshi River Breach Hazard',
    headline_ne: 'अति जरुरी सूचना: कोशी तटबन्ध कटानको उच्च जोखिम, तत्काल सुरक्षित स्थानमा जानुहोस्',
    message_en: 'River discharge has exceeded critical danger thresholds. All residents in low-lying riverside wards must immediately evacuate to designated safe shelters. Do not attempt to cross flooded roadways.',
    message_ne: 'चतारा जलमापन केन्द्रमा बहाव खतराको तह नाघेको छ। सुनसरी र सप्तरीका तटीय वडाका बासिन्दाहरू तुरुन्त उच्च सुरक्षित स्थानमा सर्नुहोस्। डुबान भएका सडक पार नगर्नुहोस्।',
  },
  {
    id: 'boil-water',
    name: 'Boil Water & Seek Higher Ground',
    severity: 'WARNING' as AlertSeverity,
    headline_en: 'HEALTH ADVISORY: Drinking Water Source Contamination & Inundation',
    headline_ne: 'स्वास्थ्य सतर्कता: खानेपानीको स्रोत दूषित र डुबान जोखिम',
    message_en: 'Floodwaters have inundated municipal tube-wells and local pipelines. Boil all drinking water or use chlorine purification tablets provided at relief stations.',
    message_ne: 'बाढीको पानीले खानेपानीका मुहानहरू दूषित बनाएकाले पिउने पानी अनिवार्य रूपमा उमालेर वा शुद्धीकरण गरेर मात्र प्रयोग गर्नुहोस्।',
  },
  {
    id: 'shelter-route',
    name: 'Shelter Route Available',
    severity: 'ADVISORY' as AlertSeverity,
    headline_en: 'TRAFFIC NOTICE: Verified Evacuation Corridor Open to Inaruwa Safe Hub',
    headline_ne: 'यातायात सूचना: इनरुवा सुरक्षित आश्रयस्थल जाने बाटो खुला',
    message_en: 'The elevated secondary bypass from Prakashpur Ward 2 towards Inaruwa Municipality is currently dry and guarded by civil defense personnel. Move safely before nightfall.',
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

  // Channels Checklist
  const [channels, setChannels] = useState({
    push: true,
    sms: true,
    siren: true,
    whatsapp: false,
  });

  // Content Editor (English & Nepali)
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

  // Handle incoming pre-filled payload from PredictionCentre
  useEffect(() => {
    if (initialPayload) {
      if (initialPayload.threatLevel?.includes('Level 4') || initialPayload.threatLevel?.includes('Severe')) {
        setSeverity('EMERGENCY');
      } else {
        setSeverity('WARNING');
      }
      setHeadlineEn(`CRITICAL FLOOD WARNING (+${initialPayload.horizon || '3h'} Forecast Horizon)`);
      setMessageEn(
        `Hydrological forecast models indicate imminent overbank surge affecting ${
          initialPayload.population ? initialPayload.population.toLocaleString() : '18,420'
        } citizens in ${initialPayload.wards?.join(', ') || 'Prakashpur & low-lying wards'}. Seek higher ground immediately.`
      );
      setToast(`Pre-filled advisory template loaded from Prediction Centre (+${initialPayload.horizon || '3h'})`);
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

  const handleConfirmBroadcast = () => {
    const selectedChannelList: string[] = [];
    if (channels.push) selectedChannelList.push('Citizen Android Push (High-Pri)');
    if (channels.sms) selectedChannelList.push('Emergency Cell Broadcast (SMS)');
    if (channels.siren) selectedChannelList.push('Local Siren / PA Array');
    if (channels.whatsapp) selectedChannelList.push('Civil Defense WhatsApp API');

    const newAlert: Alert = {
      id: `ALT-KOSHI-2026-0${activeAlerts.length + 5}`,
      code: `${severity === 'EMERGENCY' ? 'RED-ALERT' : severity === 'WARNING' ? 'AMBER-WATCH' : 'YELLOW-ADVISORY'}-0${activeAlerts.length + 5}`,
      headline: headlineEn,
      headline_ne: headlineNe,
      description: messageEn,
      description_ne: messageNe,
      severity: severity,
      risk_level: severity === 'EMERGENCY' ? 'EXTREME' : severity === 'WARNING' ? 'HIGH' : 'MODERATE',
      geofence: activeZone.name,
      population_affected: activeZone.estimatedDevices,
      status: 'DISPATCHED',
      issued_at: new Date().toISOString(),
      dispatched_at: 'Just now (Live Broadcast)',
      expires_at: new Date(Date.now() + 6 * 3600 * 1000).toISOString(),
      channels: selectedChannelList,
      approved_by: 'Authorized EOC Duty Commander',
      evacuation_notice: severity === 'EMERGENCY',
      safe_shelter: selectedShelter,
      read_rate: 91,
      reach_count: activeZone.estimatedDevices,
    };

    onBroadcastAlert(newAlert);
    setShowConfirmModal(false);
    setToast(`Broadcast successfully transmitted to ${activeZone.estimatedDevices.toLocaleString()} recipients!`);
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
      {/* Top Header */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded bg-rose-500/20 border border-rose-500/40 text-rose-400">
            <Send className="w-4 h-4 text-rose-400" />
          </div>
          <div>
            <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
              Alert Dispatcher // Emergency Geofence Studio
              <span className="px-2 py-0.5 rounded-full bg-[#38bdf8]/15 border border-[#38bdf8]/40 text-[#38bdf8] text-[9px] font-mono font-bold tracking-wider">
                CAP V1.2 PROTOCOL
              </span>
            </h1>
            <p className="font-mono text-[10px] text-[#38bdf8] uppercase tracking-wider mt-0.5 font-semibold">
              CIVIL BROADCASTING SUITE // {currentScene.name} ({currentScene.district})
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 font-mono text-xs font-bold flex items-center gap-1.5 shadow-[0_0_10px_rgba(16,185,129,0.2)]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            GATEWAYS ARMED
          </span>
        </div>
      </div>

      {/* 2-COLUMN LAYOUT: CONFIGURATION STUDIO + GEOGRAPHIC TARGETING MAP */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-start">
        {/* LEFT COLUMN: ALERT CREATION STUDIO (6 cols on lg/xl) */}
        <div className="lg:col-span-6 space-y-3.5">
          <div className="p-4 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] shadow-none space-y-3.5">
            {/* Quick Templates Bar */}
            <div className="space-y-1.5">
              <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1">
                <FileText className="w-3 h-3 text-white" />
                PRESET INCIDENT TEMPLATES:
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-1.5 font-mono">
                {PRESET_TEMPLATES.map((tmpl) => (
                  <button
                    key={tmpl.id}
                    onClick={() => handleApplyTemplate(tmpl)}
                    className="p-2 bg-black hover:bg-[#141416] text-left border border-[#3a3a3f] hover:border-white transition-colors"
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
            <div className="space-y-1 font-mono">
              <label className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] block">
                TARGETED FLOOD SECTOR GEOFENCE:
              </label>
              <select
                value={selectedZoneId}
                onChange={(e) => setSelectedZoneId(e.target.value)}
                className="w-full bg-black border border-[#3a3a3f] rounded-none px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-white uppercase"
              >
                {TARGET_GEOFENCES.map((zone) => (
                  <option key={zone.id} value={zone.id}>
                    {zone.name.toUpperCase()} ({zone.estimatedDevices.toLocaleString()} DEVICES • {zone.areaKm2} KM²)
                  </option>
                ))}
              </select>
            </div>

            {/* Severity Level Selector */}
            <div className="space-y-1 font-mono">
              <label className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] block">
                ALERT SEVERITY TIER:
              </label>
              <div className="grid grid-cols-3 gap-2">
                {(['ADVISORY', 'WATCH', 'EMERGENCY'] as const).map((sev) => {
                  const isSelected = severity === sev;
                  return (
                    <button
                      key={sev}
                      onClick={() => setSeverity(sev)}
                      className={`py-1.5 px-3 rounded-none text-xs font-mono uppercase font-bold transition-all border ${
                        isSelected
                          ? 'bg-white text-black border-white'
                          : 'bg-black text-[#5a5a5f] border-[#3a3a3f] hover:text-white hover:border-white'
                      }`}
                    >
                      {sev === 'EMERGENCY' ? 'WARNING / EVAC' : sev}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Communication Channels Checklist */}
            <div className="space-y-1 font-mono">
              <label className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] block">
                PROPAGATION GATEWAYS:
              </label>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => handleToggleChannel('push')}
                  className={`p-2 rounded-lg border text-left flex items-center justify-between transition-colors ${
                    channels.push
                      ? 'bg-cyan-950/60 border-cyan-500/50 text-cyan-200'
                      : 'bg-slate-950 border-slate-800 text-slate-500'
                  }`}
                >
                  <span className="flex items-center gap-1.5 font-medium">
                    <Smartphone className="w-3.5 h-3.5 text-cyan-400" />
                    Citizen App Push
                  </span>
                  <span className="text-[10px] font-mono font-bold">
                    {channels.push ? 'ON' : 'OFF'}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => handleToggleChannel('sms')}
                  className={`p-2 rounded-lg border text-left flex items-center justify-between transition-colors ${
                    channels.sms
                      ? 'bg-cyan-950/60 border-cyan-500/50 text-cyan-200'
                      : 'bg-slate-950 border-slate-800 text-slate-500'
                  }`}
                >
                  <span className="flex items-center gap-1.5 font-medium">
                    <Radio className="w-3.5 h-3.5 text-amber-400" />
                    Emergency SMS (Cell)
                  </span>
                  <span className="text-[10px] font-mono font-bold">
                    {channels.sms ? 'ON' : 'OFF'}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => handleToggleChannel('siren')}
                  className={`p-2 rounded-lg border text-left flex items-center justify-between transition-colors ${
                    channels.siren
                      ? 'bg-rose-950/60 border-rose-500/50 text-rose-200'
                      : 'bg-slate-950 border-slate-800 text-slate-500'
                  }`}
                >
                  <span className="flex items-center gap-1.5 font-medium">
                    <Volume2 className="w-3.5 h-3.5 text-rose-400" />
                    Siren / PA Array
                  </span>
                  <span className="text-[10px] font-mono font-bold">
                    {channels.siren ? 'ON' : 'OFF'}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => handleToggleChannel('whatsapp')}
                  className={`p-2 rounded-lg border text-left flex items-center justify-between transition-colors ${
                    channels.whatsapp
                      ? 'bg-emerald-950/60 border-emerald-500/50 text-emerald-200'
                      : 'bg-slate-950 border-slate-800 text-slate-500'
                  }`}
                >
                  <span className="flex items-center gap-1.5 font-medium">
                    <MessageSquare className="w-3.5 h-3.5 text-emerald-400" />
                    WhatsApp Gateway
                  </span>
                  <span className="text-[10px] font-mono font-bold">
                    {channels.whatsapp ? 'ON' : 'OFF'}
                  </span>
                </button>
              </div>
            </div>

            {/* Bilingual Content Editor */}
            <div className="space-y-2.5 pt-2 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                  <Languages className="w-3.5 h-3.5 text-cyan-400" />
                  Bilingual Broadcast Payload:
                </span>
                <div className="flex items-center bg-slate-950 p-0.5 rounded border border-slate-800 text-[10px]">
                  <button
                    onClick={() => setPreviewLanguage('EN')}
                    className={`px-2 py-0.5 rounded font-bold ${
                      previewLanguage === 'EN' ? 'bg-cyan-500 text-slate-950' : 'text-slate-400'
                    }`}
                  >
                    English
                  </button>
                  <button
                    onClick={() => setPreviewLanguage('NE')}
                    className={`px-2 py-0.5 rounded font-bold ${
                      previewLanguage === 'NE' ? 'bg-cyan-500 text-slate-950' : 'text-slate-400'
                    }`}
                  >
                    नेपाली (Nepali)
                  </button>
                </div>
              </div>

              {previewLanguage === 'EN' ? (
                <div className="space-y-2">
                  <div>
                    <label className="text-[10px] text-slate-400 block mb-1">Headline (English):</label>
                    <input
                      type="text"
                      value={headlineEn}
                      onChange={(e) => setHeadlineEn(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-400 block mb-1">Message Body (English):</label>
                    <textarea
                      rows={3}
                      value={messageEn}
                      onChange={(e) => setMessageEn(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <div>
                    <label className="text-[10px] text-slate-400 block mb-1">शीर्षक (Nepali Headline):</label>
                    <input
                      type="text"
                      value={headlineNe}
                      onChange={(e) => setHeadlineNe(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-400 block mb-1">विस्तृत सन्देश (Nepali Message Body):</label>
                    <textarea
                      rows={3}
                      value={messageNe}
                      onChange={(e) => setMessageNe(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Safe Shelter Destination Attachment */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                Attach Recommended Safe Shelter:
              </label>
              <select
                value={selectedShelter}
                onChange={(e) => setSelectedShelter(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-emerald-500 font-sans"
              >
                {KOSHI_SHELTERS.map((sh) => (
                  <option key={sh.id} value={sh.name}>
                    {sh.name} (Elev: {sh.elevationMsl}m MSL • Capacity: {sh.capacity})
                  </option>
                ))}
              </select>
            </div>

            {/* Recipient Reach Calculator Box */}
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between text-xs">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400 block">
                  Simulated Audience Reach
                </span>
                <span className="text-sm font-extrabold text-cyan-300 font-mono">
                  {activeZone.estimatedDevices.toLocaleString()} registered devices
                </span>
                <span className="text-[10px] text-slate-400 block mt-0.5">
                  Targeted within polygon boundary
                </span>
              </div>
              <div className="text-right">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">
                  Expected Delivery Latency
                </span>
                <span className="text-sm font-extrabold text-emerald-400 font-mono">
                  ~3.2 seconds
                </span>
                <span className="text-[10px] text-slate-400 block mt-0.5">
                  High-priority push tunnel
                </span>
              </div>
            </div>

            {/* Broadcast Action Button: Signature Ghost Pill CTA */}
            <div className="pt-2">
              <button
                onClick={() => setShowConfirmModal(true)}
                className="btn-ghost-pill w-full text-center justify-center !py-3 !text-xs font-mono"
              >
                <BellRing className="w-3.5 h-3.5 animate-pulse" />
                <span>BROADCAST CIVIL EMERGENCY DIRECTIVE</span>
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: GEOGRAPHIC TARGETING MAP & DISPATCH LOG (6 cols on lg/xl) */}
        <div className="lg:col-span-6 space-y-3.5">
          {/* Geofence Leaflet Targeting Map */}
          <div className="rounded-none bg-[#0a0a0a] border border-[#3a3a3f] overflow-hidden shadow-none">
            <div className="p-3 border-b border-[#3a3a3f] bg-[#000000] flex items-center justify-between text-xs font-mono">
              <span className="font-micro text-[9px] uppercase tracking-[0.96px] text-[#5a5a5f] flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-white" />
                TARGET GEOFENCE POLYGON ({activeZone.areaKm2} KM²)
              </span>
              <span className="text-[10px] text-white uppercase font-bold">
                {activeZone.name.split('(')[0]}
              </span>
            </div>

            <div className="relative w-full h-[300px] bg-black">
              <MapContainer
                center={[26.65, 87.08]}
                zoom={11}
                scrollWheelZoom={false}
                className="w-full h-full"
              >
                <TileLayer
                  attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
                  url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
                  maxZoom={16}
                />

                {/* Highlighted Targeted Geofence Polygon */}
                <Polygon
                  positions={activeZone.polygon}
                  pathOptions={{
                    color: '#ffffff',
                    fillColor: severity === 'EMERGENCY' ? '#ef4444' : '#d97706',
                    fillOpacity: 0.45,
                    weight: 2,
                    dashArray: '4 4',
                  }}
                >
                  <Tooltip permanent direction="center">
                    <div className="font-mono text-[10px] font-bold text-slate-950 text-center uppercase">
                      TARGET GEOFENCE<br />
                      {activeZone.estimatedDevices.toLocaleString()} Devices
                    </div>
                  </Tooltip>
                </Polygon>
              </MapContainer>

              {/* Map Floating HUD */}
              <div className="absolute bottom-2 left-2 z-[1000] px-2 py-1 bg-black border border-[#3a3a3f] text-[10px] font-mono text-white">
                BROADCAST: <strong className="text-white uppercase font-bold">{severity}</strong>
              </div>
            </div>
          </div>

          {/* Table of Recent Dispatched Bulletins */}
          <div className="p-4 rounded-none bg-[#0a0a0a] border border-[#3a3a3f] shadow-none space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-white" />
                RECENT DISPATCHED BULLETINS
              </h3>
              <span className="font-mono text-[10px] text-[#5a5a5f] uppercase">
                {activeAlerts.length} ACTIVE IN QUEUE
              </span>
            </div>

            <div className="space-y-2.5 max-h-[290px] overflow-y-auto pr-1">
              {activeAlerts.map((alert) => (
                <div
                  key={alert.id}
                  className="p-3 bg-black border border-[#3a3a3f] space-y-2 font-mono"
                >
                  <div className="flex items-start justify-between gap-1">
                    <div>
                      <div className="flex items-center gap-2">
                        <span
                          className={`badge-chip text-[9px] ${getSeverityPillColor(
                            alert.severity
                          )}`}
                        >
                          {alert.severity}
                        </span>
                        <h4 className="font-display text-xs font-bold text-white tracking-wider leading-snug uppercase">
                          {alert.headline}
                        </h4>
                      </div>
                      <span className="text-[10px] text-[#5a5a5f] mt-0.5 block uppercase">
                        {alert.dispatched_at} &bull; GEOFENCE: {alert.geofence}
                      </span>
                    </div>

                    <button
                      onClick={() => onCancelAlert(alert.id)}
                      className="btn-ghost-pill-subtle text-[9px] !py-0.5 !px-2 border-rose-600 text-rose-300"
                    >
                      SUPERSEDE
                    </button>
                  </div>

                  {/* Delivery Stats & Channels */}
                  <div className="flex flex-wrap items-center justify-between pt-1 border-t border-[#3a3a3f] text-[10px]">
                    <div className="flex items-center gap-1.5">
                      <span className="text-white font-bold">
                        {alert.read_rate || 86}% READ
                      </span>
                      <span className="text-[#3a3a3f]">&bull;</span>
                      <span className="text-[#5a5a5f] uppercase">
                        {alert.reach_count ? alert.reach_count.toLocaleString() : '14,250'} REACHED
                      </span>
                    </div>

                    <div className="flex items-center gap-1">
                      {alert.channels.slice(0, 2).map((ch, idx) => (
                        <span
                          key={idx}
                          className="badge-chip text-[9px] !py-0 !px-1.5 truncate max-w-[120px]"
                        >
                          {ch.split('(')[0]}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* CONFIRMATION MODAL TO PREVENT ACCIDENTAL DISPATCH */}
      {showConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 animate-in fade-in">
          <div className="w-full max-w-lg rounded-none bg-[#0a0a0a] border border-white p-6 shadow-none space-y-4 font-mono">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 border border-white bg-black text-white">
                  <AlertOctagon className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h3 className="font-display text-sm font-bold text-white uppercase tracking-wider">
                    AUTHORIZE EMERGENCY BROADCAST
                  </h3>
                  <p className="font-micro text-[10px] text-[#5a5a5f] uppercase">
                    HIGH-PRIORITY CIVIL DEFENSE ACTION
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowConfirmModal(false)}
                className="text-[#5a5a5f] hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3.5 bg-black border border-[#3a3a3f] text-xs space-y-2">
              <div>
                <span className="font-micro text-[9px] text-[#5a5a5f] uppercase block">TARGET SECTOR:</span>
                <span className="font-bold text-white text-xs uppercase">{activeZone.name}</span>
              </div>
              <div>
                <span className="font-micro text-[9px] text-[#5a5a5f] uppercase block">ESTIMATED REACH:</span>
                <span className="text-white font-bold">
                  {activeZone.estimatedDevices.toLocaleString()} MOBILE DEVICES &amp; SIRENS
                </span>
              </div>
              <div>
                <span className="font-micro text-[9px] text-[#5a5a5f] uppercase block">PAYLOAD HEADLINE:</span>
                <span className="text-[#f0f0fa]">{headlineEn}</span>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowConfirmModal(false)}
                className="btn-ghost-pill-subtle text-xs !py-1.5 !px-4"
              >
                CANCEL &amp; EDIT
              </button>
              <button
                onClick={handleConfirmBroadcast}
                className="btn-ghost-pill text-xs !py-1.5 !px-5"
              >
                <Send className="w-3.5 h-3.5" />
                <span>CONFIRM &amp; TRANSMIT</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Toast Notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 p-4 rounded-none bg-[#0a0a0a] border border-white text-white shadow-none animate-in slide-in-from-bottom-4 flex items-start gap-3 max-w-md font-mono">
          <CheckCircle className="w-5 h-5 text-white flex-shrink-0 mt-0.5" />
          <div className="text-xs">
            <h4 className="font-bold text-white uppercase">ALERT DISPATCH COMPLETED</h4>
            <p className="text-[#f0f0fa] mt-0.5">{toast}</p>
          </div>
        </div>
      )}
    </div>
  );
};
