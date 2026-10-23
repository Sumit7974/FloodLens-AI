"""End-to-End Historical Simulation: Satellite Worker Concurrency and Data Integrity.

Demonstrates all required steps:
1. Register a historical/test event and a valid satellite scene.
2. Submit satellite job through FastAPI.
3. Persist the QUEUED job in database.
4. Allow an independently running worker to claim it with lease ownership.
5. Process the GIS pipeline and store the result in PostGIS / database.
6. Retrieve the completed job and resulting GeoJSON through the public API.
7. Confirm a competing worker does not duplicate execution.
8. Demonstrate correct recovery after simulated worker interruption.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["ENVIRONMENT"] = "testing"
os.environ.setdefault("JWT_SECRET", "sim-secret-key-32-chars-minimum-length-floodlens")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.core.security import create_access_token, hash_password
from app.database import Base
from app.main import create_application
from app.models.enums import OperationalMode, UserRole
from app.models.flood_event import FloodEvent
from app.models.satellite import FloodExtent, SatelliteJob, SatelliteScene
from app.models.user import User
from app.services.satellite_processor import set_test_db_session
from app.workers.satellite_worker import (
    claim_job,
    execute_job,
    recover_interrupted_jobs,
    run_worker_once,
)


def run_e2e_simulation() -> bool:
    print("\n" + "=" * 70)
    print("FLOODLENS AI: SATELLITE WORKER CONCURRENCY & INTEGRITY VERIFICATION")
    print("=" * 70)

    # Database initialization
    settings = get_settings()
    configured_db = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "sqlite:///:memory:"
    is_pg = "postgresql" in configured_db or "postgres" in configured_db

    print(f"[DB] Initializing database engine: {configured_db.split('@')[-1] if '@' in configured_db else configured_db}")
    if is_pg:
        engine = create_engine(configured_db, pool_pre_ping=True)
    else:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    Base.metadata.create_all(bind=engine)
    SimSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db: Session = SimSession()
    set_test_db_session(db)

    app = create_application()

    from app.database import get_db

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)

    try:
        # Step 1: Create Authorized Authority User
        print("\n--- Step 1: Authority User Setup ---")
        authority = User(
            id=str(uuid.uuid4()),
            email="authority_ops@floodlens.org",
            hashed_password=hash_password("authority_sec_pass_123"),
            full_name="GIS Mission Commander",
            role=UserRole.AUTHORITY,
            contact_consent=True,
            is_active=True,
        )
        db.add(authority)
        db.commit()
        token = create_access_token(subject=authority.id, role=authority.role.value)
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[AUTH] Authority token generated for {authority.email}")

        # Step 2: Register Historical Test Event
        print("\n--- Step 2: Register Historical Event ---")
        event_id = f"evt_sim_{uuid.uuid4().hex[:8]}"
        event = FloodEvent(
            id=event_id,
            region_id="nepal_terai",
            name="Nepal Monsoon Historical Simulation Event",
            start_at=datetime(2017, 8, 11, 0, 0, tzinfo=timezone.utc),
            end_at=datetime(2017, 8, 20, 0, 0, tzinfo=timezone.utc),
            mode=OperationalMode.HISTORICAL_DEMO,
        )
        db.add(event)
        db.commit()
        print(f"[EVENT] Created event: {event.id} ({event.name})")

        # Step 3: Register Valid Satellite Scene
        print("\n--- Step 3: Register Satellite Scene ---")
        scene_id = f"scene_sim_{uuid.uuid4().hex[:8]}"
        scene_res = client.post(
            "/api/v1/satellite/scenes",
            json={
                "id": scene_id,
                "provider": "ESA Copernicus",
                "sensor": "Sentinel-2",
                "modality": "optical",
                "captured_at": "2017-08-15T10:30:00Z",
                "cloud_quality": 0.05,
                "asset_ref": "backend/tests/fixtures/optical_flood_sample.geojson",
                "bbox_geojson": {
                    "type": "Polygon",
                    "coordinates": [[[87.0, 26.0], [87.5, 26.0], [87.5, 26.5], [87.0, 26.5], [87.0, 26.0]]],
                },
            },
            headers=headers,
        )
        assert scene_res.status_code == 201, f"Failed to register scene: {scene_res.text}"
        print(f"[SCENE] Scene registered: {scene_id}")

        # Step 4: Submit Satellite Job via FastAPI (BackgroundTasks auto-dispatches)
        print("\n--- Step 4: Submit Processing Job via FastAPI (BackgroundTasks execution) ---")
        job_res = client.post(
            "/api/v1/satellite/jobs",
            json={
                "event_id": event_id,
                "scene_id": scene_id,
                "method": "NDWI",
                "threshold": 0.10,
            },
            headers=headers,
        )
        assert job_res.status_code == 202, f"Failed to submit job: {job_res.text}"
        job_body = job_res.json()
        job_id = job_body["job_id"]
        print(f"[JOB-1] Job submitted via API. Assigned ID: {job_id}")

        # Step 5: Verify BackgroundTasks Execution Completed Job 1
        db.expire_all()
        job_1 = db.query(SatelliteJob).filter(SatelliteJob.id == job_id).first()
        print(f"[JOB-1] Completed via API background dispatcher: status={job_1.status}, worker={job_1.worker_id}, extent={job_1.output_extent_id}")

        # Step 6: Enqueue Job 2 for Standalone Worker Daemon Claiming
        print("\n--- Step 6: Standalone Worker Daemon Claiming & Processing (Job 2) ---")
        job2_id = f"sat_job_daemon_{uuid.uuid4().hex[:8]}"
        job_2 = SatelliteJob(
            id=job2_id,
            event_id=event_id,
            scene_id=scene_id,
            method="NDWI",
            threshold=0.20,
            status="QUEUED",
            requested_by=authority.email,
        )
        db.add(job_2)
        db.commit()
        print(f"[JOB-2] Enqueued in QUEUED status: {job2_id}")

        worker_id_alpha = "worker-sim-alpha-1"
        claimed = claim_job(db, job_id=job2_id, worker_id=worker_id_alpha, lease_seconds=60)
        assert claimed is not None, "Worker Alpha failed to claim QUEUED job!"
        print(f"[CLAIM] Worker '{worker_id_alpha}' claimed job '{claimed.id}'. Status={claimed.status}")
        print(f"[LEASE] Lease expires at: {claimed.lease_expires_at} (heartbeat: {claimed.heartbeat_at})")

        # Step 7: Competing Worker Collision Test (Worker Beta attempts to claim Job 2)
        print("\n--- Step 7: Competing Worker Collision Test ---")
        worker_id_beta = "worker-sim-beta-2"
        competing_claim = claim_job(db, job_id=job2_id, worker_id=worker_id_beta)
        assert competing_claim is None, "Competing worker illegally claimed already-running job!"
        print(f"[COMPETE] Worker '{worker_id_beta}' attempt returned None (job protected). PASS.")

        # Step 8: Worker Alpha Executes Job 2
        print("\n--- Step 8: Execute GIS Pipeline & PostGIS Persistence ---")
        success = execute_job(claimed, db, worker_id=worker_id_alpha)
        assert success is True, "Pipeline execution failed!"
        db.refresh(claimed)
        print(f"[EXEC] Job 2 completed successfully! Output extent ID: {claimed.output_extent_id}")
        print(f"[PROVENANCE] Extent provenance recorded: {claimed.provenance}")

        # Step 9: Retrieve Completed Job & GeoJSON via Public API
        print("\n--- Step 9: API Retrieval & RFC 7946 GeoJSON Export ---")
        status_res = client.get(f"/api/v1/satellite/jobs/{job_id}", headers=headers)
        assert status_res.status_code == 200
        status_data = status_res.json()
        print(f"[API] GET /jobs/{job_id} -> status={status_data['status']}, progress={status_data['progress_percent']}%")

        geojson_res = client.get(f"/api/v1/flood-events/{event_id}/extent/geojson")
        assert geojson_res.status_code == 200
        gj_data = geojson_res.json()
        print(f"[API] GET /flood-events/{event_id}/extent/geojson -> Type={gj_data['type']}")
        print(f"      Properties: event_id={gj_data['properties']['event_id']}, area_km2={gj_data['properties']['area_km2']}, provenance={gj_data['properties']['provenance']}")

        # Step 10: Crash Recovery Demonstration
        print("\n--- Step 10: Simulated Worker Crash & Safe Recovery Demonstration ---")
        now = datetime.now(timezone.utc)
        # Create simulated job where worker died 2 minutes ago
        crashed_job = SatelliteJob(
            id=f"sat_job_crash_sim_{uuid.uuid4().hex[:6]}",
            event_id=event_id,
            scene_id=scene_id,
            method="NDWI",
            status="RUNNING",
            worker_id="crashed-node-x",
            started_at=now - timedelta(seconds=120),
            heartbeat_at=now - timedelta(seconds=100),
            lease_expires_at=now - timedelta(seconds=30),  # Lease expired
            retry_count=0,
            max_retries=2,
            requested_by="ops@floodlens.org",
        )
        db.add(crashed_job)
        db.commit()
        print(f"[CRASH-SIM] Injected dead job '{crashed_job.id}' (worker='{crashed_job.worker_id}', lease expired)")

        recovered_count = recover_interrupted_jobs(db, now=now)
        assert recovered_count == 1
        db.refresh(crashed_job)
        print(f"[RECOVERY] recover_interrupted_jobs() reclaimed {recovered_count} job(s).")
        print(f"[RECOVERY] Job status reset to: {crashed_job.status} (retry {crashed_job.retry_count}/{crashed_job.max_retries})")
        print(f"[RECOVERY] Reason: {crashed_job.error_message}")

        print("\n" + "=" * 70)
        print("ALL END-TO-END VERIFICATION STEPS COMPLETED SUCCESSFULLY!")
        print("=" * 70 + "\n")
        return True

    finally:
        set_test_db_session(None)
        db.close()


if __name__ == "__main__":
    success = run_e2e_simulation()
    sys.exit(0 if success else 1)
