# FloodLens AI — Backend Service

The shared backend service for **FloodLens AI**, providing REST APIs, authenticated WebSockets, PostgreSQL/PostGIS spatial persistence, and orchestration for the authority command web dashboard and citizen Android mobile application.

---

## Technology Stack

- **Framework**: Python 3.11+, [FastAPI](https://fastapi.tiangolo.com/)
- **Database & Spatial Engine**: PostgreSQL 16 with [PostGIS 3.4](https://postgis.net/)
- **ORM & Migrations**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/), [GeoAlchemy2](https://geoalchemy-2.readthedocs.io/), [Alembic](https://alembic.sqlalchemy.org/)
- **Data Validation & Contracts**: [Pydantic v2](https://docs.pydantic.dev/)
- **Real-Time Communications**: Native WebSockets with JWT Authentication & topic-based multiplexing
- **Authentication**: JWT (JSON Web Tokens) with PBKDF2/bcrypt password hashing
- **Testing**: [pytest](https://docs.pytest.org/), `pytest-asyncio`, FastAPI TestClient

---

## Directory Structure

```
backend/
├── Dockerfile                  # Container definition for FastAPI backend
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Development and testing dependencies
├── .env.example                # Environment variables template
├── README.md                   # This documentation guide
├── alembic.ini                 # Database migration configuration
├── alembic/
│   ├── env.py                  # Migration environment runner
│   ├── script.py.mako          # Revision template
│   └── versions/
│       └── 0001_initial_schema.py # Initial PostGIS extension & core tables
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point, CORS, middlewares
│   ├── config.py               # Settings management via Pydantic Settings
│   ├── database.py             # SQLAlchemy engine, session maker, PostGIS check
│   ├── core/
│   │   ├── security.py         # Bcrypt hashing & PyJWT token utilities
│   │   └── exceptions.py       # Custom exceptions & contract-compliant error handlers
│   ├── models/                 # SQLAlchemy ORM models (core contracts)
│   │   ├── base.py             # UUID generator, timestamps, GeometryType
│   │   ├── enums.py            # UserRole, OperationalMode, RiskLevel, etc.
│   │   ├── user.py             # Citizen, Authority, Admin accounts
│   │   ├── location.py         # Administrative boundaries & spatial geometries
│   │   ├── data_source.py      # Upstream provider provenance & freshness
│   │   ├── flood_event.py      # Historical demo & live flood events
│   │   ├── forecast.py         # Forecast runs & multi-horizon risk predictions
│   │   ├── satellite.py        # Satellite scenes & derived flood extent masks
│   │   ├── asset.py            # Critical assets, facilities, road hazards
│   │   ├── alert.py            # Authority draft -> approval -> dispatch lifecycle
│   │   ├── assistance.py       # Citizen help requests & responder queues
│   │   └── evaluation.py       # Prediction vs observation evaluation records
│   ├── schemas/                # Pydantic v2 API request/response contracts
│   │   ├── common.py           # Standard error response envelope & GeoJSON
│   │   ├── health.py           # GET /api/v1/health schemas
│   │   ├── auth.py             # Registration, login, JWT token models
│   │   ├── forecast.py         # Forecast & +1h/+3h/+6h horizon risk schemas
│   │   ├── event.py            # WebSocket event payloads
│   │   ├── flood_event.py      # Flood event & flood extent schemas
│   │   ├── alert.py            # Alert create, approve, and dispatch schemas
│   │   └── assistance.py       # Citizen help request schemas
│   ├── api/
│   │   ├── deps.py             # DB session & RBAC dependency injectors
│   │   └── v1/
│   │       ├── router.py       # Main API v1 router
│   │       └── endpoints/
│   │           ├── health.py       # GET /api/v1/health
│   │           ├── auth.py         # POST /auth/register, /login, GET /me
│   │           ├── predictions.py  # GET /predictions/latest, /locations/{id}
│   │           ├── flood_events.py # GET /flood-events/{id}/extent, /settlements
│   │           ├── alerts.py       # POST /alerts, /approve, /dispatch
│   │           ├── assistance.py   # POST /assistance, GET /mine, /queue
│   │           ├── monitoring.py   # GET /monitoring/weather, /rivers, /dams
│   │           ├── facilities.py   # GET /facilities/shelters, /routes/assess
│   │           ├── satellite.py    # POST /satellite/jobs, GET /scenes
│   │           └── analytics.py    # GET /analytics/events/{id}, /models
│   └── websocket/
│       ├── connection_manager.py # Authenticated connection & topic multiplexer
│       └── router.py             # WS /ws/v1/events endpoint
└── tests/                      # Automated test suite
    ├── conftest.py             # In-memory SQLite fixture, mock users, tokens
    ├── test_health.py          # Health check and root discovery tests
    ├── test_contracts.py       # Documented JSON schema conformance tests
    ├── test_auth.py            # Bcrypt, JWT, and RBAC endpoint tests
    ├── test_models.py          # SQLAlchemy model lifecycle & relation tests
    └── test_websocket.py       # Authenticated WebSocket unit & integration tests
```

---

## Local Setup & Quickstart

### Prerequisites
- Python 3.11+
- PostgreSQL 15+ with PostGIS 3.3+ (or Docker Compose)

### 1. Environment Configuration
Copy `.env.example` to create your local `.env`:
```bash
cp backend/.env.example backend/.env
```
Ensure `DATABASE_URL` and `JWT_SECRET` are adjusted for your environment.

### 2. Using Docker Compose (Recommended)
From the repository root:
```bash
docker compose up -d db
```
This spins up PostgreSQL with the PostGIS extension pre-configured on port 5432.

To run the full stack (DB + Backend):
```bash
docker compose up --build
```

### 3. Local Native Python Environment
```bash
# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt
```

### 4. Database Migrations
Run Alembic migrations to create the PostGIS extension and all core tables:
```bash
cd backend
alembic upgrade head
```

To review the SQL output without applying it directly:
```bash
alembic upgrade head --sql
```

### 5. Running the Backend Server
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## API Documentation & Endpoints

Once the server is running, interactive API documentation is available at:
- **Swagger UI**: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- **ReDoc**: [http://localhost:8000/api/v1/redoc](http://localhost:8000/api/v1/redoc)
- **OpenAPI Schema**: [http://localhost:8000/api/v1/openapi.json](http://localhost:8000/api/v1/openapi.json)

### Key Day 1 Endpoints

| Method | Path | Description | Access |
|---|---|---|---|
| `GET` | `/` | Service root and discovery | Public |
| `GET` | `/api/v1/health` (and `/health`) | Service and database/PostGIS liveness check | Public |
| `GET` | `/api/v1/ready` (and `/ready`) | Readiness probe checking database & PostGIS availability | Public |
| `POST` | `/api/v1/auth/register` | Citizen registration (authority self-grant disallowed) | Public |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT Bearer token | Public |
| `GET` | `/api/v1/auth/me` | Current authenticated user profile | Authenticated |
| `GET` | `/api/v1/predictions/latest` | Multi-horizon risk forecast (`+1h`, `+3h`, `+6h`) | Public |
| `POST` | `/api/v1/alerts` | Create draft warning for review | Authority / Admin |
| `POST` | `/api/v1/alerts/{id}/approve` | Approve draft warning | Authority / Admin |
| `POST` | `/api/v1/alerts/{id}/dispatch`| Dispatch warning (emits WebSocket event) | Authority / Admin |
| `POST` | `/api/v1/assistance` | Citizen emergency assistance request | Authenticated Citizen |
| `GET` | `/api/v1/assistance` | Emergency responder queue | Authority / Admin |
| `WS` | `/ws/v1/events?token={jwt}` | Authenticated real-time event streaming | Authenticated |

---

## Real-Time WebSocket Channel

Connect to `/ws/v1/events?token=<JWT_ACCESS_TOKEN>`.

### Event Wire Format
```json
{
  "event_id": "evt_001",
  "type": "risk.updated",
  "timestamp": "2026-10-17T06:10:00Z",
  "location_id": "demo-village-01",
  "resource_id": "demo-forecast-001",
  "version": 2
}
```

### Event Types
- `risk.updated`: New forecast run published.
- `sensor.updated`: New river/weather observation ingested.
- `flood_extent.updated`: Satellite extent processing completed.
- `alert.approved`: Authority approved warning (internal responders).
- `alert.published`: Warning dispatched to public subscribers.
- `assistance.created`: New citizen help request submitted.
- `assistance.updated`: Help request assignment/status changed.
- `processing.completed`: Background GIS/AI analysis completed.

---

## Automated Test Suite & CI

### 1. Local Testing (SQLite In-Memory)
Run unit, contract conformance, security RBAC, and regression tests locally:
```bash
python -m pytest backend/tests -v
```

### 2. Live PostgreSQL / PostGIS 16 Testing
When running against a live PostgreSQL 16 / PostGIS database:
```bash
# Run live Alembic migrations
alembic upgrade head

# Run live PostGIS spatial operations and GIST index verification
python scripts/verify_spatial_postgis.py

# Run full test suite with PostGIS integration
DATABASE_URL="postgresql+psycopg2://user:pass@localhost:5432/floodlens_db" pytest -v
```

### 3. Continuous Integration (GitHub Actions)
The repository includes `.github/workflows/backend-ci.yml` which automatically:
- Provisions a `postgis/postgis:16-3.4` service container.
- Verifies PostGIS 16 extensions and GIST indexes.
- Executes `alembic upgrade head`, migration rollback reversibility, and re-upgrade.
- Runs `verify_spatial_postgis.py` executing live spatial queries (`ST_Contains`, `ST_DWithin`, `ST_Intersects`, `ST_Area`).
- Runs the complete automated test suite (`pytest -v`).
- Validates the `/api/v1/health` and `/api/v1/ready` readiness endpoints against live services.

