"""
Reviewer-approved finalization (FR-76 – FR-83). Once a job's entity modes
are locked in by the reviewer (JobCompleteView), this burns the approved
transformations into the *original* uploaded PDF's content stream using
PyMuPDF's true redaction — the text is removed from the page, not painted
over (FR-80) — rather than the reportlab reconstruction export.py uses for
a lighter-weight on-demand download that doesn't need the original file
still on disk. This is what makes the finalized PDF byte-for-byte
attributable to the source document: same page count, size, and layout
(FR-77), with only the approved spans different (FR-78/FR-79).
"""
from __future__ import annotations

import io

import pymupdf


def _replacement_text(entity):
    if entity.mode == "mask":
        return entity.token
    if entity.mode == "pseudo":
        return entity.surrogate_value or entity.token
    return None  # "redact" burns a blank black bar; "keep" is never passed in


def build_redacted_pdf(source_bytes: bytes, entities) -> bytes:
    """Returns the finalized PDF bytes. Every non-"keep" entity's boxes
    (one rectangle per visual line — see Entity.boxes) become a true
    redaction annotation: a black bar with no recoverable text for
    "redact", or a white box carrying the category's placeholder token
    ("mask") or the entity's deterministic surrogate value ("pseudo"),
    drawn once per entity (on its first box only, so a value wrapped across
    lines doesn't repeat its replacement text). "keep" entities are left
    untouched."""
    with pymupdf.open(stream=source_bytes, filetype="pdf") as pdf:
        by_page: dict[int, list] = {}
        for entity in entities:
            if entity.mode == "keep":
                continue
            by_page.setdefault(entity.page, []).append(entity)

        for page_number, page_entities in by_page.items():
            if page_number < 1 or page_number > pdf.page_count:
                continue
            page = pdf[page_number - 1]
            for entity in page_entities:
                if not entity.boxes:
                    continue
                replacement = _replacement_text(entity)
                is_redact = entity.mode == "redact"
                for index, box in enumerate(entity.boxes):
                    rect = pymupdf.Rect(box["x0"], box["top"], box["x1"], box["bottom"])
                    page.add_redact_annot(
                        rect,
                        text=replacement if index == 0 else None,
                        fontname="helv",
                        fontsize=8,
                        fill=(0, 0, 0) if is_redact else (1, 1, 1),
                        text_color=(1, 1, 1) if is_redact else (0, 0, 0),
                        cross_out=False,
                    )

        for page in pdf:
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)

        # A source PDF's metadata/XML metadata can itself carry PHI (author,
        # title, custom fields set by the EHR that exported it).
        pdf.set_metadata({})
        pdf.del_xml_metadata()

        buf = io.BytesIO()
        pdf.save(buf, garbage=4, deflate=True, clean=True)
        return buf.getvalue()
