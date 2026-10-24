import { useState, useEffect, useRef } from 'react';
import { AlertDispatcher } from './components/AlertDispatcher';
import { CommandOverview } from './components/CommandOverview';
import { Header } from './components/Header';
import { BackendAccessPanel } from './components/BackendAccessPanel';
import { BackendSatelliteEvidence } from './components/BackendSatelliteEvidence';
import { BackendPredictionPanel, BackendAnalyticsPanel } from './components/BackendResearchPanels';
import { ModelAnalytics } from './components/ModelAnalytics';
import { PredictionCentre } from './components/PredictionCentre';
import { ResponseOperations } from './components/ResponseOperations';
import { SatelliteIntelligence } from './components/SatelliteIntelligence';
import { EnvironmentalMonitoring } from './components/EnvironmentalMonitoring';
import { EmergencyFacilities } from './components/EmergencyFacilities';
import { RouteAssessment } from './components/RouteAssessment';
import { HistoricalReports } from './components/HistoricalReports';
import { Sidebar } from './components/Sidebar';
import { ParticlesComponent } from './components/ui/particles-bg';
import {
  BENCHMARK_SCENES,
  BENCHMARK_SCENARIOS_DATA,
  MOCK_ACTIVE_ALERTS,
  MOCK_HELP_REQUESTS,
  MOCK_METRICS,
} from './data/mockData';
import { ApiService } from './services/apiService';
import {
  DEMO_MODE,
  getAssistanceQueue,
  listDemoAlerts,
  updateAssistance,
  subscribeAuthorityEvents,
  login,
  type AuthSession,
} from './services/backendApi';
import { toHelpRequest, toUiAlert } from './services/backendMappers';
import type {
  Alert,
  AuthorityHandoffStatus,
  BenchmarkScene,
  HelpRequest,
  MetricSummary,
  NavigationItemId,
} from './types';

export function App() {
  // Navigation State
  const [activeTab, setActiveTab] = useState<NavigationItemId>('command-overview');

  // Benchmark Scene State (Default: Nepal Terai - Koshi Basin Benchmark Event)
  const [currentScene, setCurrentScene] = useState<BenchmarkScene>(BENCHMARK_SCENES[0]);

  // Operational State
  const [requests, setRequests] = useState<HelpRequest[]>(DEMO_MODE ? MOCK_HELP_REQUESTS : []);
  const [alerts, setAlerts] = useState<Alert[]>(DEMO_MODE ? MOCK_ACTIVE_ALERTS : []);
  const [metrics, setMetrics] = useState<MetricSummary>(MOCK_METRICS);

  // Model Version State (Promotable via ModelAnalytics)
  const [deployedModelVersion, setDeployedModelVersion] = useState('FloodLens-LSTM-GNN v1.2');

  // Backend Connection Health State
  const [isBackendConnected, setIsBackendConnected] = useState(false);
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [websocketConnected, setWebsocketConnected] = useState(false);
  const [dataSyncError, setDataSyncError] = useState('');

  // Live Simulation State
  const [isLiveSimulation, setIsLiveSimulation] = useState(false);
  const simulationStepRef = useRef(0);

  // Pre-filled advisory payload from Prediction Centre
  const [prefilledAdvisory, setPrefilledAdvisory] = useState<{
    horizon?: string;
    threatLevel?: string;
    population?: number;
    wards?: string[];
  } | null>(null);

  // Quick Notification Toast state
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  // Periodically check FastAPI backend health (fallback to cached benchmark data if offline)
  useEffect(() => {
    let isMounted = true;
    const probe = async () => {
      const ok = await ApiService.checkHealth();
      if (isMounted) setIsBackendConnected(ok);
    };
    probe();
    const interval = setInterval(probe, 25000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Auto-establish authority session on mount so civilian SOS distress beacons appear immediately
  useEffect(() => {
    if (DEMO_MODE || authSession) return;
    let mounted = true;
    const tryAutoLogin = async () => {
      try {
        const session = await login('authority@floodlens.org', 'authoritysecure456');
        if (mounted) setAuthSession(session);
      } catch {
        // Fallback: officer can sign in manually via the authority access panel
      }
    };
    void tryAutoLogin();
    return () => {
      mounted = false;
    };
  }, [authSession]);

  // REST is the source of truth with 3.5s polling interval + WebSocket event subscriptions.
  // Polling interval ensures newly submitted civilian SOS tickets appear on map and side-panel in near real-time.
  useEffect(() => {
    if (DEMO_MODE || !authSession) {
      setWebsocketConnected(false);
      return;
    }
    let mounted = true;
    const sync = async () => {
      try {
        const [queue, backendAlerts] = await Promise.all([getAssistanceQueue(), listDemoAlerts()]);
        if (!mounted) return;
        setRequests(queue.map(toHelpRequest));
        setAlerts(backendAlerts.map(toUiAlert));
        setDataSyncError('');
      } catch (error) {
        if (mounted) setDataSyncError(error instanceof Error ? error.message : 'Backend sync failed');
      }
    };
    void sync();

    // 3.5s polling interval (3-5s requirement) for near real-time SOS queue synchronization
    const pollInterval = setInterval(() => {
      void sync();
    }, 3500);

    const stop = subscribeAuthorityEvents(event => {
      if (['resync.instructions', 'connection.established', 'assistance.created', 'assistance.updated', 'alert.approved', 'alert.published'].includes(event.type)) {
        void sync();
      }
    }, connected => {
      if (mounted) setWebsocketConnected(connected);
    });
    return () => {
      mounted = false;
      clearInterval(pollInterval);
      stop();
    };
  }, [authSession]);

  const handleAuthSessionChange = (next: AuthSession | null) => {
    setAuthSession(next);
    setDataSyncError('');
    if (!next && !DEMO_MODE) {
      setRequests([]);
      setAlerts([]);
    }
  };

  // Multi-scenario benchmark switcher
  const handleSelectScene = (scene: BenchmarkScene) => {
    setCurrentScene(scene);
    const scenarioData =
      BENCHMARK_SCENARIOS_DATA[scene.id] || BENCHMARK_SCENARIOS_DATA['koshi-basin-primary'];
    if (DEMO_MODE) {
      setMetrics(scenarioData.metrics);
      setRequests(scenarioData.requests);
      setAlerts(scenarioData.alerts);
    }
    showToast(`Selected historical benchmark view: ${scene.name}. Only actual backend records are authoritative.`);
  };

  // Anonymized Simulation Presets (Citizen privacy compliance)
  const simulationPresets = [
    {
      name: 'Citizen M. Mandal',
      phone: '+977 981-7788990',
      location: 'Prakashpur, Ward 2 (River Reach)',
      coords: [26.712, 87.078] as [number, number],
      landmark: 'Water entering ground floor shop, 4 souls sheltered on second floor balcony',
      category: 'TRAPPED' as const,
      urgency: 'CRITICAL' as const,
      score: 'Priority 1 - Flash Surge Inflow',
      depth: '1.6m (Surging)',
      people: 4,
    },
    {
      name: 'Citizen S. Shrestha',
      phone: '+977 980-4433221',
      location: 'Barahakshetra, Ward 4 Culvert',
      coords: [26.825, 87.135] as [number, number],
      landmark: 'Culvert road connection submerged, pregnant mother requiring high-ground evacuation',
      category: 'MEDICAL' as const,
      urgency: 'CRITICAL' as const,
      score: 'Priority 1 - Immediate Medical Extraction',
      depth: '1.3m (Fast Current)',
      people: 2,
    },
    {
      name: 'Citizen G. Adhikari',
      phone: '+977 984-6677889',
      location: 'Madhuban Village Sector 3',
      coords: [26.634, 87.032] as [number, number],
      landmark: '74yo bedridden grandfather on low cot, levee seeped into living area',
      category: 'ELDERLY_EVAC' as const,
      urgency: 'HIGH' as const,
      score: 'Priority 2 - Immobility Evacuation',
      depth: '0.9m',
      people: 3,
    },
  ];

  // Trigger Disaster Simulation Event
  const triggerSimulationEvent = () => {
    const preset = simulationPresets[simulationStepRef.current % simulationPresets.length];
    simulationStepRef.current += 1;

    const newId = `SOS-2026-09${simulationStepRef.current}`;
    const newRequest: HelpRequest = {
      id: newId,
      requester_name: preset.name,
      contact_number: preset.phone,
      timestamp: 'Just now (Live Ping)',
      category: preset.category,
      urgency: preset.urgency,
      urgency_score: preset.score,
      status: 'LOCAL_LOGGED',
      handoff_status: 'LOCAL_LOGGED',
      authority_handoff_target: 'DEOC Sunsari (District Emergency Operations Center)',
      people_count: preset.people,
      location_name: preset.location,
      coordinates: preset.coords,
      landmark: preset.landmark,
      notes: 'Real-time telemetry event triggered via EOC simulation stream.',
      battery_level: 45,
      estimated_water_depth: preset.depth,
      nearest_shelter: { name: 'Inaruwa Safe Hub', distance: '1.2 km' },
      nearest_highground: {
        name: 'Inaruwa Higher Secondary Safe Elevation',
        distance: '1.2 km',
        elevationMsl: 84,
      },
      report_elapsed_time: '1m elapsed',
      authority_verification: 'Awaiting handoff transmission to DEOC Sunsari',
      activity_log: [
        {
          timestamp: 'Just now',
          action: 'Distress beacon received via automated simulation',
          author: 'Live Stream',
        },
      ],
    };

    // Update state
    setRequests((prev) => [newRequest, ...prev]);

    // Bump metrics
    setMetrics((prev) => ({
      ...prev,
      populationAtRisk: {
        ...prev.populationAtRisk,
        total: prev.populationAtRisk.total + 140,
      },
      openRequests: {
        ...prev.openRequests,
        total: prev.openRequests.total + 1,
        critical:
          preset.urgency === 'CRITICAL'
            ? prev.openRequests.critical + 1
            : prev.openRequests.critical,
      },
      floodThreat: {
        ...prev.floodThreat,
        trendLabel: '+0.42 m/h overbank rate',
        description: 'Chatara Gauge +0.05m surge. Discharge progressing toward Koshi Barrage.',
      },
    }));

    showToast(`🚨 SIMULATED SOS: ${preset.name} (${preset.location}) • River Stage +0.05m`);
  };

  // Background timer for Live Simulation
  useEffect(() => {
    if (!isLiveSimulation) return;

    const interval = setInterval(() => {
      triggerSimulationEvent();
    }, 24000); // Trigger realistic event every 24 seconds

    return () => clearInterval(interval);
  }, [isLiveSimulation]);

  // A recorded historical-demo acknowledgement is not a real-world DEOC dispatch.
  const handleHandoffRequest = async (requestId: string, _authorityTarget = 'DEOC Sunsari'): Promise<boolean> => {
    if (DEMO_MODE) {
      setRequests(prev => prev.map(r => r.id === requestId
        ? { ...r, status: 'SIMULATED_AUTHORITY_ACK', handoff_status: 'SIMULATED_AUTHORITY_ACK' }
        : r));
      showToast(`DEMO ONLY: Local acknowledgement recorded for ${requestId}. No responders contacted.`);
      return true;
    }
    try {
      const saved = await updateAssistance(requestId, 'acknowledged', 'Acknowledged in FloodLens historical/test system. No operational dispatch.');
      setRequests(prev => prev.map(r => r.id === requestId ? toHelpRequest(saved) : r));
      showToast(`Backend record ${requestId} acknowledged. No rescue team was dispatched.`);
      return true;
    } catch (error) {
      showToast(`NOT SAVED: ${error instanceof Error ? error.message : 'Backend action failed'}`);
      return false;
    }
  };

  const handleUpdateRequestStatus = async (
    requestId: string,
    status: AuthorityHandoffStatus,
    authorityNote?: string
  ): Promise<boolean> => {
    if (DEMO_MODE) {
      setRequests(prev => prev.map(r => r.id === requestId
        ? { ...r, status, handoff_status: status }
        : r));
      showToast(`DEMO ONLY: Local status ${status.replace(/_/g, ' ')} recorded; no external action.`);
      return true;
    }
    const backendStatus =
      status === 'RESOLVED' ? 'resolved' :
      status === 'ACKNOWLEDGED_BY_AUTHORITY' || status === 'TRANSMITTED_TO_DEOC' ? 'acknowledged' :
      status === 'SIMULATED_AUTHORITY_ACK' ? 'in_progress' : 'pending';
    try {
      const saved = await updateAssistance(requestId, backendStatus, authorityNote);
      setRequests(prev => prev.map(r => r.id === requestId ? toHelpRequest(saved) : r));
      showToast(`Saved backend status: ${saved.status}. Test-only record, not operational dispatch.`);
      return true;
    } catch (error) {
      showToast(`NOT SAVED: ${error instanceof Error ? error.message : 'Backend update failed'}`);
      return false;
    }
  };

  const handleBroadcastAlert = (newAlert: Alert) => {
    setAlerts((prev) => [newAlert, ...prev]);
    showToast(newAlert.status === 'DRAFT'
      ? `Backend DEMO draft ${newAlert.code} created. Explicit approval is required before any test dispatch.`
      : `DEMO ONLY: Simulation record ${newAlert.code} updated (no operational warnings issued).`);
  };

  const handleCancelAlert = (_alertId: string) => {
    showToast('Action unsupported: Alert cancellation is not supported by the backend architecture. Dispatched alerts are permanent audit records.');
  };

  const handleAlertUpdated = (updated: Alert) => {
    setAlerts(prev => prev.map(a => a.id === updated.id ? updated : a));
  };

  const handleBroadcastRevision = (alertId: string) => {
    showToast(`CAP Bulletin revision drafted for ${alertId} - awaiting officer signoff`);
    setActiveTab('alert-dispatcher');
  };

  const handleDeployModel = (newVersion: string) => {
    setDeployedModelVersion(newVersion);
    showToast(`UI demo selection: ${newVersion}. No model was deployed or retrained.`);
  };

  return (
    <div className="relative min-h-screen bg-transparent text-white flex flex-col font-sans selection:bg-white selection:text-black">
      {/* Global Animated Particles Background */}
      <ParticlesComponent />

      {/* Top Navigation Header */}
      <Header
        benchmarkScenes={BENCHMARK_SCENES}
        currentScene={currentScene}
        onSelectScene={handleSelectScene}
        activeAlertCount={alerts.filter((a) => a.status === 'DISPATCHED').length}
        openReportsCount={
          requests.filter((r) => r.handoff_status === 'LOCAL_LOGGED' || r.status === 'LOCAL_LOGGED').length
        }
        criticalZoneCount={3}
        lastUpdatedText="Updated 4m ago"
        isLiveSimulation={isLiveSimulation}
        isBackendConnected={!DEMO_MODE && isBackendConnected}
        onToggleLiveSimulation={() => {
          if (!DEMO_MODE) { showToast('Backend mode does not simulate external flood data or alerts.'); return; }
          setIsLiveSimulation(!isLiveSimulation);
          showToast(
            !isLiveSimulation
              ? 'Live Simulation Stream activated (auto-events every 24s)'
              : 'Live Simulation Stream paused'
          );
        }}
        onTriggerSimulationEvent={() => DEMO_MODE ? triggerSimulationEvent() : showToast('Surge injection is disabled in backend mode. This screen never starts real alerts.')}
      />

      <BackendAccessPanel session={authSession} backendOnline={isBackendConnected} websocketOnline={websocketConnected} onSessionChange={handleAuthSessionChange} />
      {!DEMO_MODE && (
        <div className="border-b border-sky-800/50 bg-slate-950 px-5 py-2 text-xs text-amber-200" role="status">
          Displayed overview metrics, benchmark maps and depth values are illustrative until a verified historical GIS/ML dataset is loaded.
          {dataSyncError && <span className="ml-2 text-rose-300">AUTHORITY SYNC FAILED: {dataSyncError}</span>}
        </div>
      )}
      {/* Main Body Shell: Sidebar + Content Area */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Sidebar Navigation */}
        <Sidebar
          activeTab={activeTab}
          onSelectTab={setActiveTab}
          openSosCount={
            requests.filter((r) => r.handoff_status === 'LOCAL_LOGGED' || r.status === 'LOCAL_LOGGED').length
          }
          activeAlertCount={alerts.filter((a) => a.status === 'DISPATCHED').length}
        />

        {/* Primary Operational Content Area */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-6 bg-transparent">
          <div className="max-w-7xl mx-auto space-y-4">
            {/* View Switcher: All 6 Operational Views Fully Functional */}
            {activeTab === 'command-overview' && (
              <CommandOverview
                metrics={metrics}
                benchmarkScene={currentScene}
                requests={requests}
                alerts={alerts}
                onHandoffRequest={handleHandoffRequest}
                onAssignRequest={handleHandoffRequest}
                onBroadcastRevision={handleBroadcastRevision}
              />
            )}

            {activeTab === 'prediction-centre' && (DEMO_MODE ? (
              <PredictionCentre
                currentScene={currentScene}
                onNavigateToDispatcher={(payload) => {
                  setPrefilledAdvisory(payload);
                  showToast(`Draft advisory generated for ${payload?.horizon || '+3h'} horizon`);
                  setActiveTab('alert-dispatcher');
                }}
              />
            ) : <BackendPredictionPanel />)}

            {activeTab === 'satellite-intel' && (DEMO_MODE ? (
              <SatelliteIntelligence
                currentScene={currentScene}
                onSendToResponseOps={() => {
                  showToast('Navigated to coordination view. No satellite data was transferred.');
                  setActiveTab('response-ops');
                }}
              />
            ) : <BackendSatelliteEvidence />)}

            {activeTab === 'response-ops' && (
              <ResponseOperations
                currentScene={currentScene}
                requests={requests}
                onUpdateRequestStatus={handleUpdateRequestStatus}
              />
            )}

            {activeTab === 'alert-dispatcher' && (
              <AlertDispatcher
                currentScene={currentScene}
                activeAlerts={alerts}
                onBroadcastAlert={handleBroadcastAlert}
                onCancelAlert={handleCancelAlert}
                onAlertUpdated={handleAlertUpdated}
                initialPayload={prefilledAdvisory}
              />
            )}

            {activeTab === 'model-analytics' && (DEMO_MODE ? (
              <ModelAnalytics
                currentScene={currentScene}
                deployedModelVersion={deployedModelVersion}
                onDeployModel={handleDeployModel}
              />
            ) : <BackendAnalyticsPanel />)}

            {activeTab === 'environmental-monitoring' && (
              <EnvironmentalMonitoring currentScene={currentScene} />
            )}

            {activeTab === 'emergency-facilities' && (
              <EmergencyFacilities currentScene={currentScene} />
            )}

            {activeTab === 'route-assessment' && (
              <RouteAssessment currentScene={currentScene} />
            )}

            {activeTab === 'historical-reports' && (
              <HistoricalReports currentScene={currentScene} />
            )}
          </div>
        </main>
      </div>

      {/* Interactive Action Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-5 right-5 z-50 px-5 py-2.5 rounded-full bg-[#0a0a0a] border border-white text-white text-xs font-mono tracking-wider uppercase flex items-center gap-2.5 animate-in slide-in-from-bottom-5 shadow-[0_4px_24px_rgba(0,0,0,0.8)]">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping"></span>
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
}

export default App;
