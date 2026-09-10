"""
Turns an uploaded PDF into a flat list of text blocks (one paragraph-ish
chunk, or one table row, per block, tagged with a page number and a coarse
type), which is the unit both PHI detection and rendering operate on.

Real-world PDFs vary wildly in how paragraphs map to line breaks, so the
non-table path is a heuristic, not a layout parser: it groups wrapped lines
together and promotes short, early, unpunctuated lines to headings. Tables
are handled separately (see `_extract_tables`) because flattening a table
into the same paragraph text badly scrambles row/column adjacency (e.g. a
"Relation" cell and the "Name" cell in the same row end up far apart in
reading order) — PHI detection needs cells kept row-aligned to reason about
what a bare, unlabelled value in a "Name" or "MRN" column means.

Pages with no usable text layer (scanned/image-only PDFs) are rasterized and
run through Tesseract OCR as a fallback; see `_ocr_page`.
"""
import re
import shutil

import pdfplumber

_BLANK_RUN = re.compile(r"\n\s*\n+")
_HEADING_LIKE = re.compile(r"^[A-Z0-9][A-Za-z0-9 ,.'/#&:-]{0,70}$")

_MIN_NATIVE_WORDS = 3  # below this, treat the page as having no usable text layer

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None


class ExtractionError(Exception):
    pass


def _split_page_into_paragraphs(page_text):
    page_text = page_text.strip("\n")
    if not page_text:
        return []

    chunks = [c.strip() for c in _BLANK_RUN.split(page_text) if c.strip()]
    if len(chunks) > 1:
        return chunks

    # No blank-line separation available — fall back to grouping consecutive
    # "body" lines together and splitting a paragraph whenever we hit a
    # short, heading-shaped line.
    paragraphs = []
    buffer = []
    for raw_line in page_text.split("\n"):
        line = raw_line.strip()
        if not line:
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            continue
        is_heading_like = len(line) <= 70 and not line.endswith((".", ",", ";")) and _HEADING_LIKE.match(line)
        if is_heading_like:
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            paragraphs.append(line)
        else:
            buffer.append(line)
    if buffer:
        paragraphs.append(" ".join(buffer))
    return paragraphs


def _classify_block(text, index, page_number):
    is_short = len(text) <= 80
    is_shouty = text.isupper() or (text == text.title() and len(text.split()) <= 8)
    if index == 0 and page_number == 1 and is_short:
        return "title"
    if index == 1 and page_number == 1 and is_short:
        return "sub"
    if is_short and is_shouty and not text.endswith((".", ",")):
        return "h"
    return "p"


def _ocr_page(page):
    """Rasterize `page` and run Tesseract OCR over it. Returns extracted
    text, or "" if Tesseract isn't installed or OCR finds nothing."""
    if not _TESSERACT_AVAILABLE:
        return ""
    import pytesseract

    image = page.to_image(resolution=300).original
    return pytesseract.image_to_string(image) or ""


def _within_bbox(obj, bbox):
    x0, top, x1, bottom = bbox
    return obj["x0"] >= x0 - 1 and obj["x1"] <= x1 + 1 and obj["top"] >= top - 1 and obj["bottom"] <= bottom + 1


def _extract_tables(page):
    """Returns a list of tables, each a list of rows, each row a list of
    (cell_text, column_header) tuples, plus the list of table bounding boxes
    (so the caller can exclude that page area from paragraph extraction)."""
    tables_out = []
    bboxes = []
    try:
        found = page.find_tables()
    except Exception:  # pragma: no cover - pdfplumber internal failure
        found = []
    for table in found:
        try:
            rows = table.extract()
        except Exception:  # pragma: no cover
            continue
        if not rows or not any(any((cell or "").strip() for cell in row) for row in rows):
            continue
        bboxes.append(table.bbox)
        headers = [(cell or "").strip() for cell in rows[0]]
        table_rows = []
        for row in rows:
            table_rows.append([((cell or "").strip(), headers[i] if i < len(headers) else "")
                                for i, cell in enumerate(row)])
        tables_out.append(table_rows)
    return tables_out, bboxes


def _table_row_block(row_cells, index, page_number, is_header_row):
    """Builds a table_row block dict. `cells` metadata records where each
    cell's text lands in the joined `text` string plus its column header, so
    detection can be run per-cell with column context."""
    parts = []
    cells_meta = []
    cursor = 0
    for cell_text, header in row_cells:
        if cursor > 0:
            parts.append(" | ")
            cursor += 3
        start = cursor
        parts.append(cell_text)
        cursor += len(cell_text)
        cells_meta.append({
            "text": cell_text, "start": start, "end": cursor,
            "header": "" if is_header_row else header,
        })
    return {
        "index": index, "page": page_number, "type": "table_row",
        "text": "".join(parts), "source": "text", "cells": cells_meta,
    }


def extract_blocks(file_obj):
    """
    Returns (page_count, blocks) where blocks is a list of
    {index, page, type, text, source, cells?} dicts in document order.
    `source` is "text" or "ocr"; `cells` is present only on "table_row"
    blocks and carries per-cell offsets/headers for column-aware detection.

    Raises ExtractionError with a human-readable message if the PDF has no
    extractable text even after the OCR fallback (e.g. it's blank, corrupt,
    or encrypted).
    """
    blocks = []
    index = 0
    try:
        with pdfplumber.open(file_obj) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                raise ExtractionError("The PDF has no pages.")
            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    tables, table_bboxes = _extract_tables(page)
                    text_page = page.filter(lambda obj: not any(_within_bbox(obj, b) for b in table_bboxes)) \
                        if table_bboxes else page
                    page_text = text_page.extract_text() or ""
                except Exception as exc:  # pragma: no cover - pdfplumber internal failure
                    raise ExtractionError(f"Could not read page {page_number}: {exc}") from exc

                source = "text"
                if len(page_text.split()) < _MIN_NATIVE_WORDS and not tables:
                    ocr_text = _ocr_page(page)
                    if ocr_text.strip():
                        page_text = ocr_text
                        source = "ocr"

                for paragraph in _split_page_into_paragraphs(page_text):
                    blocks.append({
                        "index": index,
                        "page": page_number,
                        "type": _classify_block(paragraph, index, page_number),
                        "text": paragraph,
                        "source": source,
                    })
                    index += 1

                for table in tables:
                    for row_num, row_cells in enumerate(table):
                        blocks.append(_table_row_block(row_cells, index, page_number, is_header_row=row_num == 0))
                        index += 1
    except ExtractionError:
        raise
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        if "password" in message.lower() or "encrypt" in message.lower():
            raise ExtractionError("The PDF is password-protected. Upload an unlocked copy.") from exc
        raise ExtractionError(f"Could not parse this PDF: {message}") from exc

    if not blocks:
        hint = "" if _TESSERACT_AVAILABLE else " Tesseract OCR isn't installed on this server, so image-only pages couldn't be read either — install it and retry."
        raise ExtractionError(
            "No extractable text was found. The PDF may be a scanned image "
            f"with no text layer.{hint}"
        )
    return page_count, blocks
