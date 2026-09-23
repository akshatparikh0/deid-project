"""
Orchestrates job completion (JobCompleteView): reviewer-approved PyMuPDF
finalization (finalize.py) -> second-pass verification (verify.py) ->
permanent audit trail (audit.py) -> the canonical "pdf" export artifact.
All wrapped in one atomic step so a verification failure can never leave a
job "complete" with an unverified or partially-written result — and so the
source file (purged separately by the caller right after) is never removed
before a finalized, verified replacement exists.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from .ai_detection import build_detectors
from .audit import write_audit_records
from .finalize import build_redacted_pdf
from .models import ExportArtifact
from .policy import load_policy
from .verify import VerificationError, verify_redacted_pdf

logger = logging.getLogger(__name__)

__all__ = ["VerificationError", "complete_job"]


def complete_job(job):
    """Runs finalization + verification + audit trail for a job whose
    entities are all reviewer-approved. Raises VerificationError (leaving
    the job's file and every DB row untouched) if a blocking identifier
    survives finalization — the caller must not mark the job complete or
    purge the source file in that case. Returns the finalized PDF bytes on
    success."""
    entities = list(job.entities.order_by("code"))

    with job.file.open("rb") as fh:
        source_bytes = fh.read()

    page_rotations = {p.number: p.rotation for p in job.page_images.all()}
    redacted_bytes = build_redacted_pdf(source_bytes, entities, page_rotations)

    policy = load_policy()
    if policy.get("verify", True):
        ai_detectors = build_detectors(settings)
        # The redacted PDF's own inserted "[TOKEN]" text can, on a heavily
        # redacted page, be enough native text on its own to make
        # extract_blocks skip OCR — exactly the moment a scanned source's
        # still-fully-visible underlying image most needs re-checking (see
        # verify_redacted_pdf's docstring). Force it whenever this job's
        # original extraction needed OCR in the first place, since that
        # same source image is still sitting underneath the redaction here.
        needs_ocr = job.blocks.filter(source__in=["tesseract", "azure_ocr"]).exists()
        findings = verify_redacted_pdf(
            redacted_bytes, entities, ai_detectors,
            min_confidence=float(policy.get("verification_min_confidence", 0.85)),
            force_ocr=needs_ocr,
        )
        ai_engines = {"azure_ai_language", "anthropic"}
        blocking = [f for f in findings if f.get("detector") not in ai_engines or f["reason"] == "original_value_survived"]
        advisory = [f for f in findings if f not in blocking]

        if advisory and not policy.get("ai_verification_is_blocking", False):
            logger.warning(
                "Job %s: %d AI-only verification finding(s) did not block completion "
                "(ai_verification_is_blocking=False): %s",
                job.code, len(advisory), advisory,
            )
        elif advisory:
            blocking = blocking + advisory

        if blocking:
            raise VerificationError(
                f"Verification failed: {len(blocking)} possible identifier(s) remain in the "
                "finalized document. The document was not delivered."
            )

    with transaction.atomic():
        write_audit_records(job, entities)
        artifact, _ = ExportArtifact.objects.update_or_create(
            job=job, format="pdf", defaults={"filename": f"{job.code}_deid.pdf"},
        )
        artifact.file.save(f"{job.code}_deid.pdf", ContentFile(redacted_bytes), save=True)

    return redacted_bytes
