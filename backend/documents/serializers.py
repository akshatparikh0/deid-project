from rest_framework import serializers

from .categories import MODE_CHOICES
from .models import CategoryRule, Entity, Job


class JobSerializer(serializers.ModelSerializer):
    code = serializers.ReadOnlyField()
    entity_count = serializers.SerializerMethodField()
    unresolved_count = serializers.SerializerMethodField()
    class_count = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "code", "filename", "uploaded_by", "department", "pages",
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
            "confidence", "page", "detector", "block_index",
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


class JobPatchSerializer(serializers.Serializer):
    confidence_threshold = serializers.FloatField(required=False, min_value=0, max_value=1)
    uploaded_by = serializers.CharField(required=False, allow_blank=True, max_length=120)
    department = serializers.CharField(required=False, allow_blank=True, max_length=120)


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
    preset = serializers.ChoiceField(choices=MODE_CHOICES, required=False, default="mask")

    def validate_file(self, value):
        if not value.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF files are supported.")
        max_bytes = 50 * 1024 * 1024
        if value.size > max_bytes:
            raise serializers.ValidationError("File exceeds the 50 MB limit.")
        return value
