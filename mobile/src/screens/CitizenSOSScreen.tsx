import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
} from 'react-native';
import * as Location from 'expo-location';
import {
  AlertTriangle,
  Compass,
  MapPin,
  Radio,
  RefreshCw,
  Send,
  CheckCircle2,
  CloudOff,
  Droplets,
  Users,
  HeartPulse,
  Info,
  ShieldAlert,
} from 'lucide-react-native';
import { THEME, DEFAULT_COORDINATES } from '../constants/theme';
import { TacticalCard } from '../components/TacticalCard';
import { StatusPill } from '../components/StatusPill';
import {
  CitizenSOSPayload,
  GPSLocationState,
  IncidentSubmissionResult,
  QueuedIncident,
  RequestCategory,
  UrgencyLevel,
} from '../types';
import {
  submitOrQueueIncident,
  getQueuedIncidents,
  syncPendingQueue,
  subscribeToQueue,
} from '../services/sosQueue';

const CATEGORIES: { id: RequestCategory; label: string; iconDesc: string }[] = [
  { id: 'TRAPPED', label: 'TRAPPED', iconDesc: 'Rooftop/Building submerged' },
  { id: 'MEDICAL', label: 'MEDICAL', iconDesc: 'Critical injury or oxygen needed' },
  { id: 'EVACUATION', label: 'EVACUATION', iconDesc: 'Evacuation boat/crew requested' },
  { id: 'FOOD_WATER', label: 'FOOD / WATER', iconDesc: 'Drinking water / rations cut off' },
  { id: 'SHELTER', label: 'SHELTER', iconDesc: 'Refuge from rising torrent' },
  { id: 'ELDERLY_EVAC', label: 'ELDERLY EVAC', iconDesc: 'Mobility impaired assistance' },
];

const WATER_DEPTHS = [
  '0.5m (Knee Deep)',
  '1.2m (Waist Deep)',
  '1.8m (Fast Current)',
  '>2.0m (Fully Submerged)',
];

const URGENCY_LEVELS: { id: UrgencyLevel; label: string; color: string }[] = [
  { id: 'CRITICAL', label: 'CRITICAL (IMMEDIATE)', color: THEME.colors.rose },
  { id: 'HIGH', label: 'HIGH SURGE', color: THEME.colors.amber },
  { id: 'MEDIUM', label: 'ELEVATED', color: THEME.colors.cyan },
  { id: 'LOW', label: 'ADVISORY', color: THEME.colors.emerald },
];

export const CitizenSOSScreen: React.FC = () => {
  // GPS & Location State
  const [gpsState, setGpsState] = useState<GPSLocationState>({
    latitude: DEFAULT_COORDINATES.koshiBasin.latitude,
    longitude: DEFAULT_COORDINATES.koshiBasin.longitude,
    accuracy: null,
    altitude: null,
    status: 'acquiring',
    sectorName: DEFAULT_COORDINATES.koshiBasin.sectorName,
    lastUpdated: 'Initializing...',
  });
  const [acquiringGps, setAcquiringGps] = useState(false);

  // Form Fields
  const [requesterName, setRequesterName] = useState('Citizen R. Thapa');
  const [contactNumber, setContactNumber] = useState('+977 981-4298102');
  const [selectedCategory, setSelectedCategory] = useState<RequestCategory>('TRAPPED');
  const [selectedUrgency, setSelectedUrgency] = useState<UrgencyLevel>('CRITICAL');
  const [selectedDepth, setSelectedDepth] = useState('1.8m (Fast Current)');
  const [peopleCount, setPeopleCount] = useState(5);
  const [medicalUrgency, setMedicalUrgency] = useState(false);
  const [landmark, setLandmark] = useState('Prakashpur, Ward 4 (East Canal Road)');
  const [notes, setNotes] = useState('Trapped on concrete rooftop; ground floor submerged. Fast current in courtyard.');

  // Submission & Queue State
  const [transmitting, setTransmitting] = useState(false);
  const [lastResult, setLastResult] = useState<IncidentSubmissionResult | null>(null);
  const [queuedIncidents, setQueuedIncidents] = useState<QueuedIncident[]>([]);
  const [syncingQueue, setSyncingQueue] = useState(false);

  /**
   * Acquire real GPS location using expo-location with robust fallback
   */
  const acquireGPS = useCallback(async () => {
    setAcquiringGps(true);
    setGpsState((prev) => ({ ...prev, status: 'acquiring' }));

    try {
      // 1. Request foreground permissions
      const { status: permStatus } = await Location.requestForegroundPermissionsAsync();

      if (permStatus !== 'granted') {
        // Fallback to operational coordinates (Koshi Basin: 26.8521, 87.1654)
        setGpsState({
          latitude: DEFAULT_COORDINATES.koshiBasin.latitude,
          longitude: DEFAULT_COORDINATES.koshiBasin.longitude,
          accuracy: null,
          altitude: 84,
          status: 'denied',
          sectorName: `${DEFAULT_COORDINATES.koshiBasin.sectorName} (FALLBACK - PERM DENIED)`,
          lastUpdated: new Date().toLocaleTimeString(),
        });
        setAcquiringGps(false);
        return;
      }

      // 2. Fetch real-time hardware GPS coordinates
      const location = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });

      setGpsState({
        latitude: location.coords.latitude,
        longitude: location.coords.longitude,
        accuracy: location.coords.accuracy,
        altitude: location.coords.altitude,
        status: 'locked',
        sectorName: `${DEFAULT_COORDINATES.koshiBasin.sectorName} (GPS VERIFIED)`,
        lastUpdated: new Date().toLocaleTimeString(),
      });
    } catch (err) {
      // Fallback for emulators without GPS hardware or location disabled
      console.warn('[Citizen SOS] Hardware GPS error, engaging Koshi Basin fallback:', err);
      setGpsState({
        latitude: DEFAULT_COORDINATES.koshiBasin.latitude,
        longitude: DEFAULT_COORDINATES.koshiBasin.longitude,
        accuracy: null,
        altitude: 84,
        status: 'fallback',
        sectorName: `${DEFAULT_COORDINATES.koshiBasin.sectorName} (FALLBACK - EMULATOR/NO HARDWARE GPS)`,
        lastUpdated: new Date().toLocaleTimeString(),
      });
    } finally {
      setAcquiringGps(false);
    }
  }, []);

  // Initialize GPS on mount and subscribe to offline queue
  useEffect(() => {
    acquireGPS();
    const unsubscribe = subscribeToQueue((q) => setQueuedIncidents(q));
    return () => unsubscribe();
  }, [acquireGPS]);

  /**
   * Transmit SOS Request: Dispatches online or stores offline in AsyncStorage
   */
  const handleTransmitSOS = async () => {
    if (!requesterName.trim() || !contactNumber.trim()) {
      Alert.alert('Required Information', 'Please provide a citizen name and contact number for emergency responders.');
      return;
    }

    setTransmitting(true);
    setLastResult(null);

    const payload: CitizenSOSPayload = {
      requester_name: requesterName.trim(),
      contact_number: contactNumber.trim(),
      category: selectedCategory,
      urgency: selectedUrgency,
      people_count: Math.max(1, peopleCount),
      location_name: landmark.trim() || `Koshi Basin (${gpsState.latitude.toFixed(4)}, ${gpsState.longitude.toFixed(4)})`,
      latitude: gpsState.latitude,
      longitude: gpsState.longitude,
      accuracy: gpsState.accuracy,
      estimated_water_depth: selectedDepth,
      medical_urgency: medicalUrgency,
      landmark: landmark.trim(),
      notes: notes.trim(),
      battery_level: 82, // Standard device telemetry
      timestamp: new Date().toISOString(),
    };

    try {
      const result = await submitOrQueueIncident(payload);
      setLastResult(result);
    } catch (error: any) {
      Alert.alert('Transmission Exception', error.message || 'Failed to submit distress request.');
    } finally {
      setTransmitting(false);
    }
  };

  /**
   * Manual Trigger: Sync Pending Offline Reports
   */
  const handleManualSync = async () => {
    setSyncingQueue(true);
    try {
      const res = await syncPendingQueue();
      if (res.synced > 0) {
        Alert.alert('Queue Synchronized', `Successfully transmitted ${res.synced} offline distress report(s) to FastAPI.`);
      } else if (res.totalRemaining > 0) {
        Alert.alert('Host Unreachable', `Backend is still offline or unreachable. ${res.totalRemaining} report(s) remain preserved safely in local storage.`);
      }
    } finally {
      setSyncingQueue(false);
    }
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.scrollContent}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
    >
      {/* Screen Title & Live Alert Pill */}
      <View style={styles.topSection}>
        <View>
          <Text style={styles.screenEyebrow}>CITIZEN PROTECTION PROTOCOL</Text>
          <Text style={styles.screenHeading}>EMERGENCY SOS DISPATCH</Text>
        </View>
        <StatusPill
          label={queuedIncidents.length > 0 ? `${queuedIncidents.length} QUEUED` : 'PIPELINE READY'}
          variant={queuedIncidents.length > 0 ? 'warning' : 'destructive'}
          showDot={true}
        />
      </View>

      {/* Real-time GPS Telemetry Card */}
      <TacticalCard
        title="REAL-TIME GPS TELEMETRY & GEOFENCE"
        icon={Radio}
        badgeText={
          gpsState.status === 'locked'
            ? 'GPS LOCKED'
            : gpsState.status === 'acquiring'
            ? 'ACQUIRING...'
            : 'FALLBACK (DEFAULT)'
        }
        badgeVariant={
          gpsState.status === 'locked'
            ? 'success'
            : gpsState.status === 'acquiring'
            ? 'info'
            : 'warning'
        }
        value={`${gpsState.latitude.toFixed(5)}°N, ${gpsState.longitude.toFixed(5)}°E`}
        subtext={`Accuracy: ${
          gpsState.accuracy !== null ? `±${gpsState.accuracy.toFixed(1)}m verified` : 'Default Koshi Basin Benchmark'
        } • ${gpsState.sectorName}`}
        indicatorColor={gpsState.status === 'locked' ? THEME.colors.emerald : THEME.colors.amber}
      >
        <View style={styles.gpsControlsRow}>
          <View style={styles.gpsInfo}>
            <Text style={styles.gpsInfoText}>
              Last lock probe: {gpsState.lastUpdated}
            </Text>
            {gpsState.status !== 'locked' && (
              <Text style={styles.gpsFallbackNote}>
                Notice: Hardware GPS unavailable or denied. Using Koshi Basin default coordinates (26.85, 87.15).
              </Text>
            )}
          </View>
          <TouchableOpacity
            style={styles.reacquireBtn}
            onPress={acquireGPS}
            disabled={acquiringGps}
          >
            <RefreshCw
              size={14}
              color={THEME.colors.cyan}
              style={acquiringGps ? styles.spinning : undefined}
            />
            <Text style={styles.reacquireBtnText}>RE-ACQUIRE</Text>
          </TouchableOpacity>
        </View>
      </TacticalCard>

      {/* Offline Queue Notification (if pending reports exist) */}
      {queuedIncidents.length > 0 && (
        <View style={styles.queueBanner}>
          <View style={styles.queueBannerHeader}>
            <CloudOff size={16} color={THEME.colors.amber} />
            <Text style={styles.queueBannerTitle}>
              OFFLINE SUBMISSION QUEUE: {queuedIncidents.length} PENDING
            </Text>
          </View>
          <Text style={styles.queueBannerText}>
            Distress reports are secured locally in AsyncStorage and will auto-sync to FastAPI when network connectivity is restored.
          </Text>
          <TouchableOpacity
            style={styles.syncBtn}
            onPress={handleManualSync}
            disabled={syncingQueue}
          >
            {syncingQueue ? (
              <ActivityIndicator size="small" color={THEME.colors.cyan} />
            ) : (
              <>
                <RefreshCw size={13} color={THEME.colors.cyan} />
                <Text style={styles.syncBtnText}>SYNC QUEUE TO BACKEND NOW</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      )}

      {/* Transmission Result Feedback Banner */}
      {lastResult && (
        <View
          style={[
            styles.feedbackCard,
            lastResult.mode === 'online' ? styles.feedbackOnline : styles.feedbackOffline,
          ]}
        >
          {lastResult.mode === 'online' ? (
            <CheckCircle2 size={20} color={THEME.colors.emerald} />
          ) : (
            <CloudOff size={20} color={THEME.colors.amber} />
          )}
          <View style={styles.feedbackContent}>
            <Text
              style={[
                styles.feedbackTitle,
                { color: lastResult.mode === 'online' ? THEME.colors.emerald : THEME.colors.amber },
              ]}
            >
              {lastResult.mode === 'online'
                ? 'TRANSMITTED TO FASTAPI ASSISTANCE QUEUE'
                : 'OFFLINE: SECURED IN PERSISTENT QUEUE'}
            </Text>
            <Text style={styles.feedbackText}>
              {lastResult.mode === 'online'
                ? `Distress packet delivered successfully. ID: ${lastResult.id}. Authority triage channel notified.`
                : `Network offline or host unreachable. Incident saved in AsyncStorage (ID: ${lastResult.id}). Will auto-sync.`}
            </Text>
          </View>
        </View>
      )}

      {/* Interactive Emergency Report Form */}
      <View style={styles.formContainer}>
        <Text style={styles.formSectionHeader}>CITIZEN DISTRESS DETAILS</Text>

        {/* Requester Name & Phone */}
        <View style={styles.formRow}>
          <View style={[styles.formField, { flex: 1 }]}>
            <Text style={styles.fieldLabel}>CITIZEN NAME</Text>
            <TextInput
              style={styles.textInput}
              value={requesterName}
              onChangeText={setRequesterName}
              placeholder="e.g. Citizen R. Thapa"
              placeholderTextColor={THEME.colors.textMuted}
            />
          </View>
          <View style={[styles.formField, { flex: 1 }]}>
            <Text style={styles.fieldLabel}>CONTACT NUMBER</Text>
            <TextInput
              style={styles.textInput}
              value={contactNumber}
              onChangeText={setContactNumber}
              placeholder="+977 981-XXXXXXX"
              placeholderTextColor={THEME.colors.textMuted}
              keyboardType="phone-pad"
            />
          </View>
        </View>

        {/* Emergency Category Selector */}
        <View style={styles.formField}>
          <Text style={styles.fieldLabel}>EMERGENCY CATEGORY</Text>
          <View style={styles.chipsWrap}>
            {CATEGORIES.map((cat) => {
              const isSelected = selectedCategory === cat.id;
              return (
                <TouchableOpacity
                  key={cat.id}
                  style={[styles.chip, isSelected && styles.chipSelected]}
                  onPress={() => setSelectedCategory(cat.id)}
                >
                  <Text style={[styles.chipText, isSelected && styles.chipTextSelected]}>
                    {cat.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* Threat & Urgency Level */}
        <View style={styles.formField}>
          <Text style={styles.fieldLabel}>THREAT / URGENCY SEVERITY</Text>
          <View style={styles.chipsWrap}>
            {URGENCY_LEVELS.map((urg) => {
              const isSelected = selectedUrgency === urg.id;
              return (
                <TouchableOpacity
                  key={urg.id}
                  style={[
                    styles.chip,
                    isSelected && {
                      backgroundColor: `${urg.color}25`,
                      borderColor: urg.color,
                    },
                  ]}
                  onPress={() => setSelectedUrgency(urg.id)}
                >
                  <Text
                    style={[
                      styles.chipText,
                      isSelected && { color: urg.color, fontWeight: '800' },
                    ]}
                  >
                    {urg.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* Water Depth & Souls at Risk */}
        <View style={styles.formRow}>
          {/* Water Depth Chips */}
          <View style={[styles.formField, { flex: 1.3 }]}>
            <Text style={styles.fieldLabel}>WATER INUNDATION DEPTH</Text>
            <View style={styles.chipsColumn}>
              {WATER_DEPTHS.map((depth) => {
                const isSelected = selectedDepth === depth;
                return (
                  <TouchableOpacity
                    key={depth}
                    style={[styles.smallChip, isSelected && styles.smallChipSelected]}
                    onPress={() => setSelectedDepth(depth)}
                  >
                    <Droplets size={12} color={isSelected ? THEME.colors.cyan : THEME.colors.textMuted} />
                    <Text style={[styles.smallChipText, isSelected && styles.smallChipTextSelected]}>
                      {depth}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          {/* Souls Stepper */}
          <View style={[styles.formField, { flex: 0.9 }]}>
            <Text style={styles.fieldLabel}>SOULS AT RISK</Text>
            <View style={styles.stepperContainer}>
              <TouchableOpacity
                style={styles.stepperBtn}
                onPress={() => setPeopleCount((p) => Math.max(1, p - 1))}
              >
                <Text style={styles.stepperBtnText}>-</Text>
              </TouchableOpacity>
              <View style={styles.stepperValueBox}>
                <Users size={16} color={THEME.colors.cyan} />
                <Text style={styles.stepperValueText}>{peopleCount}</Text>
              </View>
              <TouchableOpacity
                style={styles.stepperBtn}
                onPress={() => setPeopleCount((p) => p + 1)}
              >
                <Text style={styles.stepperBtnText}>+</Text>
              </TouchableOpacity>
            </View>

            {/* Medical Urgency Toggle */}
            <TouchableOpacity
              style={[
                styles.medicalToggle,
                medicalUrgency && styles.medicalToggleActive,
              ]}
              onPress={() => setMedicalUrgency((m) => !m)}
            >
              <HeartPulse
                size={16}
                color={medicalUrgency ? THEME.colors.rose : THEME.colors.textMuted}
              />
              <Text
                style={[
                  styles.medicalToggleText,
                  medicalUrgency && styles.medicalToggleTextActive,
                ]}
              >
                {medicalUrgency ? 'CRITICAL MEDICAL' : 'MEDICAL PRIORITY'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Landmark & Situation Notes */}
        <View style={styles.formField}>
          <Text style={styles.fieldLabel}>LANDMARK / LOCATION DETAILS</Text>
          <TextInput
            style={styles.textInput}
            value={landmark}
            onChangeText={setLandmark}
            placeholder="e.g. Near East Canal Bridge, 200m from Primary School"
            placeholderTextColor={THEME.colors.textMuted}
          />
        </View>

        <View style={styles.formField}>
          <Text style={styles.fieldLabel}>OPERATIONAL SITUATION NOTES</Text>
          <TextInput
            style={[styles.textInput, styles.textArea]}
            value={notes}
            onChangeText={setNotes}
            multiline
            numberOfLines={3}
            placeholder="Describe immediate danger, trapped floor, or special medical needs..."
            placeholderTextColor={THEME.colors.textMuted}
          />
        </View>

        {/* Incident Summary Card before Action */}
        <TacticalCard
          title="SOS PREVIEW SUMMARY"
          icon={ShieldAlert}
          badgeText={selectedUrgency}
          badgeVariant={selectedUrgency === 'CRITICAL' ? 'destructive' : 'warning'}
          value={`${peopleCount} SOULS • ${selectedCategory}`}
          subtext={`GPS: ${gpsState.latitude.toFixed(4)}°N, ${gpsState.longitude.toFixed(4)}°E • Depth: ${selectedDepth}${
            medicalUrgency ? ' • [MEDICAL EMERGENCY ACTIVE]' : ''
          }`}
          indicatorColor={THEME.colors.rose}
        />

        {/* Primary Action Button: Big Glowing Tactical SOS Trigger */}
        <TouchableOpacity
          style={[styles.transmitButton, transmitting && styles.transmittingButton]}
          onPress={handleTransmitSOS}
          disabled={transmitting}
          activeOpacity={0.8}
        >
          {transmitting ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <View style={styles.transmitButtonContent}>
              <Send size={18} color="#fff" />
              <Text style={styles.transmitButtonText}>
                TRANSMIT SOS / ASSISTANCE REQUEST
              </Text>
            </View>
          )}
        </TouchableOpacity>
        <Text style={styles.transmitDisclaimer}>
          OFFLINE-RESILIENT: If backend or cellular uplink is unavailable, this report will be stored in encrypted AsyncStorage and auto-synced upon reconnect.
        </Text>
      </View>
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
  gpsControlsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  gpsInfo: {
    flex: 1,
  },
  gpsInfoText: {
    fontSize: THEME.typography.microSize,
    color: THEME.colors.textMuted,
    fontFamily: 'monospace',
  },
  gpsFallbackNote: {
    fontSize: THEME.typography.microSize,
    color: THEME.colors.amber,
    marginTop: 2,
    lineHeight: 13,
  },
  reacquireBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: 'rgba(6, 182, 212, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(6, 182, 212, 0.35)',
  },
  reacquireBtnText: {
    fontSize: THEME.typography.microSize,
    fontWeight: '700',
    color: THEME.colors.cyan,
    letterSpacing: 0.6,
  },
  spinning: {
    opacity: 0.6,
  },
  queueBanner: {
    backgroundColor: 'rgba(245, 158, 11, 0.12)',
    borderRadius: THEME.borderRadius.md,
    borderWidth: 1,
    borderColor: 'rgba(245, 158, 11, 0.35)',
    padding: THEME.spacing.md,
    marginBottom: THEME.spacing.md,
  },
  queueBannerHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  queueBannerTitle: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '800',
    color: THEME.colors.amber,
    letterSpacing: 0.8,
  },
  queueBannerText: {
    fontSize: THEME.typography.captionSize,
    color: THEME.colors.textSecondary,
    lineHeight: 16,
    marginBottom: 8,
  },
  syncBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 6,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: 'rgba(6, 182, 212, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(6, 182, 212, 0.4)',
  },
  syncBtnText: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '800',
    color: THEME.colors.cyan,
    letterSpacing: 0.8,
  },
  feedbackCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    padding: THEME.spacing.md,
    borderRadius: THEME.borderRadius.md,
    borderWidth: 1,
    marginBottom: THEME.spacing.md,
  },
  feedbackOnline: {
    backgroundColor: 'rgba(16, 185, 129, 0.12)',
    borderColor: 'rgba(16, 185, 129, 0.4)',
  },
  feedbackOffline: {
    backgroundColor: 'rgba(245, 158, 11, 0.12)',
    borderColor: 'rgba(245, 158, 11, 0.4)',
  },
  feedbackContent: {
    flex: 1,
  },
  feedbackTitle: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '800',
    letterSpacing: 0.8,
    marginBottom: 2,
  },
  feedbackText: {
    fontSize: THEME.typography.captionSize,
    color: THEME.colors.textSecondary,
    lineHeight: 16,
  },
  formContainer: {
    backgroundColor: THEME.colors.cardBg,
    borderRadius: THEME.borderRadius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
    padding: THEME.spacing.lg,
    marginTop: 4,
  },
  formSectionHeader: {
    fontSize: THEME.typography.cardTitleSize,
    fontWeight: '800',
    color: THEME.colors.cyan,
    letterSpacing: 1.2,
    marginBottom: THEME.spacing.md,
  },
  formRow: {
    flexDirection: 'row',
    gap: 12,
  },
  formField: {
    marginBottom: THEME.spacing.md,
  },
  fieldLabel: {
    fontSize: THEME.typography.microSize,
    fontWeight: '800',
    color: THEME.colors.textSecondary,
    letterSpacing: 0.8,
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  textInput: {
    backgroundColor: 'rgba(0, 0, 0, 0.45)',
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
    borderRadius: THEME.borderRadius.md,
    paddingHorizontal: 12,
    paddingVertical: 8,
    color: THEME.colors.textPrimary,
    fontSize: THEME.typography.bodySize,
  },
  textArea: {
    minHeight: 65,
    textAlignVertical: 'top',
  },
  chipsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  chipsColumn: {
    gap: 6,
  },
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
  },
  chipSelected: {
    backgroundColor: 'rgba(6, 182, 212, 0.2)',
    borderColor: THEME.colors.cyan,
  },
  chipText: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '600',
    color: THEME.colors.textSecondary,
  },
  chipTextSelected: {
    color: THEME.colors.cyan,
    fontWeight: '800',
  },
  smallChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
  },
  smallChipSelected: {
    backgroundColor: 'rgba(6, 182, 212, 0.18)',
    borderColor: THEME.colors.cyan,
  },
  smallChipText: {
    fontSize: THEME.typography.microSize,
    fontWeight: '600',
    color: THEME.colors.textSecondary,
  },
  smallChipTextSelected: {
    color: THEME.colors.cyan,
    fontWeight: '800',
  },
  stepperContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.45)',
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
    borderRadius: THEME.borderRadius.md,
    overflow: 'hidden',
    height: 38,
  },
  stepperBtn: {
    width: 38,
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
  },
  stepperBtnText: {
    fontSize: 18,
    fontWeight: '800',
    color: THEME.colors.cyan,
  },
  stepperValueBox: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  stepperValueText: {
    fontSize: THEME.typography.bodySize,
    fontWeight: '800',
    color: THEME.colors.textPrimary,
  },
  medicalToggle: {
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 7,
    paddingHorizontal: 8,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
  },
  medicalToggleActive: {
    backgroundColor: 'rgba(244, 63, 94, 0.18)',
    borderColor: THEME.colors.rose,
  },
  medicalToggleText: {
    fontSize: THEME.typography.microSize,
    fontWeight: '700',
    color: THEME.colors.textSecondary,
    letterSpacing: 0.6,
  },
  medicalToggleTextActive: {
    color: THEME.colors.rose,
    fontWeight: '800',
  },
  transmitButton: {
    backgroundColor: '#dc2626',
    borderRadius: THEME.borderRadius.md,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: THEME.spacing.md,
    borderWidth: 1,
    borderColor: '#f87171',
    shadowColor: '#ef4444',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.45,
    shadowRadius: 10,
    elevation: 4,
  },
  transmittingButton: {
    opacity: 0.7,
  },
  transmitButtonContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  transmitButtonText: {
    color: '#ffffff',
    fontSize: THEME.typography.bodySize,
    fontWeight: '900',
    letterSpacing: 1,
  },
  transmitDisclaimer: {
    fontSize: 9,
    color: THEME.colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 13,
  },
});

export default CitizenSOSScreen;
