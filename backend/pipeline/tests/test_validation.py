from __future__ import annotations

import io

import pymupdf
from django.test import SimpleTestCase

from pipeline.validation import ValidationError, validate_pdf


def _pdf_bytes(text="Synthetic medical record"):
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text)

    data = pdf.tobytes()
    pdf.close()

    return data


class PdfValidationTests(SimpleTestCase):
    def test_valid_pdf_passes(self):
        uploaded = io.BytesIO(_pdf_bytes())
        uploaded.name = "sample.pdf"

        result = validate_pdf(uploaded)

        self.assertEqual(result.page_count, 1)
        self.assertGreater(result.size_bytes, 0)
        self.assertEqual(len(result.sha256), 64)
        self.assertFalse(result.encrypted)

    def test_non_pdf_extension_is_rejected(self):
        uploaded = io.BytesIO(_pdf_bytes())
        uploaded.name = "sample.txt"

        with self.assertRaisesMessage(
            ValidationError,
            "Only PDF files are supported",
        ):
            validate_pdf(uploaded)

    def test_fake_pdf_is_rejected(self):
        uploaded = io.BytesIO(b"not actually a pdf")
        uploaded.name = "sample.pdf"

        with self.assertRaises(ValidationError):
            validate_pdf(uploaded)

    def test_empty_pdf_is_rejected(self):
        uploaded = io.BytesIO(b"")
        uploaded.name = "sample.pdf"

        with self.assertRaisesMessage(
            ValidationError,
            "empty",
        ):
            validate_pdf(uploaded)

    def test_validation_restores_file_position(self):
        uploaded = io.BytesIO(_pdf_bytes())
        uploaded.name = "sample.pdf"
        uploaded.seek(10)

        validate_pdf(uploaded)

        self.assertEqual(uploaded.tell(), 10)