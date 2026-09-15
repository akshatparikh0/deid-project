import os
import shutil
import unittest
from unittest.mock import patch

from django.test import SimpleTestCase

from documents.extraction import ExtractionError, extract_blocks

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    return open(os.path.join(FIXTURES, name), "rb")


def _fake_words(n, top=100.0):
    return [{"text": "word", "x0": 10.0 * i, "top": top, "x1": 10.0 * i + 8, "bottom": top + 10} for i in range(n)]


class DlpTableExtractionTests(SimpleTestCase):
    def test_all_rows_extracted_as_single_line_blocks(self):
        page_count, blocks, pages = extract_blocks(_fixture("dlptest_name_ssn_ccn.pdf"))
        self.assertEqual(page_count, 1)
        self.assertEqual(len(pages), 1)
        row_texts = [b["text"] for b in blocks if "489-36-8350" in b["text"]]
        self.assertEqual(len(row_texts), 1)
        self.assertIn("Robert Aragon", row_texts[0])
        self.assertIn("4929-3813-3266-4295", row_texts[0])

    def test_all_blocks_marked_as_text_source(self):
        _, blocks, _ = extract_blocks(_fixture("dlptest_name_ssn_ccn.pdf"))
        self.assertTrue(all(b["source"] == "text" for b in blocks))

    def test_page_image_dimensions_match_page_size(self):
        _, _, pages = extract_blocks(_fixture("dlptest_name_ssn_ccn.pdf"))
        self.assertEqual(pages[0]["number"], 1)
        self.assertGreater(pages[0]["width"], 0)
        self.assertGreater(pages[0]["height"], 0)
        self.assertTrue(pages[0]["png"].startswith(b"\x89PNG"))


class TableAwareExtractionTests(SimpleTestCase):
    def test_family_history_rows_kept_row_aligned(self):
        _, blocks, _ = extract_blocks(_fixture("consult_note.pdf"))
        table_rows = [b for b in blocks if b["type"] == "table_row"]
        self.assertTrue(table_rows, "expected at least one table_row block")

        row = next(b for b in table_rows if "Dorothy Whitcombe" in b["text"])
        cell_by_header = {c["header"]: c["text"] for c in row["cells"]}
        self.assertEqual(cell_by_header["Relation"], "Mother")
        self.assertEqual(cell_by_header["Name"], "Dorothy Whitcombe")

    def test_cell_offsets_match_row_text(self):
        _, blocks, _ = extract_blocks(_fixture("consult_note.pdf"))
        row = next(b for b in blocks if b["type"] == "table_row" and "Dorothy Whitcombe" in b["text"])
        for cell in row["cells"]:
            self.assertEqual(row["text"][cell["start"]:cell["end"]], cell["text"])

    def test_cell_boxes_are_plausible_page_coordinates(self):
        _, blocks, pages = extract_blocks(_fixture("consult_note.pdf"))
        page = pages[0]
        row = next(b for b in blocks if b["type"] == "table_row" and "Dorothy Whitcombe" in b["text"])
        for cell in row["cells"]:
            self.assertGreaterEqual(cell["x0"], 0)
            self.assertLessEqual(cell["x1"], page["width"])
            self.assertLess(cell["x0"], cell["x1"])
            self.assertLess(cell["top"], cell["bottom"])

    def test_table_content_not_duplicated_in_paragraph_blocks(self):
        _, blocks, _ = extract_blocks(_fixture("consult_note.pdf"))
        paragraph_text = " ".join(b["text"] for b in blocks if b["type"] != "table_row")
        self.assertNotIn("Dorothy Whitcombe", paragraph_text)


class WordPositionTests(SimpleTestCase):
    """Non-table blocks must carry per-word offsets/bboxes so detected
    entity spans can be mapped back to page coordinates for the Review
    screen's overlay boxes."""

    def test_paragraph_blocks_have_word_positions(self):
        _, blocks, _ = extract_blocks(_fixture("consult_note.pdf"))
        block = next(b for b in blocks if "Eleanor Whitcombe" in b["text"])
        self.assertIn("words", block)
        self.assertTrue(block["words"])

    def test_word_offsets_match_block_text(self):
        _, blocks, _ = extract_blocks(_fixture("consult_note.pdf"))
        block = next(b for b in blocks if "Eleanor Whitcombe" in b["text"])
        words_text = " ".join(block["text"][w["start"]:w["end"]] for w in block["words"])
        self.assertEqual(words_text, block["text"])

    def test_word_boxes_are_plausible_page_coordinates(self):
        _, blocks, pages = extract_blocks(_fixture("consult_note.pdf"))
        page = pages[0]
        block = next(b for b in blocks if "Eleanor Whitcombe" in b["text"])
        for w in block["words"]:
            self.assertGreaterEqual(w["x0"], 0)
            self.assertLessEqual(w["x1"], page["width"])
            self.assertLess(w["x0"], w["x1"])
            self.assertLess(w["top"], w["bottom"])


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
        _, blocks, pages = extract_blocks(_fixture("consult_note_scanned.pdf"))
        self.assertTrue(any(b["source"] == "tesseract" for b in blocks))
        full_text = " ".join(b["text"] for b in blocks)
        self.assertIn("Whitcombe", full_text)
        self.assertIn("4471002", full_text)
        self.assertTrue(pages[0]["png"].startswith(b"\x89PNG"))

    def test_ocr_blocks_carry_word_positions(self):
        _, blocks, _ = extract_blocks(_fixture("consult_note_scanned.pdf"))
        ocr_blocks_with_words = [b for b in blocks if b["source"] == "tesseract" and b.get("words")]
        self.assertTrue(ocr_blocks_with_words)
        block = ocr_blocks_with_words[0]
        words_text = " ".join(block["text"][w["start"]:w["end"]] for w in block["words"])
        self.assertEqual(words_text, block["text"])


class SparseNativeTextTriggersOcrTests(SimpleTestCase):
    """redacted_consult_note.pdf has, on several pages, only a handful of
    genuine text runs (a few label tokens) plus a spurious near-full-page
    "table" pdfplumber detects from border lines — while the actual visible
    page content has no selectable characters at all. A naive "is there any
    text / any table" check would wrongly treat these pages as already
    handled and never attempt OCR. Stubs `_ocr_words` so this is testable
    without the tesseract binary."""

    def test_sparse_pages_fall_back_to_ocr_when_it_finds_more(self):
        with patch("documents.extraction._ocr_words", return_value=_fake_words(200)):
            _, blocks, _ = extract_blocks(_fixture("redacted_consult_note.pdf"))
        sources_by_page = {}
        for b in blocks:
            sources_by_page.setdefault(b["page"], set()).add(b["source"])
        for page, sources in sources_by_page.items():
            self.assertEqual(sources, {"tesseract"}, f"page {page} did not fall back to OCR")
        # The spurious near-full-page tables on pages 2-4 must not survive
        # once OCR supersedes that page's native extraction.
        self.assertFalse(any(b["type"] == "table_row" for b in blocks))

    def test_sparse_native_text_kept_when_ocr_unavailable(self):
        with patch("documents.extraction._ocr_words", return_value=[]):
            _, blocks, _ = extract_blocks(_fixture("redacted_consult_note.pdf"))
        self.assertTrue(all(b["source"] == "text" for b in blocks))
