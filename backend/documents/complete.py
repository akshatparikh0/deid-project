"""
Orchestrates job completion (JobCompleteView): reviewer-approved PyMuPDF
finalization (finalize.py) -> permanent audit trail (audit.py) -> the
canonical "pdf" export artifact. Wrapped in one atomic step so the audit
trail and export artifact are never left partially written.
"""
from __future__ import annotations

from django.core.files.base import ContentFile
from django.db import transaction

from pipeline.finalize import build_redacted_pdf

from .audit import write_audit_records
from .models import ExportArtifact

__all__ = ["complete_job"]


def complete_job(job):
    """Runs finalization + audit trail for a job whose entities are all
    reviewer-approved. Returns the finalized PDF bytes."""
    entities = list(job.entities.order_by("code"))

    with job.file.open("rb") as fh:
        source_bytes = fh.read()

    page_rotations = {p.number: p.rotation for p in job.page_images.all()}
    redacted_bytes = build_redacted_pdf(source_bytes, entities, page_rotations)

    with transaction.atomic():
        write_audit_records(job, entities)
        artifact, _ = ExportArtifact.objects.update_or_create(
            job=job, format="pdf", defaults={"filename": f"{job.code}_deid.pdf"},
        )
        artifact.file.save(f"{job.code}_deid.pdf", ContentFile(redacted_bytes), save=True)

    return redacted_bytes
