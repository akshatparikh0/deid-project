from django.urls import path

from . import views

urlpatterns = [
    path("jobs/", views.JobListCreateView.as_view()),
    path("jobs/<int:job_id>/", views.JobDetailView.as_view()),
    path("jobs/<int:job_id>/document/", views.JobDocumentView.as_view()),
    path("jobs/<int:job_id>/pages/<int:number>/image/", views.JobPageImageView.as_view()),
    path("jobs/<int:job_id>/entities/bulk_update/", views.JobEntitiesBulkUpdateView.as_view()),
    path("jobs/<int:job_id>/rules/", views.JobRulesView.as_view()),
    path("jobs/<int:job_id>/rules/apply/", views.JobRulesApplyView.as_view()),
    path("jobs/<int:job_id>/rules/<str:category>/", views.JobRuleDetailView.as_view()),
    path("jobs/<int:job_id>/complete/", views.JobCompleteView.as_view()),
    path("jobs/<int:job_id>/reopen/", views.JobReopenView.as_view()),
    path("jobs/<int:job_id>/audit/", views.JobAuditView.as_view()),
    path("jobs/<int:job_id>/export/", views.JobExportView.as_view()),
    path("jobs/<int:job_id>/export/download/<str:fmt>/", views.JobExportDownloadView.as_view()),
    path("entities/<int:entity_id>/", views.EntityDetailView.as_view()),
]
