from django.contrib import admin

from .models import CategoryRule, DocumentBlock, Entity, ExportArtifact, Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "filename", "status", "pages", "uploaded_by", "created_at")
    list_filter = ("status",)


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ("code", "job", "category", "mode", "confidence", "page")
    list_filter = ("category", "mode")


admin.site.register(DocumentBlock)
admin.site.register(CategoryRule)
admin.site.register(ExportArtifact)
