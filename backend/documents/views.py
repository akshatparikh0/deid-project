from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from .categories import CATEGORY_META, CATEGORY_ORDER
from .complete import VerificationError, complete_job
from .export import build_export, content_type_for
from .models import CategoryRule, Entity, ExportArtifact, Job, Page
from .tasks import ingest_job
from .payload import build_document_payload
from .serializers import (
    BulkModeUpdateSerializer,
    CategoryRulePatchSerializer,
    CategoryRuleSerializer,
    CompleteJobSerializer,
    EntityModeUpdateSerializer,
    EntitySerializer,
    ExportRequestSerializer,
    JobPatchSerializer,
    JobSerializer,
    UploadSerializer,
)


def _job_or_404(job_id):
    return get_object_or_404(Job, pk=job_id)


def _reject_if_complete(job):
    """Completed jobs are a locked compliance record — reopen first to edit."""
    if job.status == "complete":
        return Response(
            {"detail": "This document is complete and locked for editing. Reopen it first."},
            status=409,
        )
    return None


class JobListCreateView(APIView):
    def get(self, request):
        jobs = Job.objects.all()
        return Response({"jobs": JobSerializer(jobs, many=True).data})

    def post(self, request):
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        job = Job.objects.create(
            filename=data["file"].name,
            uploaded_by=data.get("uploaded_by", ""),
            department=data.get("department", ""),
            preset=data.get("preset", "mask"),
            status="queued",
        )
        job.file.save(data["file"].name, data["file"], save=True)

        # Synchronous in-process (default, no broker configured) or a real
        # queued worker job (CELERY_BROKER_URL set) — see tasks.py. Either
        # way the job is "queued" until a worker picks it up, matching
        # Job.status's original intent for this state.
        ingest_job.delay(job.id)

        job.refresh_from_db()
        return Response({"job": JobSerializer(job).data}, status=201)


class JobDetailView(APIView):
    def get(self, request, job_id):
        return Response({"job": JobSerializer(_job_or_404(job_id)).data})

    def patch(self, request, job_id):
        job = _job_or_404(job_id)
        serializer = JobPatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(job, field, value)
        job.save()
        return Response({"job": JobSerializer(job).data})

    def delete(self, request, job_id):
        _job_or_404(job_id).delete()
        return Response(status=204)


class JobDocumentView(APIView):
    def get(self, request, job_id):
        job = _job_or_404(job_id)
        # "failed" covers two different things: ingestion never produced a
        # document at all (nothing to show), or completion's verification
        # step rejected an otherwise-fully-reviewed document (blocks and
        # entities exist, and the reviewer needs to see them to fix
        # whatever survived) — checking for blocks distinguishes the two
        # instead of blocking every "failed" job equally.
        if not job.blocks.exists():
            return Response({"detail": "This job failed to scan and has no document to review."}, status=409)
        return Response(build_document_payload(job))


class JobPageImageView(APIView):
    def get(self, request, job_id, number):
        job = _job_or_404(job_id)
        page = get_object_or_404(Page, job=job, number=number)
        return FileResponse(page.image.open("rb"), content_type="image/png")


class EntityDetailView(APIView):
    def patch(self, request, entity_id):
        entity = get_object_or_404(Entity, pk=entity_id)
        if rejected := _reject_if_complete(entity.job):
            return rejected
        serializer = EntityModeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity.mode = serializer.validated_data["mode"]
        entity.save(update_fields=["mode"])
        return Response({"entity": EntitySerializer(entity).data})


class JobEntitiesBulkUpdateView(APIView):
    def post(self, request, job_id):
        job = _job_or_404(job_id)
        if rejected := _reject_if_complete(job):
            return rejected
        serializer = BulkModeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        queryset = job.entities.all()
        category = data.get("category")
        if category:
            if category not in CATEGORY_META:
                return Response({"detail": f"Unknown category '{category}'."}, status=400)
            queryset = queryset.filter(category=category)
        queryset.update(mode=data["mode"])

        return Response({"entities": EntitySerializer(job.entities.all(), many=True).data})


def _rules_with_found_counts(job):
    found_counts = {cat: 0 for cat in CATEGORY_ORDER}
    for row in job.entities.values("category").annotate(n=Count("id")):
        found_counts[row["category"]] = row["n"]
    rules = {rule.category: rule for rule in job.rules.all()}
    ordered = [rules[cat] for cat in CATEGORY_ORDER if cat in rules]
    return ordered, found_counts


class JobRulesView(APIView):
    def get(self, request, job_id):
        job = _job_or_404(job_id)
        rules, found_counts = _rules_with_found_counts(job)
        data = CategoryRuleSerializer(rules, many=True, context={"found_counts": found_counts}).data
        return Response({"rules": data})


class JobRuleDetailView(APIView):
    def patch(self, request, job_id, category):
        job = _job_or_404(job_id)
        if rejected := _reject_if_complete(job):
            return rejected
        rule = get_object_or_404(CategoryRule, job=job, category=category)
        serializer = CategoryRulePatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(rule, field, value)
        rule.save()
        found_counts = {category: job.entities.filter(category=category).count()}
        return Response({"rule": CategoryRuleSerializer(rule, context={"found_counts": found_counts}).data})


class JobRulesApplyView(APIView):
    def post(self, request, job_id):
        job = _job_or_404(job_id)
        if rejected := _reject_if_complete(job):
            return rejected
        for rule in job.rules.filter(enabled=True):
            job.entities.filter(category=rule.category).update(mode=rule.mode)
        job.status = "in_review"
        job.save(update_fields=["status"])
        return Response({
            "job": JobSerializer(job).data,
            "entities": EntitySerializer(job.entities.all(), many=True).data,
        })


class JobCompleteView(APIView):
    def post(self, request, job_id):
        job = _job_or_404(job_id)
        serializer = CompleteJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        unresolved = job.entities.filter(mode="keep").count()
        if unresolved and not serializer.validated_data["force"]:
            return Response(
                {"detail": f"{unresolved} identifier(s) are still set to Keep.", "unresolved_count": unresolved},
                status=409,
            )

        job.status = "finalizing"
        job.save(update_fields=["status"])

        try:
            complete_job(job)
        except VerificationError as exc:
            # The source file and every DB row up to this point are
            # untouched — the job goes to "failed" rather than "complete"
            # so a partially- or unverifiably-redacted document is never
            # delivered (FR-81, AC-25).
            job.status = "failed"
            job.error_message = str(exc)
            job.save(update_fields=["status", "error_message"])
            return Response({"detail": str(exc), "job": JobSerializer(job).data}, status=422)

        job.status = "complete"
        job.save(update_fields=["status"])
        job.purge_source_file()
        return Response({"job": JobSerializer(job).data})


class JobReopenView(APIView):
    def post(self, request, job_id):
        job = _job_or_404(job_id)
        job.status = "in_review"
        job.save(update_fields=["status"])
        return Response({"job": JobSerializer(job).data})


class JobAuditView(APIView):
    def get(self, request, job_id):
        job = _job_or_404(job_id)
        audit_records = list(job.audit_records.all())
        if audit_records:
            # The permanent, immutable trail written once at finalization
            # (NFR-16) — what actually shipped, not the still-editable
            # in-review state.
            rows = [
                {
                    "entity_code": r.entity_code, "category": r.category, "value_hash": r.value_hash,
                    "action": r.action, "detector": r.detector, "confidence": round(r.confidence, 2),
                    "created_at": r.created_at.isoformat(),
                }
                for r in audit_records
            ]
        else:
            # Not finalized yet — a live preview derived from the
            # currently-editable Entity table, so a reviewer can see what
            # the audit trail *will* look like before completing the job.
            rows = [
                {
                    "entity_code": e.code, "category": e.category, "value_hash": e.value_hash(),
                    "action": e.mode, "detector": e.detector, "confidence": round(e.confidence, 2),
                    "created_at": job.updated_at.isoformat(),
                }
                for e in job.entities.order_by("code")
            ]
        return Response({"rows": rows})


class JobExportView(APIView):
    def post(self, request, job_id):
        job = _job_or_404(job_id)
        serializer = ExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = build_document_payload(job)
        entities = list(job.entities.order_by("code"))
        files = []
        for fmt in serializer.validated_data["formats"]:
            # complete_job() (see complete.py) already wrote the true
            # PyMuPDF-redacted "pdf" artifact at finalization — regenerating
            # it here via the reportlab reconstruction would silently
            # replace a verified, byte-faithful result with a lower-fidelity
            # one, and the source file it would need is purged by then
            # anyway. Only build it on demand for a job that hasn't been
            # finalized yet.
            if fmt == "pdf" and job.status == "complete":
                artifact = ExportArtifact.objects.get(job=job, format="pdf")
            else:
                artifact = build_export(job, fmt, payload["blocks"], entities)
            files.append({
                "format": fmt, "filename": artifact.filename,
                "url": f"/api/jobs/{job.id}/export/download/{fmt}/",
            })
        return Response({"files": files})


class JobExportDownloadView(APIView):
    def get(self, request, job_id, fmt):
        job = _job_or_404(job_id)
        artifact = get_object_or_404(ExportArtifact, job=job, format=fmt)
        response = FileResponse(
            artifact.file.open("rb"), content_type=content_type_for(fmt),
            as_attachment=True, filename=artifact.filename,
        )
        return response
