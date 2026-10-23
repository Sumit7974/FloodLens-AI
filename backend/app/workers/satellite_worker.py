"""Durable database-backed background worker for satellite imagery processing jobs.

Features:
- Concurrency-safe atomic job claiming:
  * PostgreSQL: Uses SELECT ... FOR UPDATE SKIP LOCKED to guarantee that concurrent workers
    never block or claim the same job simultaneously.
  * SQLite: Uses atomic conditional UPDATE (UPDATE ... WHERE id = :id AND status = 'QUEUED')
    to prevent race conditions. Note: SQLite operates under database-level locking and does
    not support row-level SKIP LOCKED; multi-process SQLite environments may experience
    OperationalError ("database is locked") under high write contention. Production deployments
    require PostgreSQL for true non-blocking row-level concurrency.
- Database-backed worker leases and heartbeating:
  * Every claimed job is assigned an explicit worker_id, heartbeat timestamp, and lease expiration.
  * Live workers periodically refresh their lease via heartbeat_job().
- Safe crash and abandonment recovery (recover_interrupted_jobs):
  * Only jobs whose lease has demonstrably expired (lease_expires_at < now or unleased legacy)
    are eligible for recovery.
  * Active RUNNING jobs with valid leases are NEVER reset or stolen by another worker's scan.
  * Bounded retry budgeting: re-queues expired jobs up to max_retries, transitioning to FAILED once exhausted.
- Standalone CLI daemon and execution: python -m app.workers.satellite_worker
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.satellite import SatelliteJob

logger = logging.getLogger("floodlens.satellite_worker")

DEFAULT_LEASE_TIMEOUT_SECONDS = 60


def _is_postgres(db: Session) -> bool:
    """Detect if the active session is bound to a PostgreSQL engine."""
    try:
        bind_url = str(db.bind.url) if db.bind else ""
        return "postgresql" in bind_url or "postgres" in bind_url
    except Exception:
        return False


def generate_worker_id(prefix: str = "worker") -> str:
    """Generate a unique worker identity token containing PID and random UUID."""
    return f"{prefix}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def get_worker_session(override_session: Optional[Session] = None) -> Session:
    """Retrieve an active database session for worker execution."""
    if override_session is not None:
        return override_session
    # Import deferred to avoid circular dependency
    from app.services.satellite_processor import get_worker_db_session
    return get_worker_db_session()


def heartbeat_job(
    db: Session,
    job_id: str,
    worker_id: str,
    extend_seconds: int = DEFAULT_LEASE_TIMEOUT_SECONDS,
) -> bool:
    """Extend the lease and update heartbeat_at for an actively owned job.

    Returns:
        True if lease was extended, False if the job was stolen/cancelled/not found.
    """
    now = datetime.now(timezone.utc)
    is_pg = _is_postgres(db)

    if is_pg:
        job = (
            db.query(SatelliteJob)
            .filter(
                SatelliteJob.id == job_id,
                SatelliteJob.status == "RUNNING",
                SatelliteJob.worker_id == worker_id,
            )
            .with_for_update()
            .first()
        )
        if not job:
            return False
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=extend_seconds)
        db.commit()
        return True
    else:
        # Atomic conditional update for SQLite / non-PG engines
        stmt = (
            update(SatelliteJob)
            .where(
                SatelliteJob.id == job_id,
                SatelliteJob.status == "RUNNING",
                SatelliteJob.worker_id == worker_id,
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=extend_seconds),
            )
        )
        res = db.execute(stmt)
        db.commit()
        return res.rowcount > 0


def recover_interrupted_jobs(
    db: Session,
    now: Optional[datetime] = None,
) -> int:
    """Recover genuinely abandoned or expired jobs left in RUNNING status.

    Safety invariants:
    - Never resets or interferes with a genuinely active worker's job whose lease is valid.
    - Only recovers jobs whose lease has expired (lease_expires_at < now) or legacy unleased jobs.
    - Increments retry_count and re-queues if retry_count < max_retries.
    - Marks job FAILED when retry budget is exhausted.
    - Clears worker_id and lease_expires_at on recovery.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    is_pg = _is_postgres(db)

    # In PostgreSQL, lock candidate expired jobs with SKIP LOCKED to prevent concurrent recovery collisions
    if is_pg:
        interrupted_jobs = (
            db.query(SatelliteJob)
            .filter(
                SatelliteJob.status == "RUNNING",
                or_(
                    SatelliteJob.lease_expires_at.is_(None),
                    SatelliteJob.lease_expires_at < now,
                ),
            )
            .with_for_update(skip_locked=True)
            .all()
        )
    else:
        interrupted_jobs = (
            db.query(SatelliteJob)
            .filter(
                SatelliteJob.status == "RUNNING",
                or_(
                    SatelliteJob.lease_expires_at.is_(None),
                    SatelliteJob.lease_expires_at < now,
                ),
            )
            .all()
        )

    recovered_count = 0
    for job in interrupted_jobs:
        job.retry_count += 1
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None

        if job.retry_count < job.max_retries:
            logger.warning(
                "Recovering expired/abandoned job '%s' (attempt %d/%d); returning to queue.",
                job.id, job.retry_count, job.max_retries,
            )
            job.status = "QUEUED"
            job.error_message = (
                f"Worker interrupted or lease expired (attempt {job.retry_count}/{job.max_retries}); "
                "re-queued for recovery."
            )
        else:
            logger.error(
                "Job '%s' exhausted max retries (%d/%d) following abandonment/crash; marking FAILED.",
                job.id, job.retry_count, job.max_retries,
            )
            job.status = "FAILED"
            job.completed_at = now
            job.error_message = (
                f"Job failed after maximum worker recovery attempts ({job.max_retries})."
            )
        recovered_count += 1

    if recovered_count > 0:
        db.commit()

    return recovered_count


def claim_job(
    db: Session,
    job_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    lease_seconds: int = DEFAULT_LEASE_TIMEOUT_SECONDS,
) -> Optional[SatelliteJob]:
    """Atomically claim a QUEUED job for execution.

    Concurrency and atomic guarantees:
    - On PostgreSQL: utilizes SELECT ... FOR UPDATE SKIP LOCKED to guarantee that concurrent
      workers never claim the same job simultaneously.
    - On SQLite: uses atomic conditional UPDATE to ensure single-worker claiming, preventing
      in-memory/process race conditions.
    - Assigns unique worker_id, heartbeat timestamp, and lease expiration.
    - Failed claims cannot mutate the job.

    Returns:
        The claimed SatelliteJob in RUNNING status, or None if no eligible job was claimed.
    """
    now = datetime.now(timezone.utc)
    lease_expires = now + timedelta(seconds=lease_seconds)
    active_worker_id = worker_id or generate_worker_id()
    is_pg = _is_postgres(db)

    if job_id:
        if is_pg:
            job = (
                db.query(SatelliteJob)
                .filter(SatelliteJob.id == job_id, SatelliteJob.status == "QUEUED")
                .with_for_update(skip_locked=True)
                .first()
            )
            if not job:
                return None
            job.status = "RUNNING"
            job.worker_id = active_worker_id
            job.started_at = now
            job.heartbeat_at = now
            job.lease_expires_at = lease_expires
            job.progress_percent = 10.0
            db.commit()
            db.refresh(job)
            return job
        else:
            # SQLite / atomic conditional update
            stmt = (
                update(SatelliteJob)
                .where(SatelliteJob.id == job_id, SatelliteJob.status == "QUEUED")
                .values(
                    status="RUNNING",
                    worker_id=active_worker_id,
                    started_at=now,
                    heartbeat_at=now,
                    lease_expires_at=lease_expires,
                    progress_percent=10.0,
                )
            )
            res = db.execute(stmt)
            if res.rowcount == 0:
                return None
            db.commit()
            return db.query(SatelliteJob).filter(SatelliteJob.id == job_id).first()

    # General queue polling
    if is_pg:
        job = (
            db.query(SatelliteJob)
            .filter(SatelliteJob.status == "QUEUED")
            .order_by(SatelliteJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if not job:
            return None
        job.status = "RUNNING"
        job.worker_id = active_worker_id
        job.started_at = now
        job.heartbeat_at = now
        job.lease_expires_at = lease_expires
        job.progress_percent = 10.0
        db.commit()
        db.refresh(job)
        return job
    else:
        # SQLite: pick candidate ID, then atomically update where status == 'QUEUED'
        candidate = (
            db.query(SatelliteJob.id)
            .filter(SatelliteJob.status == "QUEUED")
            .order_by(SatelliteJob.created_at.asc())
            .first()
        )
        if not candidate:
            return None
        candidate_id = candidate[0]
        stmt = (
            update(SatelliteJob)
            .where(SatelliteJob.id == candidate_id, SatelliteJob.status == "QUEUED")
            .values(
                status="RUNNING",
                worker_id=active_worker_id,
                started_at=now,
                heartbeat_at=now,
                lease_expires_at=lease_expires,
                progress_percent=10.0,
            )
        )
        res = db.execute(stmt)
        if res.rowcount == 0:
            return None
        db.commit()
        return db.query(SatelliteJob).filter(SatelliteJob.id == candidate_id).first()


def execute_job(
    job: SatelliteJob,
    db: Session,
    worker_id: Optional[str] = None,
) -> bool:
    """Execute GIS processing pipeline for a claimed satellite job with heartbeating."""
    from app.services.satellite_processor import execute_satellite_pipeline, sanitize_error

    active_worker = worker_id or job.worker_id or generate_worker_id()
    logger.info("Executing satellite processing job '%s' (method=%s, worker=%s)", job.id, job.method, active_worker)

    try:
        output_extent_id, provenance = execute_satellite_pipeline(
            job,
            db,
            heartbeat_cb=lambda: heartbeat_job(db, job.id, active_worker),
        )
        job.status = "COMPLETED"
        job.progress_percent = 100.0
        job.completed_at = datetime.now(timezone.utc)
        job.output_extent_id = output_extent_id
        job.provenance = provenance
        job.error_message = None
        job.lease_expires_at = None
        db.commit()
        logger.info(
            "Job '%s' completed successfully; output extent '%s' persisted (provenance=%s).",
            job.id, output_extent_id, provenance,
        )
        return True

    except Exception as exc:
        db.rollback()
        sanitized_msg = sanitize_error(exc)
        logger.exception("Execution error in satellite job '%s': %s", job.id, sanitized_msg)

        now = datetime.now(timezone.utc)
        job.retry_count += 1
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None

        if job.retry_count < job.max_retries:
            job.status = "QUEUED"
            job.error_message = (
                f"Execution attempt {job.retry_count}/{job.max_retries} failed: {sanitized_msg}. "
                "Re-queued for retry."
            )
            logger.warning("Re-queued job '%s' for retry (%d/%d)", job.id, job.retry_count, job.max_retries)
        else:
            job.status = "FAILED"
            job.completed_at = now
            job.error_message = sanitized_msg
            logger.error("Job '%s' marked FAILED after %d retries.", job.id, job.max_retries)

        db.commit()
        return False


def run_worker_once(
    db: Optional[Session] = None,
    worker_id: Optional[str] = None,
    lease_seconds: int = DEFAULT_LEASE_TIMEOUT_SECONDS,
) -> Optional[str]:
    """Execute a single worker iteration: recover abandoned jobs, claim one job, and process it.

    Invariants:
    - Only recovers jobs whose lease has expired; active unexpired jobs are left untouched.
    - Atomic claiming ensures that no two workers can claim or execute the same job.

    Returns:
        job_id if a job was processed, or None if the queue was empty.
    """
    sess = get_worker_session(db)
    close_after = (db is None)
    active_worker = worker_id or generate_worker_id()

    try:
        # 1. Recover genuinely expired or abandoned jobs
        recover_interrupted_jobs(sess)

        # 2. Claim next available job
        claimed = claim_job(sess, worker_id=active_worker, lease_seconds=lease_seconds)
        if not claimed:
            return None

        # 3. Execute processing with heartbeats
        execute_job(claimed, sess, worker_id=active_worker)
        return claimed.id

    finally:
        if close_after:
            sess.close()


def run_worker_daemon(
    poll_interval: float = 1.0,
    max_jobs: Optional[int] = None,
    db: Optional[Session] = None,
    worker_id: Optional[str] = None,
    lease_seconds: int = DEFAULT_LEASE_TIMEOUT_SECONDS,
) -> int:
    """Continuously poll and execute queued satellite processing jobs."""
    active_worker = worker_id or generate_worker_id(prefix="daemon")
    logger.info(
        "Starting FloodLens AI Satellite Worker Daemon (worker_id=%s, poll_interval=%.2fs)...",
        active_worker, poll_interval,
    )
    jobs_processed = 0

    while True:
        try:
            job_id = run_worker_once(db=db, worker_id=active_worker, lease_seconds=lease_seconds)
            if job_id:
                jobs_processed += 1
                if max_jobs is not None and jobs_processed >= max_jobs:
                    logger.info("Processed target limit of %d jobs; terminating daemon loop.", max_jobs)
                    break
            else:
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.info("Worker daemon received shutdown signal (SIGINT). Stopping cleanly.")
            break
        except Exception as e:
            logger.error("Unexpected worker loop error: %s", e)
            time.sleep(poll_interval)

    return jobs_processed


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="FloodLens AI Satellite Background Worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds")
    parser.add_argument("--max-jobs", type=int, default=None, help="Maximum jobs to process before exiting")
    parser.add_argument("--worker-id", type=str, default=None, help="Explicit worker identifier token")
    parser.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_TIMEOUT_SECONDS, help="Lease timeout duration in seconds")
    args = parser.parse_args()

    if args.once:
        processed_id = run_worker_once(worker_id=args.worker_id, lease_seconds=args.lease_seconds)
        print(f"Single iteration finished. Processed job: {processed_id}")
    else:
        run_worker_daemon(
            poll_interval=args.interval,
            max_jobs=args.max_jobs,
            worker_id=args.worker_id,
            lease_seconds=args.lease_seconds,
        )
