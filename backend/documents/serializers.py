from rest_framework import serializers

from pipeline.categories import MODE_CHOICES
from .models import CategoryRule, Entity, Folder, FolderCategoryRule, Job, JobStage, UploadBatch


class FolderSerializer(serializers.ModelSerializer):
    subfolder_count = serializers.SerializerMethodField()
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = Folder
        fields = ["id", "name", "parent", "subfolder_count", "document_count", "created_at", "updated_at"]

    def get_subfolder_count(self, obj):
        return obj.children.count()

    def get_document_count(self, obj):
        return obj.jobs.count()


def _validate_folder_parent(value):
    """Folders are exactly two levels deep — a project (level 0) and its
    patients (level 1). A patient folder holds documents, not subfolders."""
    if value is not None and value.level >= 1:
        raise serializers.ValidationError("Folders cannot be created inside a patient folder.")
    return value


class FolderWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    parent = serializers.PrimaryKeyRelatedField(queryset=Folder.objects.all(), required=False, allow_null=True)

    def validate_parent(self, value):
        return _validate_folder_parent(value)


class FolderPatchSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=255)
    parent = serializers.PrimaryKeyRelatedField(queryset=Folder.objects.all(), required=False, allow_null=True)

    def validate_parent(self, value):
        return _validate_folder_parent(value)


class JobSerializer(serializers.ModelSerializer):
    code = serializers.ReadOnlyField()
    entity_count = serializers.SerializerMethodField()
    unresolved_count = serializers.SerializerMethodField()
    class_count = serializers.SerializerMethodField()
    # Read-only FK id, not the batch object — lets a scanning/failed job in
    # QueuePage route to its batch's Status page (see lib/jobRoute.ts).
    batch = serializers.IntegerField(source="batch_id", read_only=True)

    class Meta:
        model = Job
        fields = [
            "id", "code", "filename", "uploaded_by", "department", "folder", "batch", "pages",
            "status", "error_message", "entity_count", "unresolved_count",
            "class_count", "confidence_threshold", "created_at", "updated_at",
        ]

    def get_entity_count(self, obj):
        return obj.entities.count()

    def get_unresolved_count(self, obj):
        return obj.entities.filter(mode="keep").count()

    def get_class_count(self, obj):
        return obj.entities.values("category").distinct().count()


class EntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity
        fields = [
            "id", "code", "category", "value", "surrogate_value", "mode",
            "confidence", "page", "detector", "block_index", "boxes",
        ]

    block_index = serializers.IntegerField(source="block.index", read_only=True)


class EntityModeUpdateSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=MODE_CHOICES)


class BulkModeUpdateSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=MODE_CHOICES)
    category = serializers.CharField(required=False, allow_blank=False)


class CategoryRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryRule
        fields = ["category", "enabled", "mode", "token", "found"]

    found = serializers.SerializerMethodField()

    def get_found(self, obj):
        counts = self.context.get("found_counts", {})
        return counts.get(obj.category, 0)


class CategoryRulePatchSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    mode = serializers.ChoiceField(choices=MODE_CHOICES, required=False)
    token = serializers.CharField(required=False, max_length=40)


class FolderCategoryRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FolderCategoryRule
        fields = ["category", "enabled", "mode", "token"]


class FolderCategoryRulePatchSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    mode = serializers.ChoiceField(choices=MODE_CHOICES, required=False)
    token = serializers.CharField(required=False, max_length=40)


class JobPatchSerializer(serializers.Serializer):
    confidence_threshold = serializers.FloatField(required=False, min_value=0, max_value=1)
    uploaded_by = serializers.CharField(required=False, allow_blank=True, max_length=120)
    department = serializers.CharField(required=False, allow_blank=True, max_length=120)
    filename = serializers.CharField(required=False, max_length=255)
    folder = serializers.PrimaryKeyRelatedField(queryset=Folder.objects.all(), required=False)

    def validate_filename(self, value):
        if not value.strip():
            raise serializers.ValidationError("Filename cannot be blank.")
        return value.strip()

    def validate_folder(self, value):
        if value.level != 1:
            raise serializers.ValidationError("Documents can only be placed in a patient folder.")
        return value


class CompleteJobSerializer(serializers.Serializer):
    force = serializers.BooleanField(required=False, default=False)


class ExportRequestSerializer(serializers.Serializer):
    formats = serializers.ListField(
        child=serializers.ChoiceField(choices=["pdf", "csv", "json"]),
        allow_empty=False,
    )


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    uploaded_by = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    department = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    folder = serializers.PrimaryKeyRelatedField(queryset=Folder.objects.all())
    preset = serializers.ChoiceField(choices=MODE_CHOICES, required=False, default="mask")

    def validate_file(self, value):
        if not value.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF files are supported.")
        max_bytes = 50 * 1024 * 1024
        if value.size > max_bytes:
            raise serializers.ValidationError("File exceeds the 50 MB limit.")
        return value

    def validate_folder(self, value):
        if value.level != 1:
            raise serializers.ValidationError("Documents can only be uploaded into a patient folder.")
        return value


class JobStageSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = JobStage
        fields = ["name", "sequence", "status", "started_at", "finished_at", "duration_seconds", "error_message"]

    def get_duration_seconds(self, obj):
        return obj.duration_seconds


class JobWithStagesSerializer(JobSerializer):
    """JobSerializer plus its live stage timeline — used only by the Status
    page's batch endpoint, kept off the base JobSerializer so pages that just
    need job summaries (Queue, Review, Audit) don't pay for the extra query."""
    stages = JobStageSerializer(many=True, read_only=True)

    class Meta(JobSerializer.Meta):
        fields = JobSerializer.Meta.fields + ["stages"]


class BatchUploadSerializer(serializers.Serializer):
    files = serializers.ListField(child=serializers.FileField(), allow_empty=False)
    # Each file's webkitRelativePath (e.g. "Smith/report.pdf") when the
    # upload came from a folder picker, in the same order as `files` —
    # multipart only carries each file's basename, so the frontend sends
    # this separately. Optional/order-matched rather than required so a
    # plain multi-file upload (no folder involved) still works.
    paths = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False, default=list)
    uploaded_by = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    department = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    folder = serializers.PrimaryKeyRelatedField(queryset=Folder.objects.all())
    preset = serializers.ChoiceField(choices=MODE_CHOICES, required=False, default="mask")

    def validate_folder(self, value):
        if value.level != 1:
            raise serializers.ValidationError("Documents can only be uploaded into a patient folder.")
        return value


class UploadBatchSerializer(serializers.ModelSerializer):
    jobs = JobWithStagesSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    finished = serializers.SerializerMethodField()

    class Meta:
        model = UploadBatch
        fields = ["id", "folder", "uploaded_by", "department", "preset", "created_at", "total", "finished", "jobs"]

    def get_total(self, obj):
        return obj.jobs.count()

    def get_finished(self, obj):
        return obj.jobs.exclude(status="scanning").count()
