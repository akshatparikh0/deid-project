"""
Turns an uploaded PDF into a flat list of text blocks (one paragraph-ish
chunk, or one table row, per block, tagged with a page number and a coarse
type) plus, for every block, enough position metadata to map a detected
entity's character offsets back to its exact bounding box(es) on the page —
that's what lets the Review screen draw redaction/highlight boxes on the
real rendered page image instead of reflowing text.

Real-world PDFs vary wildly in how paragraphs map to line breaks, so the
non-table path is a heuristic, not a layout parser: it clusters words into
lines by vertical position, then clusters lines into paragraphs the same
way the old text-only version did (a big vertical gap or a short heading-
shaped line starts a new paragraph). Tables are handled separately (see
`_extract_tables`) because flattening a table into the same paragraph text
badly scrambles row/column adjacency (e.g. a "Relation" cell and the "Name"
cell in the same row end up far apart in reading order) — PHI detection
needs cells kept row-aligned to reason about what a bare, unlabelled value
in a "Name" or "MRN" column means. A table cell's bounding box is just its
own cell rectangle, taken straight from pdfplumber's table-row geometry.

Every page is rasterized once (see `PAGE_IMAGE_RESOLUTION`) to back the
Review screen's page image and, when a page has little or no usable native
text, to run Tesseract OCR as a fallback; see `_ocr_words`. "Little" is
deliberately not "zero": a page can have a handful of genuine text runs (a
stray label, a border-line "table" pdfplumber mistook for real cells) while
the actual visible content is vector-drawn glyphs or a background scan with
no selectable characters at all — checking for a realistic word count
instead of just "any text at all" is what catches that case. OCR only
replaces the page's text if it finds *more* content than native extraction
did, so a genuinely short page never gets worse by attempting OCR.
"""
import io
import os
import re
import shutil

import pdfplumber

_HEADING_LIKE = re.compile(r"^[A-Z0-9][A-Za-z0-9 ,.'/#&:-]{0,70}$")

_MIN_NATIVE_WORDS = 25  # below this, also try OCR and keep whichever is more complete
_LINE_TOLERANCE = 2.0  # points; words within this vertical difference are on the same line
_PARAGRAPH_GAP_MULTIPLIER = 1.6  # a gap bigger than this multiple of the line height starts a new paragraph

PREVIEW_RESOLUTION = 150
TESSERACT_RESOLUTION = 300

MIN_TESSERACT_CONFIDENCE = 20.0

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None


class ExtractionError(Exception):
    pass


def _within_bbox(x0, top, x1, bottom, bbox):
    bx0, btop, bx1, bbottom = bbox
    return x0 >= bx0 - 1 and x1 <= bx1 + 1 and top >= btop - 1 and bottom <= bbottom + 1


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


def _group_words_into_lines(words):
    """Groups a reading-order word list into lines by vertical position.
    Each line is {"words": [...], "top", "bottom", "x0", "x1"}."""
    lines = []
    current = None
    for w in words:
        if current is not None and abs(w["top"] - current["top"]) <= _LINE_TOLERANCE:
            current["words"].append(w)
            current["top"] = min(current["top"], w["top"])
            current["bottom"] = max(current["bottom"], w["bottom"])
            current["x0"] = min(current["x0"], w["x0"])
            current["x1"] = max(current["x1"], w["x1"])
        else:
            current = {"words": [w], "top": w["top"], "bottom": w["bottom"], "x0": w["x0"], "x1": w["x1"]}
            lines.append(current)
    return lines


def _group_lines_into_blocks(lines, page_number, start_index, source):
    """Groups lines into paragraph-ish blocks, tracking per-word offsets so
    detected entity spans can be mapped back to page coordinates. Returns
    (blocks, next_index)."""
    if not lines:
        return [], start_index

    heights = sorted(l["bottom"] - l["top"] for l in lines)
    median_height = heights[len(heights) // 2] or 10.0

    blocks = []
    buffer_lines = []
    index = start_index

    def flush():
        nonlocal index
        if not buffer_lines:
            return
        parts = []
        words_meta = []
        cursor = 0
        for li, line in enumerate(buffer_lines):
            if li > 0:
                parts.append(" ")
                cursor += 1
            for wi, w in enumerate(line["words"]):
                if wi > 0:
                    parts.append(" ")
                    cursor += 1
                token = w["text"]
                parts.append(token)
                words_meta.append({
                    "start": cursor, "end": cursor + len(token),
                    "x0": w["x0"], "top": w["top"], "x1": w["x1"], "bottom": w["bottom"],
                })
                cursor += len(token)
        text = "".join(parts)
        blocks.append({
            "index": index, "page": page_number,
            "type": _classify_block(text, index, page_number),
            "text": text, "source": source, "words": words_meta,
        })
        index += 1
        buffer_lines.clear()

    prev_bottom = None
    for line in lines:
        line_text = " ".join(w["text"] for w in line["words"])
        is_heading_like = (
            len(line_text) <= 70 and not line_text.endswith((".", ",", ";")) and _HEADING_LIKE.match(line_text)
        )
        big_gap = prev_bottom is not None and (line["top"] - prev_bottom) > median_height * _PARAGRAPH_GAP_MULTIPLIER
        if is_heading_like or big_gap:
            flush()
        buffer_lines.append(line)
        if is_heading_like:
            flush()
        prev_bottom = line["bottom"]
    flush()
    return blocks, index


def _extract_tables(page, table_bboxes_only=False):
    """Returns a list of tables, each a list of rows, each row a list of
    (cell_text, column_header, bbox) tuples, plus the table bounding boxes
    (so the caller can exclude that page area from word/paragraph extraction).
    `bbox` is the cell's own (x0, top, x1, bottom) — a table cell's box is
    just its own cell rectangle."""
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
        if table_bboxes_only:
            continue
        headers = [(cell or "").strip() for cell in rows[0]]
        table_rows = []
        for row, plumber_row in zip(rows, table.rows):
            cells = []
            for i, cell in enumerate(row):
                bbox = plumber_row.cells[i] if i < len(plumber_row.cells) and plumber_row.cells[i] else table.bbox
                cells.append(((cell or "").strip(), headers[i] if i < len(headers) else "", bbox))
            table_rows.append(cells)
        tables_out.append(table_rows)
    return tables_out, bboxes


def _table_row_block(row_cells, index, page_number, is_header_row, source):
    parts = []
    cells_meta = []
    cursor = 0
    for cell_text, header, bbox in row_cells:
        if cursor > 0:
            parts.append(" | ")
            cursor += 3
        start = cursor
        parts.append(cell_text)
        cursor += len(cell_text)
        cells_meta.append({
            "text": cell_text, "start": start, "end": cursor,
            "header": "" if is_header_row else header,
            "x0": bbox[0], "top": bbox[1], "x1": bbox[2], "bottom": bbox[3],
        })
    return {
        "index": index, "page": page_number, "type": "table_row",
        "text": "".join(parts), "source": source, "cells": cells_meta,
    }


def _ocr_words(image, resolution):
    """Runs Tesseract on `image` and returns a word list shaped like
    pdfplumber's extract_words() (text/x0/top/x1/bottom), scaled from pixel
    coordinates back to PDF points so it can share the line/paragraph
    grouping logic used for native text."""
    if not _TESSERACT_AVAILABLE:
        return []
    import pytesseract
    from pytesseract import Output

    scale = 72.0 / resolution

    data = pytesseract.image_to_data(image, output_type=Output.DICT, config="--oem 3 --psm 6")
    words = []
    for index, raw_text in enumerate(data["text"]):
        text = (raw_text or "").strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1.0

        if confidence < MIN_TESSERACT_CONFIDENCE:
            continue

        left = int(data["left"][index])
        top = int(data["top"][index])
        width = int(data["width"][index])
        height = int(data["height"][index])

        words.append(
            {
                "text": text,
                "x0": left * scale,
                "top": top * scale,
                "x1": (left + width) * scale,
                "bottom": (top + height) * scale,
                "confidence": confidence / 100.0,
            }
        )
    return words


def _azure_ocr_words(image, page_width, page_height):
    """Runs Azure AI Document Intelligence (FR-60) on `image` and returns a
    word list shaped like pdfplumber's extract_words(), scaled from the
    service's own page dimensions into this page's PDF points. Third- and
    last-resort OCR tier, tried only when both the native text layer and
    Tesseract come up short (e.g. a low-quality fax scan) and
    REDACTION_ENABLE_AZURE_OCR is set. Requires
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT; falls back to a managed identity
    (FR-62) when no static key is configured."""
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    if not endpoint:
        raise ExtractionError("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT is required when REDACTION_ENABLE_AZURE_OCR=True")
    if key:
        credential = AzureKeyCredential(key)
    else:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
    client = DocumentIntelligenceClient(endpoint=endpoint, credential=credential)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    result = client.begin_analyze_document("prebuilt-read", body=buf.getvalue()).result()
    if not result.pages:
        return []

    analyzed = result.pages[0]
    x_scale = page_width / (analyzed.width or page_width)
    y_scale = page_height / (analyzed.height or page_height)

    words = []
    for word in analyzed.words or []:
        # polygon is a flat [x1, y1, x2, y2, ...] float list (clockwise
        # vertices), not a list of Point objects.
        polygon = word.polygon or []
        xs = [x * x_scale for x in polygon[0::2]]
        ys = [y * y_scale for y in polygon[1::2]]
        if not xs or not ys:
            continue
        words.append({
            "text": word.content,
            "x0": min(xs), "top": min(ys), "x1": max(xs), "bottom": max(ys),
            "confidence": float(word.confidence or 0.0),
        })
    return words


def extract_blocks(file_obj, *, force_ocr=False, azure_ocr_enabled=False):
    """
    Returns (page_count, blocks, pages) where:
    - blocks is a list of {index, page, type, text, source, words?, cells?}
      dicts in document order. `words` (non-table blocks) or `cells` (table
      rows) carry per-token offsets and page-coordinate bounding boxes so
      detected entity spans can be mapped back to exact page positions.
    - pages is a list of {number, width, height, png} — one rasterized
      preview image per page, in the same coordinate space as the boxes
      above (width/height in PDF points; png is PNG bytes at
      PAGE_IMAGE_RESOLUTION dpi).

    Raises ExtractionError with a human-readable message if the PDF has no
    extractable text even after the OCR fallback (e.g. it's blank, corrupt,
    or encrypted).
    """
    blocks = []
    pages = []
    index = 0
    try:
        with pdfplumber.open(file_obj) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                raise ExtractionError("The PDF has no pages.")
            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    tables, table_bboxes = _extract_tables(page)
                    words = [
                        w for w in page.extract_words()
                        if not any(_within_bbox(w["x0"], w["top"], w["x1"], w["bottom"], b) for b in table_bboxes)
                    ]
                    preview_image = page.to_image(resolution=PREVIEW_RESOLUTION).original
                except Exception as exc:  # pragma: no cover - pdfplumber internal failure
                    raise ExtractionError(f"Could not read page {page_number}: {exc}") from exc

                native_words = len(words) + sum(len(cell_text.split()) for table in tables for row in table for cell_text, _, _ in row)
                source = "text"
                should_try_tesseract = force_ocr or native_words < _MIN_NATIVE_WORDS

                if should_try_tesseract:
                    ocr_image = page.to_image(
                        resolution=TESSERACT_RESOLUTION
                    ).original
                    ocr_words = _ocr_words(
                        ocr_image,
                        TESSERACT_RESOLUTION,
                    )
                    if force_ocr or len(ocr_words) > native_words:
                        words = ocr_words
                        tables = []
                        source = "tesseract"

                    # Tesseract still came up short (or isn't installed) —
                    # try Azure Document Intelligence as a last resort
                    # before accepting a possibly-blank page.
                    if azure_ocr_enabled and len(words) < _MIN_NATIVE_WORDS:
                        azure_words = _azure_ocr_words(ocr_image, page.width, page.height)
                        if len(azure_words) > len(words):
                            words = azure_words
                            tables = []
                            source = "azure_ocr"

                lines = _group_words_into_lines(sorted(words, key=lambda w: (round(w["top"]), w["x0"])))
                page_blocks, index = _group_lines_into_blocks(lines, page_number, index, source)
                blocks.extend(page_blocks)

                for table in tables:
                    for row_num, row_cells in enumerate(table):
                        blocks.append(_table_row_block(row_cells, index, page_number, row_num == 0, source))
                        index += 1

                png_buf = io.BytesIO()
                preview_image.save(png_buf, format="PNG")
                pages.append({
                    "number": page_number, "width": page.width, "height": page.height,
                    "png": png_buf.getvalue(),
                })
    except ExtractionError:
        raise
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        if "password" in message.lower() or "encrypt" in message.lower():
            raise ExtractionError("The PDF is password-protected. Upload an unlocked copy.") from exc
        raise ExtractionError(f"Could not parse this PDF: {message}") from exc

    if not blocks:
        if not blocks:
            if not _TESSERACT_AVAILABLE:
                hint = (
                    " Tesseract OCR is not installed, so image-only pages "
                    "could not be processed."
                )
            else:
                hint = (
                    " Tesseract was available, but it did not find usable text."
                )

            raise ExtractionError(
                "No extractable text was found. The PDF may be blank or "
                f"contain an unreadable scanned image.{hint}"
            )
    return page_count, blocks, pages
