"""
Second-pass verification (FR-81, AC-25): re-runs detection on the finalized,
redacted PDF from finalize.py and fails the job if anything that should
have been removed is still readable there — the only check that actually
proves the pipeline obeyed the reviewer-approved policy, rather than just
trusting that the redaction step ran.

Two independent checks, since neither alone is sufficient:
- literal survival: does any non-"keep" entity's *original* text still
  appear anywhere in the re-extracted output? Catches a redaction box that
  didn't fully cover a wrapped or mis-measured span.
- re-detection: does the regex/AI detection stack (the same one ingestion
  used) still find PHI-shaped spans above the verification threshold? A
  category the reviewer deliberately left as "keep" is expected to still be
  present and isn't a failure; a mask/pseudo entity's own placeholder token
  or surrogate value re-triggering a match isn't either.

Findings never carry the original plaintext value, matching the audit
record's own no-original-value rule (FR-82's caution) — only enough to
show a reviewer or auditor what kind of risk remained.
"""
from __future__ import annotations

import io
import re

from .ai_detection import PLACEHOLDER_TOKENS
from .detection import detect_spans, merge_spans
from .extraction import extract_blocks


class VerificationError(RuntimeError):
    pass


def _word_boundary_pattern(value: str) -> re.Pattern[str]:
    # A plain substring check would flag e.g. the name "Mary" as "surviving"
    # inside the unrelated word "Primary" — require it to appear as its own
    # word(s), not as a fragment of a longer one.
    return re.compile(rf"\b{re.escape(value)}\b")


def verify_redacted_pdf(pdf_bytes, entities, ai_detectors, min_confidence=0.85):
    """Returns a list of finding dicts; empty means verification passed."""
    kept_categories = {e.category for e in entities if e.mode == "keep"}
    surrogate_texts = {
        e.surrogate_value.strip().casefold()
        for e in entities
        if e.mode == "pseudo" and e.surrogate_value and e.surrogate_value.strip()
    }
    original_value_patterns = {
        (e.value.strip().casefold(), e.category): _word_boundary_pattern(e.value.strip().casefold())
        for e in entities
        if e.mode != "keep" and e.value.strip()
    }

    _, blocks, _ = extract_blocks(io.BytesIO(pdf_bytes))

    findings = []
    for block in blocks:
        text = block["text"]
        lowered = text.casefold()

        for (value, category), pattern in original_value_patterns.items():
            if pattern.search(lowered):
                findings.append({
                    "reason": "original_value_survived", "category": category, "page": block["page"],
                })

        span_lists = [detect_spans(text)]
        for detector in ai_detectors:
            span_lists.append(detector.detect(text))
        spans = merge_spans(*span_lists) if ai_detectors else span_lists[0]

        for span in spans:
            if span["confidence"] < min_confidence or span["category"] in kept_categories:
                continue
            value = text[span["start"]:span["end"]]
            if value.strip("[]") in PLACEHOLDER_TOKENS:
                continue
            if value.strip().casefold() in surrogate_texts:
                continue
            findings.append({
                "reason": "detected_on_second_pass", "category": span["category"],
                "confidence": round(span["confidence"], 4), "detector": span["detector"],
                "page": block["page"],
            })

    return findings
