"""
Orchestrates job completion (JobCompleteView): reviewer-approved PyMuPDF
finalization (finalize.py) -> permanent audit trail (audit.py) -> the
canonical "pdf" export artifact -> replacing the Review screen's page-
preview images with renders of the finalized PDF. Wrapped in one atomic
step so none of this is ever left partially written.
"""
from __future__ import annotations

from django.core.files.base import ContentFile
from django.db import transaction

from pipeline.extraction import render_page_images
from pipeline.finalize import build_redacted_pdf

from .audit import write_audit_records
from .models import ExportArtifact, Page

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

        # Job.purge_source_file() (called by the caller right after this
        # succeeds) deletes the original upload for good — replace its
        # page-preview images with renders of the *finalized* PDF first, so
        # the Review screen's "De-identified output" pane (the only pane
        # left once a job is complete) still has something safe to show,
        # and the export button still has page images to fall back on.
        # Nothing here ever renders unredacted content.
        for page in job.page_images.all():
            page.image.delete(save=False)
        job.page_images.all().delete()
        for raw_page in render_page_images(redacted_bytes):
            page = Page(
                job=job, number=raw_page["number"], width=raw_page["width"], height=raw_page["height"],
                rotation=page_rotations.get(raw_page["number"], 0.0),
            )
            page.image.save(f"page-{raw_page['number']}.png", ContentFile(raw_page["png"]), save=False)
            page.save()

    return redacted_bytes
