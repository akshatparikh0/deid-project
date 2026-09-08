"""
The 18 HIPAA Safe Harbor identifier classes (45 CFR §164.514(b)(2)(i)) this
tool detects and transforms. Order here is the canonical display order used
by the /rules/ endpoint and mirrored by the frontend.
"""

CATEGORY_ORDER = [
    "name", "geo", "date", "phone", "fax", "email", "ssn", "mrn", "plan",
    "account", "license", "vehicle", "device", "url", "ip", "biometric",
    "photo", "other",
]

CATEGORY_META = {
    "name":      {"label": "Name",                   "color": "#7C4DBC", "token": "[NAME]"},
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

BLOCK_TYPE_CHOICES = [
    ("title", "Title"),
    ("sub", "Subtitle"),
    ("h", "Heading"),
    ("p", "Paragraph"),
]
