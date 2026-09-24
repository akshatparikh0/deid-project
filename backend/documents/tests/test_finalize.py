"""
End-to-end regression coverage for reviewer-approved finalization: the full
upload -> review -> complete flow through the actual API view, asserting
that completion (a) truly redacts the original PDF's content stream (not
just a rebuilt reportlab document), and (b) writes a permanent, append-only
audit trail.
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


class CompletionFailureHandlingTests(JobCompletionTestCase):
    def setUp(self):
        super().setUp()
        self.job = self._ingest("consult_note.pdf")
        self.job.entities.update(mode="mask")

    def test_completing_an_already_complete_job_is_a_no_op(self):
        first = self.client.post(f"/api/jobs/{self.job.id}/complete/", {}, format="json")
        self.assertEqual(first.status_code, 200, first.data)

        # A repeat "Mark complete" (a double click, a retried request) must
        # not try to re-finalize a job whose source file is already
        # purged — that used to crash uncaught and leave the job stuck on
        # "finalizing" with whatever error_message it last had.
        second = self.client.post(f"/api/jobs/{self.job.id}/complete/", {}, format="json")
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data["job"]["status"], "complete")

    def test_a_completion_failure_reverts_to_failed_instead_of_sticking_on_finalizing(self):
        # Simulate the source file having gone missing out from under a job
        # that's mid-review (storage cleanup, a bad migration, anything) —
        # whatever the cause, complete_job() must not be allowed to leave
        # the job stuck on "finalizing" after an unhandled crash.
        self.job.file.delete(save=True)

        resp = self.client.post(f"/api/jobs/{self.job.id}/complete/", {}, format="json")
        self.assertEqual(resp.status_code, 500, resp.data)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "failed")
        self.assertTrue(self.job.error_message)
