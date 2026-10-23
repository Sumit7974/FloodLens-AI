# FloodLens AI — Android Citizen App Final Validation

## 1. Overview & Framework Versions

This document details the final validation of the **FloodLens AI Android Citizen Application** for the historical-demo hackathon. The application is built using Expo SDK 58 and React Native, providing a citizen-facing mobile portal to monitor flood risks, view historical satellite extents, inspect verified facilities, and submit test assistance requests against the FastAPI backend.

| Component | Target / Installed Version | Status |
|:---|:---|:---|
| **Expo SDK** | `~58.0.17` (Expo SDK 58) | Validated |
| **React Native** | `0.88.0` | Validated |
| **React** | `19.3.0` | Validated |
| **TypeScript** | `~6.0.3` (installed `6.0.3`) | Aligned with Expo SDK 58 requirement |
| **Expo Location** | `~58.0.14` | Validated (foreground only) |
| **Expo SecureStore**| `~58.0.2` | Validated (encrypted token storage) |
| **React Native Maps**| `1.29.11` | Validated |
| **Package ID** | `ai.floodlens.citizen` | Preserved |

---

## 2. Expo Compatibility & Configuration Audit

An initial audit with `npx expo-doctor` identified two configuration and dependency issues:
1. **Unsupported Property**: `android.usesCleartextTraffic: true` in `mobile/app.json`.
   - **Resolution**: Removed the deprecated/invalid `usesCleartextTraffic` field from `mobile/app.json`. Production traffic must use secure HTTPS endpoints. Cleartext bypass is not permitted in release builds.
2. **TypeScript Version Mismatch**: `typescript: ~5.9.3` vs expected `~6.0.3`.
   - **Resolution**: Aligned `typescript` to `~6.0.3` using `npx expo install --fix`, updating `package.json` and `package-lock.json` for reproducible installations.
3. **Deprecated Architecture Flag**: Removed `newArchEnabled` top-level field from `app.json` (New Architecture is enabled by default in SDK 58).

### Validation Run:
- **`npx expo install --check`**: `Dependencies are up to date` (0 errors)
- **`npx expo-doctor`**: `20/20 checks passed. No issues detected!` (0 warnings/failures)

---

## 3. Backend API & Networking Architecture

### Configuration
The app uses dynamic API resolution defined in `mobile/src/api/client.ts`:
```typescript
export const PRODUCTION_API_URL = 'https://floodlens-backend-4pt5.onrender.com';
const DEFAULT_ENV_API_URL = (process.env.EXPO_PUBLIC_API_URL || PRODUCTION_API_URL).trim().replace(/\/+$/, '');
```
- **Live Deployed Cloud (Render)**: Defaults to `https://floodlens-backend-4pt5.onrender.com` (enforcing HTTPS encryption over the wire).
- **Android Emulator**: Supports `http://10.0.2.2:8000`, routing from the Android emulator loopback to the host FastAPI service.
- **Physical Device / Local Wi-Fi LAN**: Supports `EXPO_PUBLIC_API_URL=http://<HOST_IP>:8000` or reverse ADB port forwarding (`adb reverse tcp:8000 tcp:8000`).
- **Transparency**: The active API endpoint is visibly rendered with real-time latency probing in the application header and network settings modal.

---

## 4. Tested Citizen Features & Workflows

### A. Citizen Authentication
- **Endpoints**: `POST /auth/login`, `POST /auth/register`, `GET /auth/me`.
- **Role Enforcement**: The citizen application strictly verifies `result.role === 'citizen'`. Non-citizen accounts are rejected with clear instructional feedback.
- **Secure Token Storage**: The bearer token is saved to device hardware-backed secure storage via `expo-secure-store` using the key `floodlens_demo_citizen_token`.
- **Session Lifecycle**: On cold start, `restoreSession()` retrieves the stored token and validates the profile via `/auth/me`. If the session is invalid or returns HTTP 401, `signOut()` cleanly purges the keystore entry and returns the user to the unauthenticated view.
- **Credentials Security**: No hardcoded passwords, tokens, or JWT secrets exist in the mobile code.

### B. Location Selection & Flood Outlook (Forecasts)
- **Endpoints**: `GET /locations`, `GET /predictions/latest?location_id=<id>`.
- **Location Discovery**: Citizens select an imported administrative area or settlement from `/locations` without requiring GPS activation.
- **Multi-Horizon Risk**: Displays +1h, +3h, and +6h risk levels (e.g. `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), calibrated probabilities (`calibrated_probability * 100%`), issued timestamps, model version, and forecast limitations.
- **Simulation Disclaimer**: Prominently warns that the outlook is a prototype model estimate and must not be treated as a live measured water depth or verified evacuation route. Static placeholder risk values are never substituted for real inference. Missing forecasts display an explicit `No issued forecast is available for this area` state.

### C. Historical Risk Mapping
- **Endpoints**: `GET /flood-events`, `GET /flood-events/{id}/extent/geojson`.
- **GeoJSON Parsing**: Parses 2D MultiPolygon / Polygon geometries with `parseRing()` and centers the view using bounding-box midpoint calculation (`geometryCenter()`).
- **Historical Demarcation**: Explicitly labels extents as historical satellite observations from past flood events (e.g. 2020 historical replay), distinguishing them from real-time flooding.

### D. Safe Places & Facilities
- **Endpoints**: `GET /facilities/shelters`, `GET /facilities/hospitals`.
- **Display**: Lists verified and unverified shelters and hospitals with verification status, operating capacity, and contact information.
- **Warning**: Advises that listed locations may not be safely reachable without official civil protection clearance.

### E. Assistance Requests (Test SOS Mode)
- **Endpoints**: `POST /assistance`, `GET /assistance/mine`.
- **Safety Safeguard**: By default, `TEST_SOS_ALLOWED` is disabled (`process.env.EXPO_PUBLIC_ENABLE_TEST_SOS === 'true'`). When disabled, the UI informs the citizen that assistance submissions are disabled to prevent operational pollution.
- **Review & Confirmation**: Prior to dispatching an HTTP request, a native confirmation modal explicitly states: *"This sends a TEST record to your configured FloodLens backend. It does NOT contact emergency services or dispatch rescue teams."*
- **Payload Sanitization**: Automatic prefix injection ensures every record is tagged: `[FLOODLENS HISTORICAL TEST ONLY - NOT AN EMERGENCY]`.
- **Duplicate Tap Protection**: Submit handlers are debounced and check `if (busy) return;` at entry, preventing accidental double-taps from generating multiple backend records.
- **Private Request History**: Submissions return an assistance identifier. The citizen can monitor status progression (`PENDING`, `IN_PROGRESS`, `RESOLVED`) under "My assistance requests" (`GET /assistance/mine`).

---

## 5. Location Permissions & Citizen Privacy

1. **Foreground-Only Permissions**:
   - Manifest declares `ACCESS_COARSE_LOCATION` and `ACCESS_FINE_LOCATION`.
   - **No Background Tracking**: `ACCESS_BACKGROUND_LOCATION` is neither declared nor requested.
2. **On-Demand Access**:
   - Location is queried only when the citizen explicitly presses "Use device location for this one test request".
3. **Denial Resilience**:
   - If location permission is denied by the user, the app presents a clear notice and allows manual coordinate entry. Mapped areas, forecasts, historical maps, and facilities remain fully operable.
4. **Coordinate Privacy**:
   - Sensitive coordinates are transmitted only on explicit test submission over TLS to authorized emergency responder queues in FastAPI. They are excluded from public alert feeds and logs.

---

## 6. Android Quality Checks & CI Commands

The following commands were executed in the `mobile/` workspace:

| Step | Command | Result |
|:---|:---|:---|
| 1. Reproducible Install | `npm ci` | **PASS** (added 463 packages, lockfile in sync) |
| 2. Dependency Check | `npx expo install --check` | **PASS** (Dependencies are up to date) |
| 3. Configuration Audit | `npx expo-doctor` | **PASS** (20/20 checks passed) |
| 4. TypeScript Validation | `npm run typecheck` (`tsc --noEmit`) | **PASS** (0 errors) |
| 5. Android Export | `npm run export` (`expo export --platform android`) | **PASS** (Hermes bytecode bundle 1.7MB generated) |
| 6. Backend Contracts | `pytest backend/tests/test_auth.py backend/tests/test_contracts.py backend/tests/test_day3_alerts_assistance.py` | **PASS** (31/31 passed) |

---

## 7. Device Testing Status & Limitations

### Physical Device / Emulator Status: **BLOCKED**
- **Reason**: No physical Android hardware device or running Android emulator is attached to the local host environment (`adb` is not installed on PATH).
- **Honest Assessment**: While the Metro bundler and Hermes JavaScript bytecode export pass with zero errors, physical device installation (APK/AAB deployment, GPU map canvas rendering, and touch performance) cannot be claimed without a connected hardware device or emulator.

### Remaining Limitations:
1. **Test SOS Inactive by Default**: Operational safeguard requires `EXPO_PUBLIC_ENABLE_TEST_SOS=true` in `.env` to activate test submissions.
2. **Google Maps API Key**: Release standalone APK builds (`eas build -p android`) will require a configured Google Maps API key in `app.json` (`android.config.googleMaps.apiKey`) for Google Play Services map tile rendering on Android.
3. **Push Notifications**: Live alert broadcast push notifications are not configured (polling/pull-to-refresh is used).
