"""Comprehensive Concurrency and Crash-Recovery Test Suite for Satellite Processing.

Validates all Task 3 & 4 & 5 & 6 & 7 concurrency, leasing, recovery, and data-integrity requirements:
1. Two independent PostgreSQL sessions attempting to claim the same job concurrently.
2. Two independent database sessions racing for the general queue.
3. API dispatcher and standalone worker racing for one job.
4. An active RUNNING job surviving another worker's recovery scan (lease protection).
5. An expired, genuinely abandoned job being recovered.
6. A heartbeat preventing premature recovery.
7. Worker failure followed by bounded retry.
8. Retry exhaustion transitioning to FAILED.
9. Repeated identical jobs remaining idempotent.
10. Different thresholds preserving distinct results without overwriting.
11. Different source scenes preserving distinct observed extents.
12. Restart recovery without manually forcing incorrect job states.
13. Synthetic fixture provenance preserved in downstream API responses.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.enums import OperationalMode
from app.models.flood_event import FloodEvent
from app.models.satellite import FloodExtent, SatelliteJob, SatelliteScene
from app.services.satellite_processor import dispatch_satellite_job
from app.workers.satellite_worker import (
    claim_job,
    execute_job,
    generate_worker_id,
    heartbeat_job,
    recover_interrupted_jobs,
)


@pytest.fixture
def concurrency_event(db_session: Session) -> FloodEvent:
    """Create a flood event for concurrency testing."""
    event = FloodEvent(
        id=f"evt_conc_{uuid.uuid4().hex[:8]}",
        region_id="nepal_terai",
        name="Nepal Monsoon Concurrency Test Event",
        start_at=datetime(2017, 8, 11, 0, 0, tzinfo=timezone.utc),
        end_at=datetime(2017, 8, 20, 0, 0, tzinfo=timezone.utc),
        mode=OperationalMode.HISTORICAL_DEMO,
    )
    db_session.add(event)
    db_session.commit()
    return event


@pytest.fixture
def concurrency_scene(db_session: Session) -> SatelliteScene:
    """Create an optical scene pointing to the bundled fixture."""
    scene = SatelliteScene(
        id=f"scene_conc_{uuid.uuid4().hex[:8]}",
        provider="ESA Copernicus",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime(2017, 8, 15, 10, 30, tzinfo=timezone.utc),
        cloud_quality=0.05,
        asset_ref="backend/tests/fixtures/optical_flood_sample.geojson",
        bbox_geojson={
            "type": "Polygon",
            "coordinates": [[[87.0, 26.0], [87.5, 26.0], [87.5, 26.5], [87.0, 26.5], [87.0, 26.0]]],
        },
    )
    db_session.add(scene)
    db_session.commit()
    return scene


# ==============================================================================
# 1. Real Concurrency: Parallel Execution with Independent Sessions (Requirement 4 & 7)
# ==============================================================================
def test_two_independent_postgres_sessions_claim_same_job(
    is_postgres: bool,
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """At least one true parallel-execution test must use real independent connections.
    
    Verifies that two concurrent worker threads attempting to claim the exact same
    target job using independent database sessions cannot both succeed:
    exactly one worker claims it, the other receives None.
    Executed in live PostgreSQL 16 PostGIS environments (such as CI).
    """
    if not is_postgres:
        pytest.skip(
            "True parallel execution with independent database connections requires live PostgreSQL "
            "(runs in CI against PostgreSQL 16 PostGIS container)."
        )

    # Create target QUEUED job
    target_job = SatelliteJob(
        id=f"sat_job_parallel_{uuid.uuid4().hex[:8]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        threshold=0.0,
        status="QUEUED",
        requested_by="concurrency_tester@floodlens.org",
    )
    db_session.add(target_job)
    db_session.commit()

    engine = db_session.bind
    IndependentSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    barrier = threading.Barrier(2)
    results = {}

    def worker_claim(worker_name: str):
        sess = IndependentSession()
        try:
            # Synchronize both threads to hit claim_job at the exact same instant
            barrier.wait(timeout=5.0)
            claimed = claim_job(sess, job_id=target_job.id, worker_id=worker_name, lease_seconds=60)
            results[worker_name] = claimed.id if claimed else None
        except Exception as e:
            results[worker_name] = f"ERROR: {e}"
        finally:
            sess.close()

    t1 = threading.Thread(target=worker_claim, args=("worker-thread-1",))
    t2 = threading.Thread(target=worker_claim, args=("worker-thread-2",))

    t1.start()
    t2.start()
    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    # Exactly one thread must have succeeded in claiming the job
    non_none_claims = [val for val in results.values() if val is not None and not str(val).startswith("ERROR")]
    none_claims = [val for val in results.values() if val is None]

    assert len(non_none_claims) == 1, f"Expected exactly 1 claim, got: {results}"
    assert len(none_claims) == 1, f"Expected exactly 1 failed claim, got: {results}"
    assert non_none_claims[0] == target_job.id

    # Verify final state in database
    db_session.expire_all()
    refreshed = db_session.query(SatelliteJob).filter(SatelliteJob.id == target_job.id).first()
    assert refreshed.status == "RUNNING"
    assert refreshed.worker_id in ("worker-thread-1", "worker-thread-2")
    assert refreshed.lease_expires_at is not None
    assert refreshed.heartbeat_at is not None


def test_two_independent_sessions_claim_general_queue(
    is_postgres: bool,
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """Two concurrent threads polling the general queue claim distinct jobs without double-processing.
    Runs on live PostgreSQL in CI.
    """
    if not is_postgres:
        pytest.skip(
            "True parallel execution with independent database connections requires live PostgreSQL "
            "(runs in CI against PostgreSQL 16 PostGIS container)."
        )

    job_a = SatelliteJob(
        id=f"sat_job_q_a_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="QUEUED",
        requested_by="queue_test@floodlens.org",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    job_b = SatelliteJob(
        id=f"sat_job_q_b_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="QUEUED",
        requested_by="queue_test@floodlens.org",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    db_session.add_all([job_a, job_b])
    db_session.commit()

    engine = db_session.bind
    IndependentSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    barrier = threading.Barrier(2)
    claims = {}

    def poll_queue(worker_name: str):
        sess = IndependentSession()
        try:
            barrier.wait(timeout=5.0)
            claimed = claim_job(sess, worker_id=worker_name, lease_seconds=60)
            claims[worker_name] = claimed.id if claimed else None
        finally:
            sess.close()

    t1 = threading.Thread(target=poll_queue, args=("worker-poll-1",))
    t2 = threading.Thread(target=poll_queue, args=("worker-poll-2",))

    t1.start()
    t2.start()
    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    claimed_ids = [c for c in claims.values() if c is not None]
    assert len(claimed_ids) == 2, f"Expected 2 claimed jobs, got: {claims}"
    assert len(set(claimed_ids)) == 2, f"Both workers claimed the same job! {claims}"
    assert set(claimed_ids) == {job_a.id, job_b.id}


def test_atomic_job_claiming_safety(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """Atomic conditional claim prevents a claimed job from being claimed by a second worker."""
    job = SatelliteJob(
        id=f"sat_job_atomic_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="QUEUED",
        requested_by="atomic_test@floodlens.org",
    )
    db_session.add(job)
    db_session.commit()

    # First claim succeeds
    claimed1 = claim_job(db_session, job_id=job.id, worker_id="worker-first")
    assert claimed1 is not None
    assert claimed1.status == "RUNNING"
    assert claimed1.worker_id == "worker-first"

    # Second claim on the same job must return None
    claimed2 = claim_job(db_session, job_id=job.id, worker_id="worker-second")
    assert claimed2 is None

    # Failed claim did not mutate the job's ownership
    db_session.refresh(job)
    assert job.status == "RUNNING"
    assert job.worker_id == "worker-first"


# ==============================================================================
# 2. API Dispatcher and Standalone Worker Racing for One Job (Requirement 4 & 7)
# ==============================================================================
def test_api_dispatcher_and_standalone_worker_racing_for_one_job(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """When both the FastAPI BackgroundTasks dispatcher and the standalone worker
    attempt to claim the exact same job, only one executes and output is not duplicated."""
    race_job = SatelliteJob(
        id=f"sat_job_race_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="QUEUED",
        requested_by="race_test@floodlens.org",
    )
    db_session.add(race_job)
    db_session.commit()

    # Worker A claims it first
    claimed_by_worker = claim_job(db_session, job_id=race_job.id, worker_id="worker-daemon-1")
    assert claimed_by_worker is not None
    assert claimed_by_worker.status == "RUNNING"

    # API dispatcher attempts to claim the same job (should receive None and exit cleanly)
    claimed_by_api = claim_job(db_session, job_id=race_job.id, worker_id="api-dispatcher-1")
    assert claimed_by_api is None

    # Worker processes the job
    execute_job(claimed_by_worker, db_session, worker_id="worker-daemon-1")
    db_session.refresh(race_job)
    assert race_job.status == "COMPLETED"
    assert race_job.worker_id == "worker-daemon-1"
    assert race_job.output_extent_id is not None


# ==============================================================================
# 3. Active RUNNING Job Surviving Another Worker's Recovery Scan (Requirement 3 & 7)
# ==============================================================================
def test_active_running_job_survives_another_worker_recovery_scan(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """An active RUNNING job whose lease is unexpired MUST NOT be touched or reset
    by another worker's periodic recovery scan."""
    now = datetime.now(timezone.utc)
    active_job = SatelliteJob(
        id=f"sat_job_active_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="RUNNING",
        worker_id="active-live-worker-1",
        started_at=now - timedelta(seconds=10),
        heartbeat_at=now - timedelta(seconds=5),
        lease_expires_at=now + timedelta(seconds=55),  # 55 seconds remaining!
        retry_count=0,
        max_retries=2,
        requested_by="ops@floodlens.org",
    )
    db_session.add(active_job)
    db_session.commit()

    # Another worker runs recovery scan
    recovered_count = recover_interrupted_jobs(db_session, now=now)
    assert recovered_count == 0

    db_session.refresh(active_job)
    assert active_job.status == "RUNNING"
    assert active_job.worker_id == "active-live-worker-1"
    assert active_job.retry_count == 0


# ==============================================================================
# 4. Expired Genuinely Abandoned Job Recovered (Requirement 3 & 7)
# ==============================================================================
def test_expired_genuinely_abandoned_job_recovered(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """A job whose worker crashed and lease expired is safely returned to the queue."""
    now = datetime.now(timezone.utc)
    crashed_job = SatelliteJob(
        id=f"sat_job_crashed_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="RUNNING",
        worker_id="crashed-dead-worker-99",
        started_at=now - timedelta(seconds=120),
        heartbeat_at=now - timedelta(seconds=90),
        lease_expires_at=now - timedelta(seconds=30),  # Expired 30 seconds ago!
        retry_count=0,
        max_retries=2,
        requested_by="ops@floodlens.org",
    )
    db_session.add(crashed_job)
    db_session.commit()

    recovered_count = recover_interrupted_jobs(db_session, now=now)
    assert recovered_count == 1

    db_session.refresh(crashed_job)
    assert crashed_job.status == "QUEUED"
    assert crashed_job.retry_count == 1
    assert crashed_job.worker_id is None
    assert crashed_job.lease_expires_at is None
    assert "re-queued for recovery" in crashed_job.error_message.lower()


# ==============================================================================
# 5. Heartbeat Preventing Premature Recovery (Requirement 3 & 7)
# ==============================================================================
def test_heartbeat_prevents_premature_recovery(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """Periodic worker heartbeat extends lease and prevents premature recovery scan from resetting job."""
    now = datetime.now(timezone.utc)
    worker_id = "heartbeat-worker-01"

    job = SatelliteJob(
        id=f"sat_job_hb_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="RUNNING",
        worker_id=worker_id,
        started_at=now,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=5),  # Short initial lease
        retry_count=0,
        max_retries=2,
        requested_by="ops@floodlens.org",
    )
    db_session.add(job)
    db_session.commit()

    # Worker sends heartbeat extending lease by 120s
    ok = heartbeat_job(db_session, job.id, worker_id=worker_id, extend_seconds=120)
    assert ok is True

    db_session.refresh(job)
    lease_at = job.lease_expires_at
    if lease_at and lease_at.tzinfo is None:
        lease_at = lease_at.replace(tzinfo=timezone.utc)
    assert lease_at > now + timedelta(seconds=60)

    # Recovery scan runs at now + 10s (when original lease of 5s would have expired)
    recovered = recover_interrupted_jobs(db_session, now=now + timedelta(seconds=10))
    assert recovered == 0  # Protected by heartbeat!

    db_session.refresh(job)
    assert job.status == "RUNNING"
    assert job.worker_id == worker_id


# ==============================================================================
# 6. Worker Failure Followed by Bounded Retry (Requirement 3 & 7)
# ==============================================================================
def test_worker_failure_bounded_retry(
    db_session: Session,
    concurrency_event: FloodEvent,
):
    """Worker execution failure safely records error, increments retry count, and re-queues."""
    failing_job = SatelliteJob(
        id=f"sat_job_fail_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id="scene_nonexistent_xyz",
        method="NDWI",
        status="RUNNING",
        worker_id="test-fail-worker",
        retry_count=0,
        max_retries=2,
        requested_by="test@floodlens.org",
    )
    db_session.add(failing_job)
    db_session.commit()

    success = execute_job(failing_job, db_session)
    assert success is False

    db_session.refresh(failing_job)
    assert failing_job.status == "QUEUED"
    assert failing_job.retry_count == 1
    assert failing_job.worker_id is None
    assert failing_job.lease_expires_at is None
    assert "attempt 1/2 failed" in failing_job.error_message.lower()


# ==============================================================================
# 7. Retry Exhaustion Transitioning to FAILED (Requirement 3 & 7)
# ==============================================================================
def test_retry_exhaustion_transitions_to_failed(
    db_session: Session,
    concurrency_event: FloodEvent,
):
    """When a job reaches max_retries, it transitions to FAILED with completed_at set."""
    now = datetime.now(timezone.utc)
    exhausted_job = SatelliteJob(
        id=f"sat_job_exhaust_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id="scene_missing_for_exhaustion",
        method="NDWI",
        status="RUNNING",
        worker_id="test-exhaust-worker",
        retry_count=1,  # retry 1 done, max_retries is 2
        max_retries=2,
        lease_expires_at=now - timedelta(seconds=10),
        requested_by="test@floodlens.org",
    )
    db_session.add(exhausted_job)
    db_session.commit()

    recovered = recover_interrupted_jobs(db_session, now=now)
    assert recovered == 1

    db_session.refresh(exhausted_job)
    assert exhausted_job.status == "FAILED"
    assert exhausted_job.retry_count == 2
    assert exhausted_job.completed_at is not None
    assert "maximum" in exhausted_job.error_message.lower()


# ==============================================================================
# 8. Repeated Identical Jobs Remain Idempotent (Requirement 5 & 7)
# ==============================================================================
def test_repeated_identical_jobs_remain_idempotent(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """Re-executing an identical job updates the existing FloodExtent in-place
    without generating colliding or duplicate records."""
    job1 = SatelliteJob(
        id=f"sat_job_idem_1_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        threshold=0.10,
        status="QUEUED",
        requested_by="idempotency@floodlens.org",
    )
    db_session.add(job1)
    db_session.commit()

    claimed1 = claim_job(db_session, job_id=job1.id)
    execute_job(claimed1, db_session)
    db_session.refresh(job1)
    assert job1.status == "COMPLETED"
    extent_id_1 = job1.output_extent_id

    # Re-run identical job (same event, scene, method, threshold)
    job2 = SatelliteJob(
        id=f"sat_job_idem_2_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        threshold=0.10,
        status="QUEUED",
        requested_by="idempotency@floodlens.org",
    )
    db_session.add(job2)
    db_session.commit()

    claimed2 = claim_job(db_session, job_id=job2.id)
    execute_job(claimed2, db_session)
    db_session.refresh(job2)
    assert job2.status == "COMPLETED"
    extent_id_2 = job2.output_extent_id

    # Resulting extent ID must be identical (strict idempotency)
    assert extent_id_1 == extent_id_2

    # Total extents in database for this event must remain exactly 1
    total_extents = db_session.query(FloodExtent).filter(FloodExtent.event_id == concurrency_event.id).count()
    assert total_extents == 1


# ==============================================================================
# 9. Different Thresholds Preserve Distinct Results (Requirement 5 & 7)
# ==============================================================================
def test_different_thresholds_preserve_distinct_results(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """Different water index decision thresholds preserve distinct FloodExtent records."""
    job_t0 = SatelliteJob(
        id=f"sat_job_thresh0_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        threshold=0.0,
        status="QUEUED",
        requested_by="analyst@floodlens.org",
    )
    job_t2 = SatelliteJob(
        id=f"sat_job_thresh2_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        threshold=0.25,
        status="QUEUED",
        requested_by="analyst@floodlens.org",
    )
    db_session.add_all([job_t0, job_t2])
    db_session.commit()

    claimed_t0 = claim_job(db_session, job_id=job_t0.id)
    execute_job(claimed_t0, db_session)

    claimed_t2 = claim_job(db_session, job_id=job_t2.id)
    execute_job(claimed_t2, db_session)

    db_session.refresh(job_t0)
    db_session.refresh(job_t2)

    # Distinct extents generated
    assert job_t0.output_extent_id != job_t2.output_extent_id

    # Both extents exist in PostGIS without overwriting one another
    extents = db_session.query(FloodExtent).filter(FloodExtent.event_id == concurrency_event.id).all()
    extent_ids = {e.id for e in extents}
    assert job_t0.output_extent_id in extent_ids
    assert job_t2.output_extent_id in extent_ids
    assert len(extents) >= 2


# ==============================================================================
# 10. Different Source Scenes Preserve Distinct Extents (Requirement 5 & 7)
# ==============================================================================
def test_different_source_scenes_preserve_distinct_observed_extents(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """Different source scenes for the same event produce separate preserved extents."""
    scene_alt = SatelliteScene(
        id=f"scene_alt_{uuid.uuid4().hex[:6]}",
        provider="ESA Copernicus",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=concurrency_event.start_at + timedelta(days=3),
        asset_ref="backend/tests/fixtures/optical_flood_sample.geojson",
    )
    db_session.add(scene_alt)
    db_session.commit()

    job1 = SatelliteJob(
        id=f"sat_job_sc1_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="QUEUED",
        requested_by="multi_scene@floodlens.org",
    )
    job2 = SatelliteJob(
        id=f"sat_job_sc2_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=scene_alt.id,
        method="NDWI",
        status="QUEUED",
        requested_by="multi_scene@floodlens.org",
    )
    db_session.add_all([job1, job2])
    db_session.commit()

    execute_job(claim_job(db_session, job_id=job1.id), db_session)
    execute_job(claim_job(db_session, job_id=job2.id), db_session)

    db_session.refresh(job1)
    db_session.refresh(job2)

    assert job1.output_extent_id != job2.output_extent_id

    extents = db_session.query(FloodExtent).filter(FloodExtent.event_id == concurrency_event.id).all()
    assert len(extents) >= 2


# ==============================================================================
# 11. Restart Recovery Without Forcing Incorrect States (Requirement 3 & 7)
# ==============================================================================
def test_restart_recovery_without_forcing_incorrect_job_states(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """Demonstrates that on daemon/API startup, recover_interrupted_jobs() cleans up
    only genuinely abandoned jobs while respecting active workers and completed jobs."""
    now = datetime.now(timezone.utc)

    # Job A: RUNNING with live lease in the future (worker actively computing)
    job_live = SatelliteJob(
        id=f"sat_job_live_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="RUNNING",
        worker_id="remote-worker-node-42",
        started_at=now - timedelta(seconds=10),
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=50),
        retry_count=0,
        max_retries=2,
        requested_by="test@floodlens.org",
    )
    # Job B: RUNNING with expired lease (crashed process)
    job_dead = SatelliteJob(
        id=f"sat_job_dead_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="RUNNING",
        worker_id="crashed-worker-old",
        started_at=now - timedelta(seconds=120),
        heartbeat_at=now - timedelta(seconds=100),
        lease_expires_at=now - timedelta(seconds=40),
        retry_count=0,
        max_retries=2,
        requested_by="test@floodlens.org",
    )
    # Job C: COMPLETED (should remain untouched)
    job_completed = SatelliteJob(
        id=f"sat_job_done_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="COMPLETED",
        progress_percent=100.0,
        completed_at=now - timedelta(seconds=60),
        requested_by="test@floodlens.org",
    )
    db_session.add_all([job_live, job_dead, job_completed])
    db_session.commit()

    # Startup recovery runs
    recovered = recover_interrupted_jobs(db_session, now=now)
    assert recovered == 1  # Only job_dead recovered!

    db_session.refresh(job_live)
    db_session.refresh(job_dead)
    db_session.refresh(job_completed)

    assert job_live.status == "RUNNING"
    assert job_live.worker_id == "remote-worker-node-42"

    assert job_dead.status == "QUEUED"
    assert job_dead.retry_count == 1
    assert job_dead.worker_id is None

    assert job_completed.status == "COMPLETED"


# ==============================================================================
# 12. Synthetic Fixture Provenance in Downstream API Responses (Requirement 6 & 7)
# ==============================================================================
def test_synthetic_fixture_provenance_preserved_in_downstream_api_responses(
    client: TestClient,
    authority_token: str,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
    db_session: Session,
):
    """Downstream REST and GeoJSON extent APIs expose the provenance field so web
    and Android clients can distinguish synthetic, precomputed, and genuine data."""
    # Process job via background task
    res = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": concurrency_event.id, "scene_id": concurrency_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res.status_code == status.HTTP_202_ACCEPTED
    job_id = res.json()["job_id"]

    # Retrieve job status
    job_status = client.get(f"/api/v1/satellite/jobs/{job_id}", headers={"Authorization": f"Bearer {authority_token}"}).json()
    assert job_status["status"] == "COMPLETED"
    assert job_status["provenance"] == "SYNTHETIC_TEST_FIXTURE"

    # 1. GET /flood-events/{event_id}/extent
    extent_res = client.get(f"/api/v1/flood-events/{concurrency_event.id}/extent")
    assert extent_res.status_code == status.HTTP_200_OK
    extent_body = extent_res.json()
    assert extent_body["provenance"] == "SYNTHETIC_TEST_FIXTURE"

    # 2. GET /flood-events/{event_id}/extent/geojson
    geojson_res = client.get(f"/api/v1/flood-events/{concurrency_event.id}/extent/geojson")
    assert geojson_res.status_code == status.HTTP_200_OK
    gj = geojson_res.json()
    assert gj["type"] == "Feature"
    assert gj["properties"]["provenance"] == "SYNTHETIC_TEST_FIXTURE"


# ==============================================================================
# 13. Worker Ownership Safety: Expired Worker Cannot Complete Reclaimed Job
# ==============================================================================
def test_expired_worker_cannot_complete_reclaimed_job(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """When a worker's lease expires and another worker reclaims the job, the original
    worker's final completion attempt MUST abort cleanly without overwriting the job's
    status, worker_id, or committing orphaned results."""
    now = datetime.now(timezone.utc)
    job = SatelliteJob(
        id=f"sat_job_reclaimed_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="RUNNING",
        worker_id="slow-worker-1",
        started_at=now - timedelta(seconds=120),
        heartbeat_at=now - timedelta(seconds=90),
        lease_expires_at=now - timedelta(seconds=30),  # Lease expired
        retry_count=0,
        max_retries=2,
        requested_by="safety_test@floodlens.org",
    )
    db_session.add(job)
    db_session.commit()

    # Worker 2 reclaims the job via recovery scan and claims it
    recover_interrupted_jobs(db_session, now=now)
    claimed_worker_2 = claim_job(db_session, job_id=job.id, worker_id="fast-worker-2")
    assert claimed_worker_2 is not None
    assert claimed_worker_2.worker_id == "fast-worker-2"
    assert claimed_worker_2.status == "RUNNING"

    # Slow worker 1 finishes its computation and attempts to commit completion
    success = execute_job(job, db_session, worker_id="slow-worker-1")
    assert success is False

    # The job must remain RUNNING under fast-worker-2, NOT overwritten by slow-worker-1
    db_session.expire_all()
    refreshed = db_session.query(SatelliteJob).filter(SatelliteJob.id == job.id).first()
    assert refreshed.status == "RUNNING"
    assert refreshed.worker_id == "fast-worker-2"
    assert refreshed.output_extent_id is None


# ==============================================================================
# 14. Worker Ownership Safety: Expired Worker Cannot Fail Reclaimed Job
# ==============================================================================
def test_expired_worker_cannot_fail_reclaimed_job(
    db_session: Session,
    concurrency_event: FloodEvent,
):
    """If a slow/crashed worker encounters an error after another worker has reclaimed
    the job, the slow worker MUST NOT increment retry_count or mark the job FAILED."""
    now = datetime.now(timezone.utc)
    job = SatelliteJob(
        id=f"sat_job_no_fail_hijack_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id="scene_invalid_will_error",
        method="NDWI",
        status="RUNNING",
        worker_id="slow-failing-worker",
        started_at=now - timedelta(seconds=120),
        heartbeat_at=now - timedelta(seconds=90),
        lease_expires_at=now - timedelta(seconds=30),
        retry_count=0,
        max_retries=2,
        requested_by="safety_test@floodlens.org",
    )
    db_session.add(job)
    db_session.commit()

    # Reclaimed by worker 2
    recover_interrupted_jobs(db_session, now=now)
    claim_job(db_session, job_id=job.id, worker_id="new-worker-2")

    # Slow worker fails and tries to transition to QUEUED/FAILED
    success = execute_job(job, db_session, worker_id="slow-failing-worker")
    assert success is False

    # Verify slow worker did NOT alter new-worker-2's ownership or retry_count
    db_session.expire_all()
    refreshed = db_session.query(SatelliteJob).filter(SatelliteJob.id == job.id).first()
    assert refreshed.status == "RUNNING"
    assert refreshed.worker_id == "new-worker-2"
    assert refreshed.retry_count == 1  # Incremented once during recovery, not by slow worker


# ==============================================================================
# 15. Heartbeat Safety: Reclaimed Job Rejects Heartbeat and Aborts
# ==============================================================================
def test_heartbeat_fails_and_aborts_when_job_reclaimed(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """heartbeat_job() returns False if the job is no longer owned by the calling worker."""
    now = datetime.now(timezone.utc)
    job = SatelliteJob(
        id=f"sat_job_hb_reclaimed_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="RUNNING",
        worker_id="old-worker",
        started_at=now - timedelta(seconds=100),
        lease_expires_at=now - timedelta(seconds=10),
        retry_count=0,
        max_retries=2,
        requested_by="tester@floodlens.org",
    )
    db_session.add(job)
    db_session.commit()

    # Job is recovered
    recover_interrupted_jobs(db_session, now=now)

    # Old worker attempts to heartbeat
    ok = heartbeat_job(db_session, job.id, worker_id="old-worker")
    assert ok is False


# ==============================================================================
# 16. Long Computation Heartbeat Extends Lease Beyond 60s
# ==============================================================================
def test_long_gis_computation_heartbeat_extends_lease(
    db_session: Session,
    concurrency_event: FloodEvent,
    concurrency_scene: SatelliteScene,
):
    """Periodic heartbeats keep a long computation (exceeding initial lease) safe from recovery."""
    now = datetime.now(timezone.utc)
    worker_id = "long-computation-worker"

    # Start with a short 30-second lease
    job = SatelliteJob(
        id=f"sat_job_long_{uuid.uuid4().hex[:6]}",
        event_id=concurrency_event.id,
        scene_id=concurrency_scene.id,
        method="NDWI",
        status="RUNNING",
        worker_id=worker_id,
        started_at=now,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=30),
        retry_count=0,
        max_retries=2,
        requested_by="tester@floodlens.org",
    )
    db_session.add(job)
    db_session.commit()

    # Simulate computation advancing 25 seconds: heartbeat sent
    t1 = now + timedelta(seconds=25)
    ok1 = heartbeat_job(db_session, job.id, worker_id=worker_id, extend_seconds=60)
    assert ok1 is True

    # At t=40s (past initial 30s lease expiration), recovery scan runs
    t2 = now + timedelta(seconds=40)
    recovered = recover_interrupted_jobs(db_session, now=t2)
    assert recovered == 0  # Still protected!

    db_session.expire_all()
    refreshed = db_session.query(SatelliteJob).filter(SatelliteJob.id == job.id).first()
    assert refreshed.status == "RUNNING"
    assert refreshed.worker_id == worker_id

