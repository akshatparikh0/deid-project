"""
Orchestrates turning an uploaded PDF into a fully-populated Job: extract
text blocks, run PHI detection over each block, persist DocumentBlock and
Entity rows with stable per-job entity codes, and seed one CategoryRule per
canonical Safe Harbor category.

Runs synchronously inside the request — fine at this document scale/traffic
level. A production deployment processing large batches would move this
onto a task queue (Celery/RQ) and let the job sit in "scanning" until a
worker picks it up; the model already has that status for exactly this
reason.
"""
from django.db import transaction

from .categories import CATEGORY_META, CATEGORY_ORDER
from .detection import detect_spans
from .extraction import ExtractionError, extract_blocks
from .models import CategoryRule, DocumentBlock, Entity
from .surrogates import make_surrogate


def run_ingestion(job, file_obj):
    """Populate `job` (already saved, status='scanning') from `file_obj`.
    On success, blocks/entities/rules are created and job.status becomes
    'in_review'. On failure, job.status becomes 'failed' with error_message
    set. Either way the job is saved before returning."""
    try:
        page_count, raw_blocks = extract_blocks(file_obj)
    except ExtractionError as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.pages = 0
        job.save(update_fields=["status", "error_message", "pages"])
        return job

    with transaction.atomic():
        job.pages = page_count
        job.status = "in_review"
        job.error_message = None
        job.save(update_fields=["pages", "status", "error_message"])

        entity_seq = 0
        surrogate_cache = {}

        for raw in raw_blocks:
            block = DocumentBlock.objects.create(
                job=job, index=raw["index"], page=raw["page"],
                type=raw["type"], text=raw["text"], source=raw.get("source", "text"),
            )
            if raw.get("cells"):
                spans = []
                for cell in raw["cells"]:
                    cell_text = raw["text"][cell["start"]:cell["end"]]
                    for span in detect_spans(cell_text, column_header=cell["header"]):
                        spans.append({**span, "start": span["start"] + cell["start"], "end": span["end"] + cell["start"]})
            else:
                spans = detect_spans(raw["text"])

            for span in spans:
                entity_seq += 1
                value = raw["text"][span["start"]:span["end"]]
                cache_key = (span["category"], value.lower())
                if cache_key not in surrogate_cache:
                    surrogate_cache[cache_key] = make_surrogate(span["category"], value)
                Entity.objects.create(
                    job=job, block=block, code=f"E-{entity_seq:02d}",
                    category=span["category"], value=value,
                    surrogate_value=surrogate_cache[cache_key],
                    mode=job.preset, confidence=span["confidence"],
                    page=raw["page"], detector=span["detector"],
                    start_in_block=span["start"], end_in_block=span["end"],
                )

        CategoryRule.objects.bulk_create([
            CategoryRule(
                job=job, category=cat, enabled=True,
                mode=job.preset if job.preset != "keep" else "mask",
                token=CATEGORY_META[cat]["token"],
            )
            for cat in CATEGORY_ORDER
        ])

    return job
