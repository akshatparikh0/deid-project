"""
Runs each job's pipeline (ingest.run_ingestion) as a Celery task so the
upload request can return immediately and many files can process at once.
With no broker configured, CELERY_TASK_ALWAYS_EAGER runs the task
synchronously in-process (see deid_backend/settings.py) — same zero-setup
local-dev behavior as before, but a real broker/worker can be pointed at in
production without any code change here.
"""
import logging

from celery import shared_task
from django.utils import timezone

from .categories import STAGE_ORDER
from .ingest import run_ingestion
from .models import Job, JobStage

logger = logging.getLogger(__name__)


def seed_stages(job):
    """(Re)creates job's stage rows: 'ingest' is already done by the time
    this is called (the file is saved synchronously in the request), the
    rest start 'pending' until the worker picks the job up."""
    now = timezone.now()
    JobStage.objects.filter(job=job).delete()
    JobStage.objects.bulk_create([
        JobStage(job=job, name=name, sequence=i, status="done", started_at=now, finished_at=now)
        if name == "ingest"
        else JobStage(job=job, name=name, sequence=i, status="pending")
        for i, name in enumerate(STAGE_ORDER, start=1)
    ])


@shared_task(name="documents.ingest_job")
def ingest_job(job_id):
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
