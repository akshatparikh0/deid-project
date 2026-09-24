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
import math

import pymupdf

_MIN_ROTATION_DEGREES = 0.5  # below this a page is treated as unrotated — not worth the extra complexity/risk
# OCR's own word bounding boxes run slightly narrower than the glyphs they report (confirmed against a
# real scan — a redaction box built exactly to an OCR word's reported edges left the last character of
# an email address exposed), so every box gets a small safety margin before it's ever drawn, rotated or
# not. Horizontal padding is comfortably safe (word-to-word gaps on a line run well over this); vertical
# padding has to stay much smaller — real documents routinely pack lines only 1-2pt apart (confirmed
# against a real document, where a 2pt vertical pad on both sides of two boxes closed that whole gap and
# silently destroyed part of an entirely different field sitting on the very next line).
_BOX_PADDING_X = 2.0
_BOX_PADDING_Y = 0.4


def _padded_box(box):
    return {
        "x0": box["x0"] - _BOX_PADDING_X, "top": box["top"] - _BOX_PADDING_Y,
        "x1": box["x1"] + _BOX_PADDING_X, "bottom": box["bottom"] + _BOX_PADDING_Y,
    }


def _replacement_text(entity):
    if entity.mode == "mask":
        return entity.token
    if entity.mode == "pseudo":
        return entity.surrogate_value or entity.token
    return None  # "redact" burns a blank black bar; "keep" is never passed in


def _rotated_box_quad(box, angle_degrees):
    """A box's own (x0, top, x1, bottom) is an axis-aligned rectangle sized
    to bound the (possibly tilted) glyphs it covers on a scanned page —
    rotating that same box around its own center by the page's detected
    skew angle turns it into a close approximation of the true, tilted
    rectangle the text actually sits in, instead of a wider axis-aligned
    box that has to overshoot the glyphs on one side to still cover them on
    the other (bleeding into a neighboring line) or else undershoot and
    leave a sliver of the tilted text exposed."""
    cx = (box["x0"] + box["x1"]) / 2
    cy = (box["top"] + box["bottom"]) / 2
    half_w = (box["x1"] - box["x0"]) / 2
    half_h = (box["bottom"] - box["top"]) / 2
    rad = math.radians(angle_degrees)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    def corner(dx, dy):
        return pymupdf.Point(cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)

    return pymupdf.Quad(
        corner(-half_w, -half_h), corner(half_w, -half_h),
        corner(-half_w, half_h), corner(half_w, half_h),
    )


def _rotated_text_origin(box, angle_degrees):
    """A roughly baseline-ish start point for the replacement token, at the
    box's rotated bottom-left corner (nudged up slightly for the font's
    descent) — the same corner insert_text's un-rotated (point, text) call
    already treats as its origin, just carried through the same rotation as
    the box itself so the two stay aligned."""
    cx = (box["x0"] + box["x1"]) / 2
    cy = (box["top"] + box["bottom"]) / 2
    half_w = (box["x1"] - box["x0"]) / 2
    half_h = (box["bottom"] - box["top"]) / 2
    rad = math.radians(angle_degrees)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    dx, dy = -half_w, half_h - 2
    return pymupdf.Point(cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)


def build_redacted_pdf(source_bytes: bytes, entities, page_rotations: dict[int, float] | None = None) -> bytes:
    """Returns the finalized PDF bytes. Every non-"keep" entity's boxes
    (one rectangle per visual line — see Entity.boxes) become a true
    redaction annotation: a black bar with no recoverable text for
    "redact", or a white box carrying the category's placeholder token
    ("mask") or the entity's deterministic surrogate value ("pseudo"),
    drawn once per entity (on its first box only, so a value wrapped across
    lines doesn't repeat its replacement text). "keep" entities are left
    untouched.

    page_rotations (page number -> degrees, from Page.rotation) lets a
    scanned page's boxes and their replacement text be drawn at the same
    angle as the tilted text they cover, instead of an axis-aligned box
    that overlaps neighboring text or leaves a sliver of the original
    exposed. A redaction annotation's own `text` parameter, confirmed
    experimentally, is always drawn horizontally regardless of the quad's
    rotation — so on a rotated page the replacement token is instead
    inserted separately, after apply_redactions(), using insert_text's
    `morph` to rotate it to match (text inserted before that call would
    itself be swept up and blanked by the very redaction it's meant to
    replace)."""
    page_rotations = page_rotations or {}
    with pymupdf.open(stream=source_bytes, filetype="pdf") as pdf:
        by_page: dict[int, list] = {}
        for entity in entities:
            if entity.mode == "keep":
                continue
            by_page.setdefault(entity.page, []).append(entity)

        pending_text = []  # (page_number, origin, text, angle) — drawn after apply_redactions()

        for page_number, page_entities in by_page.items():
            if page_number < 1 or page_number > pdf.page_count:
                continue
            page = pdf[page_number - 1]
            angle = page_rotations.get(page_number, 0.0)
            rotated = abs(angle) >= _MIN_ROTATION_DEGREES
            for entity in page_entities:
                if not entity.boxes:
                    continue
                replacement = _replacement_text(entity)
                is_redact = entity.mode == "redact"
                fill = (0, 0, 0) if is_redact else (1, 1, 1)
                text_color = (1, 1, 1) if is_redact else (0, 0, 0)
                for index, box in enumerate(entity.boxes):
                    # A leading space keeps the inserted token from visually
                    # (and, worse, textually, when the PDF is re-extracted
                    # for export/audit) gluing onto whatever original word
                    # sits immediately before the box: _BOX_PADDING_X shifts
                    # the box's own left edge left by enough to consume a
                    # single-space gap entirely (e.g. "DOB 05/21/1956" ->
                    # box starts right where "05" did, padding eats the
                    # space before it), so without this the replacement
                    # token would otherwise start flush against the
                    # preceding word.
                    draw_text = f" {replacement}" if index == 0 and replacement else None
                    box = _padded_box(box)
                    if rotated:
                        quad = _rotated_box_quad(box, angle)
                        page.add_redact_annot(
                            quad, fontname="helv", fontsize=8,
                            fill=fill, text_color=text_color, cross_out=False,
                        )
                        if draw_text:
                            origin = _rotated_text_origin(box, angle)
                            pending_text.append((page_number, origin, draw_text, angle))
                    else:
                        rect = pymupdf.Rect(box["x0"], box["top"], box["x1"], box["bottom"])
                        page.add_redact_annot(
                            rect,
                            text=draw_text,
                            fontname="helv",
                            fontsize=8,
                            fill=fill,
                            text_color=text_color,
                            cross_out=False,
                        )

        for page in pdf:
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)

        for page_number, origin, text, angle in pending_text:
            page = pdf[page_number - 1]
            # Only "mask"/"pseudo" tokens ever reach here (a "redact" entity
            # has no replacement text at all — see _replacement_text), and
            # those always render in black, matching add_redact_annot's own
            # text_color=(0, 0, 0) default used for them on an unrotated page.
            page.insert_text(
                origin, text, fontsize=8, fontname="helv",
                color=(0, 0, 0), morph=(origin, pymupdf.Matrix(angle)),
            )

        # A source PDF's metadata/XML metadata can itself carry PHI (author,
        # title, custom fields set by the EHR that exported it).
        pdf.set_metadata({})
        pdf.del_xml_metadata()

        buf = io.BytesIO()
        pdf.save(buf, garbage=4, deflate=True, clean=True)
        return buf.getvalue()
