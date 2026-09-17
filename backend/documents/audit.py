"""
Writes the permanent audit trail (FR-82, NFR-16) once at job finalization —
one AuditRecord row per entity, created in a single bulk_create so the
per-instance immutability guard on AuditRecord.save() (see models.py) never
has to be bypassed to populate it in the first place. Never write the
original plaintext value: value_hash (see Entity.value_hash) is all a
compliance record needs to prove what changed.
"""
from __future__ import annotations

from .models import AuditRecord


def write_audit_records(job, entities):
    """Idempotent: if this job already has audit records (e.g. a retry
    after a transient failure past this point), leaves them untouched
    rather than raising — the immutability guard means a second attempt to
    write them would fail anyway, and the first attempt's records are the
    ones of record."""
    if job.audit_records.exists():
        return list(job.audit_records.all())

    return AuditRecord.objects.bulk_create([
        AuditRecord(
            job=job, entity_code=entity.code, category=entity.category,
            value_hash=entity.value_hash(), action=entity.mode,
            detector=entity.detector, confidence=entity.confidence,
            page=entity.page,
        )
        for entity in entities
    ])
