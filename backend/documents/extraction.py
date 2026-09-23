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

Every page is rasterized once (see `PREVIEW_RESOLUTION`) to back the
Review screen's page image and, when a page has little or no usable native
text, to run Tesseract (and, if enabled, Azure Document Intelligence) OCR
as a fallback; see `_ocr_words`/`_azure_ocr_words`. "Little" is
deliberately not "zero": a page can have a handful of genuine text runs (a
stray label, a border-line "table" pdfplumber mistook for real cells) while
the actual visible content is vector-drawn glyphs or a background scan with
no selectable characters at all — checking for a realistic word count
instead of just "any text at all" is what catches that case. OCR only
replaces the page's text if it finds *more* content than native extraction
did, so a genuinely short page never gets worse by attempting OCR.
"""
import io
<<<<<<< HEAD
=======
import math
>>>>>>> feature/screen-map
import os
import re
import shutil
import threading

import pdfplumber

_HEADING_LIKE = re.compile(r"^[A-Z0-9][A-Za-z0-9 ,.'/#&:-]{0,70}$")

_MIN_NATIVE_WORDS = 25  # below this, also try OCR and keep whichever is more complete
_LINE_TOLERANCE = 2.0  # points; words within this vertical difference are on the same line
_PARAGRAPH_GAP_MULTIPLIER = 1.6  # a gap bigger than this multiple of the line height starts a new paragraph

PREVIEW_RESOLUTION = 150
TESSERACT_RESOLUTION = 300

MIN_TESSERACT_CONFIDENCE = 20.0

# pdfplumber's page.to_image() rasterizes via pdfium (libpdfium), which is
# not safe to call from multiple threads of the same process at once — it
# reliably segfaults the whole interpreter under concurrent use, which is
# exactly what a Celery worker with more than one process/thread does
# (several jobs' 'parse' stage running at the same time). Serializing the
# whole extract_blocks() call below closes that hole; detection/transform/
# finalize for other jobs still run concurrently, only PDF parsing itself
# queues up.
_PDFIUM_LOCK = threading.Lock()

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


_COLUMN_GAP_THRESHOLD = 30.0  # points; a horizontal gap this large between
# two consecutive words otherwise on the same line means they actually sit
# in different columns of a form/label:value grid (e.g. a label ending and
# an unrelated field's value starting several inches later on the same
# printed row) — not just generously spaced prose. Ordinary word-to-word
# gaps within a sentence, even fully-justified, run a few points at most.


def _cluster_line(words):
    return {
        "words": words,
        "top": min(w["top"] for w in words),
        "bottom": max(w["bottom"] for w in words),
        "x0": min(w["x0"] for w in words),
        "x1": max(w["x1"] for w in words),
    }


def _split_line_columns(lines):
    """Splits any line whose words jump by more than _COLUMN_GAP_THRESHOLD
    into separate clusters, one per horizontal cluster — otherwise two
    unrelated fields sitting at the same row height (common in a two-column
    demographics grid with no detectable table structure, e.g. an OCR'd
    scan) get concatenated into one nonsense block.

    Returns (lines, form_runs): `lines` are single-cluster lines, unchanged,
    fed to the normal paragraph grouping below. `form_runs` are maximal
    consecutive runs of multi-cluster lines (a demographics grid's worth of
    rows, say), each a list of rows, each row a list of clusters (word
    lists) — routed to _emit_form_row_blocks instead, which treats them
    exactly like a real vector-detected table's rows (one cell of text per
    cluster, not one flattened string), because joining a row's clusters
    into a single string is itself ambiguous: e.g. "Kwame Whitfield Granite
    Peak Memorial Hospital" (a patient name cluster directly beside a
    facility name cluster, no punctuation between them) reads exactly like
    one long facility name, and there is no text-shape rule that can always
    tell the two readings apart after the fact — keeping the clusters as
    separate cells sidesteps the ambiguity instead of trying to resolve it."""
    single_lines = []
    form_runs = []
    current_run = []

    def end_run():
        if current_run:
            form_runs.append(current_run.copy())
            current_run.clear()

    for line in lines:
        words = sorted(line["words"], key=lambda w: w["x0"])
        clusters = [[words[0]]]
        for prev, w in zip(words, words[1:]):
            if w["x0"] - prev["x1"] > _COLUMN_GAP_THRESHOLD:
                clusters.append([])
            clusters[-1].append(w)
        if len(clusters) == 1:
            end_run()
            single_lines.append({**line, "words": words})
            continue
        current_run.append(clusters)
    end_run()
    return single_lines, form_runs


_MIN_SKEW_SAMPLES = 5  # below this, there isn't enough evidence to call a page "rotated"


def _estimate_skew_angle(lines):
    """Estimates a scanned page's rotation angle in degrees (the same sign
    convention as pymupdf.Matrix(angle) and the quad rotation in
    finalize.py — positive turns text clockwise in top-down page
    coordinates) from OCR line geometry: for each detected line with at
    least two words, the angle from its first word's vertical center to its
    last gives one sample of the page's tilt; the median across all lines
    is robust to a handful of noisy short lines. Returns 0.0 if there isn't
    enough data to tell (e.g. too few multi-word lines — including on a
    native-text page, which was never skewed in the first place and never
    reaches this function)."""
    samples = []
    for line in lines:
        words = sorted(line["words"], key=lambda w: w["x0"])
        first, last = words[0], words[-1]
        dx = last["x0"] - first["x0"]
        if dx <= 0:
            continue
        dy = ((last["top"] + last["bottom"]) / 2) - ((first["top"] + first["bottom"]) / 2)
        samples.append(math.degrees(math.atan2(dy, dx)))
    if len(samples) < _MIN_SKEW_SAMPLES:
        return 0.0
    samples.sort()
    return samples[len(samples) // 2]


def _group_words_into_lines(words):
    """Groups a reading-order word list into lines, then splits out any
    line that actually spans multiple form columns (see
    _split_line_columns). Returns (lines, form_runs, skew_angle) — see
    _split_line_columns for what the first two hold, and
    _estimate_skew_angle for the third.

    OCR'd words (see _ocr_words) carry Tesseract's own (block, paragraph,
    line) grouping from its internal layout analysis, which is skew-
    tolerant — grouping instead by a simple vertical-position tolerance, as
    the native-text path below does, breaks down on a rotated/skewed scan:
    words on the same printed row can land tens of points apart vertically
    (comparable to or bigger than the gap between two different rows),
    scrambling adjacent rows together. Native-text words have no such
    Tesseract grouping and don't need it — a PDF's own text layer reports
    exact, reliable coordinates.

    Each line (before column-splitting) is {"words": [...], "top",
    "bottom", "x0", "x1"}."""
    if words and "line_key" in words[0]:
        grouped = {}
        order = []
        for w in words:
            key = w["line_key"]
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(w)
        lines = [_cluster_line(grouped[key]) for key in order]
        lines.sort(key=lambda l: l["top"])
        skew_angle = _estimate_skew_angle(lines)
        single_lines, form_runs = _split_line_columns(lines)
        return single_lines, form_runs, skew_angle

    lines = []
    current = None
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if current is not None and abs(w["top"] - current["top"]) <= _LINE_TOLERANCE:
            current["words"].append(w)
            current["top"] = min(current["top"], w["top"])
            current["bottom"] = max(current["bottom"], w["bottom"])
            current["x0"] = min(current["x0"], w["x0"])
            current["x1"] = max(current["x1"], w["x1"])
        else:
            current = {"words": [w], "top": w["top"], "bottom": w["bottom"], "x0": w["x0"], "x1": w["x1"]}
            lines.append(current)
    single_lines, form_runs = _split_line_columns(lines)
    return single_lines, form_runs, 0.0


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
                    # Which of this block's own already-correctly-clustered
                    # physical lines (see _group_words_into_lines) this word
                    # came from — _line_group_boxes (ingest.py) groups a
                    # span's words back into per-line boxes using this,
                    # instead of re-deriving line boundaries from raw
                    # top-coordinates a second time (which breaks the same
                    # way on a skewed scan as it did before that fix).
                    "line_key": li,
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


def _looks_like_label(text):
    """A short, digit-free phrase — the shape of a form field's own label
    ("Legal name", "Date of birth", "City / State / ZIP"), as opposed to a
    data value. Used to recognize a repeating label:value form (see
    `_label_columns`), not to classify PHI itself. Bare punctuation tokens
    ("/" in a label like "City / State / ZIP") don't count as words."""
    text = (text or "").strip()
    if not text or any(ch.isdigit() for ch in text):
        return False
    words = [w for w in text.split() if any(ch.isalpha() for ch in w)]
    return 1 <= len(words) <= 4


def _value_shape(text):
    """A coarse bucket for a cell's value, used only to tell a heterogeneous
    column (many different kinds of value — the signature of a form's
    value column, one different field type per row) apart from a
    homogeneous one (a real data column, e.g. every row the same kind of
    thing: a name, a relation word, a drug name)."""
    text = (text or "").strip()
    if not text:
        return "empty"
    if "@" in text:
        return "email"
    if re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b", text):
        return "date"
    if re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", text):
        return "phone"
    digit_count = sum(ch.isdigit() for ch in text)
    if digit_count and digit_count >= max(2, len(text) // 3):
        return "numeric"
    words = text.split()
    alpha_words = [w for w in words if w[:1].isalpha()]
    if len(words) >= 2 and alpha_words and all(w[:1].isupper() for w in alpha_words):
        return "name-like"
    return "word"


def _label_columns(rows):
    """Column indices whose cells, across every data row (not just row 0),
    are themselves short field-name-shaped phrases — the signature of a
    repeating label:value form (a demographics grid with "Legal name" /
    "Date of birth" / "Age" / ... running down one column, each row a
    completely different field) rather than a genuine header naming a
    column of homogeneous data below it (e.g. "MEDICATION" over a column of
    actual drug names, or "Relation" over a column of relation words).
    Confirmed by checking the *paired* column immediately to the right: a
    real label column's values are a different kind of thing on every row
    (a date, then a phone number, then an email, ...); a homogeneous data
    column's values are all the same kind of thing."""
    data_rows = rows[1:]
    if not data_rows:
        return set()
    ncols = max(len(row) for row in rows)
    label_cols = set()
    for col in range(ncols - 1):
        values = [(row[col] or "").strip() for row in data_rows if col < len(row)]
        if not values:
            continue
        # A strict "every row" requirement means one OCR-garbled cell (e.g.
        # "Account no." misread as ".") disqualifies an otherwise-obvious
        # label column entirely — a strong majority is enough to trust the
        # column's shape without being derailed by isolated OCR noise.
        label_like = sum(1 for v in values if _looks_like_label(v))
        if label_like < max(1, round(len(values) * 0.7)):
            continue
        paired_values = [(row[col + 1] or "").strip() for row in data_rows if col + 1 < len(row)]
        shapes = {_value_shape(v) for v in paired_values if v}
        if len(shapes) >= 3:
            label_cols.add(col)
    return label_cols


def _cluster_cell(cluster):
    text = " ".join(w["text"] for w in cluster)
    bbox = (
        min(w["x0"] for w in cluster), min(w["top"] for w in cluster),
        max(w["x1"] for w in cluster), max(w["bottom"] for w in cluster),
    )
    return text, bbox


def _row_looks_like_header(text_row):
    """True if most of this row's non-empty cells look like field labels —
    the signature of a genuine one-row header immediately followed by one
    matching data row (e.g. "PATIENT NAME | DATE OF BIRTH | AGE | SEX" over
    "Beatriz Kowalczyk | 07/24/1997 | 28 | Female"), a transposed-
    spreadsheet section common in intake forms. This is a row-wise check,
    a companion to _label_columns' column-wise one: _label_columns decides
    whether a *column* is a repeating label across many data rows, which
    can't tell a genuine header apart from a value that's merely short and
    label-shaped too when there's only one data row underneath it to
    compare against — this catches that case directly instead.

    A repeating label:value grid row (e.g. "Legal name | Kwame Whitfield |
    Medical record no. | 75405792", a demographics grid handled by
    _label_columns instead) can cross the same overall threshold by
    coincidence — a short, digit-free *value* like a name looks exactly
    like a label by shape alone. What tells the two apart is alternation:
    a real header has every cell label-shaped; a label:value row only has
    every *other* cell label-shaped. Rejecting a row where even-position
    cells are much more label-like than odd-position ones (or vice versa)
    catches that even when the overall fraction alone would not."""
    cells = [c for c in text_row if c.strip()]
    if len(cells) < 2:
        return False
    label_like = sum(1 for c in cells if _looks_like_label(c))
    if label_like < max(1, round(len(cells) * 0.6)):
        return False
    if len(text_row) >= 4:
        evens = [c for i, c in enumerate(text_row) if i % 2 == 0 and c.strip()]
        odds = [c for i, c in enumerate(text_row) if i % 2 == 1 and c.strip()]
        if evens and odds:
            even_frac = sum(1 for c in evens if _looks_like_label(c)) / len(evens)
            odd_frac = sum(1 for c in odds if _looks_like_label(c)) / len(odds)
            if abs(even_frac - odd_frac) >= 0.5:
                return False
    return True


def _pair_header_rows(text_rows):
    """Finds (header_row_index -> data_row_index) pairs: a row that looks
    like a header (see _row_looks_like_header) immediately followed by a
    row that doesn't. Returns a dict mapping the data row's index to the
    header row's own cell texts, position-aligned by column."""
    pairs = {}
    i = 0
    n = len(text_rows)
    while i + 1 < n:
        if _row_looks_like_header(text_rows[i]) and not _row_looks_like_header(text_rows[i + 1]):
            pairs[i + 1] = text_rows[i]
            i += 2
        else:
            i += 1
    return pairs


def _emit_form_row_blocks(form_runs, page_number, start_index, source):
    """Turns the form_runs from _split_line_columns (maximal consecutive
    runs of multi-cluster OCR lines) into table_row blocks exactly like a
    real vector-detected table's rows (_table_row_block).

    Two different header shapes get reconciled here: a repeating label:
    value grid, where every row is its own different field with no genuine
    header row at all (a demographics grid — handled by _label_columns,
    the same fix already applied to real vector-detected tables in
    _extract_tables), and a one-row header directly over one matching data
    row (handled by _pair_header_rows). Rows already explained by a header
    pairing are excluded from the _label_columns pass so a real header row
    and its data row don't get miscounted as more samples of a repeating
    grid.

    Returns (blocks, next_index)."""
    blocks = []
    index = start_index
    for run in form_runs:
        text_rows = [[_cluster_cell(cluster)[0] for cluster in row] for row in run]
        header_pairs = _pair_header_rows(text_rows)
        paired_indices = set(header_pairs) | {h - 1 for h in header_pairs}
        remaining_rows = [r for i, r in enumerate(text_rows) if i not in paired_indices]
        label_cols = _label_columns(remaining_rows) if remaining_rows else set()
        for row_index, (row, text_row) in enumerate(zip(run, text_rows)):
            if row_index in header_pairs:
                row_headers = header_pairs[row_index]
            elif row_index in paired_indices:
                row_headers = [""] * len(row)
            else:
                row_headers = [""] * len(row)
                for col in label_cols:
                    if col + 1 < len(row_headers):
                        row_headers[col + 1] = text_row[col]
            cells_meta = []
            parts = []
            cursor = 0
            for i, cluster in enumerate(row):
                if cursor > 0:
                    parts.append(" | ")
                    cursor += 3
                text, bbox = _cluster_cell(cluster)
                start = cursor
                parts.append(text)
                cursor += len(text)
                cells_meta.append({
                    "text": text, "start": start, "end": cursor,
                    "header": row_headers[i] if i < len(row_headers) else "",
                    "x0": bbox[0], "top": bbox[1], "x1": bbox[2], "bottom": bbox[3],
                })
            blocks.append({
                "index": index, "page": page_number, "type": "table_row",
                "text": "".join(parts), "source": source, "cells": cells_meta,
            })
            index += 1
    return blocks, index


def _extract_tables(page, table_bboxes_only=False):
    """Returns a list of tables, each a list of rows, each row a list of
    (cell_text, column_header, bbox) tuples, plus the table bounding boxes
    (so the caller can exclude that page area from word/paragraph extraction).
    `bbox` is the cell's own (x0, top, x1, bottom) — a table cell's box is
    just its own cell rectangle.

    Most tables here have a real header row naming homogeneous data columns
    below it (e.g. a medication table: MEDICATION | DIRECTIONS | QUANTITY).
    Some are a repeating label:value form instead — a demographics grid
    where every row pairs a short field-name cell ("Legal name", "Date of
    birth", "Attending") with its own value, and there's no row that's
    actually different from the rest. Treating row 0 as a header for a form
    like that would apply one row's field name to every other row's
    completely different field (turning "Date of birth", "Payer",
    "Attending" themselves into false PHI matches, while the real value
    next to them — an account number, a payer name — goes unclassified) —
    `_label_columns` detects that shape, and each value cell there gets its
    own row's label as its column_header instead of row 0's."""
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
        label_cols = _label_columns(rows)
        headers = [(cell or "").strip() for cell in rows[0]]
        table_rows = []
        for row_num, (row, plumber_row) in enumerate(zip(rows, table.rows)):
            if label_cols:
                row_headers = [""] * len(row)
                for col in label_cols:
                    if col + 1 < len(row_headers):
                        row_headers[col + 1] = (row[col] or "").strip()
            else:
                row_headers = ["" if row_num == 0 else h for h in headers]
            cells = []
            for i, cell in enumerate(row):
                bbox = plumber_row.cells[i] if i < len(plumber_row.cells) and plumber_row.cells[i] else table.bbox
                header = row_headers[i] if i < len(row_headers) else ""
                cells.append(((cell or "").strip(), header, bbox))
            table_rows.append(cells)
        tables_out.append(table_rows)
    return tables_out, bboxes


def _table_row_block(row_cells, index, page_number, source):
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
            "header": header,
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
<<<<<<< HEAD
=======
                # Tesseract's own line grouping, from its internal layout
                # analysis — see _group_words_into_lines for why this is
                # used instead of re-deriving lines from raw coordinates.
                "line_key": (data["block_num"][index], data["par_num"][index], data["line_num"][index]),
>>>>>>> feature/screen-map
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
      PREVIEW_RESOLUTION dpi).

    Raises ExtractionError with a human-readable message if the PDF has no
    extractable text even after the OCR fallback (e.g. it's blank, corrupt,
    or encrypted).
    """
    blocks = []
    pages = []
    index = 0
    try:
        with _PDFIUM_LOCK, pdfplumber.open(file_obj) as pdf:
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
<<<<<<< HEAD

                    # Tesseract still came up short (or isn't installed) —
                    # try Azure Document Intelligence as a last resort
                    # before accepting a possibly-blank page.
                    if azure_ocr_enabled and len(words) < _MIN_NATIVE_WORDS:
                        azure_words = _azure_ocr_words(ocr_image, page.width, page.height)
                        if len(azure_words) > len(words):
                            words = azure_words
                            tables = []
                            source = "azure_ocr"
=======
>>>>>>> feature/screen-map

                    # Tesseract still came up short (or isn't installed) —
                    # try Azure Document Intelligence as a last resort
                    # before accepting a possibly-blank page.
                    if azure_ocr_enabled and len(words) < _MIN_NATIVE_WORDS:
                        azure_words = _azure_ocr_words(ocr_image, page.width, page.height)
                        if len(azure_words) > len(words):
                            words = azure_words
                            tables = []
                            source = "azure_ocr"

                lines, form_runs, skew_angle = _group_words_into_lines(words)
                page_blocks, index = _group_lines_into_blocks(lines, page_number, index, source)
                blocks.extend(page_blocks)

                form_blocks, index = _emit_form_row_blocks(form_runs, page_number, index, source)
                blocks.extend(form_blocks)

                for table in tables:
                    for row_cells in table:
                        blocks.append(_table_row_block(row_cells, index, page_number, source))
                        index += 1

                png_buf = io.BytesIO()
                preview_image.save(png_buf, format="PNG")
                pages.append({
                    "number": page_number, "width": page.width, "height": page.height,
                    "png": png_buf.getvalue(), "rotation": skew_angle,
                })
    except ExtractionError:
        raise
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        if "password" in message.lower() or "encrypt" in message.lower():
            raise ExtractionError("The PDF is password-protected. Upload an unlocked copy.") from exc
        raise ExtractionError(f"Could not parse this PDF: {message}") from exc

    if not blocks:
<<<<<<< HEAD
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
=======
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
>>>>>>> feature/screen-map
    return page_count, blocks, pages
