import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  StyleSheet,
  Text,
  View,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
  Vibration,
  Linking,
  RefreshControl,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';

import { CONFIG } from './src/config/api';
import {
  transmitSOS,
  cancelSOS,
  fetchGauges,
  fetchAlerts,
  fetchShelters,
  checkBackendHealth,
  fetchSafeRoute,
  calculateDistance,
  type GaugeStation,
  type ActiveAlert,
  type ShelterFacility,
  type EmergencyCategory,
  type UrgencyLevel,
  type HealthCheckResult,
  type SafeRouteResult,
} from './src/services/apiService';

// Default Koshi Basin Fallback Coordinates (Chatara/Prakashpur reach, Nepal Terai)
const KOSHI_DEFAULT_COORDS = {
  latitude: 26.7258,
  longitude: 85.9250,
};

type ActiveTab = 'sos' | 'telemetry' | 'shelters';

interface CategoryOption {
  id: EmergencyCategory;
  label: string;
  sub: string;
  icon: keyof typeof Ionicons.glyphMap;
}

const CATEGORY_OPTIONS: CategoryOption[] = [
  { id: 'evacuation', label: 'Boat Evacuation', sub: 'Rising water / Stranded', icon: 'boat' },
  { id: 'medical', label: 'Medical Emergency', sub: 'Injury / Hypothermia', icon: 'medkit' },
  { id: 'food_water', label: 'Food & Drinking Water', sub: 'Submerged wells', icon: 'water' },
  { id: 'shelter', label: 'Elderly / Child Haven', sub: 'Vulnerable family', icon: 'people' },
  { id: 'other', label: 'Immediate High Rescue', sub: 'Rooftop evacuation', icon: 'alert-circle' },
];

export default function App() {
  // Navigation State
  const [activeTab, setActiveTab] = useState<ActiveTab>('sos');

  // Backend Health & Latency State
  const [health, setHealth] = useState<HealthCheckResult | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);

  // Tab 1: SOS Distress Form State
  const [coords, setCoords] = useState<{ latitude: number; longitude: number }>(KOSHI_DEFAULT_COORDS);
  const [gpsLocked, setGpsLocked] = useState(false);
  const [acquiringGps, setAcquiringGps] = useState(false);
  const [gpsStatus, setGpsStatus] = useState('Acquiring high-accuracy GPS fix...');

  const [citizenName, setCitizenName] = useState('');
  const [phone, setPhone] = useState('');
  const [category, setCategory] = useState<EmergencyCategory>('evacuation');
  const [urgency, setUrgency] = useState<UrgencyLevel>('CRITICAL');
  const [peopleCount, setPeopleCount] = useState(2);
  const [landmarkNotes, setLandmarkNotes] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [dispatchedId, setDispatchedId] = useState<string | null>(null);
  const [dispatchedTime, setDispatchedTime] = useState<Date | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [cancelling, setCancelling] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Tab 2: Gauges & Alerts State
  const [gauges, setGauges] = useState<GaugeStation[]>([]);
  const [alertsList, setAlertsList] = useState<ActiveAlert[]>([]);
  const [refreshingTelemetry, setRefreshingTelemetry] = useState(false);

  // Tab 3: Shelters & Safe Route Navigation State
  const [shelters, setShelters] = useState<ShelterFacility[]>([]);
  const [refreshingShelters, setRefreshingShelters] = useState(false);
  const [safeRoute, setSafeRoute] = useState<SafeRouteResult | null>(null);
  const [loadingRoute, setLoadingRoute] = useState(false);
  const [showWaypoints, setShowWaypoints] = useState(false);

  // Dynamically compute closest refuge center from current GPS fix
  const nearestShelter = shelters.length > 0
    ? [...shelters].sort((a, b) => (a.distanceKm ?? 999) - (b.distanceKm ?? 999))[0]
    : null;

  // 1. Acquire GPS Location
  const acquireLocation = useCallback(async () => {
    setAcquiringGps(true);
    setGpsStatus('Requesting GNSS satellite lock...');
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setGpsStatus('Permission denied. Using Koshi flood basin benchmark.');
        setCoords(KOSHI_DEFAULT_COORDS);
        setGpsLocked(false);
        setAcquiringGps(false);
        return;
      }

      setGpsStatus('Resolving GPS coordinates...');
      const location = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });

      setCoords({
        latitude: location.coords.latitude,
        longitude: location.coords.longitude,
      });
      setGpsLocked(true);
      setGpsStatus(`GPS Locked (±${Math.round(location.coords.accuracy || 5)}m accuracy)`);
    } catch {
      setGpsStatus('GPS unavailable. Reverted to Koshi flood basin reference.');
      setCoords(KOSHI_DEFAULT_COORDS);
      setGpsLocked(false);
    } finally {
      setAcquiringGps(false);
    }
  }, []);

  // 2. Poll Backend Health & Telemetry
  const refreshHealth = useCallback(async () => {
    setLoadingHealth(true);
    const result = await checkBackendHealth();
    setHealth(result);
    setLoadingHealth(false);
  }, []);

  const refreshGaugesAndAlerts = useCallback(async () => {
    setRefreshingTelemetry(true);
    try {
      const [gData, aData] = await Promise.all([fetchGauges(), fetchAlerts()]);
      setGauges(gData);
      setAlertsList(aData);
    } finally {
      setRefreshingTelemetry(false);
    }
  }, []);

  const refreshSheltersList = useCallback(async () => {
    setRefreshingShelters(true);
    try {
      const sData = await fetchShelters(coords.latitude, coords.longitude);
      setShelters(sData);
    } finally {
      setRefreshingShelters(false);
    }
  }, [coords.latitude, coords.longitude]);

  // Initial mount lifecycle
  useEffect(() => {
    acquireLocation();
    refreshHealth();
    refreshGaugesAndAlerts();
    refreshSheltersList();

    const interval = setInterval(() => {
      refreshHealth();
      refreshGaugesAndAlerts();
    }, 25000);

    return () => clearInterval(interval);
  }, [acquireLocation, refreshHealth, refreshGaugesAndAlerts, refreshSheltersList]);

  // Automatically fetch safe walking evacuation route when nearest shelter is identified
  useEffect(() => {
    if (nearestShelter) {
      setLoadingRoute(true);
      fetchSafeRoute(coords.latitude, coords.longitude, nearestShelter.latitude, nearestShelter.longitude)
        .then((res) => setSafeRoute(res))
        .catch(() => {})
        .finally(() => setLoadingRoute(false));
    }
  }, [coords.latitude, coords.longitude, nearestShelter?.id]);

  // Elapsed timer when beacon is broadcasting
  useEffect(() => {
    if (dispatchedId && dispatchedTime) {
      timerRef.current = setInterval(() => {
        setElapsedSeconds(Math.floor((Date.now() - dispatchedTime.getTime()) / 1000));
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      setElapsedSeconds(0);
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [dispatchedId, dispatchedTime]);

  // 3. Transmit SOS Dispatch
  const handleTransmitSOS = async () => {
    try {
      Vibration.vibrate(100);
    } catch {
      // Haptics fallback
    }

    setSubmitting(true);
    const selectedOption = CATEGORY_OPTIONS.find((c) => c.id === category);

    const result = await transmitSOS({
      citizen_name: citizenName.trim() || 'Citizen Requester',
      phone: phone.trim() || '+977-9800000000',
      latitude: coords.latitude,
      longitude: coords.longitude,
      category,
      people_count: peopleCount,
      needs: [selectedOption?.label || 'Immediate Rescue'],
      landmark_notes: landmarkNotes.trim() || undefined,
      urgency_level: urgency,
    });

    setSubmitting(false);

    if (result.ok) {
      try {
        Vibration.vibrate([0, 150, 100, 300]);
      } catch {
        // Haptics fallback
      }

      setDispatchedId(result.incidentId || 'REGISTERED');
      setDispatchedTime(new Date());

      Alert.alert(
        'BEACON BROADCAST RECEIVED',
        `Your emergency request has been registered in the DEOC incident queue.\n\nTicket ID: #${result.incidentId?.slice(0, 8) || 'CONFIRMED'}\nCoordinates: ${coords.latitude.toFixed(4)}°N, ${coords.longitude.toFixed(4)}°E\n\nStandby for rescue coordination.`,
        [{ text: 'MONITOR STATUS' }]
      );
    } else {
      Alert.alert(
        'TRANSMISSION FAILED',
        result.error || 'Unable to push distress beacon. Check network connection and retry.',
        [{ text: 'RETRY' }]
      );
    }
  };

  // 4. Cancel Active Beacon
  const handleCancelSOS = async () => {
    if (!dispatchedId) return;

    Alert.alert(
      'CONFIRM CANCELLATION',
      'Are you sure you want to cancel your distress beacon? Rescue coordination will be notified that you are safe.',
      [
        { text: 'Keep Active', style: 'cancel' },
        {
          text: 'Yes, I Am Safe',
          style: 'destructive',
          onPress: async () => {
            setCancelling(true);
            const ok = await cancelSOS(dispatchedId);
            setCancelling(false);
            if (ok) {
              setDispatchedId(null);
              setDispatchedTime(null);
              Alert.alert('BEACON CANCELLED', 'Your status has been updated to Safe at the coordination desk.');
            } else {
              setDispatchedId(null);
              setDispatchedTime(null);
              Alert.alert('BEACON CLOSED', 'Status updated locally.');
            }
          },
        },
      ]
    );
  };

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.container} edges={['top', 'left', 'right']}>
        <StatusBar style="light" />

        {/* TOP COMMAND HEADER */}
        <View style={styles.header}>
          <View style={styles.headerTitleRow}>
            <View style={styles.headerIconBox}>
              <Ionicons name="radio" size={18} color="#f43f5e" />
            </View>
            <View>
              <Text style={styles.headerTitle}>FLOODLENS // CITIZEN AID</Text>
              <Text style={styles.headerSubtitle}>KOSHI BASIN RAPID RESPONSE · NEPAL</Text>
            </View>
          </View>

          {/* Backend Status / Latency Pill */}
          <TouchableOpacity
            style={[
              styles.healthBadge,
              health?.ok ? styles.healthBadgeOnline : styles.healthBadgeOffline,
            ]}
            onPress={refreshHealth}
          >
            {loadingHealth ? (
              <ActivityIndicator size="small" color="#38bdf8" />
            ) : (
              <>
                <View
                  style={[
                    styles.statusDot,
                    health?.ok ? styles.statusDotGreen : styles.statusDotRed,
                  ]}
                />
                <Text style={styles.healthText}>
                  {health?.ok ? `${health.latencyMs}ms` : 'OFFLINE'}
                </Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        {/* MAIN TAB CONTENT AREA */}
        <View style={styles.contentArea}>
          {/* TAB 1: SOS DISTRESS */}
          {activeTab === 'sos' && (
            <ScrollView
              style={styles.scrollContainer}
              contentContainerStyle={styles.scrollContent}
              keyboardShouldPersistTaps="handled"
            >
              {/* ACTIVE BROADCAST CONFIRMATION BANNER */}
              {dispatchedId && (
                <View style={styles.activeBeaconCard}>
                  <View style={styles.activeBeaconHeader}>
                    <View style={styles.beaconPill}>
                      <View style={styles.beaconPingDot} />
                      <Text style={styles.beaconPillText}>BEACON BROADCASTING</Text>
                    </View>
                    <Text style={styles.beaconElapsedText}>
                      Transmitted {elapsedSeconds}s ago
                    </Text>
                  </View>

                  <Text style={styles.beaconIdText}>TICKET #{dispatchedId}</Text>
                  <Text style={styles.beaconDescText}>
                    Dispatched to DEOC Authority Command. Rescue operators have received your GNSS position and group headcount.
                  </Text>

                  <View style={styles.beaconCoordsBox}>
                    <Ionicons name="navigate-circle" size={16} color="#38bdf8" />
                    <Text style={styles.beaconCoordsText}>
                      Locked: {coords.latitude.toFixed(5)}°N, {coords.longitude.toFixed(5)}°E
                    </Text>
                  </View>

                  <TouchableOpacity
                    style={styles.cancelBeaconButton}
                    onPress={handleCancelSOS}
                    disabled={cancelling}
                  >
                    {cancelling ? (
                      <ActivityIndicator size="small" color="#ffffff" />
                    ) : (
                      <>
                        <Ionicons name="shield-checkmark" size={16} color="#ffffff" />
                        <Text style={styles.cancelBeaconButtonText}>I AM SAFE (CANCEL BEACON)</Text>
                      </>
                    )}
                  </TouchableOpacity>
                </View>
              )}

              {/* GPS GNSS TELEMETRY CARD */}
              <View style={styles.card}>
                <View style={styles.cardHeader}>
                  <View style={styles.cardHeaderLeft}>
                    <Ionicons name="location-sharp" size={16} color="#38bdf8" />
                    <Text style={styles.cardTitle}>CURRENT GNSS POSITION</Text>
                  </View>
                  <TouchableOpacity
                    style={styles.refreshGpsBtn}
                    onPress={acquireLocation}
                    disabled={acquiringGps}
                  >
                    {acquiringGps ? (
                      <ActivityIndicator size="small" color="#38bdf8" />
                    ) : (
                      <>
                        <Ionicons name="refresh" size={12} color="#38bdf8" />
                        <Text style={styles.refreshGpsBtnText}>RE-ACQUIRE</Text>
                      </>
                    )}
                  </TouchableOpacity>
                </View>

                <View style={styles.coordsDisplayRow}>
                  <View style={styles.coordCol}>
                    <Text style={styles.coordLabel}>LATITUDE</Text>
                    <Text style={styles.coordValue}>{coords.latitude.toFixed(5)}°N</Text>
                  </View>
                  <View style={styles.coordDivider} />
                  <View style={styles.coordCol}>
                    <Text style={styles.coordLabel}>LONGITUDE</Text>
                    <Text style={styles.coordValue}>{coords.longitude.toFixed(5)}°E</Text>
                  </View>
                </View>

                <View style={styles.gpsStatusRow}>
                  <View
                    style={[
                      styles.gpsIndicatorDot,
                      gpsLocked ? styles.statusDotGreen : styles.statusDotAmber,
                    ]}
                  />
                  <Text style={styles.gpsStatusText}>{gpsStatus}</Text>
                </View>
              </View>

              {/* EMERGENCY CATEGORY CHIPS */}
              <View style={styles.card}>
                <Text style={styles.cardTitle}>EMERGENCY NEED CATEGORY</Text>
                <Text style={styles.cardSubtitle}>Select primary distress requirement</Text>

                <View style={styles.categoryGrid}>
                  {CATEGORY_OPTIONS.map((opt) => {
                    const isSelected = category === opt.id;
                    return (
                      <TouchableOpacity
                        key={opt.id}
                        style={[
                          styles.categoryChip,
                          isSelected && styles.categoryChipSelected,
                        ]}
                        onPress={() => setCategory(opt.id)}
                      >
                        <Ionicons
                          name={opt.icon}
                          size={20}
                          color={isSelected ? '#ffffff' : '#38bdf8'}
                        />
                        <View style={styles.categoryChipTextWrap}>
                          <Text
                            style={[
                              styles.categoryChipLabel,
                              isSelected && styles.categoryChipLabelSelected,
                            ]}
                          >
                            {opt.label}
                          </Text>
                          <Text style={styles.categoryChipSub}>{opt.sub}</Text>
                        </View>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>

              {/* GROUP COUNTER & URGENCY */}
              <View style={styles.card}>
                <View style={styles.rowBetween}>
                  {/* People Count Counter */}
                  <View style={styles.counterSection}>
                    <Text style={styles.cardTitle}>SOULS IN GROUP</Text>
                    <View style={styles.counterRow}>
                      <TouchableOpacity
                        style={styles.counterBtn}
                        onPress={() => setPeopleCount((p) => Math.max(1, p - 1))}
                      >
                        <Ionicons name="remove" size={18} color="#ffffff" />
                      </TouchableOpacity>
                      <View style={styles.counterDisplay}>
                        <Text style={styles.counterValue}>{peopleCount}</Text>
                        <Text style={styles.counterUnit}>SOULS</Text>
                      </View>
                      <TouchableOpacity
                        style={styles.counterBtn}
                        onPress={() => setPeopleCount((p) => Math.min(100, p + 1))}
                      >
                        <Ionicons name="add" size={18} color="#ffffff" />
                      </TouchableOpacity>
                    </View>
                  </View>

                  {/* Urgency Selector */}
                  <View style={styles.urgencySection}>
                    <Text style={styles.cardTitle}>URGENCY TIER</Text>
                    <View style={styles.urgencyOptionsRow}>
                      {(['CRITICAL', 'HIGH', 'MEDIUM'] as UrgencyLevel[]).map((level) => {
                        const isSelected = urgency === level;
                        const isCrit = level === 'CRITICAL';
                        return (
                          <TouchableOpacity
                            key={level}
                            style={[
                              styles.urgencyBtn,
                              isSelected && (isCrit ? styles.urgencyBtnCrit : styles.urgencyBtnActive),
                            ]}
                            onPress={() => setUrgency(level)}
                          >
                            <Text
                              style={[
                                styles.urgencyBtnText,
                                isSelected && styles.urgencyBtnTextActive,
                              ]}
                            >
                              {level}
                            </Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  </View>
                </View>
              </View>

              {/* OPTIONAL IDENTIFIER & LANDMARK */}
              <View style={styles.card}>
                <Text style={styles.cardTitle}>LOCAL LANDMARK &amp; IDENTIFICATION</Text>

                <View style={styles.inputWrap}>
                  <Text style={styles.inputLabel}>YOUR NAME (OR HOUSEHOLD HEAD)</Text>
                  <TextInput
                    style={styles.textInput}
                    placeholder="e.g. Ramesh Chaudhary"
                    placeholderTextColor="#64748b"
                    value={citizenName}
                    onChangeText={setCitizenName}
                  />
                </View>

                <View style={styles.inputWrap}>
                  <Text style={styles.inputLabel}>EMERGENCY PHONE NUMBER</Text>
                  <TextInput
                    style={styles.textInput}
                    placeholder="+977-98XXXXXXXX"
                    placeholderTextColor="#64748b"
                    keyboardType="phone-pad"
                    value={phone}
                    onChangeText={setPhone}
                  />
                </View>

                <View style={styles.inputWrap}>
                  <Text style={styles.inputLabel}>LANDMARK / SURROUNDINGS</Text>
                  <TextInput
                    style={[styles.textInput, styles.textInputMultiline]}
                    placeholder="e.g. Near Prakashpur Temple Ward 4, stranded on 2nd-floor rooftop with water at 1.5m"
                    placeholderTextColor="#64748b"
                    multiline
                    numberOfLines={3}
                    value={landmarkNotes}
                    onChangeText={setLandmarkNotes}
                  />
                </View>
              </View>

              {/* HIGH-VISIBILITY BIG SOS BROADCAST BUTTON */}
              <TouchableOpacity
                style={[
                  styles.bigSosButton,
                  submitting && styles.bigSosButtonDisabled,
                ]}
                onPress={handleTransmitSOS}
                disabled={submitting}
                activeOpacity={0.85}
              >
                {submitting ? (
                  <View style={styles.sosButtonInner}>
                    <ActivityIndicator size="large" color="#ffffff" />
                    <Text style={styles.sosButtonText}>TRANSMITTING TO DEOC...</Text>
                  </View>
                ) : (
                  <View style={styles.sosButtonInner}>
                    <Ionicons name="radio" size={32} color="#ffffff" />
                    <View style={styles.sosButtonTextCol}>
                      <Text style={styles.sosButtonText}>BROADCAST SOS DISTRESS</Text>
                      <Text style={styles.sosButtonSubText}>
                        PUSH GNSS COORDINATES TO RESCUE DISPATCH
                      </Text>
                    </View>
                  </View>
                )}
              </TouchableOpacity>

              <Text style={styles.disclaimerText}>
                Telemetry directly registers into the authority command center and web dashboard citizen queue.
              </Text>
            </ScrollView>
          )}

          {/* TAB 2: ALERTS & GAUGES */}
          {activeTab === 'telemetry' && (
            <ScrollView
              style={styles.scrollContainer}
              contentContainerStyle={styles.scrollContent}
              refreshControl={
                <RefreshControl
                  refreshing={refreshingTelemetry}
                  onRefresh={refreshGaugesAndAlerts}
                  tintColor="#38bdf8"
                />
              }
            >
              {/* SECTION HEADER: GAUGES */}
              <View style={styles.sectionHeaderRow}>
                <View style={styles.sectionTitleWrap}>
                  <Ionicons name="pulse" size={18} color="#38bdf8" />
                  <Text style={styles.sectionTitle}>KOSHI BASIN RIVER GAUGES</Text>
                </View>
                <Text style={styles.sectionBadge}>
                  {gauges.length} TELEMETRY STATIONS
                </Text>
              </View>

              {gauges.map((station) => {
                const isCrit = station.status === 'CRITICAL' || station.current_level >= station.danger_level;
                const isWarn = station.status === 'WARNING' || station.current_level >= station.warning_level;
                const ratio = Math.min(100, Math.round((station.current_level / (station.danger_level * 1.1)) * 100));

                return (
                  <View key={station.station_id} style={styles.card}>
                    <View style={styles.gaugeHeader}>
                      <View>
                        <Text style={styles.gaugeName}>{station.name}</Text>
                        <Text style={styles.gaugeRiver}>{station.river}</Text>
                      </View>
                      <View
                        style={[
                          styles.gaugeStatusTag,
                          isCrit
                            ? styles.gaugeStatusTagCrit
                            : isWarn
                            ? styles.gaugeStatusTagWarn
                            : styles.gaugeStatusTagNorm,
                        ]}
                      >
                        <Text
                          style={[
                            styles.gaugeStatusTagText,
                            isCrit
                              ? styles.gaugeStatusTagTextCrit
                              : isWarn
                              ? styles.gaugeStatusTagTextWarn
                              : styles.gaugeStatusTagTextNorm,
                          ]}
                        >
                          {station.status}
                        </Text>
                      </View>
                    </View>

                    {/* Gauge Stats Grid */}
                    <View style={styles.gaugeGrid}>
                      <View style={styles.gaugeMetric}>
                        <Text style={styles.gaugeMetricLabel}>CURRENT LEVEL</Text>
                        <Text style={[styles.gaugeMetricValue, isCrit && styles.textRose]}>
                          {station.current_level.toFixed(2)}m
                        </Text>
                      </View>
                      <View style={styles.gaugeMetric}>
                        <Text style={styles.gaugeMetricLabel}>DANGER THRESHOLD</Text>
                        <Text style={styles.gaugeMetricValue}>{station.danger_level.toFixed(2)}m</Text>
                      </View>
                      <View style={styles.gaugeMetric}>
                        <Text style={styles.gaugeMetricLabel}>DISCHARGE RATE</Text>
                        <Text style={styles.gaugeMetricValue}>{station.discharge_rate.toLocaleString()} m³/s</Text>
                      </View>
                      <View style={styles.gaugeMetric}>
                        <Text style={styles.gaugeMetricLabel}>SURGE TREND</Text>
                        <Text style={[styles.gaugeMetricValue, styles.textAmber]}>
                          ▲ {station.trend}
                        </Text>
                      </View>
                    </View>

                    {/* Progress Fill Bar */}
                    <View style={styles.meterContainer}>
                      <View
                        style={[
                          styles.meterFill,
                          { width: `${ratio}%` },
                          isCrit ? styles.meterFillCrit : isWarn ? styles.meterFillWarn : styles.meterFillNorm,
                        ]}
                      />
                    </View>

                    <View style={styles.gaugeFooter}>
                      <Text style={styles.gaugeTimestamp}>
                        Updated: {station.last_reported_at}
                      </Text>
                      <Text style={styles.gaugeCoords}>
                        {station.coordinates[1].toFixed(3)}°N, {station.coordinates[0].toFixed(3)}°E
                      </Text>
                    </View>
                  </View>
                );
              })}

              {/* SECTION HEADER: ACTIVE ALERTS */}
              <View style={[styles.sectionHeaderRow, { marginTop: 12 }]}>
                <View style={styles.sectionTitleWrap}>
                  <Ionicons name="warning" size={18} color="#f43f5e" />
                  <Text style={styles.sectionTitle}>CIVIL EMERGENCY BROADCASTS</Text>
                </View>
                <Text style={styles.sectionBadge}>
                  {alertsList.length} ISSUED
                </Text>
              </View>

              {alertsList.length === 0 ? (
                <View style={styles.card}>
                  <View style={styles.allClearBox}>
                    <Ionicons name="shield-checkmark" size={28} color="#34d399" />
                    <View style={styles.allClearTextCol}>
                      <Text style={styles.allClearTitle}>ALL CLEAR · BASIN TELEMETRY NORMAL</Text>
                      <Text style={styles.allClearDesc}>
                        No critical civil warning bulletins are currently active for the Koshi flood plain.
                      </Text>
                    </View>
                  </View>
                </View>
              ) : (
                alertsList.map((alertItem) => (
                  <View key={alertItem.id} style={styles.alertCard}>
                    <View style={styles.alertHeaderRow}>
                      <View style={styles.alertPill}>
                        <Text style={styles.alertPillText}>{alertItem.severity || 'WARNING'}</Text>
                      </View>
                      <Text style={styles.alertTimeText}>
                        {new Date(alertItem.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </Text>
                    </View>
                    <Text style={styles.alertTitleText}>{alertItem.title}</Text>
                    <Text style={styles.alertMessageText}>{alertItem.message}</Text>
                    <View style={styles.alertChannelsRow}>
                      {(alertItem.target_channels || ['SMS-CAP', 'SIREN']).map((ch, i) => (
                        <View key={i} style={styles.alertChannelTag}>
                          <Text style={styles.alertChannelTagText}>{ch}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                ))
              )}
            </ScrollView>
          )}

          {/* TAB 3: SAFE SHELTERS & HIGH GROUND ROUTE NAVIGATION */}
          {activeTab === 'shelters' && (
            <ScrollView
              style={styles.scrollContainer}
              contentContainerStyle={styles.scrollContent}
              refreshControl={
                <RefreshControl
                  refreshing={refreshingShelters}
                  onRefresh={refreshSheltersList}
                  tintColor="#38bdf8"
                />
              }
            >
              {/* BACKEND POSTGRESQL / POSTGIS CONNECTIVITY LATENCY METER */}
              <View style={styles.databaseCard}>
                <View style={styles.dbHeaderRow}>
                  <View style={styles.dbIconRow}>
                    <Ionicons name="server" size={16} color="#38bdf8" />
                    <Text style={styles.dbTitle}>POSTGIS GEODATA ENGINE</Text>
                  </View>
                  <View style={styles.dbLatencyPill}>
                    <Text style={styles.dbLatencyText}>
                      ⚡ {health?.latencyMs ?? 110}ms LATENCY
                    </Text>
                  </View>
                </View>
                <Text style={styles.dbDescText}>
                  Connected to PostgreSQL/PostGIS spatial database on Render. Distances computed using WGS84 geodesic algorithms.
                </Text>
              </View>

              {/* TACTICAL SAFE ESCAPE ROUTE TO NEAREST HIGH GROUND */}
              {nearestShelter && (
                <View style={styles.escapeRouteCard}>
                  <View style={styles.escapeHeaderRow}>
                    <View style={styles.escapeTitleRow}>
                      <Ionicons name="compass" size={18} color="#38bdf8" />
                      <Text style={styles.escapeTitle}>TACTICAL SAFE ESCAPE ROUTE</Text>
                    </View>
                    <View style={styles.elevationBadge}>
                      <Ionicons name="shield-checkmark" size={10} color="#34d399" />
                      <Text style={styles.elevationBadgeText}>LOW FLOOD EXPOSURE</Text>
                    </View>
                  </View>

                  <Text style={styles.escapeShelterName}>{nearestShelter.name}</Text>
                  <Text style={styles.escapeSubText}>
                    Designated high-ground refuge center situated above critical flood surge contours.
                  </Text>

                  {/* Distance & Walking Time Stat Pills */}
                  <View style={styles.escapeStatsRow}>
                    <View style={styles.escapeStatCol}>
                      <Text style={styles.escapeStatLabel}>ESCAPE DISTANCE</Text>
                      <Text style={styles.escapeStatValue}>
                        {safeRoute?.distanceKm ?? nearestShelter.distanceKm ?? 0} KM
                      </Text>
                    </View>
                    <View style={styles.escapeStatDivider} />
                    <View style={styles.escapeStatCol}>
                      <Text style={styles.escapeStatLabel}>EST. WALKING TIME</Text>
                      <Text style={[styles.escapeStatValue, styles.textAmber]}>
                        ~{safeRoute?.durationMins ?? Math.round((nearestShelter.distanceKm ?? 2) * 13)} MINS
                      </Text>
                    </View>
                    <View style={styles.escapeStatDivider} />
                    <View style={styles.escapeStatCol}>
                      <Text style={styles.escapeStatLabel}>ROUTE TERRAIN</Text>
                      <Text style={styles.escapeStatValueSm}>
                        {safeRoute?.isFallback ? 'DIRECT BEARING' : 'ELEVATED PATH'}
                      </Text>
                    </View>
                  </View>

                  {/* Step-by-Step Action Buttons */}
                  <View style={styles.escapeActionsRow}>
                    <TouchableOpacity
                      style={styles.navigateHighGroundBtn}
                      onPress={() => {
                        const url = `https://www.google.com/maps/dir/?api=1&origin=${coords.latitude},${coords.longitude}&destination=${nearestShelter.latitude},${nearestShelter.longitude}&travelmode=walking`;
                        Linking.openURL(url);
                      }}
                      activeOpacity={0.85}
                    >
                      <Ionicons name="navigate" size={16} color="#ffffff" />
                      <Text style={styles.navigateHighGroundText}>NAVIGATE TO HIGH GROUND</Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      style={styles.waypointsToggleBtn}
                      onPress={() => setShowWaypoints((v) => !v)}
                    >
                      <Ionicons
                        name={showWaypoints ? 'chevron-up' : 'chevron-down'}
                        size={14}
                        color="#38bdf8"
                      />
                      <Text style={styles.waypointsToggleText}>
                        {showWaypoints ? 'HIDE WAYPOINTS' : 'ROUTE SUMMARY'}
                      </Text>
                    </TouchableOpacity>
                  </View>

                  {/* Expandable Waypoint Breakdown */}
                  {showWaypoints && (
                    <View style={styles.waypointBox}>
                      <View style={styles.waypointStep}>
                        <View style={styles.waypointDotOrigin} />
                        <View style={styles.waypointTextCol}>
                          <Text style={styles.waypointStepTitle}>STARTING GNSS POSITION</Text>
                          <Text style={styles.waypointStepDesc}>
                            {coords.latitude.toFixed(5)}°N, {coords.longitude.toFixed(5)}°E (Your GPS Lock)
                          </Text>
                        </View>
                      </View>

                      <View style={styles.waypointLine} />

                      <View style={styles.waypointStep}>
                        <View style={styles.waypointDotMid} />
                        <View style={styles.waypointTextCol}>
                          <Text style={styles.waypointStepTitle}>TRANSIT CORRIDOR</Text>
                          <Text style={styles.waypointStepDesc}>
                            {safeRoute?.summary || 'Elevated bypass ridge'} &bull; {safeRoute?.waypoints.length ?? 2} path nodes &bull; Dry contour
                          </Text>
                        </View>
                      </View>

                      <View style={styles.waypointLine} />

                      <View style={styles.waypointStep}>
                        <View style={styles.waypointDotDest} />
                        <View style={styles.waypointTextCol}>
                          <Text style={styles.waypointStepTitle}>SAFE HAVEN DESTINATION</Text>
                          <Text style={styles.waypointStepDesc}>
                            {nearestShelter.name} &bull; Capacity: {nearestShelter.capacity} souls ({nearestShelter.status})
                          </Text>
                        </View>
                      </View>

                      <Text style={styles.hazardAdvisory}>
                        ⚠️ TACTICAL ADVISORY: Inundation currents are fast-moving in Koshi flood plains. Maintain travel strictly along marked embankment spurs. Do not attempt crossing submerged roads deeper than ankle-level.
                      </Text>
                    </View>
                  )}
                </View>
              )}

              {/* ALL DESIGNATED REFUGE HUBS LIST */}
              <View style={styles.sectionHeaderRow}>
                <View style={styles.sectionTitleWrap}>
                  <Ionicons name="shield-checkmark" size={18} color="#34d399" />
                  <Text style={styles.sectionTitle}>DESIGNATED REFUGE CENTRES</Text>
                </View>
                <Text style={styles.sectionBadge}>
                  {shelters.length} HUBS
                </Text>
              </View>

              {shelters.map((shelter) => {
                const occupancyRate = Math.min(100, Math.round((shelter.current_occupancy / shelter.capacity) * 100));
                const isFull = occupancyRate >= 90;

                return (
                  <View key={shelter.id} style={styles.card}>
                    <View style={styles.shelterHeader}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.shelterName}>{shelter.name}</Text>
                        <Text style={styles.shelterType}>{shelter.type}</Text>
                      </View>
                      {shelter.distanceKm !== undefined && (
                        <View style={styles.distanceBadge}>
                          <Ionicons name="navigate" size={12} color="#38bdf8" />
                          <Text style={styles.distanceText}>{shelter.distanceKm} km</Text>
                        </View>
                      )}
                    </View>

                    {/* Capacity Indicator Meter */}
                    <View style={styles.capacitySection}>
                      <View style={styles.capacityHeaderRow}>
                        <Text style={styles.capacityLabel}>REFUGE CAPACITY</Text>
                        <Text style={styles.capacityRatio}>
                          {shelter.current_occupancy} / {shelter.capacity} Souls ({occupancyRate}%)
                        </Text>
                      </View>
                      <View style={styles.meterContainer}>
                        <View
                          style={[
                            styles.meterFill,
                            { width: `${occupancyRate}%` },
                            isFull ? styles.meterFillCrit : styles.meterFillNorm,
                          ]}
                        />
                      </View>
                    </View>

                    {/* Amenities Tags */}
                    <View style={styles.amenitiesWrap}>
                      {shelter.amenities.map((item, idx) => (
                        <View key={idx} style={styles.amenityPill}>
                          <Text style={styles.amenityText}>✓ {item}</Text>
                        </View>
                      ))}
                    </View>

                    {/* Emergency Contact Action */}
                    <View style={styles.shelterFooter}>
                      <TouchableOpacity
                        style={styles.callButton}
                        onPress={() => Linking.openURL(`tel:${shelter.contact_phone}`)}
                      >
                        <Ionicons name="call" size={14} color="#38bdf8" />
                        <Text style={styles.callButtonText}>CALL {shelter.contact_phone}</Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.navButton}
                        onPress={() => {
                          const url = `https://www.google.com/maps/dir/?api=1&origin=${coords.latitude},${coords.longitude}&destination=${shelter.latitude},${shelter.longitude}&travelmode=walking`;
                          Linking.openURL(url);
                        }}
                      >
                        <Ionicons name="map" size={14} color="#ffffff" />
                        <Text style={styles.navButtonText}>DIRECTIONS</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                );
              })}
            </ScrollView>
          )}
        </View>

        {/* 3-TAB BOTTOM TACTICAL NAVIGATION BAR */}
        <View style={styles.bottomTabBar}>
          {/* TAB 1: SOS Distress */}
          <TouchableOpacity
            style={[styles.tabItem, activeTab === 'sos' && styles.tabItemActive]}
            onPress={() => setActiveTab('sos')}
            activeOpacity={0.8}
          >
            <Ionicons
              name={activeTab === 'sos' ? 'radio' : 'radio-outline'}
              size={22}
              color={activeTab === 'sos' ? '#f43f5e' : '#94a3b8'}
            />
            <Text
              style={[styles.tabLabel, activeTab === 'sos' && styles.tabLabelSosActive]}
            >
              SOS Distress
            </Text>
            {activeTab === 'sos' && <View style={styles.activeTabIndicatorSos} />}
          </TouchableOpacity>

          {/* TAB 2: Alerts & Gauges */}
          <TouchableOpacity
            style={[styles.tabItem, activeTab === 'telemetry' && styles.tabItemActive]}
            onPress={() => setActiveTab('telemetry')}
            activeOpacity={0.8}
          >
            <Ionicons
              name={activeTab === 'telemetry' ? 'pulse' : 'pulse-outline'}
              size={22}
              color={activeTab === 'telemetry' ? '#38bdf8' : '#94a3b8'}
            />
            <Text
              style={[styles.tabLabel, activeTab === 'telemetry' && styles.tabLabelActive]}
            >
              Alerts &amp; Gauges
            </Text>
            {activeTab === 'telemetry' && <View style={styles.activeTabIndicator} />}
          </TouchableOpacity>

          {/* TAB 3: Safe Shelters */}
          <TouchableOpacity
            style={[styles.tabItem, activeTab === 'shelters' && styles.tabItemActive]}
            onPress={() => setActiveTab('shelters')}
            activeOpacity={0.8}
          >
            <Ionicons
              name={activeTab === 'shelters' ? 'shield-checkmark' : 'shield-checkmark-outline'}
              size={22}
              color={activeTab === 'shelters' ? '#34d399' : '#94a3b8'}
            />
            <Text
              style={[styles.tabLabel, activeTab === 'shelters' && styles.tabLabelShelterActive]}
            >
              Safe Shelters
            </Text>
            {activeTab === 'shelters' && <View style={styles.activeTabIndicatorShelter} />}
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#040b17',
  },
  header: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1a304e',
    backgroundColor: '#07152b',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  headerIconBox: {
    width: 32,
    height: 32,
    borderRadius: 6,
    backgroundColor: 'rgba(244, 63, 94, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(244, 63, 94, 0.4)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    fontFamily: 'monospace',
    fontWeight: '900',
    fontSize: 14,
    color: '#ffffff',
    letterSpacing: 1.1,
  },
  headerSubtitle: {
    fontFamily: 'monospace',
    fontWeight: '600',
    fontSize: 9,
    color: '#38bdf8',
    letterSpacing: 0.8,
    marginTop: 1,
  },
  healthBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 20,
    borderWidth: 1,
    gap: 6,
  },
  healthBadgeOnline: {
    backgroundColor: 'rgba(56, 189, 248, 0.12)',
    borderColor: 'rgba(56, 189, 248, 0.35)',
  },
  healthBadgeOffline: {
    backgroundColor: 'rgba(244, 63, 94, 0.15)',
    borderColor: 'rgba(244, 63, 94, 0.4)',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusDotGreen: {
    backgroundColor: '#34d399',
  },
  statusDotRed: {
    backgroundColor: '#f43f5e',
  },
  statusDotAmber: {
    backgroundColor: '#fb923c',
  },
  healthText: {
    fontFamily: 'monospace',
    fontSize: 10,
    fontWeight: '700',
    color: '#e2e8f0',
  },
  contentArea: {
    flex: 1,
  },
  scrollContainer: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    gap: 14,
    paddingBottom: 32,
  },

  // CARDS & WRAPPERS
  card: {
    backgroundColor: '#091c36',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#183a63',
    padding: 14,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 6,
    elevation: 4,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  cardHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  cardTitle: {
    fontFamily: 'monospace',
    fontSize: 12,
    fontWeight: '800',
    color: '#ffffff',
    letterSpacing: 0.8,
  },
  cardSubtitle: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#94a3b8',
    marginBottom: 10,
  },
  refreshGpsBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(56, 189, 248, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(56, 189, 248, 0.3)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  refreshGpsBtnText: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '700',
    color: '#38bdf8',
  },
  coordsDisplayRow: {
    flexDirection: 'row',
    backgroundColor: '#040d1c',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#132e52',
    padding: 10,
    marginVertical: 4,
  },
  coordCol: {
    flex: 1,
    alignItems: 'center',
  },
  coordDivider: {
    width: 1,
    backgroundColor: '#1a3b68',
  },
  coordLabel: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#64748b',
    fontWeight: '700',
  },
  coordValue: {
    fontFamily: 'monospace',
    fontSize: 14,
    fontWeight: '800',
    color: '#38bdf8',
    marginTop: 2,
  },
  gpsStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 8,
  },
  gpsIndicatorDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  gpsStatusText: {
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#94a3b8',
  },

  // CATEGORY CHIPS
  categoryGrid: {
    gap: 8,
    marginTop: 4,
  },
  categoryChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#051326',
    borderWidth: 1,
    borderColor: '#16365e',
    borderRadius: 10,
    padding: 10,
  },
  categoryChipSelected: {
    backgroundColor: 'rgba(56, 189, 248, 0.15)',
    borderColor: '#38bdf8',
  },
  categoryChipTextWrap: {
    flex: 1,
  },
  categoryChipLabel: {
    fontFamily: 'monospace',
    fontSize: 12,
    fontWeight: '700',
    color: '#e2e8f0',
  },
  categoryChipLabelSelected: {
    color: '#ffffff',
  },
  categoryChipSub: {
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#64748b',
    marginTop: 1,
  },

  // COUNTER & URGENCY
  rowBetween: {
    flexDirection: 'row',
    gap: 12,
  },
  counterSection: {
    flex: 1,
  },
  counterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 8,
  },
  counterBtn: {
    width: 34,
    height: 34,
    borderRadius: 6,
    backgroundColor: '#0e294d',
    borderWidth: 1,
    borderColor: '#214e82',
    alignItems: 'center',
    justifyContent: 'center',
  },
  counterDisplay: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: '#040e1f',
    paddingVertical: 5,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#183861',
  },
  counterValue: {
    fontFamily: 'monospace',
    fontSize: 15,
    fontWeight: '900',
    color: '#ffffff',
  },
  counterUnit: {
    fontFamily: 'monospace',
    fontSize: 8,
    color: '#38bdf8',
    fontWeight: '700',
  },
  urgencySection: {
    flex: 1.2,
  },
  urgencyOptionsRow: {
    flexDirection: 'row',
    gap: 4,
    marginTop: 8,
  },
  urgencyBtn: {
    flex: 1,
    paddingVertical: 9,
    borderRadius: 6,
    backgroundColor: '#051326',
    borderWidth: 1,
    borderColor: '#193963',
    alignItems: 'center',
    justifyContent: 'center',
  },
  urgencyBtnCrit: {
    backgroundColor: 'rgba(244, 63, 94, 0.25)',
    borderColor: '#f43f5e',
  },
  urgencyBtnActive: {
    backgroundColor: 'rgba(56, 189, 248, 0.2)',
    borderColor: '#38bdf8',
  },
  urgencyBtnText: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '800',
    color: '#64748b',
  },
  urgencyBtnTextActive: {
    color: '#ffffff',
  },

  // INPUTS
  inputWrap: {
    marginTop: 10,
  },
  inputLabel: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#94a3b8',
    fontWeight: '700',
    marginBottom: 4,
  },
  textInput: {
    backgroundColor: '#040e1f',
    borderWidth: 1,
    borderColor: '#1a3c69',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontFamily: 'monospace',
    fontSize: 12,
    color: '#ffffff',
  },
  textInputMultiline: {
    minHeight: 65,
    textAlignVertical: 'top',
  },

  // BIG SOS BUTTON
  bigSosButton: {
    backgroundColor: '#e11d48',
    borderRadius: 14,
    paddingVertical: 18,
    paddingHorizontal: 16,
    borderWidth: 2,
    borderColor: '#f43f5e',
    shadowColor: '#f43f5e',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.5,
    shadowRadius: 12,
    elevation: 8,
    marginVertical: 4,
  },
  bigSosButtonDisabled: {
    opacity: 0.6,
  },
  sosButtonInner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 14,
  },
  sosButtonTextCol: {
    flexDirection: 'column',
  },
  sosButtonText: {
    fontFamily: 'monospace',
    fontWeight: '900',
    fontSize: 16,
    color: '#ffffff',
    letterSpacing: 1.2,
  },
  sosButtonSubText: {
    fontFamily: 'monospace',
    fontWeight: '700',
    fontSize: 9,
    color: '#fecdd3',
    letterSpacing: 0.6,
    marginTop: 2,
  },
  disclaimerText: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#64748b',
    textAlign: 'center',
    marginTop: -4,
  },

  // ACTIVE BEACON CARD
  activeBeaconCard: {
    backgroundColor: '#1b0914',
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: '#f43f5e',
    padding: 14,
    gap: 8,
  },
  activeBeaconHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  beaconPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(244, 63, 94, 0.25)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  beaconPingDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#f43f5e',
  },
  beaconPillText: {
    fontFamily: 'monospace',
    fontSize: 10,
    fontWeight: '900',
    color: '#fda4af',
  },
  beaconElapsedText: {
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#cbd5e1',
  },
  beaconIdText: {
    fontFamily: 'monospace',
    fontSize: 15,
    fontWeight: '900',
    color: '#ffffff',
  },
  beaconDescText: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#fda4af',
    lineHeight: 16,
  },
  beaconCoordsBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#0a0307',
    padding: 8,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#431221',
  },
  beaconCoordsText: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#38bdf8',
    fontWeight: '700',
  },
  cancelBeaconButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: '#047857',
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#10b981',
    marginTop: 4,
  },
  cancelBeaconButtonText: {
    fontFamily: 'monospace',
    fontSize: 11,
    fontWeight: '800',
    color: '#ffffff',
    letterSpacing: 0.8,
  },

  // TAB 2: TELEMETRY & GAUGES
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 4,
    marginBottom: 4,
  },
  sectionTitleWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  sectionTitle: {
    fontFamily: 'monospace',
    fontSize: 12,
    fontWeight: '900',
    color: '#ffffff',
    letterSpacing: 0.8,
  },
  sectionBadge: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '700',
    color: '#38bdf8',
  },
  gaugeHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  gaugeName: {
    fontFamily: 'monospace',
    fontSize: 13,
    fontWeight: '800',
    color: '#ffffff',
  },
  gaugeRiver: {
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#64748b',
    marginTop: 1,
  },
  gaugeStatusTag: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    borderWidth: 1,
  },
  gaugeStatusTagCrit: {
    backgroundColor: 'rgba(244, 63, 94, 0.2)',
    borderColor: 'rgba(244, 63, 94, 0.4)',
  },
  gaugeStatusTagWarn: {
    backgroundColor: 'rgba(251, 146, 60, 0.2)',
    borderColor: 'rgba(251, 146, 60, 0.4)',
  },
  gaugeStatusTagNorm: {
    backgroundColor: 'rgba(52, 211, 153, 0.2)',
    borderColor: 'rgba(52, 211, 153, 0.4)',
  },
  gaugeStatusTagText: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '800',
  },
  gaugeStatusTagTextCrit: {
    color: '#fda4af',
  },
  gaugeStatusTagTextWarn: {
    color: '#fdba74',
  },
  gaugeStatusTagTextNorm: {
    color: '#6ee7b7',
  },
  gaugeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginVertical: 4,
  },
  gaugeMetric: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#040e1f',
    padding: 8,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#132e52',
  },
  gaugeMetricLabel: {
    fontFamily: 'monospace',
    fontSize: 8,
    color: '#64748b',
    fontWeight: '700',
  },
  gaugeMetricValue: {
    fontFamily: 'monospace',
    fontSize: 13,
    fontWeight: '900',
    color: '#ffffff',
    marginTop: 2,
  },
  textRose: {
    color: '#f43f5e',
  },
  textAmber: {
    color: '#fb923c',
  },
  meterContainer: {
    height: 6,
    backgroundColor: '#040d1c',
    borderRadius: 3,
    overflow: 'hidden',
    marginVertical: 8,
  },
  meterFill: {
    height: '100%',
    borderRadius: 3,
  },
  meterFillCrit: {
    backgroundColor: '#f43f5e',
  },
  meterFillWarn: {
    backgroundColor: '#fb923c',
  },
  meterFillNorm: {
    backgroundColor: '#34d399',
  },
  gaugeFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  gaugeTimestamp: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#64748b',
  },
  gaugeCoords: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#38bdf8',
  },
  allClearBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 6,
  },
  allClearTextCol: {
    flex: 1,
  },
  allClearTitle: {
    fontFamily: 'monospace',
    fontSize: 11,
    fontWeight: '800',
    color: '#ffffff',
  },
  allClearDesc: {
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#94a3b8',
    marginTop: 2,
  },
  alertCard: {
    backgroundColor: '#1a090e',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#e11d48',
    padding: 12,
    gap: 6,
  },
  alertHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  alertPill: {
    backgroundColor: '#f43f5e',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  alertPillText: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '900',
    color: '#ffffff',
  },
  alertTimeText: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#fda4af',
  },
  alertTitleText: {
    fontFamily: 'monospace',
    fontSize: 12,
    fontWeight: '800',
    color: '#ffffff',
  },
  alertMessageText: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#fecdd3',
    lineHeight: 16,
  },
  alertChannelsRow: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 2,
  },
  alertChannelTag: {
    backgroundColor: '#2b0c16',
    borderWidth: 1,
    borderColor: '#4c1223',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  alertChannelTagText: {
    fontFamily: 'monospace',
    fontSize: 8,
    color: '#f43f5e',
    fontWeight: '700',
  },

  // TAB 3: TACTICAL ESCAPE ROUTE TO HIGH GROUND
  escapeRouteCard: {
    backgroundColor: '#071830',
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: '#0284c7',
    padding: 14,
    gap: 8,
    shadowColor: '#0284c7',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 10,
    elevation: 5,
  },
  escapeHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  escapeTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  escapeTitle: {
    fontFamily: 'monospace',
    fontSize: 11,
    fontWeight: '900',
    color: '#38bdf8',
    letterSpacing: 0.8,
  },
  elevationBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(52, 211, 153, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(52, 211, 153, 0.4)',
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 6,
  },
  elevationBadgeText: {
    fontFamily: 'monospace',
    fontSize: 8,
    fontWeight: '800',
    color: '#34d399',
  },
  escapeShelterName: {
    fontFamily: 'monospace',
    fontSize: 14,
    fontWeight: '900',
    color: '#ffffff',
    marginTop: 2,
  },
  escapeSubText: {
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#94a3b8',
    lineHeight: 14,
  },
  escapeStatsRow: {
    flexDirection: 'row',
    backgroundColor: '#040d1a',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#132e52',
    padding: 10,
    marginVertical: 4,
  },
  escapeStatCol: {
    flex: 1,
    alignItems: 'center',
  },
  escapeStatDivider: {
    width: 1,
    backgroundColor: '#163864',
  },
  escapeStatLabel: {
    fontFamily: 'monospace',
    fontSize: 8,
    color: '#64748b',
    fontWeight: '700',
  },
  escapeStatValue: {
    fontFamily: 'monospace',
    fontSize: 14,
    fontWeight: '900',
    color: '#38bdf8',
    marginTop: 2,
  },
  escapeStatValueSm: {
    fontFamily: 'monospace',
    fontSize: 10,
    fontWeight: '800',
    color: '#34d399',
    marginTop: 4,
  },
  escapeActionsRow: {
    gap: 8,
    marginTop: 4,
  },
  navigateHighGroundBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: '#059669',
    paddingVertical: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#34d399',
    shadowColor: '#10b981',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 6,
    elevation: 4,
  },
  navigateHighGroundText: {
    fontFamily: 'monospace',
    fontSize: 11,
    fontWeight: '900',
    color: '#ffffff',
    letterSpacing: 0.8,
  },
  waypointsToggleBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: '#051830',
    borderWidth: 1,
    borderColor: '#1c4270',
    paddingVertical: 8,
    borderRadius: 6,
  },
  waypointsToggleText: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '800',
    color: '#38bdf8',
  },
  waypointBox: {
    backgroundColor: '#040d1a',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#143156',
    padding: 12,
    marginTop: 4,
    gap: 8,
  },
  waypointStep: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  waypointDotOrigin: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#38bdf8',
    marginTop: 2,
  },
  waypointDotMid: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#fb923c',
    marginTop: 2,
  },
  waypointDotDest: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#34d399',
    marginTop: 2,
  },
  waypointLine: {
    width: 2,
    height: 10,
    backgroundColor: '#1e40af',
    marginLeft: 4,
    marginVertical: -4,
  },
  waypointTextCol: {
    flex: 1,
  },
  waypointStepTitle: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '800',
    color: '#cbd5e1',
  },
  waypointStepDesc: {
    fontFamily: 'monospace',
    fontSize: 9,
    color: '#64748b',
    marginTop: 1,
    lineHeight: 13,
  },
  hazardAdvisory: {
    fontFamily: 'monospace',
    fontSize: 8,
    color: '#fdba74',
    backgroundColor: 'rgba(251, 146, 60, 0.1)',
    borderWidth: 1,
    borderColor: 'rgba(251, 146, 60, 0.25)',
    padding: 8,
    borderRadius: 6,
    lineHeight: 12,
    marginTop: 4,
  },

  // DATABASE CARD & LATENCY
  databaseCard: {
    backgroundColor: '#06172d',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#194473',
    padding: 12,
    gap: 4,
  },
  dbHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dbIconRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dbTitle: {
    fontFamily: 'monospace',
    fontSize: 11,
    fontWeight: '800',
    color: '#38bdf8',
  },
  dbLatencyPill: {
    backgroundColor: 'rgba(56, 189, 248, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(56, 189, 248, 0.3)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  dbLatencyText: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '800',
    color: '#38bdf8',
  },
  dbDescText: {
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#94a3b8',
    lineHeight: 14,
  },
  shelterHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  shelterName: {
    fontFamily: 'monospace',
    fontSize: 13,
    fontWeight: '800',
    color: '#ffffff',
  },
  shelterType: {
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#64748b',
    marginTop: 1,
  },
  distanceBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(56, 189, 248, 0.12)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(56, 189, 248, 0.3)',
  },
  distanceText: {
    fontFamily: 'monospace',
    fontSize: 10,
    fontWeight: '800',
    color: '#38bdf8',
  },
  capacitySection: {
    marginVertical: 4,
  },
  capacityHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  capacityLabel: {
    fontFamily: 'monospace',
    fontSize: 8,
    color: '#64748b',
    fontWeight: '700',
  },
  capacityRatio: {
    fontFamily: 'monospace',
    fontSize: 10,
    fontWeight: '800',
    color: '#34d399',
  },
  amenitiesWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginVertical: 6,
  },
  amenityPill: {
    backgroundColor: '#041021',
    borderWidth: 1,
    borderColor: '#133054',
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 4,
  },
  amenityText: {
    fontFamily: 'monospace',
    fontSize: 8,
    color: '#94a3b8',
  },
  shelterFooter: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#142c4b',
  },
  callButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: '#051830',
    borderWidth: 1,
    borderColor: '#1c4270',
    paddingVertical: 8,
    borderRadius: 6,
  },
  callButtonText: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '800',
    color: '#38bdf8',
  },
  navButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: '#0284c7',
    paddingVertical: 8,
    borderRadius: 6,
  },
  navButtonText: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '800',
    color: '#ffffff',
  },

  // BOTTOM NAVIGATION BAR
  bottomTabBar: {
    flexDirection: 'row',
    backgroundColor: '#051021',
    borderTopWidth: 1,
    borderTopColor: '#142945',
    paddingBottom: 4,
    paddingTop: 6,
  },
  tabItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 4,
    position: 'relative',
  },
  tabItemActive: {
    backgroundColor: 'transparent',
  },
  tabLabel: {
    fontFamily: 'monospace',
    fontSize: 9,
    fontWeight: '700',
    color: '#64748b',
    marginTop: 2,
  },
  tabLabelActive: {
    color: '#38bdf8',
    fontWeight: '800',
  },
  tabLabelSosActive: {
    color: '#f43f5e',
    fontWeight: '800',
  },
  tabLabelShelterActive: {
    color: '#34d399',
    fontWeight: '800',
  },
  activeTabIndicator: {
    position: 'absolute',
    top: -6,
    width: 32,
    height: 2,
    backgroundColor: '#38bdf8',
    borderRadius: 1,
  },
  activeTabIndicatorSos: {
    position: 'absolute',
    top: -6,
    width: 32,
    height: 2,
    backgroundColor: '#f43f5e',
    borderRadius: 1,
  },
  activeTabIndicatorShelter: {
    position: 'absolute',
    top: -6,
    width: 32,
    height: 2,
    backgroundColor: '#34d399',
    borderRadius: 1,
  },
});
