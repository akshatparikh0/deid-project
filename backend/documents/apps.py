from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _configure_sqlite(sender, connection, **kwargs):
    """Background worker threads now write to SQLite concurrently with the
    request thread (see documents/tasks.py) — WAL mode lets readers and a
    writer proceed together instead of blocking, and the busy timeout
    (DATABASES.OPTIONS.timeout in settings.py) makes a writer wait instead of
    raising 'database is locked' under brief contention."""
    if connection.vendor == "sqlite":
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")


class DocumentsConfig(AppConfig):
    name = 'documents'

    def ready(self):
        connection_created.connect(_configure_sqlite)
