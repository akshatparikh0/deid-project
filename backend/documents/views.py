from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from .categories import CATEGORY_META, CATEGORY_ORDER
from .complete import VerificationError, complete_job
from .export import build_export, content_type_for
from .models import CategoryRule, Entity, ExportArtifact, Folder, FolderCategoryRule, Job, Page, UploadBatch
from .payload import build_document_payload
from .serializers import (
    BatchUploadSerializer,
    BulkModeUpdateSerializer,
    CategoryRulePatchSerializer,
    CategoryRuleSerializer,
    CompleteJobSerializer,
    EntityModeUpdateSerializer,
    EntitySerializer,
    ExportRequestSerializer,
    FolderCategoryRulePatchSerializer,
    FolderCategoryRuleSerializer,
    FolderPatchSerializer,
    FolderSerializer,
    FolderWriteSerializer,
    JobPatchSerializer,
    JobSerializer,
    UploadBatchSerializer,
    UploadSerializer,
)
from .tasks import ingest_job, seed_stages


def _job_or_404(job_id):
    return get_object_or_404(Job, pk=job_id)


def _folder_or_404(folder_id):
    return get_object_or_404(Folder, pk=folder_id)


class FolderListCreateView(APIView):
    def get(self, request):
        folders = Folder.objects.all()
        return Response({"folders": FolderSerializer(folders, many=True).data})

    def post(self, request):
        serializer = FolderWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"].strip()
        parent = serializer.validated_data.get("parent")
        if not name:
            return Response({"detail": "Folder name cannot be blank."}, status=400)
        if Folder.objects.filter(parent=parent, name__iexact=name).exists():
            return Response({"detail": f'A folder named "{name}" already exists here.'}, status=400)
        folder = Folder.objects.create(name=name, parent=parent)
        return Response({"folder": FolderSerializer(folder).data}, status=201)


class FolderDetailView(APIView):
    def get(self, request, folder_id):
        return Response({"folder": FolderSerializer(_folder_or_404(folder_id)).data})

    def patch(self, request, folder_id):
        folder = _folder_or_404(folder_id)
        serializer = FolderPatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target_parent = data["parent"] if "parent" in data else folder.parent
        if "parent" in data:
            new_parent = data["parent"]
            if new_parent and (new_parent.pk == folder.pk or new_parent.pk in folder.descendant_ids()):
                return Response(
                    {"detail": "Cannot move a folder into itself or one of its own subfolders."}, status=400,
                )

        target_name = data["name"].strip() if "name" in data else folder.name
        if "name" in data and not target_name:
            return Response({"detail": "Folder name cannot be blank."}, status=400)

        if ("name" in data or "parent" in data) and Folder.objects.filter(
            parent=target_parent, name__iexact=target_name,
        ).exclude(pk=folder.pk).exists():
            return Response({"detail": f'A folder named "{target_name}" already exists here.'}, status=400)

        if "name" in data:
            folder.name = target_name
        if "parent" in data:
            folder.parent = data["parent"]
        folder.save()
        return Response({"folder": FolderSerializer(folder).data})

    def delete(self, request, folder_id):
        folder = _folder_or_404(folder_id)
        recursive = request.query_params.get("recursive") == "true"
        subfolder_count = folder.children.count()
        document_count = folder.jobs.count()
        if (subfolder_count or document_count) and not recursive:
            return Response(
                {
                    "detail": "This folder is not empty. Pass ?recursive=true to delete it and everything inside.",
                    "subfolder_count": subfolder_count,
                    "document_count": document_count,
                },
                status=409,
            )
        folder.delete()
        return Response(status=204)


def _ensure_folder_rules(folder):
    """Lazily seed a folder's default ruleset with one row per Safe Harbor
    category the first time it's requested, so Config Rules always has
    every category to show even before the user has touched anything."""
    existing = {r.category for r in folder.rules.all()}
    missing = [cat for cat in CATEGORY_ORDER if cat not in existing]
    if missing:
        FolderCategoryRule.objects.bulk_create([
            FolderCategoryRule(folder=folder, category=cat, enabled=True, mode="mask", token=CATEGORY_META[cat]["token"])
            for cat in missing
        ])
    rules = {r.category: r for r in folder.rules.all()}
    return [rules[cat] for cat in CATEGORY_ORDER]


class FolderRulesView(APIView):
    def get(self, request, folder_id):
        folder = _folder_or_404(folder_id)
        rules = _ensure_folder_rules(folder)
        return Response({"rules": FolderCategoryRuleSerializer(rules, many=True).data})


class FolderRuleDetailView(APIView):
    def patch(self, request, folder_id, category):
        folder = _folder_or_404(folder_id)
        _ensure_folder_rules(folder)
        rule = get_object_or_404(FolderCategoryRule, folder=folder, category=category)
        serializer = FolderCategoryRulePatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(rule, field, value)
        rule.save()
        return Response({"rule": FolderCategoryRuleSerializer(rule).data})


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
        folder_param = request.query_params.get("folder")
        if folder_param is not None:
            jobs = jobs.filter(folder_id=None if folder_param in ("", "null") else folder_param)
        return Response({"jobs": JobSerializer(jobs, many=True).data})

    def post(self, request):
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        job = Job.objects.create(
            filename=data["file"].name,
            uploaded_by=data.get("uploaded_by", ""),
            department=data.get("department", ""),
            folder=data.get("folder"),
            preset=data.get("preset", "mask"),
            status="scanning",
        )
        job.file.save(data["file"].name, data["file"], save=True)

        seed_stages(job)
        ingest_job.delay(job.id)

        job.refresh_from_db()
        return Response({"job": JobSerializer(job).data}, status=201)


_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class UploadBatchListCreateView(APIView):
    """Accepts several PDFs (or a whole folder's worth, flattened client-
    side) in one request, creating one Job per valid file and handing each
    off to a background worker (see tasks.py) instead of processing inline —
    the response returns as soon as files are saved, not once they're
    scanned. GET /api/uploads/<id>/ (UploadBatchDetailView) is what the
    frontend Status page polls afterwards."""

    def post(self, request):
        serializer = BatchUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        batch = UploadBatch.objects.create(
            folder=data["folder"],
            uploaded_by=data.get("uploaded_by", ""),
            department=data.get("department", ""),
            preset=data.get("preset", "mask"),
        )

        rejected = []
        for f in data["files"]:
            if not f.name.lower().endswith(".pdf"):
                rejected.append({"filename": f.name, "reason": "Only PDF files are supported."})
                continue
            if f.size > _MAX_UPLOAD_BYTES:
                rejected.append({"filename": f.name, "reason": "File exceeds the 50 MB limit."})
                continue

            job = Job.objects.create(
                filename=f.name,
                batch=batch,
                folder=batch.folder,
                uploaded_by=batch.uploaded_by,
                department=batch.department,
                preset=batch.preset,
                status="scanning",
            )
            job.file.save(f.name, f, save=True)  # "ingest" stage — must stay synchronous (see tasks.seed_stages)
            seed_stages(job)
            ingest_job.delay(job.id)

        if not batch.jobs.exists():
            batch.delete()
            return Response({"detail": "No valid PDF files were uploaded.", "rejected": rejected}, status=400)

        return Response({"batch": UploadBatchSerializer(batch).data, "rejected": rejected}, status=202)


class UploadBatchDetailView(APIView):
    def get(self, request, batch_id):
        batch = get_object_or_404(UploadBatch, pk=batch_id)
        return Response({"batch": UploadBatchSerializer(batch).data})


class JobRetryView(APIView):
    def post(self, request, job_id):
        job = _job_or_404(job_id)
        if job.status != "failed":
            return Response({"detail": "Only failed jobs can be retried."}, status=409)
        job.status = "scanning"
        job.error_message = None
        job.save(update_fields=["status", "error_message"])
        seed_stages(job)
        ingest_job.delay(job.id)
        return Response({"job": JobSerializer(job).data}, status=202)


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
            # delivered.
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
            # The permanent, immutable trail written once at finalization —
            # what actually shipped, not the still-editable in-review state.
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
