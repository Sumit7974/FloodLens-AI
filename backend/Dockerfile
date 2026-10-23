# Multi-purpose container image for FloodLens AI:
# - FastAPI web server: CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
# - Database migrations: command: alembic upgrade head
# - Satellite worker daemon: command: python -m app.workers.satellite_worker --interval 2.0
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    FLOODLENS_REPO_ROOT=/app \
    PYTHONPATH=/app/backend:/app

WORKDIR /app

# Install system dependencies for PostgreSQL, PostGIS client, and GIS C-libraries (GDAL, GEOS, PROJ)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first to leverage Docker layer caching
COPY backend/requirements.txt backend/requirements-dev.txt /app/backend/
COPY ml/requirements.txt /app/ml/

# Install Python dependencies (core backend + ML GIS processing requirements)
RUN pip install --upgrade pip && \
    pip install -r /app/backend/requirements.txt && \
    pip install -r /app/ml/requirements.txt

# Copy backend, ml, and baseline data
COPY backend /app/backend
COPY ml /app/ml
COPY data /app/data

# Ensure runtime directories exist and are writable by any container UID
RUN mkdir -p /app/backend/app/storage/satellite_outputs \
             /app/data/rasters \
             /app/data/reports \
             /app/data/historical_koshi_optical && \
    chmod -R 777 /app/backend/app/storage /app/data

WORKDIR /app/backend

# Expose default HTTP port
EXPOSE 8000

# Production startup command without --reload, binding to 0.0.0.0 and dynamic $PORT
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
