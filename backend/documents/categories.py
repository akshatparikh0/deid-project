"""
The category classes this tool detects and transforms. Most map 1:1 onto the
18 HIPAA Safe Harbor identifier classes (45 CFR §164.514(b)(2)(i)); "name" is
split into patient_name/physician_name/name (other person) for reviewer
clarity even though Safe Harbor's "Names" identifier covers all three the
same way, and "facility" (organization/institution name) is tracked
alongside "geo" since it's routinely treated as identifying alongside
geographic subdivisions even though it isn't its own numbered identifier.
Order here is the canonical display order used by the /rules/ endpoint and
mirrored by the frontend.
"""

CATEGORY_ORDER = [
    "patient_name", "physician_name", "name", "facility", "geo", "date",
    "phone", "fax", "email", "ssn", "mrn", "plan", "account", "license",
    "vehicle", "device", "url", "ip", "biometric", "photo", "other",
]

CATEGORY_META = {
    "patient_name":   {"label": "Patient name",          "color": "#6A3FA0", "token": "[PATIENT_NAME]"},
    "physician_name": {"label": "Physician / provider name", "color": "#9B6FD1", "token": "[PHYSICIAN]"},
    "name":      {"label": "Other person name",      "color": "#7C4DBC", "token": "[NAME]"},
    "facility":  {"label": "Facility / organization", "color": "#3A7CA5", "token": "[FACILITY]"},
    "geo":       {"label": "Geographic",              "color": "#2D6FB8", "token": "[LOCATION]"},
    "date":      {"label": "Date",                    "color": "#B8792D", "token": "[DATE]"},
    "phone":     {"label": "Telephone",                "color": "#1F8A70", "token": "[PHONE]"},
    "fax":       {"label": "Fax",                      "color": "#1F8A70", "token": "[FAX]"},
    "email":     {"label": "Email",                    "color": "#1F8A70", "token": "[EMAIL]"},
    "ssn":       {"label": "SSN",                      "color": "#A4291F", "token": "[SSN]"},
    "mrn":       {"label": "Medical record no.",       "color": "#A4291F", "token": "[MRN]"},
    "plan":      {"label": "Health plan no.",          "color": "#A4291F", "token": "[PLAN_ID]"},
    "account":   {"label": "Account no.",              "color": "#8A5A1B", "token": "[ACCOUNT]"},
    "license":   {"label": "Certificate / licence",    "color": "#8A5A1B", "token": "[LICENSE]"},
    "vehicle":   {"label": "Vehicle identifier",       "color": "#5B6770", "token": "[VEHICLE]"},
    "device":    {"label": "Device identifier",        "color": "#5B6770", "token": "[DEVICE]"},
    "url":       {"label": "URL",                      "color": "#2D6FB8", "token": "[URL]"},
    "ip":        {"label": "IP address",               "color": "#2D6FB8", "token": "[IP]"},
    "biometric": {"label": "Biometric",                "color": "#7C4DBC", "token": "[BIOMETRIC]"},
    "photo":     {"label": "Full-face image",          "color": "#7C4DBC", "token": "[PHOTO]"},
    "other":     {"label": "Other identifier",         "color": "#5B6770", "token": "[IDENTIFIER]"},
}

CATEGORY_CHOICES = [(k, CATEGORY_META[k]["label"]) for k in CATEGORY_ORDER]

MODE_CHOICES = [
    ("redact", "Redact"),
    ("mask", "Mask"),
    ("pseudo", "Pseudonymize"),
    ("keep", "Keep"),
]

JOB_STATUS_CHOICES = [
    ("scanning", "Scanning"),
    ("in_review", "In review"),
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
    ("ocr", "OCR"),
]
