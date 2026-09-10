"""
One-off generator for the synthetic clinical-note fixtures used by the
detection/extraction/ingest tests. Not a test itself (doesn't match
Django's `test*.py` discovery) — run manually to regenerate the fixture PDFs
if the fixture content below changes:

    python manage.py shell -c "from documents.tests.make_fixtures import build_all; build_all()"

Produces:
- fixtures/consult_note.pdf        — real text layer (tests table-aware
                                      extraction + name/facility/mrn/date
                                      detection end to end)
- fixtures/consult_note_scanned.pdf — same content, rasterized with no text
                                      layer (tests the Tesseract OCR fallback)
- fixtures/consult_note_expected.json — ground truth entity list for
                                      fixtures/consult_note.pdf
"""
import io
import json
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

PATIENT_NAME = "Eleanor Whitcombe"
PHYSICIAN_NAME = "Michael Ostrander, MD"
FACILITY_NAME = "Cedar Grove Medical Center"
MRN = "4471002"
CONSULT_DATE = "09/02/2026"
DOB = "03/14/1953"

FAMILY_ROWS = [
    ("Problem", "Relation", "Name", "Age of Onset"),
    ("Hypertension", "Mother", "Dorothy Whitcombe", ""),
    ("Type 2 diabetes", "Father", "Harold Whitcombe", "52"),
    ("Arthritis", "Sister", "Margaret Ellery", "40"),
    ("Asthma", "Brother", "Daniel Ellery", "15"),
]

SURGICAL_ROWS = [
    ("Procedure", "Laterality", "Date"),
    ("Carpal tunnel release", "Right", ""),
    ("Eye surgery", "", "7/2023"),
    ("Gastric bypass", "", "2014"),
]


def _build_flowables():
    styles = getSampleStyleSheet()
    flow = []
    flow.append(Paragraph(f"Consult Note — {CONSULT_DATE}", styles["Title"]))
    flow.append(Spacer(1, 10))
    flow.append(Paragraph(f"MRN: {MRN}   DOB: {DOB}", styles["Normal"]))
    flow.append(Paragraph(f"Patient: {PATIENT_NAME}", styles["Normal"]))
    flow.append(Paragraph(f"Provider: {PHYSICIAN_NAME} (Family Medicine)", styles["Normal"]))
    flow.append(Paragraph(f"Facility: {FACILITY_NAME}", styles["Normal"]))
    flow.append(Spacer(1, 14))

    flow.append(Paragraph("Family History", styles["Heading2"]))
    table = Table(FAMILY_ROWS, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
    ]))
    flow.append(table)
    flow.append(Spacer(1, 14))

    flow.append(Paragraph("Past Surgical History", styles["Heading2"]))
    table2 = Table(SURGICAL_ROWS, hAlign="LEFT")
    table2.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
    ]))
    flow.append(table2)
    return flow


def build_text_pdf():
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, topMargin=0.9 * inch, bottomMargin=0.9 * inch)
    doc.build(_build_flowables())
    return buf.getvalue()


def build_scanned_pdf(text_pdf_bytes):
    """Rasterize every page of `text_pdf_bytes` and rebuild a PDF with only
    the page images (no text layer), to exercise the OCR fallback path."""
    import pdfplumber
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    with pdfplumber.open(io.BytesIO(text_pdf_bytes)) as pdf:
        for page in pdf.pages:
            pil_image = page.to_image(resolution=150).original
            c.drawImage(ImageReader(pil_image), 0, 0, width=LETTER[0], height=LETTER[1])
            c.showPage()
    c.save()
    return buf.getvalue()


def build_expected():
    return {
        "patient_name": [PATIENT_NAME],
        "physician_name": [PHYSICIAN_NAME],
        "facility": [FACILITY_NAME],
        "mrn": [MRN],
        "date": [CONSULT_DATE, DOB, "7/2023"],
        "name": ["Dorothy Whitcombe", "Harold Whitcombe", "Margaret Ellery", "Daniel Ellery"],
    }


def build_all():
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    text_pdf = build_text_pdf()
    with open(os.path.join(FIXTURES_DIR, "consult_note.pdf"), "wb") as f:
        f.write(text_pdf)

    scanned_pdf = build_scanned_pdf(text_pdf)
    with open(os.path.join(FIXTURES_DIR, "consult_note_scanned.pdf"), "wb") as f:
        f.write(scanned_pdf)

    with open(os.path.join(FIXTURES_DIR, "consult_note_expected.json"), "w") as f:
        json.dump(build_expected(), f, indent=2)


if __name__ == "__main__":
    build_all()
