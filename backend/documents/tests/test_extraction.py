import os
import shutil
import unittest
from unittest.mock import patch

from django.test import SimpleTestCase

from documents.extraction import ExtractionError, extract_blocks

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    return open(os.path.join(FIXTURES, name), "rb")


class DlpTableExtractionTests(SimpleTestCase):
    def test_all_rows_extracted_as_single_line_blocks(self):
        pages, blocks = extract_blocks(_fixture("dlptest_name_ssn_ccn.pdf"))
        self.assertEqual(pages, 1)
        row_texts = [b["text"] for b in blocks if "489-36-8350" in b["text"]]
        self.assertEqual(len(row_texts), 1)
        self.assertIn("Robert Aragon", row_texts[0])
        self.assertIn("4929-3813-3266-4295", row_texts[0])

    def test_all_blocks_marked_as_text_source(self):
        _, blocks = extract_blocks(_fixture("dlptest_name_ssn_ccn.pdf"))
        self.assertTrue(all(b["source"] == "text" for b in blocks))


class TableAwareExtractionTests(SimpleTestCase):
    def test_family_history_rows_kept_row_aligned(self):
        _, blocks = extract_blocks(_fixture("consult_note.pdf"))
        table_rows = [b for b in blocks if b["type"] == "table_row"]
        self.assertTrue(table_rows, "expected at least one table_row block")

        row = next(b for b in table_rows if "Dorothy Whitcombe" in b["text"])
        cell_by_header = {c["header"]: c["text"] for c in row["cells"]}
        self.assertEqual(cell_by_header["Relation"], "Mother")
        self.assertEqual(cell_by_header["Name"], "Dorothy Whitcombe")

    def test_cell_offsets_match_row_text(self):
        _, blocks = extract_blocks(_fixture("consult_note.pdf"))
        row = next(b for b in blocks if b["type"] == "table_row" and "Dorothy Whitcombe" in b["text"])
        for cell in row["cells"]:
            self.assertEqual(row["text"][cell["start"]:cell["end"]], cell["text"])

    def test_table_content_not_duplicated_in_paragraph_blocks(self):
        _, blocks = extract_blocks(_fixture("consult_note.pdf"))
        paragraph_text = " ".join(b["text"] for b in blocks if b["type"] != "table_row")
        self.assertNotIn("Dorothy Whitcombe", paragraph_text)


class NoTextLayerTests(SimpleTestCase):
    def test_blank_pdf_raises_extraction_error(self):
        # A single-page PDF with no content stream text at all and no tables.
        import io

        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.showPage()
        c.save()
        buf.seek(0)
        with self.assertRaises(ExtractionError):
            extract_blocks(buf)


@unittest.skipUnless(shutil.which("tesseract"), "tesseract binary not installed")
class OcrFallbackTests(SimpleTestCase):
    def test_scanned_page_is_ocrd(self):
        _, blocks = extract_blocks(_fixture("consult_note_scanned.pdf"))
        self.assertTrue(any(b["source"] == "ocr" for b in blocks))
        full_text = " ".join(b["text"] for b in blocks)
        self.assertIn("Whitcombe", full_text)
        self.assertIn("4471002", full_text)


class SparseNativeTextTriggersOcrTests(SimpleTestCase):
    """redacted_consult_note.pdf has, on several pages, only a handful of
    genuine text runs (a few label tokens) plus a spurious near-full-page
    "table" pdfplumber detects from border lines — while the actual visible
    page content has no selectable characters at all. A naive "is there any
    text / any table" check would wrongly treat these pages as already
    handled and never attempt OCR. Stubs `_ocr_page` so this is testable
    without the tesseract binary."""

    def test_sparse_pages_fall_back_to_ocr_when_it_finds_more(self):
        fake_text = " ".join(["word"] * 200)
        with patch("documents.extraction._ocr_page", return_value=fake_text):
            _, blocks = extract_blocks(_fixture("redacted_consult_note.pdf"))
        sources_by_page = {}
        for b in blocks:
            sources_by_page.setdefault(b["page"], set()).add(b["source"])
        for page, sources in sources_by_page.items():
            self.assertEqual(sources, {"ocr"}, f"page {page} did not fall back to OCR")
        # The spurious near-full-page tables on pages 2-4 must not survive
        # once OCR supersedes that page's native extraction.
        self.assertFalse(any(b["type"] == "table_row" for b in blocks))

    def test_sparse_native_text_kept_when_ocr_unavailable(self):
        with patch("documents.extraction._ocr_page", return_value=""):
            _, blocks = extract_blocks(_fixture("redacted_consult_note.pdf"))
        self.assertTrue(all(b["source"] == "text" for b in blocks))
