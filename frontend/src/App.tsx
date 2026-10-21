import { useState, useEffect, useRef } from 'react';
import { AlertDispatcher } from './components/AlertDispatcher';
import { CommandOverview } from './components/CommandOverview';
import { Header } from './components/Header';
import { ModelAnalytics } from './components/ModelAnalytics';
import { PredictionCentre } from './components/PredictionCentre';
import { ResponseOperations } from './components/ResponseOperations';
import { SatelliteIntelligence } from './components/SatelliteIntelligence';
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
  const [requests, setRequests] = useState<HelpRequest[]>(MOCK_HELP_REQUESTS);
  const [alerts, setAlerts] = useState<Alert[]>(MOCK_ACTIVE_ALERTS);
  const [metrics, setMetrics] = useState<MetricSummary>(MOCK_METRICS);

  // Model Version State (Promotable via ModelAnalytics)
  const [deployedModelVersion, setDeployedModelVersion] = useState('FloodLens-LSTM-GNN v1.2');

  // Backend Connection Health State
  const [isBackendConnected, setIsBackendConnected] = useState(false);

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

  // Multi-scenario benchmark switcher
  const handleSelectScene = (scene: BenchmarkScene) => {
    setCurrentScene(scene);
    const scenarioData =
      BENCHMARK_SCENARIOS_DATA[scene.id] || BENCHMARK_SCENARIOS_DATA['koshi-basin-primary'];
    setMetrics(scenarioData.metrics);
    setRequests(scenarioData.requests);
    setAlerts(scenarioData.alerts);
    showToast(`Switched active event benchmark to: ${scene.name}`);
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

  // Transmit standardized incident dossier to District Emergency Operation Center (DEOC)
  const handleHandoffRequest = (
    requestId: string,
    authorityTarget: string = 'DEOC Sunsari'
  ) => {
    setRequests((prev) =>
      prev.map((r) =>
        r.id === requestId
          ? {
              ...r,
              status: 'TRANSMITTED_TO_DEOC',
              handoff_status: 'TRANSMITTED_TO_DEOC',
              authority_handoff_target: authorityTarget,
              activity_log: [
                ...(r.activity_log || []),
                {
                  timestamp: 'Just now',
                  action: `Standardized incident packet transmitted to ${authorityTarget}`,
                  author: 'EOC Duty Officer',
                },
              ],
            }
          : r
      )
    );
    showToast(`Authority Handoff Transmitted: DEOC packet dispatched for ticket #${requestId}`);
  };

  const handleUpdateRequestStatus = (
    requestId: string,
    status: AuthorityHandoffStatus,
    authorityNote?: string
  ) => {
    setRequests((prev) =>
      prev.map((r) => {
        if (r.id !== requestId) return r;
        return {
          ...r,
          status: status as any,
          handoff_status: status,
          activity_log: [
            ...(r.activity_log || []),
            {
              timestamp: 'Just now',
              action: `Authority status updated to ${status}${authorityNote ? `: ${authorityNote}` : ''}`,
              author: 'EOC Duty Officer',
            },
          ],
        };
      })
    );
    showToast(`Ticket #${requestId} updated to ${status.replace(/_/g, ' ')}`);
  };

  const handleBroadcastAlert = (newAlert: Alert) => {
    setAlerts((prev) => [newAlert, ...prev]);
    showToast(
      `Simulated Alert Record Logged: ${newAlert.code} registered in EOC simulation audit log`
    );
  };

  const handleCancelAlert = (alertId: string) => {
    setAlerts((prev) =>
      prev.map((a) => (a.id === alertId ? { ...a, status: 'CANCELLED' } : a))
    );
    showToast(`Alert #${alertId} has been superseded / cancelled in audit log`);
  };

  const handleBroadcastRevision = (alertId: string) => {
    showToast(`CAP Bulletin revision drafted for ${alertId} - awaiting officer signoff`);
    setActiveTab('alert-dispatcher');
  };

  const handleDeployModel = (newVersion: string) => {
    setDeployedModelVersion(newVersion);
    showToast(`Active EOC Production inference engine updated to: ${newVersion}`);
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
        isBackendConnected={isBackendConnected}
        onToggleLiveSimulation={() => {
          setIsLiveSimulation(!isLiveSimulation);
          showToast(
            !isLiveSimulation
              ? 'Live Simulation Stream activated (auto-events every 24s)'
              : 'Live Simulation Stream paused'
          );
        }}
        onTriggerSimulationEvent={triggerSimulationEvent}
      />

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

            {activeTab === 'prediction-centre' && (
              <PredictionCentre
                currentScene={currentScene}
                onNavigateToDispatcher={(payload) => {
                  setPrefilledAdvisory(payload);
                  showToast(`Draft advisory generated for ${payload?.horizon || '+3h'} horizon`);
                  setActiveTab('alert-dispatcher');
                }}
              />
            )}

            {activeTab === 'satellite-intel' && (
              <SatelliteIntelligence
                currentScene={currentScene}
                onSendToResponseOps={() => {
                  showToast('Satellite flood mask sent to Incident Coordination queue');
                  setActiveTab('response-ops');
                }}
              />
            )}

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
                initialPayload={prefilledAdvisory}
              />
            )}

            {activeTab === 'model-analytics' && (
              <ModelAnalytics
                currentScene={currentScene}
                deployedModelVersion={deployedModelVersion}
                onDeployModel={handleDeployModel}
              />
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
