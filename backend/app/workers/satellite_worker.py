"""Durable database-backed background worker for satellite imagery processing jobs.

Features:
- Atomic job claiming to prevent duplicate execution across multiple workers (FOR UPDATE SKIP LOCKED on PostgreSQL).
- Controlled retry budgeting with safe error recording.
- Safe crash/restart recovery (recover_interrupted_jobs).
- Bounded concurrency and idempotent output extent persistence.
- Standalone CLI execution: python -m app.workers.satellite_worker
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.satellite import SatelliteJob

logger = logging.getLogger("floodlens.satellite_worker")


def get_worker_session(override_session: Optional[Session] = None) -> Session:
    """Retrieve an active database session for worker execution."""
    if override_session is not None:
        return override_session
    # Import deferred to avoid circular dependency
    from app.services.satellite_processor import get_worker_db_session
    return get_worker_db_session()


def recover_interrupted_jobs(db: Session) -> int:
    """Recover jobs left in RUNNING status following a process crash or worker restart.

    Interrupted jobs with remaining retry budget are reset to QUEUED.
    Jobs that have exhausted their retry budget are marked FAILED.
    """
    interrupted_jobs = (
        db.query(SatelliteJob)
        .filter(SatelliteJob.status == "RUNNING")
        .all()
    )
    recovered_count = 0
    now = datetime.now(timezone.utc)

    for job in interrupted_jobs:
        job.retry_count += 1
        if job.retry_count < job.max_retries:
            logger.warning(
                "Recovering interrupted job '%s' (retry %d/%d); re-queuing.",
                job.id, job.retry_count, job.max_retries,
            )
            job.status = "QUEUED"
            job.error_message = (
                f"Worker interrupted during execution (attempt {job.retry_count}/{job.max_retries}); "
                "re-queued for recovery."
            )
        else:
            logger.error(
                "Job '%s' exhausted max retries (%d/%d) after worker interruption; marking FAILED.",
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


def claim_job(db: Session, job_id: Optional[str] = None) -> Optional[SatelliteJob]:
    """Atomically claim a QUEUED job for execution.

    On PostgreSQL, utilizes SELECT ... FOR UPDATE SKIP LOCKED to guarantee that concurrent
    workers never claim the same job simultaneously.
    On SQLite, performs an atomic state verification and transition.

    Returns:
        The claimed SatelliteJob in RUNNING status, or None if no eligible job was claimed.
    """
    now = datetime.now(timezone.utc)

    if job_id:
        # Claim a specific target job if still QUEUED
        job = (
            db.query(SatelliteJob)
            .filter(SatelliteJob.id == job_id, SatelliteJob.status == "QUEUED")
            .first()
        )
        if not job:
            return None
        job.status = "RUNNING"
        job.started_at = now
        job.progress_percent = 10.0
        db.commit()
        db.refresh(job)
        return job

    # Autonomous queue polling: pick oldest QUEUED job
    is_pg = False
    try:
        bind_url = str(db.bind.url) if db.bind else ""
        is_pg = "postgresql" in bind_url or "postgres" in bind_url
    except Exception:
        pass

    if is_pg:
        job = (
            db.query(SatelliteJob)
            .filter(SatelliteJob.status == "QUEUED")
            .order_by(SatelliteJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
    else:
        job = (
            db.query(SatelliteJob)
            .filter(SatelliteJob.status == "QUEUED")
            .order_by(SatelliteJob.created_at.asc())
            .first()
        )

    if not job:
        return None

    job.status = "RUNNING"
    job.started_at = now
    job.progress_percent = 10.0
    db.commit()
    db.refresh(job)
    return job


def execute_job(job: SatelliteJob, db: Session) -> bool:
    """Execute GIS processing pipeline for a claimed satellite job."""
    from app.services.satellite_processor import execute_satellite_pipeline, sanitize_error

    logger.info("Executing satellite processing job '%s' (method=%s)", job.id, job.method)
    try:
        output_extent_id, provenance = execute_satellite_pipeline(job, db)
        job.status = "COMPLETED"
        job.progress_percent = 100.0
        job.completed_at = datetime.now(timezone.utc)
        job.output_extent_id = output_extent_id
        job.provenance = provenance
        job.error_message = None
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


def run_worker_once(db: Optional[Session] = None) -> Optional[str]:
    """Execute a single worker iteration: recover interrupted jobs, then claim and process one job.

    Returns:
        job_id if a job was processed, or None if the queue was empty.
    """
    sess = get_worker_session(db)
    close_after = (db is None)

    try:
        # 1. Recover any interrupted jobs
        recover_interrupted_jobs(sess)

        # 2. Claim next available job
        claimed = claim_job(sess)
        if not claimed:
            return None

        # 3. Execute processing
        execute_job(claimed, sess)
        return claimed.id

    finally:
        if close_after:
            sess.close()


def run_worker_daemon(
    poll_interval: float = 1.0,
    max_jobs: Optional[int] = None,
    db: Optional[Session] = None,
) -> int:
    """Continuously poll and execute queued satellite processing jobs."""
    logger.info("Starting FloodLens AI Satellite Worker Daemon (poll_interval=%.2fs)...", poll_interval)
    jobs_processed = 0

    while True:
        try:
            job_id = run_worker_once(db=db)
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
    args = parser.parse_args()

    if args.once:
        processed_id = run_worker_once()
        print(f"Single iteration finished. Processed job: {processed_id}")
    else:
        run_worker_daemon(poll_interval=args.interval, max_jobs=args.max_jobs)
