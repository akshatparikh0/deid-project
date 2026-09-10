import json
import os
import shutil
import unittest

from django.test import TestCase

from documents.ingest import run_ingestion
from documents.models import Job

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    return open(os.path.join(FIXTURES, name), "rb")


def _run(filename):
    job = Job.objects.create(filename=filename)
    with _fixture(filename) as f:
        run_ingestion(job, f)
    job.refresh_from_db()
    return job


class DlpFixtureIngestTests(TestCase):
    """30 rows of (Name, SSN, Credit Card Number) — every SSN and every CCN
    is a real, high-precision structured identifier, so recall must be 100%
    for both; names are heuristic so a small miss margin is tolerated."""

    @classmethod
    def setUpTestData(cls):
        cls.job = _run("dlptest_name_ssn_ccn.pdf")

    def test_ingestion_succeeded(self):
        self.assertEqual(self.job.status, "in_review")
        self.assertIsNone(self.job.error_message)

    def test_all_30_ssns_found(self):
        self.assertEqual(self.job.entities.filter(category="ssn").count(), 30)

    def test_all_30_credit_card_numbers_found(self):
        # Tagged "other" per product decision (no dedicated ccn category).
        self.assertEqual(self.job.entities.filter(category="other").count(), 30)

    def test_name_recall_at_least_90_percent(self):
        expected_names = {
            "Robert Aragon", "Ashley Borden", "Thomas Conley", "Susan Davis",
            "Christopher Diaz", "Rick Edwards", "Victor Faulkner", "Lisa Garrison",
            "Marjorie Green", "Mark Hall", "James Heard", "Albert Iorio",
            "Charles Jackson", "Teresa Kaminski", "Tim Lowe", "Monte Mceachern",
            "Adriane Morrison", "Jerome Munsch", "Agnes Nelson", "Lynette Oyola",
            "Stacey Peacock", "Julie Renfro", "Danny Reyes", "Jacki Russell",
            "Thomas Santos", "Mireille Townsend", "Lillian Venson", "Gail Watson",
            "Johnson White", "Rebecca Zwick",
        }
        found_names = set(self.job.entities.filter(category="name").values_list("value", flat=True))
        recall = len(expected_names & found_names) / len(expected_names)
        self.assertGreaterEqual(recall, 0.9, f"only found {found_names & expected_names}")


class ConsultNoteIngestTests(TestCase):
    """Synthetic clinical note exercising patient/physician/facility/mrn/date
    detection plus table-aware family-history name detection, against the
    hand-authored ground truth in fixtures/consult_note_expected.json."""

    @classmethod
    def setUpTestData(cls):
        cls.job = _run("consult_note.pdf")
        with open(os.path.join(FIXTURES, "consult_note_expected.json")) as f:
            cls.expected = json.load(f)

    def test_ingestion_succeeded(self):
        self.assertEqual(self.job.status, "in_review")

    def test_high_precision_categories_fully_recalled(self):
        for category in ("patient_name", "physician_name", "facility", "mrn"):
            found = set(self.job.entities.filter(category=category).values_list("value", flat=True))
            self.assertEqual(found, set(self.expected[category]), category)

    def test_dates_fully_recalled(self):
        found = set(self.job.entities.filter(category="date").values_list("value", flat=True))
        self.assertEqual(found, set(self.expected["date"]))

    def test_family_history_names_fully_recalled(self):
        found = set(self.job.entities.filter(category="name").values_list("value", flat=True))
        self.assertEqual(found, set(self.expected["name"]))

    def test_no_bare_year_or_age_false_positives(self):
        # "2014" (surgery year, Safe-Harbor-permitted) and "40"/"52"/"15"
        # (ages under 90) must never be tagged as PHI.
        all_values = set(self.job.entities.values_list("value", flat=True))
        self.assertFalse(all_values & {"2014", "40", "52", "15"})


class RedactedSampleNegativeControlTests(TestCase):
    """A real EHR export whose real PHI values were already scrubbed to
    bracket placeholders ([PATIENT_NAME], [MRN-1], ...) before it reached
    this repo — confirmed independently with pdfplumber, poppler's
    pdftotext, and a raw byte-level `strings` scan, so this isn't an
    extraction bug. Most of the page is drawn as vector glyphs with no
    underlying text-showing operator at all (not an image either — the only
    embedded images are tiny icons), so the OCR fallback is what recovers
    it. This is a negative control for shapes that plainly can't be present
    (no SSN, email, phone, or credit-card-shaped digit run exists anywhere
    in this file, redacted or not) — it must hold with or without the
    tesseract binary installed."""

    def test_no_ssn_email_phone_or_other_structured_entities(self):
        job = _run("redacted_consult_note.pdf")
        self.assertEqual(job.status, "in_review")
        structured = job.entities.filter(category__in=["ssn", "email", "phone", "ip", "other"])
        self.assertEqual(structured.count(), 0)

    @unittest.skipUnless(shutil.which("tesseract"), "tesseract binary not installed")
    def test_ocr_recovers_the_real_non_phi_clinical_narrative(self):
        # With OCR active, the surrounding non-PHI content (diagnoses,
        # medications, review of systems) — genuinely real text, just drawn
        # as vector glyphs pdfplumber can't extract — must come through
        # readable rather than being silently dropped. The specific PHI
        # fields (patient/physician/facility name) correctly stay empty:
        # there's no real value left there to recover, only the bracket
        # placeholder that was already burned into the page.
        job = _run("redacted_consult_note.pdf")
        all_text = " ".join(job.blocks.values_list("text", flat=True))
        self.assertIn("allergic rhinitis", all_text)
        self.assertIn("Review of Systems", all_text)
        self.assertTrue(job.blocks.filter(source="ocr").exists())
