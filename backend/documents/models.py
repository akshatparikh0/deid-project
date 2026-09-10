import hashlib

from django.db import models

from .categories import (
    BLOCK_SOURCE_CHOICES,
    BLOCK_TYPE_CHOICES,
    CATEGORY_CHOICES,
    CATEGORY_META,
    JOB_STATUS_CHOICES,
    MODE_CHOICES,
)


def upload_path(instance, filename):
    return f"uploads/{filename}"


class Job(models.Model):
    filename = models.CharField(max_length=255)
    uploaded_by = models.CharField(max_length=120, blank=True, default="")
    department = models.CharField(max_length=120, blank=True, default="")
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
        """Delete the uploaded source PDF from disk once it's no longer needed
        for editing — de-identified output and the audit trail don't need it."""
        if self.file:
            self.file.delete(save=False)
            self.file = None
            self.save(update_fields=["file"])


class DocumentBlock(models.Model):
    job = models.ForeignKey(Job, related_name="blocks", on_delete=models.CASCADE)
    index = models.PositiveIntegerField()
    page = models.PositiveIntegerField()
    type = models.CharField(max_length=9, choices=BLOCK_TYPE_CHOICES, default="p")
    text = models.TextField()
    source = models.CharField(max_length=4, choices=BLOCK_SOURCE_CHOICES, default="text")

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["job", "index"], name="unique_block_index_per_job"),
        ]


class Entity(models.Model):
    job = models.ForeignKey(Job, related_name="entities", on_delete=models.CASCADE)
    block = models.ForeignKey(DocumentBlock, related_name="entities", on_delete=models.CASCADE)
    code = models.CharField(max_length=12)  # "E-01"
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES)
    value = models.TextField()
    surrogate_value = models.TextField(blank=True, default="")
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="keep")
    confidence = models.FloatField()
    page = models.PositiveIntegerField()
    detector = models.CharField(max_length=16, default="pattern")
    start_in_block = models.PositiveIntegerField()
    end_in_block = models.PositiveIntegerField()

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
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES)
    enabled = models.BooleanField(default=True)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="mask")
    token = models.CharField(max_length=40)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "category"], name="unique_rule_per_job_category"),
        ]

    def __str__(self):
        return f"{self.job.code}:{self.category}"


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
