import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert as RNAlert, AppState, Pressable, ScrollView, StatusBar,
  StyleSheet, Text, View,
} from 'react-native';
import * as Location from 'expo-location';
import {
  API_BASE, ApiError, getAlerts, getHealth, getHistoricalEvents, getHospitals,
  getLatestForecast, getLocations, getMyRequests, getObservedExtent, getProfile,
  getShelters, login, register, restoreSession, signOut, submitHelpRequest,
  type AlertRecord, type AssistanceRecord, type CitizenProfile, type Facility,
  type FloodEvent, type Forecast, type LocationRecord, type ExtentFeature,
} from './src/api';
import { exteriorRings, geometryCenter, pointFromFacility } from './src/geo';
import { MapViewFallback, type MapMarker, type MapPolygon } from './src/MapViewFallback';
import {
  Action, Banner, C, Field, Heading, Label, Panel, Pill,
  Placeholder, evidenceAge, formatUtc,
} from './src/ui';

type Screen = 'area' | 'forecast' | 'map' | 'alerts' | 'places' | 'help' | 'requests' | 'safety' | 'account';
const NAV: { id: Screen; title: string }[] = [
  { id: 'area', title: 'My area' }, { id: 'forecast', title: 'Forecast' },
  { id: 'map', title: 'Risk map' }, { id: 'alerts', title: 'Alerts' },
  { id: 'places', title: 'Safe places' }, { id: 'help', title: 'Request help' },
  { id: 'requests', title: 'My requests' }, { id: 'safety', title: 'Safety' },
  { id: 'account', title: 'Account' },
];

const TEST_SOS_ALLOWED = process.env.EXPO_PUBLIC_ENABLE_TEST_SOS === 'true';
function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Request failed. Check connection and try again.';
}
function ErrorPanel({ message, retry }: { message: string; retry?: () => void }) {
  return <Panel>
    <Label style={{ color: C.red }}>{message}</Label>
    {retry && <Action title="Try again" secondary onPress={retry} />}
  </Panel>;
}

function AccountScreen({ profile, onAuth }: {
  profile: CitizenProfile | null; onAuth: (p: CitizenProfile | null) => void;
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async () => {
    if (busy) return;
    if (!email.includes('@') || password.length < 8) { setError('Enter a valid email and a password of at least 8 characters.'); return; }
    setBusy(true); setError('');
    try {
      const result = mode === 'login'
        ? await login(email, password)
        : await register(email, password, fullName, consent);
      setPassword('');
      onAuth(result);
    } catch (err) { setError(errorText(err)); }
    finally { setBusy(false); }
  };
  if (profile) return <View style={styles.stack}>
    <Heading>Citizen account</Heading>
    <Panel>
      <Label>{profile.full_name || 'Citizen'}</Label>
      <Label muted>{profile.email}</Label>
      <Pill>ROLE: {profile.role.toUpperCase()}</Pill>
      <Label muted>Notice consent: {profile.contact_consent ? 'Enabled' : 'Not enabled'}</Label>
      <Label muted>Session token stored in device encrypted storage.</Label>
    </Panel>
    <Action title="Sign out" secondary onPress={() => { void signOut().then(() => onAuth(null)); }} />
  </View>;

  return <View style={styles.stack}>
    <Heading>{mode === 'login' ? 'Citizen sign in' : 'Create citizen account'}</Heading>
    <Banner>Public map and forecast views do not require an account. Sign in to submit and view your own test assistance reports.</Banner>
    <Panel>
      {mode === 'register' && <Field label="Name (optional)" value={fullName} onChangeText={setFullName} autoCapitalize="words" />}
      <Field label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" autoComplete="email" />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete={mode === 'register' ? 'new-password' : 'current-password'} />
      {mode === 'register' && <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: consent }} onPress={() => setConsent(!consent)}>
        <Label>{consent ? '☑' : '☐'} Optional consent to emergency contact notices (not needed to register)</Label>
      </Pressable>}
      {error && <Label style={{ color: C.red }}>{error}</Label>}
      <Action title={mode === 'login' ? 'Sign in' : 'Register as citizen'} busy={busy} onPress={() => void submit()} />
      <Action title={mode === 'login' ? 'Create account' : 'I already have an account'} secondary onPress={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }} />
    </Panel>
  </View>;
}

function MyAreaScreen({ selectedId, setSelectedId, locations, setLocations, go }: {
  selectedId: string; setSelectedId: (v: string) => void;
  locations: LocationRecord[]; setLocations: (v: LocationRecord[]) => void;
  go: (s: Screen) => void;
}) {
  const [health, setHealth] = useState<string>('Checking backend…');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    setBusy(true); setError('');
    const [healthRes, locationRes] = await Promise.allSettled([getHealth(), getLocations()]);
    setHealth(healthRes.status === 'fulfilled'
      ? `FastAPI ${healthRes.value.status} · Database ${healthRes.value.database?.connected ? 'connected' : 'unavailable'}`
      : 'Backend unreachable (server may be starting)');
    if (locationRes.status === 'fulfilled') {
      setLocations(locationRes.value);
      if (locationRes.value.length > 0) {
        setSelectedId(locationRes.value[0].id);
      }
    } else { setError(errorText(locationRes.reason)); }
    setBusy(false);
  }, [setLocations, setSelectedId]);
  useEffect(() => { void refresh(); }, [refresh]);
  const selected = locations.find(l => l.id === selectedId);
  return <View style={styles.stack}>
    <Heading>My area</Heading>
    <Banner warning>Historical flood replay / prototype only. Not a live emergency warning system. Forecasts and maps may be missing or outdated.</Banner>
    <Panel>
      <Label muted>BACKEND</Label>
      <Label>{health}</Label>
      <Label muted>Device location is not accessed here. Select a mapped area explicitly.</Label>
      <Action title="Refresh locations" busy={busy} secondary onPress={() => void refresh()} />
    </Panel>
    {error && <ErrorPanel message={error} retry={() => void refresh()} />}
    <Label muted>Available mapped locations ({locations.length})</Label>
    {locations.length === 0 && !busy && !error && <Placeholder>No locations have been imported. Member 2's GIS package must be connected to FastAPI first.</Placeholder>}
    {locations.slice(0, 75).map(location => <Pressable
      key={location.id}
      onPress={() => setSelectedId(location.id)}
      style={[styles.pick, selectedId === location.id && styles.selected]}
    >
      <Label>{selectedId === location.id ? '◉ ' : '○ '}{location.name}</Label>
      <Label muted>{location.id} · Admin level {location.admin_level}</Label>
    </Pressable>)}
    {selected && <Panel>
      <Label>Selected: {selected.name}</Label>
      <Action title="View +1h / +3h / +6h forecast" onPress={() => go('forecast')} />
      <Action title="Explore historical flood map" secondary onPress={() => go('map')} />
    </Panel>}
  </View>;
}

function ForecastScreen({ location }: { location: LocationRecord | undefined }) {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const reload = useCallback(async () => {
    if (!location) return;
    setBusy(true); setError(''); setForecast(null);
    try { setForecast(await getLatestForecast(location.id)); }
    catch (err) { setError(errorText(err)); }
    finally { setBusy(false); }
  }, [location?.id]);
  useEffect(() => { void reload(); }, [reload]);
  return <View style={styles.stack}>
    <Heading>Flood outlook</Heading>
    {!location ? <Placeholder>Choose a mapped location under My area.</Placeholder> : <>
      <Panel><Label>{location.name}</Label>
        <Label muted>Source: FastAPI location ID {location.id}</Label>
        <Action title="Refresh forecast" onPress={() => void reload()} busy={busy} secondary />
      </Panel>
      {error && <ErrorPanel message={error} retry={() => void reload()} />}
      {!forecast && !busy && !error && <Placeholder>No issued forecast is available for this area.</Placeholder>}
      {forecast && <>
        <Banner warning>{forecast.mode.toUpperCase()} · Quality {forecast.data_quality}. A risk estimate is not a measured depth or a safe route.</Banner>
        <Panel>
          <Label muted>ISSUED AT · {formatUtc(forecast.issued_at)} · {evidenceAge(forecast.issued_at)}</Label>
          <Label>Model: {forecast.model_version}</Label>
          <Label muted>Forecast ID: {forecast.forecast_id}</Label>
        </Panel>
        {forecast.horizons.sort((a,b) => a.hours-b.hours).map(item => <Panel key={item.hours}>
          <View style={styles.between}>
            <Heading>+{item.hours} hours</Heading>
            <Pill color={item.risk_level.toLowerCase() === 'critical' ? C.red : C.yellow}>{item.risk_level.toUpperCase()}</Pill>
          </View>
          <Label muted>Calibrated probability: {item.calibrated_probability == null ? 'Not available' : `${Math.round(item.calibrated_probability * 100)}%`}</Label>
        </Panel>)}
        {forecast.limitations.length > 0 && <Panel><Label>Known limitations</Label>
          {forecast.limitations.map((limitation, i) => <Label key={i} muted>• {limitation}</Label>)}
        </Panel>}
      </>}
    </>}
  </View>;
}

function RiskMapScreen({ location }: { location: LocationRecord | undefined }) {
  const [events, setEvents] = useState<FloodEvent[]>([]);
  const [eventId, setEventId] = useState('');
  const [extent, setExtent] = useState<ExtentFeature | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    getHistoricalEvents().then(data => {
      if (!live) return;
      setEvents(data);
      setEventId(old => data.some(e => e.id === old) ? old : (data[0]?.id || ''));
    }).catch(err => { if (live) setError(errorText(err)); });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!eventId) return;
    let live = true; setLoading(true); setExtent(null); setError('');
    getObservedExtent(eventId).then(data => { if (live) setExtent(data); })
      .catch(err => { if (live) setError(errorText(err)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [eventId]);

  const rings = useMemo(() => exteriorRings(extent?.geometry), [extent?.geometry]);
  const center = useMemo(() => geometryCenter(rings) || geometryCenter(location?.geometry), [rings, location?.geometry]);

  // Simplify/cap polygons for performance: take up to 80 largest rings by point count
  const displayPolygons = useMemo((): MapPolygon[] => {
    if (!rings.length) return [];
    const sorted = [...rings].sort((a, b) => b.length - a.length).slice(0, 80);
    return sorted.map(r => ({
      coordinates: r,
      strokeColor: C.aqua,
      fillColor: 'rgba(20,179,191,0.28)',
      strokeWidth: 2,
    }));
  }, [rings]);

  const markers = useMemo((): MapMarker[] => {
    if (!location) return [];
    const locCenter = geometryCenter(location.geometry);
    if (!locCenter) return [];
    return [{
      coordinate: locCenter,
      title: location.name,
      description: 'Mapped location, not current GPS position',
      color: C.aqua,
    }];
  }, [location]);

  return <View style={styles.stack}>
    <Heading>Historical flood map</Heading>
    <Banner warning>The polygons below come from the backend's recorded historical satellite extent, not real-time flooding, forecast depth, or a navigation recommendation.</Banner>
    <Panel>
      <Label>Choose a historical event</Label>
      {events.length === 0 && <Label muted>No historical events have been imported.</Label>}
      {events.map(event => <Pressable
        accessibilityRole="button" key={event.id} onPress={() => setEventId(event.id)}
        style={[styles.pick, eventId === event.id && styles.selected]}
      >
        <Label>{eventId === event.id ? '◉ ' : '○ '}{event.name}</Label>
        <Label muted>{formatUtc(event.start_at)} · {event.mode}</Label>
      </Pressable>)}
    </Panel>
    {loading && <Label muted>Loading event-linked GeoJSON…</Label>}
    {error && <ErrorPanel message={error} />}
    {!loading && !extent && !error && <Placeholder>Select a historical event with an imported observed flood extent.</Placeholder>}
    {extent && <Panel>
      <Label>Mapped area: {extent.properties?.area_km2 ?? 'Unknown'} km²</Label>
      <Label muted>Observation: {formatUtc(extent.properties?.observed_at || '')}</Label>
      <Label muted>Method: {extent.properties?.method ?? 'Satellite'} · Confidence: {extent.properties?.confidence == null ? 'Not reported' : extent.properties.confidence.toFixed(2)}</Label>
      {rings.length === 0 && <Label style={{ color: C.yellow }}>The backend extent does not contain displayable polygons.</Label>}
    </Panel>}
    {center && rings.length > 0 ? <View style={styles.mapWrap}>
      <MapViewFallback
        key={eventId}
        center={center}
        polygons={displayPolygons}
        markers={markers}
      />
    </View> : <Placeholder>Map unavailable until a historical GeoJSON extent with valid coordinates is loaded.</Placeholder>}
    <Label muted>Visual-only interactive map. No suggested routes or real-time road safety guarantees.</Label>
  </View>;
}

function AlertsScreen() {
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const reload = useCallback(async () => {
    setLoading(true); setError('');
    try { setAlerts(await getAlerts()); }
    catch (err) { setError(errorText(err)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  return <View style={styles.stack}>
    <Heading>Public alerts</Heading>
    <Banner warning>Only backend-published public alerts are shown. The backend intentionally excludes historical/demo dispatches from the citizen feed. No Android push notifications are configured.</Banner>
    <Action title="Refresh alerts" secondary busy={loading} onPress={() => void reload()} />
    {error && <ErrorPanel message={error} retry={() => void reload()} />}
    {alerts.length === 0 && !loading && !error && <Placeholder>No public alerts available. This does not mean there is no flood risk.</Placeholder>}
    {alerts.map(a => <Panel key={a.id}>
      <Pill color={C.yellow}>{a.status.toUpperCase()} · {a.mode}</Pill>
      <Label>{a.title}</Label><Label>{a.message}</Label>
      <Label muted>Area ID: {a.area_id}</Label>
      <Label muted>Issued: {formatUtc(a.issued_at)} · {evidenceAge(a.issued_at || a.created_at)}</Label>
    </Panel>)}
  </View>;
}

function FacilitiesScreen() {
  const [shelters, setShelters] = useState<Facility[]>([]);
  const [hospitals, setHospitals] = useState<Facility[]>([]);
  const [notes, setNotes] = useState<string[]>([]);
  const [mode, setMode] = useState<'shelters' | 'hospitals'>('shelters');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const reload = useCallback(async () => {
    setLoading(true); setError('');
    const [sheltersResult, hospitalsResult] = await Promise.allSettled([getShelters(), getHospitals()]);
    if (sheltersResult.status === 'fulfilled') {
      setShelters(sheltersResult.value.shelters);
    } else if (sheltersResult.status === 'rejected') {
      setError(errorText(sheltersResult.reason));
    }
    if (hospitalsResult.status === 'fulfilled') {
      setHospitals(hospitalsResult.value.hospitals);
    } else if (hospitalsResult.status === 'rejected') {
      const hospitalError = errorText(hospitalsResult.reason);
      setError(previous => previous || hospitalError);
    }
    setNotes([
      sheltersResult.status === 'fulfilled' ? (sheltersResult.value.data_notes || '') : '',
      hospitalsResult.status === 'fulfilled' ? (hospitalsResult.value.data_notes || '') : '',
    ].filter(Boolean));
    setLoading(false);
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  const rows = mode === 'shelters' ? shelters : hospitals;
  const mapped = useMemo(() => rows.filter(f => pointFromFacility(f.latitude, f.longitude)), [rows]);

  const markers = useMemo((): MapMarker[] => {
    return mapped.map(f => ({
      id: f.id,
      coordinate: { latitude: f.latitude!, longitude: f.longitude! },
      title: f.name,
      description: `Verification: ${f.verification_status}`,
      color: f.verification_status === 'verified' ? C.green : C.yellow,
    }));
  }, [mapped]);

  const center = useMemo(() => {
    return markers.length > 0 ? markers[0].coordinate : null;
  }, [markers]);

  return <View style={styles.stack}>
    <Heading>Places and facilities</Heading>
    <Banner warning>Presence on this map is not proof that a facility is open, staffed, accessible or safe during a flood. Contact local authorities to confirm.</Banner>
    <View style={styles.two}>
      <View style={{ flex: 1 }}><Action title="Shelters" secondary={mode !== 'shelters'} onPress={() => setMode('shelters')} /></View>
      <View style={{ flex: 1 }}><Action title="Hospitals" secondary={mode !== 'hospitals'} onPress={() => setMode('hospitals')} /></View>
    </View>
    <Action title="Refresh facilities" busy={loading} secondary onPress={() => void reload()} />
    {error && <ErrorPanel message={error} retry={() => void reload()} />}
    {mapped.length > 0 && <View style={styles.mapWrap}>
      <MapViewFallback
        key={mode}
        center={center}
        markers={markers}
      />
    </View>}
    {rows.length === 0 && !error && !loading && <Placeholder>No facilities have been imported for this category.</Placeholder>}
    {rows.map(f => <Panel key={f.id}>
      <Label>{f.name}</Label>
      <Pill color={f.verification_status === 'verified' ? C.green : C.yellow}>VERIFICATION: {f.verification_status.toUpperCase()}</Pill>
      <Label muted>Last verified: {formatUtc(f.status_checked_at)}</Label>
      <Label muted>Capacity: {f.capacity ?? 'Unknown'} · Contact: {f.contact_info || 'Not available'}</Label>
      <Label muted>Data source: {f.source || 'Unspecified'}</Label>
      {f.limitations.map((lim, i) => <Label key={i} muted>• {lim}</Label>)}
    </Panel>)}
    {notes.map((n, i) => <Label key={i} muted>{n}</Label>)}
    <Banner>Routes are not calculated by the citizen app. Any evacuation route requires current hazard verification and official guidance.</Banner>
  </View>;
}

function HelpScreen({ profile, go, onSubmitted }: {
  profile: CitizenProfile | null; go: (s: Screen) => void; onSubmitted: () => void;
}) {
  const [category, setCategory] = useState<AssistanceRecord['category']>('evacuation');
  const [people, setPeople] = useState('1');
  const [details, setDetails] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [gpsBusy, setGpsBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const categories: AssistanceRecord['category'][] = ['evacuation', 'medical', 'food_water', 'shelter', 'other'];
  const getGps = async () => {
    setGpsBusy(true); setError('');
    try {
      const result = await Location.requestForegroundPermissionsAsync();
      if (result.status !== 'granted') { setError('Location permission denied. You can enter coordinates manually.'); return; }
      const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      setLatitude(position.coords.latitude.toFixed(6));
      setLongitude(position.coords.longitude.toFixed(6));
    } catch (err) { setError(errorText(err)); }
    finally { setGpsBusy(false); }
  };
  const submit = () => {
    if (busy) return;
    setError('');
    if (!profile) { go('account'); return; }
    if (!TEST_SOS_ALLOWED) { setError('Test submissions are disabled. Configure EXPO_PUBLIC_ENABLE_TEST_SOS=true only with an isolated demonstration backend.'); return; }
    const lat = Number(latitude), lon = Number(longitude), count = Number(people);
    if (!latitude.trim() || !longitude.trim() || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      setError('Enter valid latitude (-90 to 90) and longitude (-180 to 180), or choose Use device location.'); return;
    }
    if (!Number.isInteger(count) || count < 1 || count > 100) { setError('People count must be between 1 and 100.'); return; }
    RNAlert.alert('Confirm historical test request', 'This sends a TEST record to your configured FloodLens backend. It does NOT contact emergency services or dispatch rescue teams. Do not use it for real emergencies.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Submit test record', onPress: () => {
        if (busy) return;
        setBusy(true);
        void (async () => {
        try {
          await submitHelpRequest({
            latitude: lat, longitude: lon, people_count: count, category,
            details: `[FLOODLENS HISTORICAL TEST ONLY - NOT AN EMERGENCY] ${details.trim() || 'Demo assistance request'}`,
          });
          setDetails(''); onSubmitted(); go('requests');
        } catch (err) { setError(errorText(err)); }
        finally { setBusy(false); }
      })(); } },
    ]);
  };
  return <View style={styles.stack}>
    <Heading>Request help · test mode</Heading>
    <Banner warning>This prototype does not contact emergency services. In a real emergency, use official local emergency channels. Never rely on this app for rescue.</Banner>
    {!profile && <Panel><Label>Sign in as a citizen to submit and track requests.</Label>
      <Action title="Go to citizen account" onPress={() => go('account')} /></Panel>}
    {!TEST_SOS_ALLOWED && <Banner warning>Backend test submissions are disabled by default to prevent accidental operational records. This form can be enabled only for an isolated historical/test environment.</Banner>}
    <Panel>
      <Label>Type of help</Label>
      <View style={styles.wrap}>
        {categories.map(value => <Pressable key={value}
          accessibilityRole="button" accessibilityState={{ selected: category === value }}
          onPress={() => setCategory(value)}
          style={[styles.chip, category === value && styles.selected]}>
          <Label>{value.replace('_', ' ')}</Label>
        </Pressable>)}
      </View>
      <Field label="Number of people" value={people} onChangeText={setPeople} keyboardType="number-pad" />
      <Field label="Details (avoid names, phone numbers, and sensitive personal information)" value={details} onChangeText={setDetails} multiline numberOfLines={3} maxLength={400} placeholder="Describe the simulated assistance need" />
      <Action title="Use device location for this one test request" secondary busy={gpsBusy} onPress={() => void getGps()} />
      <Field label="Latitude" value={latitude} onChangeText={setLatitude} keyboardType="numbers-and-punctuation" placeholder="e.g. 26.65000" />
      <Field label="Longitude" value={longitude} onChangeText={setLongitude} keyboardType="numbers-and-punctuation" placeholder="e.g. 87.05000" />
      <Label muted>Coordinates are sent only when you confirm Submit. The app does not track your location in the background.</Label>
      {error && <Label style={{ color: C.red }}>{error}</Label>}
      <Action title="Review and submit TEST request" busy={busy} disabled={!profile || !TEST_SOS_ALLOWED} onPress={submit} />
    </Panel>
  </View>;
}

function MyRequestsScreen({ profile, refreshKey }: { profile: CitizenProfile | null; refreshKey: number }) {
  const [requests, setRequests] = useState<AssistanceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    if (!profile) { setRequests([]); return; }
    setLoading(true); setError('');
    try { setRequests(await getMyRequests()); }
    catch (err) { setError(errorText(err)); }
    finally { setLoading(false); }
  }, [profile?.id]);
  useEffect(() => { void refresh(); }, [refresh, refreshKey]);
  return <View style={styles.stack}>
    <Heading>My assistance requests</Heading>
    <Banner warning>Authenticated private request history from FastAPI. A database status update is not proof that responders are dispatched.</Banner>
    {!profile ? <Placeholder>Sign in as a citizen to view your own request history.</Placeholder> : <>
      <Action title="Refresh my requests" secondary busy={loading} onPress={() => void refresh()} />
      {error && <ErrorPanel message={error} retry={() => void refresh()} />}
      {!loading && !error && requests.length === 0 && <Placeholder>You have no submitted assistance requests.</Placeholder>}
      {requests.map(record => <Panel key={record.id}>
        <Label>Request {record.id}</Label>
        <Pill color={record.status === 'resolved' ? C.green : C.yellow}>{record.status.toUpperCase()}</Pill>
        <Label muted>Category: {record.category} · People: {record.people_count}</Label>
        <Label muted>Created: {formatUtc(record.created_at)}</Label>
        <Label muted>Last updated: {formatUtc(record.updated_at)}</Label>
        <Label>{record.status_notes || 'No officer notes recorded.'}</Label>
        <Label muted>Assigned responder: {record.assigned_to || 'Not recorded'}</Label>
      </Panel>)}
    </>}
  </View>;
}

function SafetyScreen() {
  return <View style={styles.stack}>
    <Heading>Safety and help</Heading>
    <Banner warning>FloodLens is an educational historical-replay prototype. It is not an operational warning, evacuation, or rescue service.</Banner>
    <Panel><Label>In a real flood emergency</Label>
      <Label>• Follow local emergency-management and meteorological authority announcements.</Label>
      <Label>• Do not enter or attempt to cross moving floodwater, even if it appears shallow.</Label>
      <Label>• If instructed to evacuate, follow official instructions rather than routes estimated by this prototype.</Label>
      <Label>• Contact the official emergency service for your location. FloodLens does not place calls or dispatch responders.</Label>
    </Panel>
    <Panel><Label>Data limitations</Label>
      <Label muted>Forecasts are model estimates and may be missing or stale. Historical satellite flood polygons show observations from a past event, not current flood depth or road safety. Shelter operating status must be confirmed directly.</Label>
    </Panel>
    <Panel><Label>Privacy</Label>
      <Label muted>Device location permission is requested only when you tap the location button; the app never requests background location. Passwords are not stored. Login tokens use Android secure storage. Test assistance requests include coordinates, which the backend restricts to authorized responders.</Label>
    </Panel>
  </View>;
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('area');
  const [profile, setProfile] = useState<CitizenProfile | null>(null);
  const [locations, setLocations] = useState<LocationRecord[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [init, setInit] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        if (await restoreSession()) {
          const loggedIn = await getProfile();
          if (live && loggedIn.role === 'citizen') setProfile(loggedIn);
          else await signOut();
        }
      } catch {
        await signOut();
      } finally { if (live) setInit(false); }
    })();
    return () => { live = false; };
  }, []);
  useEffect(() => {
    const sub = AppState.addEventListener('change', state => {
      if (state === 'active') setRefreshKey(k => k + 1);
    });
    return () => sub.remove();
  }, []);
  const selected = locations.find(l => l.id === selectedId);
  const changeScreen = (next: Screen) => { setScreen(next); };
  const onAuth = (next: CitizenProfile | null) => {
    setProfile(next);
    if (next) changeScreen('requests');
    else changeScreen('area');
  };
  return <View style={styles.root}>
    <StatusBar barStyle="light-content" />
    <View style={styles.header}>
      <View style={styles.between}>
        <Text style={styles.brand}>◉ FLOODLENS <Text style={{ color: C.aqua }}>CITIZEN</Text></Text>
        <Text style={styles.tiny}>HISTORICAL · TEST</Text>
      </View>
      <Text style={styles.headerSub}>Flood intelligence prototype · No real-time rescue dispatch</Text>
    </View>
    <ScrollView horizontal showsHorizontalScrollIndicator={false}
      style={{ flexGrow: 0, borderBottomColor: C.border, borderBottomWidth: 1 }}
      contentContainerStyle={styles.navigation}>
      {NAV.map(item => <Pressable key={item.id} onPress={() => changeScreen(item.id)}
        accessibilityRole="tab" accessibilityState={{ selected: screen === item.id }}
        style={[styles.navItem, screen === item.id && styles.activeNav]}>
        <Text style={{ color: screen === item.id ? C.aqua : C.muted, fontWeight: '700', fontSize: 12 }}>{item.title}</Text>
      </Pressable>)}
    </ScrollView>
    <ScrollView key={screen} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
      {init ? <Placeholder>Checking saved citizen session…</Placeholder> : <>
        {screen === 'area' && <MyAreaScreen selectedId={selectedId} setSelectedId={setSelectedId} locations={locations} setLocations={setLocations} go={changeScreen} />}
        {screen === 'forecast' && <ForecastScreen location={selected} />}
        {screen === 'map' && <RiskMapScreen location={selected} />}
        {screen === 'alerts' && <AlertsScreen />}
        {screen === 'places' && <FacilitiesScreen />}
        {screen === 'help' && <HelpScreen profile={profile} go={changeScreen} onSubmitted={() => setRefreshKey(k => k + 1)} />}
        {screen === 'requests' && <MyRequestsScreen profile={profile} refreshKey={refreshKey} />}
        {screen === 'safety' && <SafetyScreen />}
        {screen === 'account' && <AccountScreen profile={profile} onAuth={onAuth} />}
      </>}
      <View style={styles.footer}>
        <Text style={styles.footerText}>FloodLens historical-replay prototype · Never use as an emergency service.</Text>
        <Text style={styles.footerText}>API: {API_BASE}</Text>
      </View>
    </ScrollView>
  </View>;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg, paddingTop: StatusBar.currentHeight || 25 },
  header: { paddingHorizontal: 18, paddingTop: 12, paddingBottom: 14, gap: 6 },
  between: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 },
  brand: { color: C.text, fontSize: 20, fontWeight: '900', letterSpacing: 0.7 },
  tiny: { color: C.yellow, fontSize: 9, fontWeight: '800' },
  headerSub: { color: C.muted, fontSize: 12 },
  navigation: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, gap: 5, paddingVertical: 7 },
  navItem: { paddingHorizontal: 13, paddingVertical: 10, borderRadius: 100 },
  activeNav: { backgroundColor: '#173a4d' },
  content: { padding: 16, gap: 24, paddingBottom: 44 },
  stack: { gap: 13 },
  pick: { padding: 12, gap: 5, borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.surface },
  selected: { borderColor: C.aqua, backgroundColor: '#104056' },
  two: { flexDirection: 'row', gap: 10 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingVertical: 7, paddingHorizontal: 10, borderRadius: 10, backgroundColor: C.surface, borderColor: C.border, borderWidth: 1 },
  mapWrap: { height: 300, borderColor: C.border, borderRadius: 14, borderWidth: 1, overflow: 'hidden', backgroundColor: C.surface },
  footer: { paddingTop: 14, borderTopWidth: 1, borderColor: C.border, gap: 5 },
  footerText: { fontSize: 10, color: C.muted },
});
