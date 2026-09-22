"""
Celery application for async pipeline processing (FR-56/FR-57: each
pipeline stage runs as a queue-driven job against a broker, scaling to zero
on an empty queue — NFR-23). With no CELERY_BROKER_URL configured (the
default for local dev and the test suite), CELERY_TASK_ALWAYS_EAGER runs
every task synchronously in-process instead, so nothing extra needs to be
running for `./dev.sh` or `manage.py test` to work — see settings.py.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deid_backend.settings")

app = Celery("deid_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
