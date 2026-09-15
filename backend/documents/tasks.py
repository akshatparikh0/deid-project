"""
Celery task wrapping run_ingestion (FR-56/FR-57). documents/ingest.py stays
framework-agnostic on purpose — this is the only module that knows about
Celery, the same "framework-neutral facade" pattern
redaction_pipeline/integration.py uses for the standalone pipeline.

With no broker configured, CELERY_TASK_ALWAYS_EAGER (settings.py) runs this
synchronously in the request, so JobListCreateView's behavior is unchanged
from before async processing was added — .delay() just becomes a same-
process function call. A real deployment sets CELERY_BROKER_URL and runs
`celery -A deid_backend worker -Q deid-ingest`.
"""
from celery import shared_task

from .ingest import run_ingestion
from .models import Job


@shared_task(name="documents.ingest_job")
def ingest_job(job_id):
    job = Job.objects.get(pk=job_id)
    with job.file.open("rb") as fh:
        run_ingestion(job, fh)
    return job.status
