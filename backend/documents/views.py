from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from .categories import CATEGORY_META, CATEGORY_ORDER
from .export import build_export, content_type_for
from .ingest import run_ingestion
from .models import CategoryRule, Entity, ExportArtifact, Job
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
            status="scanning",
        )
        job.file.save(data["file"].name, data["file"], save=True)

        with job.file.open("rb") as fh:
            run_ingestion(job, fh)

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
        if job.status == "failed":
            return Response({"detail": "This job failed to scan and has no document to review."}, status=409)
        return Response(build_document_payload(job))


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
