import hashlib

from django.db import models
from django.utils import timezone

from .categories import (
    BLOCK_SOURCE_CHOICES,
    BLOCK_TYPE_CHOICES,
    CATEGORY_CHOICES,
    CATEGORY_META,
    JOB_STATUS_CHOICES,
    MODE_CHOICES,
    STAGE_CHOICES,
    STAGE_STATUS_CHOICES,
)


def upload_path(instance, filename):
    return f"uploads/{filename}"


class Folder(models.Model):
    """A node in the document library's file tree. The tree is exactly two
    levels deep: level 0 is a project, level 1 (a project's child) is a
    patient. Patient folders hold documents, not further folders — enforced
    in the serializers, not here, since the model itself stays generic."""
    name = models.CharField(max_length=255)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def level(self):
        level = 0
        current = self
        while current.parent_id is not None:
            level += 1
            current = current.parent
        return level

    def descendant_ids(self):
        ids = set()
        stack = [self]
        while stack:
            current = stack.pop()
            for child in current.children.all():
                ids.add(child.id)
                stack.append(child)
        return ids


class UploadBatch(models.Model):
    """A set of PDFs uploaded together (multi-file or whole-folder upload).
    Exists so the Status page can be reloaded/refreshed and still show every
    file from that upload, even though each file becomes its own independent
    Job that processes and can be reviewed on its own schedule."""
    folder = models.ForeignKey(Folder, null=True, blank=True, related_name="upload_batches", on_delete=models.CASCADE)
    uploaded_by = models.CharField(max_length=120, blank=True, default="")
    department = models.CharField(max_length=120, blank=True, default="")
    preset = models.CharField(max_length=16, choices=MODE_CHOICES, default="mask")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Job(models.Model):
    filename = models.CharField(max_length=255)
    uploaded_by = models.CharField(max_length=120, blank=True, default="")
    department = models.CharField(max_length=120, blank=True, default="")
    folder = models.ForeignKey(Folder, null=True, blank=True, related_name="jobs", on_delete=models.CASCADE)
    batch = models.ForeignKey(UploadBatch, null=True, blank=True, related_name="jobs", on_delete=models.SET_NULL)
    pages = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=JOB_STATUS_CHOICES, default="scanning")
    error_message = models.TextField(null=True, blank=True)
    confidence_threshold = models.FloatField(default=0.85)
    preset = models.CharField(max_length=16, choices=MODE_CHOICES, default="mask")
    file = models.FileField(upload_to=upload_path, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def code(self):
        return f"JOB-{self.id:04d}"

    def __str__(self):
        return f"{self.code} ({self.filename})"

    def purge_source_file(self):
        """Delete the uploaded source PDF, and the rendered page preview
        images derived from it, from disk once they're no longer needed for
        editing — de-identified output and the audit trail don't need
        either. Page images show the full original page content (that's the
        point, for the Review screen), so they get purged on the same
        schedule as the source PDF itself, not kept around indefinitely."""
        if self.file:
            self.file.delete(save=False)
            self.file = None
            self.save(update_fields=["file"])
        for page in self.page_images.all():
            page.image.delete(save=False)
        self.page_images.all().delete()


class JobStage(models.Model):
    """One step of the pipeline (see categories.STAGE_ORDER) for a single
    job, timestamped as it starts/finishes so the Status page can show live
    per-stage progress and duration while a job's status is 'scanning'."""
    job = models.ForeignKey(Job, related_name="stages", on_delete=models.CASCADE)
    name = models.CharField(max_length=16, choices=STAGE_CHOICES)
    sequence = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=STAGE_STATUS_CHOICES, default="pending")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["job", "name"], name="unique_stage_per_job"),
        ]

    @property
    def duration_seconds(self):
        if not self.started_at:
            return None
        return ((self.finished_at or timezone.now()) - self.started_at).total_seconds()


class DocumentBlock(models.Model):
    job = models.ForeignKey(Job, related_name="blocks", on_delete=models.CASCADE)
    index = models.PositiveIntegerField()
    page = models.PositiveIntegerField()
    type = models.CharField(max_length=9, choices=BLOCK_TYPE_CHOICES, default="p")
    text = models.TextField()
    source = models.CharField(max_length=20, choices=BLOCK_SOURCE_CHOICES, default="text")

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["job", "index"], name="unique_block_index_per_job"),
        ]


class Page(models.Model):
    """A rendered preview image of one page of the uploaded PDF, in the same
    coordinate space (PDF points, top-left origin) as Entity.boxes — this is
    what the Review screen's original/de-identified panes actually render,
    with entity boxes drawn on top positioned as percentages of width/height."""
    job = models.ForeignKey(Job, related_name="page_images", on_delete=models.CASCADE)
    number = models.PositiveIntegerField()
    width = models.FloatField()
    height = models.FloatField()
    image = models.ImageField(upload_to="page_images/")
    # Degrees of rotation/skew detected from OCR line geometry (0 for a
    # native-text page, which is never skewed) — see extraction.py's
    # _estimate_skew_angle. finalize.py uses this so a redaction box and its
    # replacement token are drawn at the same angle as the scanned text they
    # cover, instead of an axis-aligned box that either misses part of the
    # tilted glyphs or bleeds into an unrelated neighboring line.
    rotation = models.FloatField(default=0.0)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["job", "number"], name="unique_page_per_job"),
        ]


class Entity(models.Model):
    job = models.ForeignKey(Job, related_name="entities", on_delete=models.CASCADE)
    block = models.ForeignKey(DocumentBlock, related_name="entities", on_delete=models.CASCADE)
    code = models.CharField(max_length=12)  # "E-01"
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    value = models.TextField()
    surrogate_value = models.TextField(blank=True, default="")
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="keep")
    confidence = models.FloatField()
    page = models.PositiveIntegerField()
    detector = models.CharField(max_length=32, default="pattern")
    start_in_block = models.PositiveIntegerField()
    end_in_block = models.PositiveIntegerField()
    boxes = models.JSONField(default=list, blank=True)  # [{x0, top, x1, bottom}, ...] in PDF points, one per line

    class Meta:
        ordering = ["block__index", "start_in_block"]
        constraints = [
            models.UniqueConstraint(fields=["job", "code"], name="unique_entity_code_per_job"),
        ]

    def __str__(self):
        return f"{self.code} [{self.category}]"

    @property
    def token(self):
        return CATEGORY_META[self.category]["token"]

    def value_hash(self):
        digest = hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:20]
        return f"sha256:{digest}"


class CategoryRule(models.Model):
    job = models.ForeignKey(Job, related_name="rules", on_delete=models.CASCADE)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    enabled = models.BooleanField(default=True)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="mask")
    token = models.CharField(max_length=40)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "category"], name="unique_rule_per_job_category"),
        ]

    def __str__(self):
        return f"{self.job.code}:{self.category}"


class FolderCategoryRule(models.Model):
    """The default detection ruleset for a patient folder, configured before
    any document is uploaded into it. New jobs created under the folder seed
    their per-job CategoryRule rows from this (see ingest.run_ingestion)."""
    folder = models.ForeignKey(Folder, related_name="rules", on_delete=models.CASCADE)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    enabled = models.BooleanField(default=True)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="mask")
    token = models.CharField(max_length=40)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["folder", "category"], name="unique_rule_per_folder_category"),
        ]

    def __str__(self):
        return f"{self.folder.name}:{self.category}"


class ImmutableRecordError(RuntimeError):
    pass


class AuditRecord(models.Model):
    """One permanent row per entity, written once at job finalization
    (documents.audit.write_audit_records) — never derived live from the
    (still-editable, pre-completion) Entity table the way the old
    JobAuditView response was. This is the append-only compliance record
    NFR-16 requires: save() refuses any change to an existing row, and
    delete() refuses to remove one directly. Note this only guards
    application-level access — cascading deletion of the parent Job (see
    Job.delete, used by the existing job-management API) still removes
    these rows at the database level, same as every other per-job table;
    true database-enforced append-only (a Postgres REVOKE UPDATE/DELETE
    grant) is a deployment-time hardening step, not something the ORM layer
<<<<<<< HEAD
    alone can guarantee — see infra/README.md."""
=======
    alone can guarantee."""
>>>>>>> feature/screen-map
    job = models.ForeignKey(Job, related_name="audit_records", on_delete=models.CASCADE)
    entity_code = models.CharField(max_length=12)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    value_hash = models.CharField(max_length=80)
    action = models.CharField(max_length=16, choices=MODE_CHOICES)
    detector = models.CharField(max_length=32)
    confidence = models.FloatField()
    page = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["entity_code"]
        constraints = [
            models.UniqueConstraint(fields=["job", "entity_code"], name="unique_audit_record_per_job_entity"),
        ]

    def __str__(self):
        return f"{self.job.code}:{self.entity_code}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableRecordError("Audit records are append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError("Audit records are append-only and cannot be deleted.")


class ExportArtifact(models.Model):
    """A generated export file (pdf/csv/json) kept on disk so repeated
    downloads don't require regenerating it."""
    job = models.ForeignKey(Job, related_name="export_artifacts", on_delete=models.CASCADE)
    format = models.CharField(max_length=8)
    file = models.FileField(upload_to="exports/")
    filename = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "format"], name="unique_export_per_job_format"),
        ]
