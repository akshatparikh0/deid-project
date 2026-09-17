"""
Runs each job's pipeline (ingest.run_ingestion) on a background thread so the
upload request can return immediately and many files can process at once,
without introducing a separate task-queue service (Celery/RQ) — appropriate
for this app's in-process, single-server scale.

Caveat: the executor below is a per-process singleton. If this app is ever
deployed under multiple WSGI worker processes, effective concurrency
multiplies by the process count — lower INGEST_MAX_WORKERS accordingly.
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections
from django.utils import timezone

from .categories import STAGE_ORDER
from .ingest import run_ingestion
from .models import Job, JobStage

logger = logging.getLogger(__name__)

# OCR/extraction is CPU- and memory-heavy per file, and SQLite (even in WAL
# mode) still serializes writes — a small pool keeps a typical box responsive
# to Status-page polling while several files progress in parallel.
MAX_WORKERS = int(os.environ.get("INGEST_MAX_WORKERS", "3"))
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="ingest")


def seed_stages(job):
    """(Re)creates job's stage rows: 'ingest' is already done by the time
    this is called (the file is saved synchronously in the request), the
    rest start 'pending' until the worker thread picks the job up."""
    now = timezone.now()
    JobStage.objects.filter(job=job).delete()
    JobStage.objects.bulk_create([
        JobStage(job=job, name=name, sequence=i, status="done", started_at=now, finished_at=now)
        if name == "ingest"
        else JobStage(job=job, name=name, sequence=i, status="pending")
        for i, name in enumerate(STAGE_ORDER, start=1)
    ])


def submit_job(job_id):
    _executor.submit(_process, job_id)


def _process(job_id):
    close_old_connections()
    try:
        job = Job.objects.select_related("folder").get(pk=job_id)
        with job.file.open("rb") as fh:
            run_ingestion(job, fh)
    except Exception:
        logger.exception("Unhandled error processing job %s", job_id)
        Job.objects.filter(pk=job_id).update(
            status="failed",
            error_message="An unexpected server error interrupted processing.",
        )
        JobStage.objects.filter(job_id=job_id, status="running").update(
            status="failed", finished_at=timezone.now(), error_message="Unexpected server error.",
        )
    finally:
        close_old_connections()
