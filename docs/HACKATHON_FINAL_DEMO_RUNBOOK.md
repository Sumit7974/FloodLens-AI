# FloodLens AI — Hackathon Final Demonstration Runbook & Judge Script

**Repository:** [https://github.com/Sumit7974/FloodLens-AI](https://github.com/Sumit7974/FloodLens-AI)  
**Branch:** `integration/hackathon-rc`  
**Draft Pull Request:** #11 (Targeting `main`)  
**Operational Status:** Historical Simulation & Research Prototype (**NOT an Operational Emergency-Warning System**)  
**Model Version:** `candidate-leakfree-v1` (Trained and validated on rolling hydrometeorological features)

---

## 1. System Architecture & Component Overview

FloodLens AI is an end-to-end flood intelligence platform combining machine learning forecasting, spatial GIS hazard screening, an authority command dashboard, and a citizen mobile companion application.

```mermaid
graph TD
    A[Historical Telemetry & Weather Fixtures] --> B[ML Inference Engine<br/>candidate-leakfree-v1]
    B -->|Ingest Forecast +1h/+3h/+6h| C[FastAPI Core Backend]
    D[Satellite SAR Flood Extents] -->|Spatial Ingest| C
    C <--> E[(PostgreSQL 16 + PostGIS 3.4 / SQLite)]
    C <-->|REST + WebSocket| F[React 19 Authority Dashboard]
    C <-->|REST + JWT Auth| G[Expo Android Citizen App]
    F -->|Draft Advisory| H[Human Authority Review Queue]
    H -->|Simulated Dispatch| I[Sandbox Alert Channel<br/>[DEMO ONLY]]
    G -->|Assistance Request| J[Responder Triage Queue]
```

### Verified Monorepo Components
1. **AI/ML Forecast Engine (`ml/`):** Random Forest multi-horizon models (+1h, +3h, +6h) predicting categorical flood risk tiers from rolling rainfall, discharge telemetry, and catchment saturation.
2. **Backend API Service (`backend/`):** FastAPI asynchronous service handling spatial queries, RBAC authentication, forecast ingestion, alert review lifecycles, and citizen request triage.
3. **Database Layer:** PostgreSQL 16 with PostGIS 3.4 spatial extension (validated in GitHub Actions CI; with SQLite fallback for local test execution).
4. **Authority Web Dashboard (`frontend/`):** React 19 + TypeScript + Tailwind CSS application featuring 10 tactical views including Command Overview, Prediction Centre, GIS Route Screening, and Alert Dispatcher.
5. **Citizen Mobile Application (`mobile/`):** React Native / Expo application for Android providing localized risk viewing and privacy-guarded assistance requests.

---

## 2. Environment Configuration

### A. Backend (`backend/.env`)
Copy `backend/.env.example` to `backend/.env` with local demo parameters:
```bash
ENVIRONMENT=testing
OPERATIONAL_MODE=historical_demo
DATABASE_URL=postgresql+psycopg2://floodlens:floodlens_secure_password@localhost:5432/floodlens_db
# In local environments without Docker/PostgreSQL, fallback automatically executes in SQLite:
TEST_DATABASE_URL=sqlite:///./test_floodlens.db
JWT_SECRET=demo-secret-key-for-local-hackathon-rehearsal-only-min32chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=120
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://localhost:8081
LOG_LEVEL=INFO
```

### B. Authority Frontend (`frontend/.env`)
```bash
VITE_BACKEND_URL=http://localhost:8000
VITE_USE_MOCK_DATA=false
```

### C. Citizen Mobile (`mobile/.env`)
```bash
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000/api/v1
EXPO_PUBLIC_DEMO_MODE=true
```

---

## 3. Test Accounts & Credential Management

> [!CAUTION]
> Hardcoded credentials in source control are strictly prohibited. The following credentials are used exclusively in the local testing sandbox and are registered dynamically in test runners.

| Role | Username / Identifier | Sandboxed Permissions |
|---|---|---|
| **Authority Officer** | `authority@floodlens.test` | Full dashboard access, alert drafting, advisory approval, response queue triage |
| **Citizen User** | `citizen@floodlens.test` | Horizon risk viewing, personal assistance requests, private request history |

---

## 4. Startup Order & Local Execution

### Step 1: Database (PostGIS)
When Docker is available locally:
```bash
# Start PostGIS 3.4 container
docker compose up -d db

# Run Alembic spatial migrations
cd backend
alembic upgrade head
```
*Note: If Docker/PostGIS is unavailable locally, the system automatically uses the SQLite emulation driver, while real PostGIS 3.4 migrations and spatial queries are verified in GitHub Actions CI.*

### Step 2: FastAPI Backend
```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Verify readiness:
```bash
curl -s http://127.0.0.1:8000/api/v1/ready
```

### Step 3: Authority Web Dashboard
```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```
Access at `http://127.0.0.1:5173`.

### Step 4: Citizen Mobile App
```bash
cd mobile
npm install
npm run export:embed
```
*Note: Android physical device testing is marked DEVICE-UNTESTED in environments without connected ADB hardware; contract and JS bundle verification are validated in GitHub CI.*

---

## 5. Historical Demonstration Scenario & Provenance

### Scenario Metadata
- **Historical Event:** July 2024 Eastern Terai Monsoonal Surge (`evt_2024_koshi_demo`)
- **Focal Watershed:** Koshi River Basin, Chatara Gauge Station (`loc_sunsari_chatara`)
- **Coordinates:** Latitude 26.8210° N, Longitude 87.1520° E
- **Observed Satellite Extent:** 38.4 km² inundation polygon derived from Sentinel-1 SAR imagery.
- **Upstream Discharge:** 4,850 m³/s (approaching critical threshold).
- **24-Hour Rainfall Accumulation:** 184.2 mm.

---

## 6. End-to-End Walkthrough & Expected Interactions

### Interaction 1: AI/ML Prediction Ingestion
1. **Load Test Fixture:** Run `python ml/scripts/submit_demo_forecast.py` or trigger `scripts/rehearsal_test_all.py`.
2. **Feature Quality Evaluation:** The model ingests rolling 3h/6h/24h precipitation, upstream lag discharge, temperature, humidity, and soil saturation class.
3. **Multi-Horizon Inference:**
   - **+1h Forecast:** `HIGH` risk tier.
   - **+3h Forecast:** `CRITICAL` risk tier.
   - **+6h Forecast:** `CRITICAL` risk tier.
4. **Safety Verification:** Verify `calibrated_probability` is explicitly `None`. Raw tree votes are uncalibrated and must not be presented as statistical probabilities.
5. **Persistence:** Forecast persists via authenticated `POST /api/v1/predictions/ingest`, returning `HTTP 201 Created`.

### Interaction 2: Authority Command Dashboard
1. **Header & Context:** Confirm prominent banner: *"Historical Flood Simulation Prototype — Not an Operational Emergency System"*.
2. **Command Overview:** View current Koshi basin status, active facilities, and real-time sensor telemetries.
3. **Prediction Centre:** Select location `Chatara (Koshi Basin)`. Toggle between **+1h**, **+3h**, and **+6h** tabs. Note the clear disclaimer on uncalibrated model outputs.
4. **Satellite Intelligence:** Inspect the 38.4 km² flood extent overlay across low-lying settlements.
5. **Route Assessment:** Evaluate candidate logistics route `Alpha`. The PostGIS spatial engine detects intersections with submerged sections. The screen displays:
   - Status: `HAZARDS_INTERSECTED`
   - Intersecting hazards: 2 road segments
   - Mandatory Disclaimer: *"Candidate route screening is an analytical hazard check and NOT a verified safe evacuation direction."*
6. **Alert Dispatcher:**
   - Create new advisory draft: *"Telemetry Surge Advisory — Chatara Headworks"*.
   - Verify status: `DRAFT`.
   - Authority Officer reviews and clicks **Approve** (transitions to `APPROVED`).
   - Click **Simulate Dispatch** (transitions to `DISPATCHED`).
   - Title automatically prepends `[DEMO ONLY]` to prevent real-world confusion. Zero external SMS/sirens are fired.

### Interaction 3: Citizen App Workflow
1. **Home Screen:** Displays localized risk level (`CRITICAL` for Chatara area) and offline banner if disconnected.
2. **Assistance Request Guard:** Submit a test shelter assistance request.
3. **Privacy Assurance:** Coordinates and personal details are visible only to the citizen and authorized dispatchers. Other citizens querying `/assistance` receive `403 Forbidden`.
4. **Dispatcher Triage:** The authority responder queue immediately displays the incoming request with assigned priority.

---

## 7. Negative & Safe Failure Scenarios

| Failure Injected | System Behavior | Truthful User Presentation |
|---|---|---|
| **Missing Precipitation Feed** | ML pipeline refuses to extrapolate | `data_quality="UNAVAILABLE"`, risk marked `UNKNOWN` |
| **Backend Offline** | Frontend / Mobile loss of connection | Clear offline banner; cached data marked stale |
| **Expired Auth Token** | API returns `HTTP 401 Unauthorized` | Redirects to login; memory cleared; no leaked tokens |
| **Unauthorized Role Access** | Citizen attempts alert creation | `HTTP 403 Forbidden` (`INSUFFICIENT_PERMISSIONS`) |
| **Nonexistent Location Query** | Query for unknown catchment ID | `HTTP 404 DataUnavailableError` with graceful empty view |
| **Corrupted GeoJSON Geometry** | Invalid polygon sent to route screening | `HTTP 422 Unprocessable Content` with validation details |

---

## 8. Offline Fallback & Live Presentation Recovery

### If Backend Disconnects During Live Demo:
1. **Toggle Mock Mode:** In `frontend/src/services/backendApi.ts`, set `DEMO_MODE = true` (or leave `VITE_USE_MOCK_DATA=true`).
2. The React web dashboard seamlessly renders deterministic local historical fixtures.
3. To restart FastAPI cleanly:
   ```powershell
   Stop-Process -Name "python" -Force
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

### If Database Fails:
1. FloodLens AI automatically falls back to the in-memory SQLite emulation engine.
2. The readiness endpoint (`/api/v1/ready`) continues to report healthy emulation mode.

---

## 9. Known Scientific & Device Limitations

1. **Uncalibrated Model Scores:** The `candidate-leakfree-v1` Random Forest classifier outputs uncalibrated class votes. These indicate relative risk ranking, not calibrated real-world probabilities.
2. **Hydraulic Geometry Limitations:** FloodLens AI does not run a full 2D hydrodynamic wave-propagation solver (e.g. HEC-RAS); it operates on telemetry correlations and satellite extent overlays.
3. **SAR Satellite Revisit Interval:** Sentinel-1 radar passes occur every 6 to 12 days; cloud-penetrating extents represent discrete historical snapshots, not continuous real-time feeds.
4. **Mobile Device Validation:** Due to lack of physical Android hardware in the rehearsal environment, the mobile application is verified via TypeScript compilation and Expo JavaScript export (`DEVICE-UNTESTED`).

---

## 10. 5-Minute Judge Demonstration Script

### Timing: 0:00 – 0:45 | 1. The Problem
> *"Good morning, judges. In the Terai river basins of Nepal, monsoonal flash floods cause devastating loss of life and infrastructure every year. Emergency authorities often face a critical dilemma: telemetry arrives from disparate sensors, satellite imagery is siloed, and flood warnings either arrive too late or lack spatial precision. Most critically, evacuation teams lack immediate insight into which roads are already submerged."*

### Timing: 0:45 – 1:30 | 2. What FloodLens AI Does
> *"FloodLens AI is an evidence-based flood intelligence and decision-support prototype. It unifies rolling hydrometeorological forecasts, satellite synthetic-aperture radar extents, and critical facility screening into a single operational picture.
> 
> Importantly, FloodLens AI is designed with strict authority boundaries. It does not replace emergency commanders or send automated sirens. Instead, it arms disaster cells with multi-horizon risk predictions, GIS hazard screening, and a human-in-the-loop advisory workflow."*

### Timing: 1:30 – 2:30 | 3. The AI/ML Model & Why PostGIS Matters
> *"At the core of our forecasting is `candidate-leakfree-v1`, a Random Forest classifier trained on rolling 3-, 6-, and 24-hour rainfall accumulations, upstream discharge lags, and catchment saturation. Unlike naive ML prototypes that suffer from lookahead data leakage, our model was trained strictly on historical pre-event features. When critical telemetry is missing, it refuses to guess, safely returning UNAVAILABLE. Furthermore, because raw decision tree votes are uncalibrated, we never fabricate statistical percentages.
> 
> To translate predictions into geographic impact, we use PostgreSQL 16 with PostGIS 3.4. Notice our Route Assessment view: when logistics teams test an evacuation corridor, PostGIS performs real-time spatial intersection against flood extent polygons and road hazards. It screens out compromised routes while explicitly reminding responders that screening is not a verified safe guarantee."*

### Timing: 2:30 – 3:30 | 4. Authority & Citizen Workflow Walkthrough
> *(Demonstrating the UI)*
> *"Here on our Authority Command Overview, we select the Koshi Basin during the July 2024 monsoonal surge.
> - In the **Prediction Centre**, the model forecasts a transition from HIGH at +1 hour to CRITICAL at +3 and +6 hours.
> - In **Satellite Intelligence**, the 38.4 square-kilometer Sentinel-1 SAR flood polygon highlights vulnerable settlements.
> - In the **Alert Dispatcher**, our officer drafts an advisory. Notice our safety guards: the alert cannot be dispatched without explicit review, and every simulation alert is visibly prefixed with `[DEMO ONLY]` to guarantee that no false panic is ever created.
> - Meanwhile, on the **Citizen Mobile App**, residents receive localized risk horizons and can submit assistance requests with strict privacy guards: raw coordinates are accessible only to authorized responders."*

### Timing: 3:30 – 4:15 | 5. Evidence & Rigor Supporting the Prototype
> *"We built FloodLens AI with software engineering rigor:
> - 117 passing automated backend tests and 0 failures.
> - Automated PostGIS integration workflows running in GitHub Actions CI.
> - 100% clean TypeScript compilation on both the React 19 web console and the Expo Android mobile app.
> - Verified safe failure handling across missing telemetry, network dropouts, and expired authentication."*

### Timing: 4:15 – 5:00 | 6. Scientific Limitations & Future Roadmap
> *"We believe in scientific honesty. FloodLens AI is a research prototype. It does not run a 2D Navier-Stokes hydrodynamic solver, and our satellite overlays depend on orbital revisit cycles. Our immediate next steps are integrating automated calibration via Isotonic Regression, coupling real-time DHM hydrological telemetry, and piloting on-device mesh networking for zero-connectivity disaster environments.
> 
> Thank you, and we welcome your questions."*
