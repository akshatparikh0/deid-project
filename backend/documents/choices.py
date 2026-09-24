"""
Django-facing choices that only make sense inside this app's models/API —
job/stage lifecycle states and block/source labels. The entity taxonomy
itself (CATEGORY_ORDER, CATEGORY_META, MODE_CHOICES) lives in
pipeline.categories; CATEGORY_CHOICES here is just that taxonomy reshaped
into the (value, label) tuples a Django model field's `choices=` expects.
"""
from pipeline.categories import CATEGORY_META, CATEGORY_ORDER

CATEGORY_CHOICES = [
    (category, CATEGORY_META[category]["label"])
    for category in CATEGORY_ORDER
]

JOB_STATUS_CHOICES = [
    ("queued", "Queued"),
    ("scanning", "Scanning"),
    ("in_review", "In review"),
    ("finalizing", "Finalizing"),
    ("complete", "Complete"),
    ("failed", "Failed"),
]

# The pipeline stages a job passes through while status="scanning", in the
# order they run. Each name corresponds to a real, distinct unit of work in
# ingest.py — not a cosmetic label — so a stage's start/finish timestamps
# reflect actual processing time the Status page can show the user.
STAGE_ORDER = ["ingest", "parse", "detect", "transform", "finalize"]

STAGE_CHOICES = [
    ("ingest", "Ingest"),
    ("parse", "Parse"),
    ("detect", "Detect"),
    ("transform", "Transform"),
    ("finalize", "Finalize"),
]

STAGE_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("running", "Running"),
    ("done", "Done"),
    ("failed", "Failed"),
]

BLOCK_TYPE_CHOICES = [
    ("title", "Title"),
    ("sub", "Subtitle"),
    ("h", "Heading"),
    ("p", "Paragraph"),
    ("table_row", "Table row"),
]

BLOCK_SOURCE_CHOICES = [
    ("text", "Text layer"),
    ("tesseract", "Tesseract OCR"),
    ("azure_ocr", "Azure Document Intelligence"),
]
