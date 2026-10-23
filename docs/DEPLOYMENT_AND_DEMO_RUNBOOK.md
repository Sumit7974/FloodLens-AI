# FloodLens AI — Deployment & Historical Demo Runbook

**Release Target:** Member 1, Day 5 Final Backend Release Candidate  
**Branch:** `feature/backend-day5`  
**Repository:** [https://github.com/Sumit7974/FloodLens-AI](https://github.com/Sumit7974/FloodLens-AI)  
**System Status:** Backend release-candidate validated. Monorepo contains `backend/` and `frontend/`. No verified Android/Expo application has been implemented or verified in the repository baseline to date.

---

## Executive Overview & Authority Boundary

FloodLens AI is an evidence-based historical flood intelligence and decision-support platform focused on Nepal's Terai river basins (Kamala and Bagmati basins in Dhanusha and Rautahat districts).

> [!IMPORTANT]
> **OPERATIONAL SAFETY & BOUNDARY DECLARATION**:
> FloodLens AI collects, organizes, simulates, and communicates flood intelligence to authorities.
> **FloodLens does NOT command, assign, or deploy rescue forces, personnel, or emergency units.**
> All operational decisions, warning issuances, and rescue deployments are conducted strictly and independently by statutory authorities (NDRRMA, DHM, Nepal Army, APF, and local municipal disaster cells).
>
> All alert dispatches in this release are **strictly confined to historical demonstrations and test sandbox simulations**. Software safeguards reject any live/operational alert dispatch requests.

---

## A. Prerequisites

### 1. System Requirements & Runtime Environment
- **Python**: Version 3.11.x (verified on Python 3.11.9)
- **Database**: PostgreSQL 16 with PostGIS 3.4 extension (or SQLite in-memory fallback for unit testing)
- **Node.js**: Version 18+ (for `frontend/` React dashboard if running web UI)
- **Operating System**: Linux (Ubuntu 22.04 LTS), macOS, or Windows 10/11 with PowerShell

### 2. Dependency Installation
Activate your virtual environment and install backend requirements:
```bash
# From repository root:
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt
```

### 3. Environment Configuration
Copy the safe template `backend/.env.example` to `backend/.env`:
```bash
cp backend/.env.example backend/.env
```

Required environment variables:
| Variable | Default / Example Value | Description |
|---|---|---|
| `ENVIRONMENT` | `development` (or `testing`) | Runtime mode |
| `DATABASE_URL` | `postgresql+psycopg2://floodlens:floodlens@localhost:5432/floodlens_db` | PostgreSQL connection string |
| `JWT_SECRET` | `generate-a-secure-random-32-char-key-here` | Secret key for JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token validity window |
| `DEFAULT_OPERATIONAL_MODE` | `historical_demo` | Enforces demo/simulation safety |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Authorized frontend origins |

> [!CAUTION]
> Never commit real secrets, API keys, or operational contacts to source control.

---

---

## B. Production & Container Deployment (Task 2 Architecture)

FloodLens AI packages a single, multi-purpose container image that can execute as:
1. **FastAPI Web API Service** (serving HTTP REST, OpenAPI docs, and WebSockets)
2. **Database Migration Runner** (executing Alembic migrations deterministically)
3. **Durable Satellite Background Worker** (polling and processing GIS optical/SAR jobs with atomic leases)

### 1. Image Build & Specifications
- **Build Context:** Repository root (`.`)
- **Dockerfile Path:** `Dockerfile` (or `backend/Dockerfile`)
- **System Dependencies:** Python 3.11, PostgreSQL client, GDAL, GEOS, PROJ C-libraries
- **Working Directory:** `/app/backend`
- **Environment Roots:** `FLOODLENS_REPO_ROOT=/app`, `PYTHONPATH=/app/backend:/app`

Build command:
```bash
docker build -t floodlens-backend:latest -f Dockerfile .
```

### 2. Service Commands & Execution Modes

| Service Role | Startup Command | Port / Protocol | Notes |
|---|---|---|---|
| **Web API Server** | `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` | `8000` (or dynamic `$PORT`) | Production mode without `--reload` |
| **Database Migrations** | `alembic upgrade head` | None (one-shot exit 0) | Run before replicas or workers start |
| **Satellite Worker Daemon** | `python -m app.workers.satellite_worker --interval 2.0` | None (background worker) | Atomic leases & crash recovery |

### 3. Required Persistent Storage & Volumes

| Volume / Mount | Container Path | Purpose |
|---|---|---|
| `floodlens_pgdata` | `/var/lib/postgresql/data` | Persistent PostgreSQL 16 + PostGIS 3.4 database storage |
| `floodlens_satellite_outputs` | `/app/backend/app/storage/satellite_outputs` | Persisted satellite raster masks, GeoJSON extents, and comparison PNGs |
| `./data` (Host Mount) | `/app/data` | Provides local GIS layers and authentic Sentinel-2 GeoTIFF inputs without committing binary rasters to Git |

### 4. Deploying with Docker Compose (Turnkey Prototype)

The repository provides a complete, multi-container orchestration in `docker-compose.yml`:
```bash
# 1. Copy and customize environment file (optional; defaults work for local demo)
cp .env.example .env

# 2. Build and start services (db, migration, backend, satellite-worker)
docker compose up -d

# 3. View service status
docker compose ps
```
The Compose setup:
- Launches `db` (`postgis/postgis:16-3.4`) and validates `pg_isready` healthcheck.
- Executes `migration` (`alembic upgrade head`) deterministically to head revision `0003_satellite_worker_lease`.
- Starts `backend` and `satellite-worker` only after migrations successfully complete.
- Shares `floodlens_satellite_outputs` and `./data` across both `backend` and `satellite-worker`.

### 5. Deploying to Container-Hosting Cloud Platforms (Render, Railway, Fly.io, etc.)

When deploying to a container hosting provider with managed PostgreSQL/PostGIS (e.g. Neon, Supabase, Render Postgres, AWS RDS):
1. **Database:** Provision PostgreSQL 16 with PostGIS extension (`CREATE EXTENSION IF NOT EXISTS postgis;`).
2. **Web Service Configuration:**
   - **Build Context:** `.` (repository root)
   - **Dockerfile Path:** `Dockerfile`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`
   - **Pre-deploy / Migration Command:** `alembic upgrade head`
   - **Healthcheck Path:** `/health` (or `/ready`)
3. **Background Worker Service Configuration:**
   - Deploy from the same Docker image / repository.
   - **Start Command:** `python -m app.workers.satellite_worker --interval 2.0`
4. **Environment Variables Required:**
   ```ini
   ENVIRONMENT=production
   DEBUG=false
   DATABASE_URL=postgresql+psycopg2://<user>:<password>@<db-host>:<db-port>/<db-name>
   JWT_SECRET=<random-32-plus-character-secret>
   CORS_ORIGINS=https://your-frontend-domain.com
   OPERATIONAL_MODE=historical_demo
   FLOODLENS_REPO_ROOT=/app
   PYTHONPATH=/app/backend:/app
   ```
5. **Making Historical Sentinel-2 Rasters Available:**
   - In container hosting, mount a persistent disk at `/app/data` and copy/rsync `data/historical_koshi_optical/` into `/app/data/historical_koshi_optical/`.
   - Alternatively, mount an S3/GCS bucket or pre-populate the deployment volume using a setup script.

### 6. Health & Readiness Verification
```bash
# Liveness probe
curl -fsS http://localhost:8000/health

# Readiness probe (verifies database & PostGIS connectivity)
curl -fsS http://localhost:8000/ready

# API v1 Health probe
curl -fsS http://localhost:8000/api/v1/health
```

---

## C. Test Execution & Verification

### 1. Local Pytest Suite (In-Memory SQLite)
Executes all unit, contract, security, RBAC, and regression test suites:
```bash
python -m pytest backend/tests/ -v
```
*Expected Result:* 117+ passed, 5 skipped (live PostGIS tests skip in environments lacking a running PostGIS instance; this is truthful and expected).

### 2. Pyrefly Static Type Checking
Verify static typing across the entire codebase:
```bash
python -m pyrefly check
```
*Expected Result:* `0 errors`.

### 3. Day 3 Demonstration Regression Flow
Run the Day 3 citizen assistance and authority alert simulation:
```bash
python scripts/demo_day3_flows.py
```
*Expected Result:* Exits with code 0 (`ALL FLOWS DEMONSTRATED AND VALIDATED SUCCESSFULLY!`).

### 4. Day 5 Final Release Candidate Demonstration
Run the end-to-end historical Nepal Terai flood intelligence demo:
```bash
python scripts/demo_day5_backend.py
```
*Expected Result:* Exits with code 0 (`ALL 13 DAY 5 BACKEND CAPABILITIES VERIFIED SUCCESSFULLY!`).

### 5. Live PostGIS Integration Tests
In an environment with a running PostgreSQL 16 + PostGIS 3.4 database (or in GitHub Actions CI):
```bash
DATABASE_URL="postgresql+psycopg2://floodlens:floodlens@localhost:5432/floodlens_db" python -m pytest backend/tests/test_spatial_postgis.py -v
```
*Expected Result:* 5 passed (testing `ST_Intersects`, `ST_Area`, `ST_Buffer`, and `GIST` spatial indexes).

---

## D. Historical Demonstration Script & Judge Walkthrough

The recommended demonstration replays the **July 2024 Nepal Terai Monsoon Inundation** (Kamala River basin, Dhanusha district):

1. **Historical Event Registration (`/api/v1/flood-events`)**:
   - Register historical episode `evt_2024_terai_monsoon` with DHM telemetry and Sentinel-1 SAR provenance.
2. **Settlement & Asset Ingestion (`/api/v1/locations`)**:
   - Ingest Janakpurdham Sub-Metropolitan and Sabaila Municipality with census populations and vulnerability scores.
3. **Multi-Horizon Prediction Ingestion (`/api/v1/predictions/ingest`)**:
   - Ingest `+1h`, `+3h`, and `+6h` risk horizons. Issue time (`2024-07-08T08:00:00Z`) is kept strictly distinct from valid horizons.
4. **Satellite Observed Flood Extent (`/api/v1/flood-events/{id}/extent`)**:
   - Ingest Copernicus Sentinel-1 SAR water mask polygon (42.6 km² inundated area).
5. **Multi-Horizon Risk Map (`/api/v1/predictions/map`)**:
   - Retrieve GeoJSON risk zones showing spatial risk progression.
6. **Affected Settlements Assessment (`/api/v1/flood-events/{id}/settlements`)**:
   - Perform spatial intersection identifying exposed settlements without fabricating unverified casualty counts.
7. **Exposed Assets Assessment (`/api/v1/flood-events/{id}/assets`)**:
   - Assess critical road links, substations, and shelters intersecting the satellite flood mask.
8. **Candidate Route Hazard Screening (`/api/v1/routes/assess`)**:
   - Screen candidate evacuation path against submerged road hazards; returns `hazards_detected` or `conditional`, never "safe".
9. **Authority Simulated Alert (`/api/v1/alerts`)**:
   - Authority drafts alert -> reviews and approves -> dispatches in `historical_demo` mode with mandatory `[DEMO / TEST ONLY]` prefix.
10. **Citizen Assistance Triage (`/api/v1/assistance`)**:
    - Citizen submits GPS help request -> authority reviews triage queue -> assigns municipal relief unit. Private coordinates omitted from public feeds.
11. **Synthesized Impact Report & Exports (`/api/v1/flood-events/{id}/report`)**:
    - Query synthesized report and download physical JSON and CSV export artifacts.
12. **Historical Replay Timeline (`/api/v1/flood-events/{id}/timeline`)**:
    - Retrieve chronological sequence of all milestones (episode start, forecasts, satellite extents, episode end).
13. **Model Evaluation Retrieval (`/api/v1/analytics/events/{id}`)**:
    - Retrieve retrospective spatial benchmark metrics (IoU, F1 score, precision, recall) evaluated against Sentinel-1 reference observations.

---

## E. Disaster Recovery & Edge Case Procedures

| Failure Scenario | Backend Detection | System Response & Graceful Recovery |
|---|---|---|
| **PostgreSQL / PostGIS Outage** | Connection refused / pool timeout | Readiness probe `/api/v1/ready` returns `HTTP 503 Service Unavailable`. Test and local environments fall back gracefully to in-memory SQLite and Shapely operations. |
| **Missing Satellite Extent Layer** | `db.query(FloodExtent)` returns None | `GET /settlements`, `/assets`, and `/report` return structured `status="no_extent_available"` with explanatory notes instead of failing. |
| **Missing Settlement GIS Layers** | 0 settlements in study area | Spatial assessment returns `status="no_settlement_data"` rather than claiming zero exposure. |
| **Missing ML Forecast Run** | `db.query(ForecastRun)` empty | `/predictions/latest` returns `HTTP 404 DataUnavailableError` with code `FORECAST_UNAVAILABLE`. |
| **WebSocket Connection Drop** | Network disconnect / timeout | Client receives disconnect; upon reconnecting, client invokes `action: "resync"` to obtain REST endpoint URLs and reconcile state. |
| **Upstream Telemetry Outage** | External provider down | System preserves archived observations and records `data_quality: "DEGRADED"` or `"UNAVAILABLE"` without fabricating real-time values. |

---

## F. Security & Privacy Safeguards

1. **No Production Credentials**: The codebase contains zero production API tokens, private signing keys, or personal phone numbers.
2. **Citizen Privacy**:
   - Raw citizen GPS coordinates and phone numbers are restricted to authenticated authority triage queues.
   - Citizens can only query their own submitted requests via `/api/v1/assistance/mine`.
   - Real-time WebSocket notifications emit only sanitized metadata (`category`, `people_count`) without private coordinates.
3. **Simulated Dispatches Only**:
   - Backend logic rejects any alert dispatch where `simulated == False`.
   - Real-world SMS gateways, WhatsApp APIs, or public siren integrations are deliberately not enabled.
4. **Authorized Demonstration Participants**:
   - Access to demo simulation alerts via `?include_demo=true` or WebSocket topic `demo_alerts` is strictly restricted to authenticated authorities or explicitly registered demo participant IDs.
