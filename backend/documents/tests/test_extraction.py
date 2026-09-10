import os
import shutil
import unittest

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
