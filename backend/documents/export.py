"""
Generates the three downloadable export artifacts for a completed (or
in-progress) job:

- pdf:  a reconstructed de-identified document. It is *rebuilt* from the
        extracted text blocks rather than edited in place over the original
        PDF bytes — precise pixel-level redaction of an arbitrary source PDF
        (matching original fonts/coordinates) is its own large project;
        rebuilding from the same block/entity model that drives the review
        screen guarantees the export always matches exactly what the
        reviewer approved.
- csv:  the audit trail (hash of the original value, never the value itself).
- json: an entity manifest for programmatic consumers, also hash-only.
"""
import csv
import io
import json

from django.core.files.base import ContentFile
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .models import ExportArtifact

_XML_ESCAPE = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def _escape(text):
    for char, replacement in _XML_ESCAPE.items():
        text = text.replace(char, replacement)
    return text


def _rendered_part_xml(part, entities_by_code):
    if "text" in part:
        return _escape(part["text"])
    entity = entities_by_code[part["entity"]]
    mode = entity.mode
    if mode == "redact":
        blocks = "█" * max(3, min(len(entity.value), 24))
        return f'<font face="Courier">{blocks}</font>'
    if mode == "mask":
        return f'<font face="Courier" color="#0C5344">{_escape(entity.token)}</font>'
    if mode == "pseudo":
        return f'<i color="#20558A">{_escape(entity.surrogate_value or entity.value)}</i>'
    return _escape(entity.value)  # keep


def generate_pdf(job, blocks, entities):
    entities_by_code = {e.code: e for e in entities}
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("PHITitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=16)
    sub_style = ParagraphStyle("PHISub", parent=styles["Normal"], alignment=TA_CENTER, textColor="#6E7278")
    heading_style = ParagraphStyle("PHIHeading", parent=styles["Heading2"], spaceBefore=10)
    body_style = ParagraphStyle("PHIBody", parent=styles["BodyText"], leading=16)

    style_for_type = {"title": title_style, "sub": sub_style, "h": heading_style, "p": body_style}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, topMargin=0.9 * inch, bottomMargin=0.9 * inch)
    flowables = []
    for block in blocks:
        xml = "".join(_rendered_part_xml(part, entities_by_code) for part in block["parts"])
        flowables.append(Paragraph(xml or "&nbsp;", style_for_type.get(block["type"], body_style)))
        flowables.append(Spacer(1, 6))
    doc.build(flowables)
    return buf.getvalue()


def generate_csv(job, entities):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["entity", "category", "value_hash", "action", "detector", "confidence", "page"])
    for entity in entities:
        writer.writerow([
            entity.code, entity.category, entity.value_hash(), entity.mode,
            entity.detector, f"{entity.confidence:.2f}", entity.page,
        ])
    return buf.getvalue().encode("utf-8")


def generate_json(job, entities):
    manifest = {
        "job": job.code,
        "filename": job.filename,
        "generated_at": job.updated_at.isoformat(),
        "entities": [
            {
                "code": e.code,
                "category": e.category,
                "action": e.mode,
                "detector": e.detector,
                "confidence": round(e.confidence, 2),
                "page": e.page,
                "value_hash": e.value_hash(),
                "applied_value": e.token if e.mode == "mask" else (
                    e.surrogate_value if e.mode == "pseudo" else ("[REDACTED]" if e.mode == "redact" else None)
                ),
            }
            for e in entities
        ],
    }
    return json.dumps(manifest, indent=2).encode("utf-8")


_CONTENT_TYPES = {"pdf": "application/pdf", "csv": "text/csv", "json": "application/json"}
_GENERATORS = {"pdf": generate_pdf, "csv": generate_csv, "json": generate_json}


def build_export(job, fmt, blocks, entities):
    """Generate (or regenerate) the artifact for `fmt` and persist it,
    returning the ExportArtifact row."""
    generator = _GENERATORS[fmt]
    content = generator(job, blocks, entities) if fmt == "pdf" else generator(job, entities)
    filename = f"{job.code}_{'deid' if fmt == 'pdf' else ('audit' if fmt == 'csv' else 'entities')}.{fmt}"

    artifact, _ = ExportArtifact.objects.update_or_create(
        job=job, format=fmt, defaults={"filename": filename},
    )
    artifact.file.save(filename, ContentFile(content), save=True)
    return artifact


def content_type_for(fmt):
    return _CONTENT_TYPES.get(fmt, "application/octet-stream")
