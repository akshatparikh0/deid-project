"""
Orchestrates turning an uploaded PDF into a fully-populated Job: validate,
extract text blocks, run PHI detection (the regex engine, plus Azure AI
Language and/or Claude when enabled) over each block, persist
DocumentBlock and Entity rows (each entity carrying page-coordinate
bounding boxes so the Review screen can draw redaction/highlight boxes on
the real rendered page image), one Page row per page image, and seed one
CategoryRule per canonical Safe Harbor category.

Runs as a Celery task (see tasks.py), advancing job.status through the
parse/detect/transform/finalize stages (categories.STAGE_ORDER) and recording
each one's start/finish on a JobStage row so the Status page can poll live
per-stage progress and timing for many jobs at once.
"""
import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .ai_detection import DetectorConfigError, build_detectors
from .categories import CATEGORY_META, CATEGORY_ORDER, STAGE_ORDER
from .detection import detect_spans, merge_spans
from .extraction import ExtractionError, extract_blocks
from .models import CategoryRule, DocumentBlock, Entity, JobStage, Page
from .surrogates import make_surrogate
from .validation import ValidationError, validate_pdf

logger = logging.getLogger(__name__)

_LINE_TOLERANCE = 2.0  # points; matches extraction.py's line clustering


def _line_group_boxes(words, start, end):
    """Given a block's per-word position metadata and a detected span's
    character range, returns one box per visual line the span touches — a
    span wrapped across two lines gets two boxes rather than one box
    spanning (and over-covering) the gap between them.

    Words carry a "line_key" marking which of the block's own already-
    correctly-clustered physical lines they came from (see
    extraction.py's _group_words_into_lines/_group_lines_into_blocks) —
    grouping by that instead of re-deriving line boundaries from raw
    top-coordinates a second time matters on a skewed scan, where a single
    line's words can land more than _LINE_TOLERANCE apart vertically:
    re-clustering by tolerance alone would fragment one true line into
    several undersized boxes, or bleed two adjacent lines into one
    oversized box that then overlaps neighboring text once finalize.py
    draws (and, for a rotated page, rotates) it."""
    covering = [w for w in words if w["start"] < end and w["end"] > start]
    if not covering:
        return []
    if all("line_key" in w for w in covering):
        grouped = {}
        order = []
        for w in covering:
            key = w["line_key"]
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(w)
        lines = []
        for key in order:
            group = grouped[key]
            lines.append({
                "x0": min(w["x0"] for w in group), "top": min(w["top"] for w in group),
                "x1": max(w["x1"] for w in group), "bottom": max(w["bottom"] for w in group),
            })
        return sorted(lines, key=lambda l: l["top"])

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


def _start_stage(job, name):
    """get_or_create (rather than a strict get) means run_ingestion stays
    independently callable without a prior seed_stages() call — exactly how
    the ingest test suite invokes it today — so no test fixture needed to
    change for this refactor."""
    stage, _ = JobStage.objects.get_or_create(
        job=job, name=name, defaults={"sequence": STAGE_ORDER.index(name) + 1},
    )
    stage.status = "running"
    stage.started_at = timezone.now()
    stage.finished_at = None
    stage.error_message = None
    stage.save(update_fields=["status", "started_at", "finished_at", "error_message"])
    return stage


def _finish_stage(stage):
    stage.status = "done"
    stage.finished_at = timezone.now()
    stage.save(update_fields=["status", "finished_at"])


def _fail_stage(stage, message):
    stage.status = "failed"
    stage.finished_at = timezone.now()
    stage.error_message = message
    stage.save(update_fields=["status", "finished_at", "error_message"])


def _fail_job(job, message, pages=None):
    job.status = "failed"
    job.error_message = message
    fields = ["status", "error_message"]
    if pages is not None:
        job.pages = pages
        fields.append("pages")
    job.save(update_fields=fields)


def _detect_all(text, ai_detectors, column_header=None):
    """Runs the regex engine plus every enabled AI detector (Azure AI
    Language, Claude — see ai_detection.py) over one block/cell of text and
    resolves overlaps across all of them together, so a higher-confidence
    match from either kind of engine always wins (FR-20)."""
    span_lists = [detect_spans(text, column_header=column_header)]
    for detector in ai_detectors:
        span_lists.append(detector.detect(text))
    return merge_spans(*span_lists) if ai_detectors else span_lists[0]


def _spans_for_block(raw, ai_detectors):
    """Runs PHI detection over one extracted block, returning
    [(span, boxes), ...] — boxes already mapped onto the block's page-
    coordinate geometry so entities can be persisted directly from this."""
    spans_with_boxes = []
    if raw.get("cells"):
        for cell in raw["cells"]:
            cell_text = raw["text"][cell["start"]:cell["end"]]
            cell_box = [{"x0": cell["x0"], "top": cell["top"], "x1": cell["x1"], "bottom": cell["bottom"]}]
            for span in _detect_all(cell_text, ai_detectors, column_header=cell["header"]):
                adjusted = {**span, "start": span["start"] + cell["start"], "end": span["end"] + cell["start"]}
                spans_with_boxes.append((adjusted, cell_box))
    else:
        words = raw.get("words", [])
        for span in _detect_all(raw["text"], ai_detectors):
            spans_with_boxes.append((span, _line_group_boxes(words, span["start"], span["end"])))
    return spans_with_boxes


def run_ingestion(job, file_obj):
    """Populate `job` (already saved, status='scanning') from `file_obj`,
    advancing it through parse -> detect -> transform -> finalize. On
    success, blocks/entities/rules/pages are created and job.status becomes
    'in_review' with enabled rules already applied (see the 'finalize'
    stage below). On failure, job.status becomes 'failed' with
    error_message set, and the stage that failed is recorded. Either way
    the job is saved before returning."""
    parse_stage = _start_stage(job, "parse")
    try:
        ai_detectors = build_detectors(settings)

        validate_pdf(
            file_obj,
            filename=getattr(file_obj, "name", job.filename),
        )

        file_obj.seek(0)

        page_count, raw_blocks, raw_pages = extract_blocks(
            file_obj,
            force_ocr=settings.REDACTION_FORCE_OCR,
            azure_ocr_enabled=settings.REDACTION_ENABLE_AZURE_OCR,
        )
    except (ValidationError, ExtractionError, DetectorConfigError) as exc:
        _fail_stage(parse_stage, str(exc))
        _fail_job(job, str(exc), pages=0)
        return job
    except Exception:
        logger.exception("Unexpected error parsing job %s", job.id)
        message = "An unexpected error occurred while parsing this PDF."
        _fail_stage(parse_stage, message)
        _fail_job(job, message, pages=0)
        return job
    _finish_stage(parse_stage)

    detect_stage = _start_stage(job, "detect")
    try:
        # [(raw_block, [(span, boxes), ...]), ...] — kept in memory; nothing
        # is persisted until 'finalize' so a mid-stage failure leaves no
        # partial rows behind.
        detected = [(raw, _spans_for_block(raw, ai_detectors)) for raw in raw_blocks]
    except Exception:
        logger.exception("Unexpected error detecting PHI for job %s", job.id)
        message = "An unexpected error occurred while detecting identifiers."
        _fail_stage(detect_stage, message)
        _fail_job(job, message)
        return job
    _finish_stage(detect_stage)

    transform_stage = _start_stage(job, "transform")
    try:
        surrogate_cache = {}
        for raw, spans_with_boxes in detected:
            for span, _boxes in spans_with_boxes:
                value = raw["text"][span["start"]:span["end"]]
                cache_key = (span["category"], value.lower())
                if cache_key not in surrogate_cache:
                    surrogate_cache[cache_key] = make_surrogate(span["category"], value)
    except Exception:
        logger.exception("Unexpected error generating surrogates for job %s", job.id)
        message = "An unexpected error occurred while transforming identifiers."
        _fail_stage(transform_stage, message)
        _fail_job(job, message)
        return job
    _finish_stage(transform_stage)

    finalize_stage = _start_stage(job, "finalize")
    try:
        with transaction.atomic():
            job.pages = page_count
            job.status = "in_review"
            job.error_message = None
            job.save(update_fields=["pages", "status", "error_message"])

            for raw_page in raw_pages:
                page = Page(
                    job=job, number=raw_page["number"], width=raw_page["width"], height=raw_page["height"],
                    rotation=raw_page.get("rotation", 0.0),
                )
                page.image.save(f"page-{raw_page['number']}.png", ContentFile(raw_page["png"]), save=False)
                page.save()

            entity_seq = 0
            for raw, spans_with_boxes in detected:
                block = DocumentBlock.objects.create(
                    job=job, index=raw["index"], page=raw["page"],
                    type=raw["type"], text=raw["text"], source=raw.get("source", "text"),
                )
                for span, boxes in spans_with_boxes:
                    entity_seq += 1
                    value = raw["text"][span["start"]:span["end"]]
                    cache_key = (span["category"], value.lower())
                    # FR-21: apply detection.min_confidence via the job's
                    # confidence_threshold — a span below it still becomes a
                    # reviewable Entity (never silently dropped), it just
                    # defaults to "keep" instead of the job's preset mode, so
                    # a low-confidence guess doesn't change the document
                    # until a reviewer confirms it (AC-13). The auto-apply
                    # step below (for jobs with no manual review checkpoint)
                    # is scoped to respect this same floor.
                    default_mode = job.preset if span["confidence"] >= job.confidence_threshold else "keep"
                    Entity.objects.create(
                        job=job, block=block, code=f"E-{entity_seq:02d}",
                        category=span["category"], value=value,
                        surrogate_value=surrogate_cache[cache_key],
                        mode=default_mode, confidence=span["confidence"],
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

            # Equivalent to the old client-triggered POST /rules/apply/ step
            # (JobRulesApplyView), folded into the pipeline itself: a batch
            # of jobs has no per-job human checkpoint between scan and
            # review, so a job reaching 'in_review' must already be fully
            # review-ready. Scoped to confidence_threshold and above so this
            # can't undo the FR-21 "keep" floor a low-confidence entity just
            # got above — those still need an explicit reviewer decision.
            for rule in job.rules.filter(enabled=True):
                job.entities.filter(
                    category=rule.category, confidence__gte=job.confidence_threshold,
                ).update(mode=rule.mode)
    except Exception:
        logger.exception("Unexpected error finalizing job %s", job.id)
        message = "An unexpected error occurred while saving results."
        _fail_stage(finalize_stage, message)
        _fail_job(job, message)
        return job
    _finish_stage(finalize_stage)

    return job
