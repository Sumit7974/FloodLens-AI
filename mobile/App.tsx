import React, { useEffect, useState, useCallback } from 'react';
import {
  StyleSheet,
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  TextInput,
  Modal,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import {
  Activity,
  AlertTriangle,
  LifeBuoy,
  Radio,
  RefreshCw,
  Users,
  ShieldCheck,
  Server,
  CloudOff,
  Settings,
  X,
  Wifi,
  Send,
  ShieldAlert,
} from 'lucide-react-native';

import { THEME } from './src/constants/theme';
import { HeaderBar, TacticalCard, StatusPill } from './src/components';
import {
  checkBackendHealth,
  getEffectiveApiBaseUrl,
  setCustomApiBaseUrl,
  resetApiBaseUrl,
  RECOMMENDED_LAN_IP_HINT,
} from './src/api/client';
import { BackendHealthResponse, QueuedIncident } from './src/types';
import { CitizenSOSScreen, ResponderScreen } from './src/screens';
import {
  getQueuedIncidents,
  startAutoSync,
  stopAutoSync,
  subscribeToQueue,
} from './src/services/sosQueue';

type ActiveTab = 'OVERVIEW' | 'CITIZEN_SOS' | 'RESPONDER';

interface BackendConnectionState {
  loading: boolean;
  connected: boolean;
  status: string;
  latencyMs: number;
  data?: BackendHealthResponse;
  error?: string;
  lastChecked?: string;
  resolvedUrl: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('OVERVIEW');
  const [backendState, setBackendState] = useState<BackendConnectionState>({
    loading: true,
    connected: false,
    status: 'Checking...',
    latencyMs: 0,
    resolvedUrl: 'Resolving...',
  });

  const [refreshing, setRefreshing] = useState(false);
  const [queuedIncidents, setQueuedIncidents] = useState<QueuedIncident[]>([]);
  const [networkModalVisible, setNetworkModalVisible] = useState(false);
  const [customUrlInput, setCustomUrlInput] = useState('');
  const [updatingUrl, setUpdatingUrl] = useState(false);

  const performHealthCheck = useCallback(async () => {
    setBackendState((prev) => ({ ...prev, loading: true }));
    const result = await checkBackendHealth();
    setBackendState({
      loading: false,
      connected: result.ok,
      status: result.status,
      latencyMs: result.latencyMs,
      data: result.data,
      error: result.error,
      lastChecked: new Date().toLocaleTimeString(),
      resolvedUrl: result.resolvedUrl,
    });
    setCustomUrlInput(result.resolvedUrl);
  }, []);

  useEffect(() => {
    performHealthCheck();

    // Start offline queue auto-sync daemon
    startAutoSync(15000);

    // Subscribe to offline queue changes
    const unsub = subscribeToQueue((q) => setQueuedIncidents(q));

    return () => {
      stopAutoSync();
      unsub();
    };
  }, [performHealthCheck]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await performHealthCheck();
    setRefreshing(false);
  }, [performHealthCheck]);

  /**
   * Save Custom API Base URL
   */
  const handleSaveCustomUrl = async (url: string) => {
    setUpdatingUrl(true);
    try {
      await setCustomApiBaseUrl(url);
      setNetworkModalVisible(false);
      await performHealthCheck();
    } finally {
      setUpdatingUrl(false);
    }
  };

  /**
   * Reset API Base URL to build defaults
   */
  const handleResetUrl = async () => {
    setUpdatingUrl(true);
    try {
      await resetApiBaseUrl();
      setNetworkModalVisible(false);
      await performHealthCheck();
    } finally {
      setUpdatingUrl(false);
    }
  };

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
        <StatusBar style="light" />

        {/* Tactical Header Bar */}
        <HeaderBar
          backendConnected={backendState.connected}
          latencyMs={backendState.latencyMs}
        />

        {/* Tactical Top Navigation Tab Bar */}
        <View style={styles.navBar}>
          <TouchableOpacity
            style={[styles.navTab, activeTab === 'OVERVIEW' && styles.navTabActive]}
            onPress={() => setActiveTab('OVERVIEW')}
            activeOpacity={0.7}
          >
            <Activity
              size={13}
              color={activeTab === 'OVERVIEW' ? THEME.colors.cyan : THEME.colors.textMuted}
            />
            <Text
              style={[
                styles.navTabText,
                activeTab === 'OVERVIEW' && styles.navTabTextActive,
              ]}
            >
              TELEMETRY
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.navTab, activeTab === 'CITIZEN_SOS' && styles.navTabActive]}
            onPress={() => setActiveTab('CITIZEN_SOS')}
            activeOpacity={0.7}
          >
            <AlertTriangle
              size={13}
              color={activeTab === 'CITIZEN_SOS' ? THEME.colors.rose : THEME.colors.textMuted}
            />
            <Text
              style={[
                styles.navTabText,
                activeTab === 'CITIZEN_SOS' && [styles.navTabTextActive, { color: THEME.colors.rose }],
              ]}
            >
              CITIZEN SOS
            </Text>
            {queuedIncidents.length > 0 && (
              <View style={styles.tabBadge}>
                <Text style={styles.tabBadgeText}>{queuedIncidents.length}</Text>
              </View>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.navTab, activeTab === 'RESPONDER' && styles.navTabActive]}
            onPress={() => setActiveTab('RESPONDER')}
            activeOpacity={0.7}
          >
            <ShieldAlert
              size={13}
              color={activeTab === 'RESPONDER' ? THEME.colors.amber : THEME.colors.textMuted}
            />
            <Text
              style={[
                styles.navTabText,
                activeTab === 'RESPONDER' && [styles.navTabTextActive, { color: THEME.colors.amber }],
              ]}
            >
              RESPONDER
            </Text>
          </TouchableOpacity>
        </View>

        {/* Network & API Routing Sub-Header Banner */}
        <View style={styles.networkSubHeader}>
          <View style={styles.networkInfoGroup}>
            <Wifi
              size={12}
              color={backendState.connected ? THEME.colors.emerald : THEME.colors.rose}
            />
            <Text style={styles.networkEndpointText} numberOfLines={1}>
              API: {backendState.resolvedUrl}
            </Text>
          </View>
          <TouchableOpacity
            style={styles.configBtn}
            onPress={() => setNetworkModalVisible(true)}
          >
            <Settings size={12} color={THEME.colors.cyan} />
            <Text style={styles.configBtnText}>ROUTE</Text>
          </TouchableOpacity>
        </View>

        {/* Tab 1: TELEMETRY OVERVIEW */}
        {activeTab === 'OVERVIEW' && (
          <ScrollView
            style={styles.scrollView}
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                onRefresh={onRefresh}
                tintColor={THEME.colors.cyan}
                colors={[THEME.colors.cyan]}
              />
            }
          >
            {/* Section Eyebrow */}
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>TACTICAL TELEMETRY OVERVIEW</Text>
              <TouchableOpacity
                onPress={performHealthCheck}
                disabled={backendState.loading}
                style={styles.refreshButton}
              >
                <RefreshCw
                  size={12}
                  color={THEME.colors.cyan}
                  style={backendState.loading ? styles.spinning : undefined}
                />
                <Text style={styles.refreshText}>PING</Text>
              </TouchableOpacity>
            </View>

            {/* Card 1: Surge Threat Level */}
            <TacticalCard
              title="SURGE THREAT LEVEL"
              icon={AlertTriangle}
              badgeText="LEVEL 3"
              badgeVariant="warning"
              value="ELEVATED RISK"
              subtext="Chatara Gauge: 8.18m / Danger: 8.00m (+0.18m over alert line)"
              indicatorColor={THEME.colors.amber}
            />

            {/* Card 2: Exposed Population */}
            <TacticalCard
              title="EXPOSED POPULATION"
              icon={Users}
              badgeText="ACTIVE"
              badgeVariant="info"
              value="~18,420"
              subtext="DEM flood envelope overlay onto settlement census cells."
              indicatorColor={THEME.colors.cyan}
            />

            {/* Card 3: Assistance Reports */}
            <TacticalCard
              title="ASSISTANCE REPORTS"
              icon={LifeBuoy}
              badgeText={queuedIncidents.length > 0 ? `${queuedIncidents.length} OFFLINE QUEUED` : '3 CRITICAL'}
              badgeVariant="destructive"
              value="14 LOGGED"
              subtext="14 Reports • 3 Critical Risk • Field responder queue active"
              indicatorColor={THEME.colors.rose}
            />

            {/* Card 4: Telemetry Uplink */}
            <TacticalCard
              title="TELEMETRY UPLINK"
              icon={Radio}
              badgeText="100% ONLINE"
              badgeVariant="success"
              value="12/12 ACTIVE"
              subtext="12/12 Gauges Online • LoRa & Gov API Stream active"
              indicatorColor={THEME.colors.emerald}
            />

            {/* Card 5: Backend Live Connection Diagnostic */}
            <TacticalCard
              title="FASTAPI BACKEND BRIDGE"
              icon={Server}
              badgeText={backendState.connected ? 'ONLINE' : 'OFFLINE'}
              badgeVariant={backendState.connected ? 'success' : 'destructive'}
              value={backendState.connected ? `${backendState.latencyMs}ms LATENCY` : 'OFFLINE'}
              subtext={`Target endpoint: ${backendState.resolvedUrl}/health`}
              indicatorColor={backendState.connected ? THEME.colors.emerald : THEME.colors.rose}
            >
              <View style={styles.diagnosticDetails}>
                <View style={styles.diagRow}>
                  <Text style={styles.diagKey}>FastAPI Status:</Text>
                  <Text
                    style={[
                      styles.diagValue,
                      { color: backendState.connected ? THEME.colors.emerald : THEME.colors.rose },
                    ]}
                  >
                    {backendState.status.toUpperCase()}
                  </Text>
                </View>

                <View style={styles.diagRow}>
                  <Text style={styles.diagKey}>Database Mode:</Text>
                  <Text style={styles.diagValue}>
                    {backendState.data?.database?.database_type?.toUpperCase() || 'SQLITE (FALLBACK)'}
                  </Text>
                </View>

                <View style={styles.diagRow}>
                  <Text style={styles.diagKey}>Last Probe Ping:</Text>
                  <Text style={styles.diagValue}>
                    {backendState.lastChecked || 'Pending initial ping'}
                  </Text>
                </View>

                {backendState.error && (
                  <View style={styles.errorBanner}>
                    <Text style={styles.errorText}>Notice: {backendState.error}</Text>
                    <TouchableOpacity
                      style={styles.lanIpSuggestBtn}
                      onPress={() => handleSaveCustomUrl(RECOMMENDED_LAN_IP_HINT)}
                    >
                      <Text style={styles.lanIpSuggestText}>
                        💡 Tap to switch to Host LAN IP ({RECOMMENDED_LAN_IP_HINT})
                      </Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            </TacticalCard>

            {/* Quick Actions to Switch Tabs */}
            <View style={styles.quickActionsRow}>
              <TouchableOpacity
                style={[styles.quickActionCard, { borderColor: THEME.colors.rose }]}
                onPress={() => setActiveTab('CITIZEN_SOS')}
              >
                <AlertTriangle size={18} color={THEME.colors.rose} />
                <View>
                  <Text style={[styles.quickActionTitle, { color: THEME.colors.rose }]}>
                    LAUNCH CITIZEN SOS
                  </Text>
                  <Text style={styles.quickActionSub}>
                    GPS Tagged Emergency Dispatch
                  </Text>
                </View>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.quickActionCard, { borderColor: THEME.colors.amber }]}
                onPress={() => setActiveTab('RESPONDER')}
              >
                <ShieldAlert size={18} color={THEME.colors.amber} />
                <View>
                  <Text style={[styles.quickActionTitle, { color: THEME.colors.amber }]}>
                    OPEN RESPONDER QUEUE
                  </Text>
                  <Text style={styles.quickActionSub}>
                    Authority Triage & Team Dispatch
                  </Text>
                </View>
              </TouchableOpacity>
            </View>

            {/* Footer Metadata */}
            <View style={styles.footer}>
              <Text style={styles.footerText}>
                FLOODLENS AI • DEPLOYMENT PHASES 1-4 • CORE MOBILE WORKFLOWS & BACKEND INTEGRATION
              </Text>
            </View>
          </ScrollView>
        )}

        {/* Tab 2: CITIZEN SOS SCREEN */}
        {activeTab === 'CITIZEN_SOS' && <CitizenSOSScreen />}

        {/* Tab 3: FIELD RESPONDER SCREEN */}
        {activeTab === 'RESPONDER' && <ResponderScreen />}

        {/* Network Configuration Modal */}
        <Modal
          visible={networkModalVisible}
          transparent={true}
          animationType="fade"
          onRequestClose={() => setNetworkModalVisible(false)}
        >
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <View style={styles.modalHeader}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Settings size={18} color={THEME.colors.cyan} />
                  <Text style={styles.modalTitle}>DYNAMIC NETWORK CONFIGURATION</Text>
                </View>
                <TouchableOpacity onPress={() => setNetworkModalVisible(false)}>
                  <X size={20} color={THEME.colors.textSecondary} />
                </TouchableOpacity>
              </View>

              <Text style={styles.modalDescription}>
                Configure target FastAPI address so physical Android devices running Expo Go or Emulators can reach the host machine.
              </Text>

              {/* Quick Preset Buttons */}
              <Text style={styles.presetLabel}>RECOMMENDED PRESETS:</Text>
              <View style={styles.presetsWrap}>
                <TouchableOpacity
                  style={styles.presetBtn}
                  onPress={() => handleSaveCustomUrl(RECOMMENDED_LAN_IP_HINT)}
                >
                  <Text style={styles.presetBtnTitle}>Physical Phone (Wi-Fi LAN)</Text>
                  <Text style={styles.presetBtnUrl}>{RECOMMENDED_LAN_IP_HINT}</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.presetBtn}
                  onPress={() => handleSaveCustomUrl('http://10.0.2.2:8000')}
                >
                  <Text style={styles.presetBtnTitle}>Android Emulator</Text>
                  <Text style={styles.presetBtnUrl}>http://10.0.2.2:8000</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.presetBtn}
                  onPress={() => handleSaveCustomUrl('http://localhost:8000')}
                >
                  <Text style={styles.presetBtnTitle}>Localhost (PC / Web)</Text>
                  <Text style={styles.presetBtnUrl}>http://localhost:8000</Text>
                </TouchableOpacity>
              </View>

              {/* Manual URL Input */}
              <Text style={styles.presetLabel}>CUSTOM ADDRESS:</Text>
              <TextInput
                style={styles.modalInput}
                value={customUrlInput}
                onChangeText={setCustomUrlInput}
                placeholder="http://192.168.x.x:8000"
                placeholderTextColor={THEME.colors.textMuted}
                autoCapitalize="none"
                autoCorrect={false}
              />

              <View style={styles.modalActionsRow}>
                <TouchableOpacity
                  style={styles.modalResetBtn}
                  onPress={handleResetUrl}
                  disabled={updatingUrl}
                >
                  <Text style={styles.modalResetBtnText}>RESET DEFAULT</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.modalSaveBtn}
                  onPress={() => handleSaveCustomUrl(customUrlInput)}
                  disabled={updatingUrl}
                >
                  <Text style={styles.modalSaveBtnText}>APPLY & PROBE</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: THEME.colors.darkBg,
  },
  navBar: {
    flexDirection: 'row',
    backgroundColor: '#071228',
    borderBottomWidth: 1,
    borderBottomColor: THEME.colors.cardBorder,
    paddingHorizontal: THEME.spacing.sm,
  },
  navTab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 11,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
    position: 'relative',
  },
  navTabActive: {
    borderBottomColor: THEME.colors.cyan,
    backgroundColor: 'rgba(6, 182, 212, 0.08)',
  },
  navTabText: {
    fontSize: THEME.typography.microSize,
    fontWeight: '800',
    color: THEME.colors.textMuted,
    letterSpacing: 0.8,
  },
  navTabTextActive: {
    color: THEME.colors.cyan,
    fontWeight: '900',
  },
  tabBadge: {
    backgroundColor: THEME.colors.amber,
    borderRadius: 8,
    paddingHorizontal: 4,
    paddingVertical: 1,
    minWidth: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabBadgeText: {
    fontSize: 8,
    fontWeight: '900',
    color: '#000',
  },
  networkSubHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: 5,
    backgroundColor: 'rgba(3, 7, 18, 0.85)',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(30, 41, 59, 0.4)',
  },
  networkInfoGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flex: 1,
    marginRight: 8,
  },
  networkEndpointText: {
    fontSize: THEME.typography.microSize,
    color: THEME.colors.textMuted,
    fontFamily: 'monospace',
  },
  configBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    backgroundColor: 'rgba(6, 182, 212, 0.1)',
  },
  configBtnText: {
    fontSize: 9,
    fontWeight: '800',
    color: THEME.colors.cyan,
    letterSpacing: 0.5,
  },
  scrollView: {
    flex: 1,
    backgroundColor: THEME.colors.darkBg,
  },
  scrollContent: {
    padding: THEME.spacing.lg,
    paddingBottom: THEME.spacing.xxl * 2,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: THEME.spacing.md,
    paddingHorizontal: 2,
  },
  sectionTitle: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '800',
    color: THEME.colors.cyan,
    letterSpacing: 1.2,
  },
  refreshButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: 'rgba(6, 182, 212, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(6, 182, 212, 0.3)',
  },
  refreshText: {
    fontSize: THEME.typography.microSize,
    fontWeight: '700',
    color: THEME.colors.cyan,
    letterSpacing: 0.8,
  },
  spinning: {
    opacity: 0.6,
  },
  diagnosticDetails: {
    marginTop: 4,
    gap: 6,
  },
  diagRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  diagKey: {
    fontSize: THEME.typography.captionSize,
    color: THEME.colors.textSecondary,
  },
  diagValue: {
    fontSize: THEME.typography.captionSize,
    color: THEME.colors.textPrimary,
    fontFamily: 'monospace',
    fontWeight: '600',
  },
  errorBanner: {
    marginTop: 8,
    padding: 8,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: 'rgba(244, 63, 94, 0.1)',
    borderWidth: 1,
    borderColor: 'rgba(244, 63, 94, 0.25)',
  },
  errorText: {
    fontSize: THEME.typography.captionSize,
    color: THEME.colors.rose,
  },
  lanIpSuggestBtn: {
    marginTop: 6,
    padding: 6,
    borderRadius: 4,
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(245, 158, 11, 0.35)',
  },
  lanIpSuggestText: {
    fontSize: THEME.typography.microSize,
    fontWeight: '700',
    color: THEME.colors.amber,
  },
  quickActionsRow: {
    gap: 10,
    marginTop: 6,
    marginBottom: THEME.spacing.md,
  },
  quickActionCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: THEME.colors.cardBg,
    borderRadius: THEME.borderRadius.md,
    borderWidth: 1,
    padding: 12,
  },
  quickActionTitle: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  quickActionSub: {
    fontSize: THEME.typography.microSize,
    color: THEME.colors.textMuted,
    marginTop: 1,
  },
  footer: {
    alignItems: 'center',
    marginTop: THEME.spacing.lg,
    marginBottom: THEME.spacing.lg,
  },
  footerText: {
    fontSize: 9,
    color: THEME.colors.textMuted,
    fontFamily: 'monospace',
    letterSpacing: 1,
    textAlign: 'center',
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.82)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: THEME.spacing.lg,
  },
  modalCard: {
    width: '100%',
    backgroundColor: '#0a1428',
    borderRadius: THEME.borderRadius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.cardBorderHighlight,
    padding: THEME.spacing.lg,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.6,
    shadowRadius: 16,
    elevation: 8,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  modalTitle: {
    fontSize: THEME.typography.cardTitleSize,
    fontWeight: '900',
    color: THEME.colors.textPrimary,
    letterSpacing: 0.8,
  },
  modalDescription: {
    fontSize: THEME.typography.captionSize,
    color: THEME.colors.textSecondary,
    lineHeight: 16,
    marginBottom: 12,
  },
  presetLabel: {
    fontSize: THEME.typography.microSize,
    fontWeight: '800',
    color: THEME.colors.cyan,
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  presetsWrap: {
    gap: 6,
    marginBottom: 12,
  },
  presetBtn: {
    padding: 8,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
  },
  presetBtnTitle: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '700',
    color: THEME.colors.textPrimary,
  },
  presetBtnUrl: {
    fontSize: THEME.typography.microSize,
    color: THEME.colors.cyan,
    fontFamily: 'monospace',
    marginTop: 2,
  },
  modalInput: {
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
    borderRadius: THEME.borderRadius.md,
    paddingHorizontal: 12,
    paddingVertical: 8,
    color: THEME.colors.textPrimary,
    fontFamily: 'monospace',
    fontSize: THEME.typography.captionSize,
    marginBottom: 16,
  },
  modalActionsRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
  },
  modalResetBtn: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: THEME.borderRadius.sm,
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
  },
  modalResetBtnText: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '700',
    color: THEME.colors.textMuted,
  },
  modalSaveBtn: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: THEME.colors.cyan,
  },
  modalSaveBtnText: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '900',
    color: '#000',
    letterSpacing: 0.6,
  },
});
