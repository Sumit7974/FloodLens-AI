import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Alert,
} from 'react-native';
import {
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  Radio,
  Send,
  Navigation,
  Clock,
  MapPin,
  Users,
  Droplets,
  HeartPulse,
  RefreshCw,
  Server,
  CloudOff,
  Filter,
} from 'lucide-react-native';
import { THEME } from '../constants/theme';
import { TacticalCard } from '../components/TacticalCard';
import { StatusPill } from '../components/StatusPill';
import { HelpRequest, ResponderAction, AuthorityHandoffStatus } from '../types';
import { fetchAssistanceQueue, updateAssistanceStatus } from '../api/client';
import { getQueuedIncidents, queuedIncidentToHelpRequest } from '../services/sosQueue';

type FilterTab = 'ALL' | 'CRITICAL' | 'LOCAL_LOGGED' | 'IN_PROGRESS' | 'RESOLVED';

export const ResponderScreen: React.FC = () => {
  const [incidents, setIncidents] = useState<HelpRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeFilter, setActiveFilter] = useState<FilterTab>('ALL');
  const [actionInProgressId, setActionInProgressId] = useState<string | null>(null);
  const [sourceType, setSourceType] = useState<'live_backend' | 'offline_fallback'>('live_backend');
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  /**
   * Load incident queue from FastAPI backend merged with any offline pending items
   */
  const loadIncidentQueue = useCallback(async () => {
    try {
      const [backendRes, offlineQueue] = await Promise.all([
        fetchAssistanceQueue(),
        getQueuedIncidents(),
      ]);

      const offlineMapped = offlineQueue.map(queuedIncidentToHelpRequest);
      setSourceType(backendRes.source);

      // Merge: Offline pending reports appear at the top
      const combined = [...offlineMapped, ...backendRes.incidents];
      setIncidents(combined);
    } catch (err: any) {
      console.warn('[Responder Screen] Queue load error:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadIncidentQueue();
  }, [loadIncidentQueue]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadIncidentQueue();
  }, [loadIncidentQueue]);

  /**
   * Execute Actionable Responder Command (ACKNOWLEDGE, DISPATCH TEAM, RESOLVE)
   */
  const handleResponderAction = async (incident: HelpRequest, action: ResponderAction) => {
    setActionInProgressId(incident.id);
    setActionFeedback(null);

    try {
      const res = await updateAssistanceStatus(incident.id, action);

      // Optimistically update local incident list
      setIncidents((prev) =>
        prev.map((item) => {
          if (item.id === incident.id) {
            return {
              ...item,
              status: res.status,
            };
          }
          return item;
        })
      );

      const actionTitle =
        action === 'ACKNOWLEDGE'
          ? 'ACKNOWLEDGED'
          : action === 'DISPATCH_TEAM'
          ? 'TEAM DISPATCHED'
          : 'RESOLVED';

      setActionFeedback(`Incident ${incident.id}: ${actionTitle}. Synced to FastAPI.`);
      setTimeout(() => setActionFeedback(null), 4000);
    } catch (err: any) {
      Alert.alert('Action Failed', err.message || 'Failed to update backend assistance status.');
    } finally {
      setActionInProgressId(null);
    }
  };

  /**
   * Filter incidents according to active tab
   */
  const filteredIncidents = incidents.filter((item) => {
    if (activeFilter === 'ALL') return true;
    if (activeFilter === 'CRITICAL') return item.urgency === 'CRITICAL';
    if (activeFilter === 'LOCAL_LOGGED') return item.status === 'LOCAL_LOGGED';
    if (activeFilter === 'IN_PROGRESS')
      return item.status === 'SIMULATED_AUTHORITY_ACK' || item.status === 'TRANSMITTED_TO_DEOC';
    if (activeFilter === 'RESOLVED') return item.status === 'RESOLVED';
    return true;
  });

  const getStatusBadgeConfig = (status: AuthorityHandoffStatus) => {
    switch (status) {
      case 'TRANSMITTED_TO_DEOC':
        return { label: 'TRANSMITTED TO DEOC', variant: 'info' as const };
      case 'SIMULATED_AUTHORITY_ACK':
      case 'ACKNOWLEDGED_BY_AUTHORITY':
        return { label: 'TEAM EN ROUTE', variant: 'warning' as const };
      case 'RESOLVED':
        return { label: 'RESOLVED', variant: 'success' as const };
      default:
        return { label: 'LOCAL LOGGED', variant: 'destructive' as const };
    }
  };

  const getCategoryBadgeColor = (category: string) => {
    switch (category) {
      case 'TRAPPED':
        return THEME.colors.rose;
      case 'MEDICAL':
        return THEME.colors.purple;
      case 'EVACUATION':
      case 'ELDERLY_EVAC':
        return THEME.colors.amber;
      default:
        return THEME.colors.cyan;
    }
  };

  return (
    <ScrollView
      style={styles.container}
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
      {/* Screen Title & Pipeline Status */}
      <View style={styles.topSection}>
        <View>
          <Text style={styles.screenEyebrow}>FIELD OPERATIONS • AUTHORITY TRIAGE</Text>
          <Text style={styles.screenHeading}>CITIZEN ASSISTANCE QUEUE</Text>
        </View>
        <StatusPill
          label={sourceType === 'live_backend' ? 'FASTAPI LIVE' : 'BENCHMARK QUEUE'}
          variant={sourceType === 'live_backend' ? 'success' : 'warning'}
          showDot={true}
        />
      </View>

      {/* Overview Mission Status Card */}
      <TacticalCard
        title="TACTICAL DISPATCH OVERVIEW"
        icon={ShieldAlert}
        badgeText={`${incidents.filter((i) => i.urgency === 'CRITICAL').length} CRITICAL`}
        badgeVariant="destructive"
        value={`${incidents.length} TOTAL REPORTS`}
        subtext="Live priority queue matching the Authority Web Command Center. Select actionable commands to triage and dispatch response units."
        indicatorColor={THEME.colors.amber}
      />

      {/* Action Feedback Banner */}
      {actionFeedback && (
        <View style={styles.feedbackBanner}>
          <CheckCircle2 size={16} color={THEME.colors.emerald} />
          <Text style={styles.feedbackText}>{actionFeedback}</Text>
        </View>
      )}

      {/* Filter Tabs */}
      <View style={styles.filterBar}>
        {(['ALL', 'CRITICAL', 'LOCAL_LOGGED', 'IN_PROGRESS', 'RESOLVED'] as FilterTab[]).map((tab) => {
          const isSelected = activeFilter === tab;
          const count =
            tab === 'ALL'
              ? incidents.length
              : tab === 'CRITICAL'
              ? incidents.filter((i) => i.urgency === 'CRITICAL').length
              : tab === 'LOCAL_LOGGED'
              ? incidents.filter((i) => i.status === 'LOCAL_LOGGED').length
              : tab === 'IN_PROGRESS'
              ? incidents.filter((i) => i.status === 'SIMULATED_AUTHORITY_ACK' || i.status === 'TRANSMITTED_TO_DEOC').length
              : incidents.filter((i) => i.status === 'RESOLVED').length;

          return (
            <TouchableOpacity
              key={tab}
              style={[styles.filterChip, isSelected && styles.filterChipSelected]}
              onPress={() => setActiveFilter(tab)}
            >
              <Text style={[styles.filterChipText, isSelected && styles.filterChipTextSelected]}>
                {tab.replace('_', ' ')} ({count})
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Loading Indicator */}
      {loading && (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={THEME.colors.cyan} />
          <Text style={styles.loadingText}>Connecting to FastAPI Incident Pipeline...</Text>
        </View>
      )}

      {/* Empty State */}
      {!loading && filteredIncidents.length === 0 && (
        <View style={styles.emptyContainer}>
          <CheckCircle2 size={32} color={THEME.colors.emerald} />
          <Text style={styles.emptyTitle}>NO INCIDENTS IN THIS TRIAGE CATEGORY</Text>
          <Text style={styles.emptySubtext}>
            All citizen distress reports for this filter have been acknowledged or resolved.
          </Text>
        </View>
      )}

      {/* Active Incident List */}
      {!loading &&
        filteredIncidents.map((incident) => {
          const badge = getStatusBadgeConfig(incident.status);
          const catColor = getCategoryBadgeColor(incident.category);
          const isBusy = actionInProgressId === incident.id;

          return (
            <View key={incident.id} style={styles.incidentCard}>
              {/* Card Top: Requester Name, Category Tag, Urgency */}
              <View style={styles.cardHeader}>
                <View style={styles.headerLeft}>
                  <Text style={styles.requesterName}>{incident.requester_name}</Text>
                  <Text style={styles.incidentId}>#{incident.id}</Text>
                </View>
                <View style={styles.headerRight}>
                  <StatusPill
                    label={incident.category}
                    variant={incident.category === 'TRAPPED' || incident.category === 'MEDICAL' ? 'destructive' : 'warning'}
                    showDot={false}
                    style={{ backgroundColor: `${catColor}20`, borderColor: catColor }}
                    textStyle={{ color: catColor }}
                  />
                  <StatusPill
                    label={badge.label}
                    variant={badge.variant}
                    showDot={true}
                  />
                </View>
              </View>

              {/* Triage Telemetry Line */}
              <View style={styles.metaRow}>
                <View style={styles.metaItem}>
                  <Users size={13} color={THEME.colors.cyan} />
                  <Text style={styles.metaText}>{incident.people_count} Souls</Text>
                </View>

                {incident.estimated_water_depth && (
                  <View style={styles.metaItem}>
                    <Droplets size={13} color={THEME.colors.amber} />
                    <Text style={[styles.metaText, { color: THEME.colors.amber }]}>
                      {incident.estimated_water_depth}
                    </Text>
                  </View>
                )}

                {incident.medical_urgency && (
                  <View style={styles.metaItem}>
                    <HeartPulse size={13} color={THEME.colors.rose} />
                    <Text style={[styles.metaText, { color: THEME.colors.rose, fontWeight: '800' }]}>
                      MEDICAL
                    </Text>
                  </View>
                )}

                <View style={styles.metaItem}>
                  <Clock size={13} color={THEME.colors.textMuted} />
                  <Text style={styles.metaTextMuted}>{incident.timestamp}</Text>
                </View>
              </View>

              {/* Location & GPS Landmark */}
              <View style={styles.locationContainer}>
                <MapPin size={13} color={THEME.colors.cyan} style={styles.locIcon} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.locationName}>{incident.location_name}</Text>
                  <Text style={styles.coordinatesText}>
                    GPS: {incident.coordinates[0]?.toFixed(4)}°N, {incident.coordinates[1]?.toFixed(4)}°E
                  </Text>
                </View>
              </View>

              {/* Situation & Landmark Notes */}
              {(incident.landmark || incident.notes) && (
                <View style={styles.notesBox}>
                  <Text style={styles.notesText}>
                    {incident.landmark || incident.notes}
                  </Text>
                </View>
              )}

              {/* Actionable Responder Control Buttons */}
              <View style={styles.actionsRow}>
                {/* 1. ACKNOWLEDGE (TRANSMIT TO DEOC) */}
                <TouchableOpacity
                  style={[
                    styles.actionBtn,
                    styles.ackBtn,
                    incident.status === 'TRANSMITTED_TO_DEOC' && styles.actionBtnActive,
                  ]}
                  onPress={() => handleResponderAction(incident, 'ACKNOWLEDGE')}
                  disabled={isBusy || incident.status === 'RESOLVED'}
                >
                  <Radio size={12} color={THEME.colors.sky} />
                  <Text style={[styles.actionBtnText, { color: THEME.colors.sky }]}>
                    ACKNOWLEDGE
                  </Text>
                </TouchableOpacity>

                {/* 2. DISPATCH TEAM */}
                <TouchableOpacity
                  style={[
                    styles.actionBtn,
                    styles.dispatchBtn,
                    incident.status === 'SIMULATED_AUTHORITY_ACK' && styles.actionBtnActive,
                  ]}
                  onPress={() => handleResponderAction(incident, 'DISPATCH_TEAM')}
                  disabled={isBusy || incident.status === 'RESOLVED'}
                >
                  <Navigation size={12} color={THEME.colors.amber} />
                  <Text style={[styles.actionBtnText, { color: THEME.colors.amber }]}>
                    DISPATCH TEAM
                  </Text>
                </TouchableOpacity>

                {/* 3. RESOLVE INCIDENT */}
                <TouchableOpacity
                  style={[
                    styles.actionBtn,
                    styles.resolveBtn,
                    incident.status === 'RESOLVED' && styles.actionBtnActive,
                  ]}
                  onPress={() => handleResponderAction(incident, 'RESOLVE')}
                  disabled={isBusy || incident.status === 'RESOLVED'}
                >
                  <CheckCircle2 size={12} color={THEME.colors.emerald} />
                  <Text style={[styles.actionBtnText, { color: THEME.colors.emerald }]}>
                    RESOLVE
                  </Text>
                </TouchableOpacity>
              </View>

              {isBusy && (
                <View style={styles.busyOverlay}>
                  <ActivityIndicator size="small" color={THEME.colors.cyan} />
                </View>
              )}
            </View>
          );
        })}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.darkBg,
  },
  scrollContent: {
    padding: THEME.spacing.lg,
    paddingBottom: THEME.spacing.xxl * 3,
  },
  topSection: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: THEME.spacing.md,
  },
  screenEyebrow: {
    fontSize: THEME.typography.microSize,
    fontWeight: '800',
    color: THEME.colors.cyan,
    letterSpacing: 1.2,
  },
  screenHeading: {
    fontSize: THEME.typography.headerSize,
    fontWeight: '900',
    color: THEME.colors.textPrimary,
    letterSpacing: 0.8,
  },
  feedbackBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.4)',
    borderRadius: THEME.borderRadius.md,
    padding: THEME.spacing.md,
    marginBottom: THEME.spacing.md,
  },
  feedbackText: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '800',
    color: THEME.colors.emerald,
    letterSpacing: 0.6,
  },
  filterBar: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: THEME.spacing.md,
  },
  filterChip: {
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
  },
  filterChipSelected: {
    backgroundColor: 'rgba(6, 182, 212, 0.2)',
    borderColor: THEME.colors.cyan,
  },
  filterChipText: {
    fontSize: THEME.typography.microSize,
    fontWeight: '700',
    color: THEME.colors.textSecondary,
    letterSpacing: 0.6,
  },
  filterChipTextSelected: {
    color: THEME.colors.cyan,
    fontWeight: '800',
  },
  loadingContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 36,
    gap: 10,
  },
  loadingText: {
    fontSize: THEME.typography.captionSize,
    color: THEME.colors.cyan,
    letterSpacing: 0.8,
    fontWeight: '600',
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 40,
    gap: 8,
    backgroundColor: THEME.colors.cardBg,
    borderRadius: THEME.borderRadius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
    paddingHorizontal: 20,
  },
  emptyTitle: {
    fontSize: THEME.typography.cardTitleSize,
    fontWeight: '800',
    color: THEME.colors.emerald,
    letterSpacing: 0.8,
    textAlign: 'center',
  },
  emptySubtext: {
    fontSize: THEME.typography.captionSize,
    color: THEME.colors.textMuted,
    textAlign: 'center',
    lineHeight: 16,
  },
  incidentCard: {
    backgroundColor: THEME.colors.cardBg,
    borderRadius: THEME.borderRadius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
    padding: THEME.spacing.lg,
    marginBottom: THEME.spacing.md,
    position: 'relative',
    overflow: 'hidden',
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  headerLeft: {
    flex: 1,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  requesterName: {
    fontSize: THEME.typography.bodySize,
    fontWeight: '800',
    color: THEME.colors.textPrimary,
    letterSpacing: 0.6,
  },
  incidentId: {
    fontSize: THEME.typography.microSize,
    color: THEME.colors.textMuted,
    fontFamily: 'monospace',
    marginTop: 1,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 12,
    marginBottom: 8,
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.05)',
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  metaText: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '700',
    color: THEME.colors.textPrimary,
  },
  metaTextMuted: {
    fontSize: THEME.typography.microSize,
    color: THEME.colors.textMuted,
    fontFamily: 'monospace',
  },
  locationContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    marginBottom: 8,
  },
  locIcon: {
    marginTop: 2,
  },
  locationName: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '700',
    color: THEME.colors.textPrimary,
  },
  coordinatesText: {
    fontSize: THEME.typography.microSize,
    color: THEME.colors.textSecondary,
    fontFamily: 'monospace',
    marginTop: 1,
  },
  notesBox: {
    backgroundColor: 'rgba(0, 0, 0, 0.4)',
    borderRadius: THEME.borderRadius.sm,
    padding: 8,
    borderLeftWidth: 2,
    borderLeftColor: THEME.colors.amber,
    marginBottom: 10,
  },
  notesText: {
    fontSize: THEME.typography.captionSize,
    color: THEME.colors.textSecondary,
    lineHeight: 16,
  },
  actionsRow: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 4,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.06)',
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 8,
    borderRadius: THEME.borderRadius.sm,
    borderWidth: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.03)',
  },
  ackBtn: {
    borderColor: 'rgba(56, 189, 248, 0.35)',
    backgroundColor: 'rgba(56, 189, 248, 0.08)',
  },
  dispatchBtn: {
    borderColor: 'rgba(245, 158, 11, 0.35)',
    backgroundColor: 'rgba(245, 158, 11, 0.08)',
  },
  resolveBtn: {
    borderColor: 'rgba(16, 185, 129, 0.35)',
    backgroundColor: 'rgba(16, 185, 129, 0.08)',
  },
  actionBtnActive: {
    opacity: 0.5,
  },
  actionBtnText: {
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.7,
  },
  busyOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(3, 7, 18, 0.75)',
    alignItems: 'center',
    justifyContent: 'center',
  },

});

export default ResponderScreen;
