"""
Full-stack regression test: exercises the actual HTTP API surface a real
client (the React frontend) drives, end to end — upload -> queued/async
ingestion -> review -> rules -> complete -> export -> audit -> reopen — with
no shortcuts through internal functions. This is the flow every other test
module in this package checks one slice of in isolation.
"""
import io
import os

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from documents.models import AuditRecord, Folder, Job

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _upload_file(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        data = f.read()
    return io.BytesIO(data), data


class FullWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="reviewer", password="pw123456!")
        project = Folder.objects.create(name="Project")
        cls.patient_folder = Folder.objects.create(name="Patient", parent=project)

    def setUp(self):
        self.client = APIClient()
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_unauthenticated_request_is_rejected(self):
        anon = APIClient()
        resp = anon.get("/api/jobs/")
        self.assertEqual(resp.status_code, 401)

    def test_upload_runs_the_queued_task_synchronously_by_default(self):
        buf, _ = _upload_file("consult_note.pdf")
        buf.name = "consult_note.pdf"
        resp = self.client.post(
            "/api/jobs/", {"file": buf, "preset": "mask", "folder": self.patient_folder.id}, format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        # CELERY_TASK_ALWAYS_EAGER (no broker configured, the test default)
        # means ingestion has already run by the time the response comes
        # back — the whole point of "scanning" being a real, inspectable
        # status for a deployment that *does* have a broker.
        self.assertEqual(resp.data["job"]["status"], "in_review")
        job = Job.objects.get(pk=resp.data["job"]["id"])
        self.assertGreater(job.entities.count(), 0)

    def test_full_lifecycle_upload_to_export_and_audit(self):
        buf, _ = _upload_file("consult_note.pdf")
        buf.name = "consult_note.pdf"
        create_resp = self.client.post(
            "/api/jobs/", {"file": buf, "preset": "mask", "folder": self.patient_folder.id}, format="multipart",
        )
        self.assertEqual(create_resp.status_code, 201, create_resp.data)
        job_id = create_resp.data["job"]["id"]

        # Review screen: fetch the document payload.
        doc_resp = self.client.get(f"/api/jobs/{job_id}/document/")
        self.assertEqual(doc_resp.status_code, 200)
        self.assertGreater(len(doc_resp.data["entities"]), 0)
        self.assertGreater(len(doc_resp.data["pages"]), 0)

        # Rules screen: every canonical category has a row, apply them.
        rules_resp = self.client.get(f"/api/jobs/{job_id}/rules/")
        self.assertEqual(rules_resp.status_code, 200)
        self.assertGreater(len(rules_resp.data["rules"]), 0)
        apply_resp = self.client.post(f"/api/jobs/{job_id}/rules/apply/", {}, format="json")
        self.assertEqual(apply_resp.status_code, 200)

        # A low-confidence heuristic hit may still be "keep" after applying
        # rules (confidence below the job's threshold) — force through it,
        # same as a reviewer clicking "complete anyway".
        complete_resp = self.client.post(f"/api/jobs/{job_id}/complete/", {"force": True}, format="json")
        self.assertEqual(complete_resp.status_code, 200, complete_resp.data)
        self.assertEqual(complete_resp.data["job"]["status"], "complete")

        # The immutable audit trail is now the one the API serves.
        self.assertTrue(AuditRecord.objects.filter(job_id=job_id).exists())
        audit_resp = self.client.get(f"/api/jobs/{job_id}/audit/")
        self.assertEqual(audit_resp.status_code, 200)
        self.assertEqual(len(audit_resp.data["rows"]), AuditRecord.objects.filter(job_id=job_id).count())

        # Export every format and download each one.
        export_resp = self.client.post(
            f"/api/jobs/{job_id}/export/", {"formats": ["pdf", "csv", "json"]}, format="json",
        )
        self.assertEqual(export_resp.status_code, 200, export_resp.data)
        self.assertEqual({f["format"] for f in export_resp.data["files"]}, {"pdf", "csv", "json"})
        for f in export_resp.data["files"]:
            download_resp = self.client.get(f["url"])
            self.assertEqual(download_resp.status_code, 200, f["url"])

        # A completed job is locked for entity/rule edits.
        entity_id = doc_resp.data["entities"][0]["id"]
        locked_resp = self.client.patch(
            f"/api/entities/{entity_id}/", {"mode": "redact"}, format="json",
        )
        self.assertEqual(locked_resp.status_code, 409)

        # Reopening unlocks it again.
        reopen_resp = self.client.post(f"/api/jobs/{job_id}/reopen/", {}, format="json")
        self.assertEqual(reopen_resp.status_code, 200)
        self.assertEqual(reopen_resp.data["job"]["status"], "in_review")

    def test_upload_rejects_non_pdf(self):
        resp = self.client.post(
            "/api/jobs/",
            {"file": io.BytesIO(b"not a pdf"), "preset": "mask", "folder": self.patient_folder.id},
            format="multipart",
        )
        # DRF field validation on the .pdf extension check rejects this
        # before a Job row (or a task) is ever created.
        self.assertEqual(resp.status_code, 400)


@override_settings(CELERY_TASK_ALWAYS_EAGER=False, CELERY_BROKER_URL="memory://", CELERY_TASK_STORE_EAGER_RESULT=True)
class AsyncDispatchTests(TestCase):
    """With a broker configured (simulated here via Celery's in-memory
    transport) the endpoint must return before ingestion necessarily
    finishes, proving upload no longer blocks the request on pipeline work
    the way the original synchronous design did."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="reviewer2", password="pw123456!")
        project = Folder.objects.create(name="Project")
        cls.patient_folder = Folder.objects.create(name="Patient", parent=project)

    def test_job_is_dispatched_to_a_worker_not_run_inline(self):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=self.user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        buf, _ = _upload_file("consult_note.pdf")
        buf.name = "consult_note.pdf"
        resp = client.post(
            "/api/jobs/", {"file": buf, "preset": "mask", "folder": self.patient_folder.id}, format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        # The task was queued, not executed inline — status is exactly what
        # Job.objects.create() left it as, since no worker is actually
        # consuming this in-memory queue in the test.
        self.assertEqual(resp.data["job"]["status"], "scanning")

        # A real worker picking up the queued message runs exactly this.
        job = Job.objects.get(pk=resp.data["job"]["id"])
        with job.file.open("rb") as fh:
            from documents.ingest import run_ingestion
            run_ingestion(job, fh)
        job.refresh_from_db()
        self.assertEqual(job.status, "in_review")
