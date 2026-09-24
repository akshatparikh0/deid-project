"""
End-to-end regression coverage for reviewer-approved finalization: the full
upload -> review -> complete flow through the actual API view, asserting
that completion (a) truly redacts the original PDF's content stream (not
just a rebuilt reportlab document), (b) fails closed and leaves the job
recoverable when verification finds a survivor, and (c) writes a permanent,
append-only audit trail.
"""
import io
import os

import pdfplumber
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from documents.ingest import run_ingestion
from documents.models import AuditRecord, ExportArtifact, ImmutableRecordError, Job

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "pipeline", "tests", "fixtures")


def _fixture(name):
    return open(os.path.join(FIXTURES, name), "rb")


def _pdf_text(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


class JobCompletionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="reviewer", password="pw123456!")

    def setUp(self):
        self.client = APIClient()
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def _ingest(self, filename):
        # Mirrors JobListCreateView.post: job.file must be saved before
        # ingestion, since finalize.py reads the original bytes back from
        # it at completion time.
        job = Job.objects.create(filename=filename)
        with _fixture(filename) as f:
            job.file.save(filename, f, save=True)
        with job.file.open("rb") as f:
            run_ingestion(job, f)
        job.refresh_from_db()
        return job


class SuccessfulFinalizationTests(JobCompletionTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

    def setUp(self):
        super().setUp()
        self.job = self._ingest("consult_note.pdf")
        # Force every entity to a concrete transform so completion needs no
        # force=True and finalize.py actually has something to redact.
        self.job.entities.exclude(category__in=("date_of_service", "age_89_or_below")).update(mode="mask")
        self.job.entities.filter(category__in=("date_of_service", "age_89_or_below")).update(mode="keep")
        self.entity_count = self.job.entities.count()

    def test_complete_succeeds_and_purges_source(self):
        resp = self.client.post(f"/api/jobs/{self.job.id}/complete/", {}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "complete")
        self.assertFalse(self.job.file)

    def test_finalized_pdf_has_true_redaction_not_a_rebuild(self):
        self.client.post(f"/api/jobs/{self.job.id}/complete/", {}, format="json")
        artifact = ExportArtifact.objects.get(job=self.job, format="pdf")
        with artifact.file.open("rb") as fh:
            text = _pdf_text(fh.read())
        self.assertNotIn("Eleanor Whitcombe", text)
        self.assertNotIn("Cedar Grove Medical Center", text)
        self.assertIn("[PATIENT_NAME]", text)
        self.assertIn("[FACILITY]", text)
        # A bare 4-digit year is Safe-Harbor-permitted and never flagged by
        # detect_spans, so it must survive verbatim even though every
        # actual date entity in this document was masked.
        self.assertIn("2014", text)

    def test_audit_trail_is_written_once_and_is_immutable(self):
        self.client.post(f"/api/jobs/{self.job.id}/complete/", {}, format="json")
        records = list(self.job.audit_records.all())
        self.assertEqual(len(records), self.entity_count)
        self.assertTrue(all(r.value_hash.startswith("sha256:") for r in records))

        record = records[0]
        record.confidence = 0.01
        with self.assertRaises(ImmutableRecordError):
            record.save()
        with self.assertRaises(ImmutableRecordError):
            record.delete()

    def test_export_after_completion_does_not_overwrite_the_finalized_pdf(self):
        self.client.post(f"/api/jobs/{self.job.id}/complete/", {}, format="json")
        finalized = ExportArtifact.objects.get(job=self.job, format="pdf")
        finalized_bytes = finalized.file.read()

        resp = self.client.post(f"/api/jobs/{self.job.id}/export/", {"formats": ["pdf"]}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)

        artifact = ExportArtifact.objects.get(job=self.job, format="pdf")
        with artifact.file.open("rb") as fh:
            reread_bytes = fh.read()
        self.assertEqual(reread_bytes, finalized_bytes)
        self.assertIn("[PATIENT_NAME]", _pdf_text(reread_bytes))

    def test_audit_endpoint_switches_to_the_permanent_trail_after_completion(self):
        pre_resp = self.client.get(f"/api/jobs/{self.job.id}/audit/")
        self.assertEqual(len(pre_resp.data["rows"]), self.entity_count)

        self.client.post(f"/api/jobs/{self.job.id}/complete/", {}, format="json")
        self.assertEqual(AuditRecord.objects.filter(job=self.job).count(), self.entity_count)

        post_resp = self.client.get(f"/api/jobs/{self.job.id}/audit/")
        self.assertEqual(len(post_resp.data["rows"]), self.entity_count)


class VerificationFailureTests(JobCompletionTestCase):
    def test_a_span_that_cannot_be_redacted_fails_the_job_closed(self):
        job = self._ingest("consult_note.pdf")
        job.entities.update(mode="mask")
        # Sabotage one entity's boxes so finalize.py has nothing to draw a
        # redaction rectangle over — its original text necessarily survives
        # in the finalized PDF, which verification must catch.
        victim = job.entities.filter(category="patient_name").first()
        self.assertIsNotNone(victim)
        victim.boxes = []
        victim.save(update_fields=["boxes"])

        resp = self.client.post(f"/api/jobs/{job.id}/complete/", {}, format="json")
        self.assertEqual(resp.status_code, 422, resp.data)
        self.assertIn("Verification failed", resp.data["detail"])

        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIn("Verification failed", job.error_message)
        # Nothing destructive happened: the source file is intact and no
        # (necessarily-unverified) audit trail was written.
        self.assertTrue(job.file)
        self.assertEqual(job.audit_records.count(), 0)
        self.assertFalse(ExportArtifact.objects.filter(job=job, format="pdf").exists())

    def test_failed_job_can_be_reopened_and_recompleted(self):
        job = self._ingest("consult_note.pdf")
        job.entities.update(mode="mask")
        victim = job.entities.filter(category="patient_name").first()
        victim.boxes = []
        victim.save(update_fields=["boxes"])
        self.client.post(f"/api/jobs/{job.id}/complete/", {}, format="json")

        # A reviewer fixes the problem the only way the API exposes:
        # setting that entity to "keep" so it's no longer a redaction
        # target (in practice they'd re-run detection; this isolates the
        # reopen -> recomplete path without needing a second fixture).
        self.client.post(f"/api/jobs/{job.id}/reopen/", {}, format="json")
        job.refresh_from_db()
        self.assertEqual(job.status, "in_review")
        job.entities.filter(pk=victim.pk).update(mode="keep")

        resp = self.client.post(f"/api/jobs/{job.id}/complete/", {"force": True}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        job.refresh_from_db()
        self.assertEqual(job.status, "complete")
