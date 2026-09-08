"""
Turns an uploaded PDF into a flat list of text blocks (one paragraph-ish
chunk per block, tagged with a page number and a coarse type), which is the
unit both PHI detection and rendering operate on.

Real-world PDFs vary wildly in how paragraphs map to line breaks, so this is
a heuristic, not a layout parser: it groups wrapped lines together and
promotes short, early, unpunctuated lines to headings. It is deliberately
simple and legible rather than exhaustive — a production system would use
the PDF's actual layout/font metadata (also available via pdfplumber) to do
this more precisely.
"""
import re

import pdfplumber

_BLANK_RUN = re.compile(r"\n\s*\n+")
_HEADING_LIKE = re.compile(r"^[A-Z0-9][A-Za-z0-9 ,.'/#&:-]{0,70}$")


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


def extract_blocks(file_obj):
    """
    Returns (page_count, blocks) where blocks is a list of
    {index, page, type, text} dicts in document order.

    Raises ExtractionError with a human-readable message if the PDF has no
    extractable text (e.g. it's a scanned image with no OCR layer, or it's
    encrypted).
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
                    page_text = page.extract_text() or ""
                except Exception as exc:  # pragma: no cover - pdfplumber internal failure
                    raise ExtractionError(f"Could not read page {page_number}: {exc}") from exc
                for paragraph in _split_page_into_paragraphs(page_text):
                    blocks.append({
                        "index": index,
                        "page": page_number,
                        "type": _classify_block(paragraph, index, page_number),
                        "text": paragraph,
                    })
                    index += 1
    except ExtractionError:
        raise
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        if "password" in message.lower() or "encrypt" in message.lower():
            raise ExtractionError("The PDF is password-protected. Upload an unlocked copy.") from exc
        raise ExtractionError(f"Could not parse this PDF: {message}") from exc

    if not blocks:
        raise ExtractionError(
            "No extractable text was found. The PDF may be a scanned image "
            "with no text layer — OCR it first, then re-upload."
        )
    return page_count, blocks
