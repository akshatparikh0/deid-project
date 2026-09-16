"""
Orchestrates turning an uploaded PDF into a fully-populated Job: extract
text blocks, run PHI detection over each block, persist DocumentBlock and
Entity rows (each entity carrying page-coordinate bounding boxes so the
Review screen can draw redaction/highlight boxes on the real rendered page
image), one Page row per page image, and seed one CategoryRule per
canonical Safe Harbor category.

Runs synchronously inside the request — fine at this document scale/traffic
level. A production deployment processing large batches would move this
onto a task queue (Celery/RQ) and let the job sit in "scanning" until a
worker picks it up; the model already has that status for exactly this
reason.
"""
from django.core.files.base import ContentFile
from django.db import transaction

from .categories import CATEGORY_META, CATEGORY_ORDER
from .detection import detect_spans
from .extraction import ExtractionError, extract_blocks
from .models import CategoryRule, DocumentBlock, Entity, Page
from .surrogates import make_surrogate

_LINE_TOLERANCE = 2.0  # points; matches extraction.py's line clustering


def _line_group_boxes(words, start, end):
    """Given a block's per-word position metadata and a detected span's
    character range, returns one box per visual line the span touches — a
    span wrapped across two lines gets two boxes rather than one box
    spanning (and over-covering) the gap between them."""
    covering = [w for w in words if w["start"] < end and w["end"] > start]
    if not covering:
        return []
    lines = []
    for w in sorted(covering, key=lambda w: w["top"]):
        if lines and abs(w["top"] - lines[-1]["top"]) <= _LINE_TOLERANCE:
            line = lines[-1]
            line["x0"] = min(line["x0"], w["x0"])
            line["x1"] = max(line["x1"], w["x1"])
            line["top"] = min(line["top"], w["top"])
            line["bottom"] = max(line["bottom"], w["bottom"])
        else:
            lines.append({"x0": w["x0"], "top": w["top"], "x1": w["x1"], "bottom": w["bottom"]})
    return lines


def run_ingestion(job, file_obj):
    """Populate `job` (already saved, status='scanning') from `file_obj`.
    On success, blocks/entities/rules/pages are created and job.status
    becomes 'in_review'. On failure, job.status becomes 'failed' with
    error_message set. Either way the job is saved before returning."""
    try:
        page_count, raw_blocks, raw_pages = extract_blocks(file_obj)
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

        for raw_page in raw_pages:
            page = Page(job=job, number=raw_page["number"], width=raw_page["width"], height=raw_page["height"])
            page.image.save(f"page-{raw_page['number']}.png", ContentFile(raw_page["png"]), save=False)
            page.save()

        entity_seq = 0
        surrogate_cache = {}

        for raw in raw_blocks:
            block = DocumentBlock.objects.create(
                job=job, index=raw["index"], page=raw["page"],
                type=raw["type"], text=raw["text"], source=raw.get("source", "text"),
            )

            spans_with_boxes = []
            if raw.get("cells"):
                for cell in raw["cells"]:
                    cell_text = raw["text"][cell["start"]:cell["end"]]
                    cell_box = [{"x0": cell["x0"], "top": cell["top"], "x1": cell["x1"], "bottom": cell["bottom"]}]
                    for span in detect_spans(cell_text, column_header=cell["header"]):
                        adjusted = {**span, "start": span["start"] + cell["start"], "end": span["end"] + cell["start"]}
                        spans_with_boxes.append((adjusted, cell_box))
            else:
                words = raw.get("words", [])
                for span in detect_spans(raw["text"]):
                    spans_with_boxes.append((span, _line_group_boxes(words, span["start"], span["end"])))

            for span, boxes in spans_with_boxes:
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
                    boxes=boxes,
                )

        folder_rules = {r.category: r for r in job.folder.rules.all()} if job.folder_id else {}
        CategoryRule.objects.bulk_create([
            CategoryRule(
                job=job,
                category=cat,
                enabled=folder_rules[cat].enabled if cat in folder_rules else True,
                mode=folder_rules[cat].mode if cat in folder_rules
                    else (job.preset if job.preset != "keep" else "mask"),
                token=folder_rules[cat].token if cat in folder_rules else CATEGORY_META[cat]["token"],
            )
            for cat in CATEGORY_ORDER
        ])

    return job
