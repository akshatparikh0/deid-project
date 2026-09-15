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
    "patient_name",
    "physician_name",
    "person_name",
    "guarantor_name",
    "facility_name",
    "employer",
    "date_of_birth",
    "date_of_service",
    "other_date",
    "age_over_89",
    "age_89_or_below",
    "street_address",
    "zip_code",
    "phone",
    "fax",
    "email",
    "url",
    "ssn",
    "mrn",
    "member_id",
    "account",
    "payment_card",
    "ip_address",
    "device_id",
    "license",
    "vehicle",
    "biometric",
    "photo",
    "other",
]

CATEGORY_META = {
    "patient_name": {
        "label": "Patient name",
        "color": "#6A3FA0",
        "token": "[PATIENT_NAME]",
    },
    "physician_name": {
        "label": "Physician / provider name",
        "color": "#9B6FD1",
        "token": "[PHYSICIAN]",
    },
    "person_name": {
        "label": "Other person name",
        "color": "#7C4DBC",
        "token": "[PERSON_NAME]",
    },
    "guarantor_name": {
        "label": "Guarantor / next of kin",
        "color": "#7C4DBC",
        "token": "[GUARANTOR]",
    },
    "facility_name": {
        "label": "Facility / organization",
        "color": "#3A7CA5",
        "token": "[FACILITY]",
    },
    "employer": {
        "label": "Employer",
        "color": "#3A7CA5",
        "token": "[EMPLOYER]",
    },
    "date_of_birth": {
        "label": "Date of birth",
        "color": "#B8792D",
        "token": "[DOB]",
    },
    "date_of_service": {
        "label": "Date of service",
        "color": "#B8792D",
        "token": "[DATE_OF_SERVICE]",
    },
    "other_date": {
        "label": "Other date",
        "color": "#B8792D",
        "token": "[DATE]",
    },
    "age_over_89": {
        "label": "Age above 89",
        "color": "#B8792D",
        "token": "[AGE_90_PLUS]",
    },
    "age_89_or_below": {
        "label": "Age 89 or below",
        "color": "#B8792D",
        "token": "[AGE]",
    },
    "street_address": {
        "label": "Street address",
        "color": "#2D6FB8",
        "token": "[ADDRESS]",
    },
    "zip_code": {
        "label": "ZIP code",
        "color": "#2D6FB8",
        "token": "[ZIP]",
    },
    "phone": {
        "label": "Telephone",
        "color": "#1F8A70",
        "token": "[PHONE]",
    },
    "fax": {
        "label": "Fax",
        "color": "#1F8A70",
        "token": "[FAX]",
    },
    "email": {
        "label": "Email",
        "color": "#1F8A70",
        "token": "[EMAIL]",
    },
    "url": {
        "label": "URL",
        "color": "#2D6FB8",
        "token": "[URL]",
    },
    "ssn": {
        "label": "SSN / government ID",
        "color": "#A4291F",
        "token": "[SSN]",
    },
    "mrn": {
        "label": "Medical record number",
        "color": "#A4291F",
        "token": "[MRN-1]",
    },
    "member_id": {
        "label": "Member ID",
        "color": "#A4291F",
        "token": "[MEMBER_ID]",
    },
    "account": {
        "label": "Account number",
        "color": "#8A5A1B",
        "token": "[ACCOUNT]",
    },
    "payment_card": {
        "label": "Payment card / bank identifier",
        "color": "#A4291F",
        "token": "[PAYMENT_CARD]",
    },
    "ip_address": {
        "label": "IP address",
        "color": "#2D6FB8",
        "token": "[IP]",
    },
    "device_id": {
        "label": "Device identifier",
        "color": "#5B6770",
        "token": "[DEVICE]",
    },
    "license": {
        "label": "Certificate / licence",
        "color": "#8A5A1B",
        "token": "[LICENSE]",
    },
    "vehicle": {
        "label": "Vehicle identifier",
        "color": "#5B6770",
        "token": "[VEHICLE]",
    },
    "biometric": {
        "label": "Biometric identifier",
        "color": "#7C4DBC",
        "token": "[BIOMETRIC]",
    },
    "photo": {
        "label": "Full-face image",
        "color": "#7C4DBC",
        "token": "[PHOTO]",
    },
    "other": {
        "label": "Other identifier",
        "color": "#5B6770",
        "token": "[IDENTIFIER]",
    },
}

CATEGORY_CHOICES = [
    (category, CATEGORY_META[category]["label"])
    for category in CATEGORY_ORDER
]

MODE_CHOICES = [
    ("redact", "Redact"),
    ("mask", "Mask"),
    ("pseudo", "Pseudonymize"),
    ("keep", "Keep"),
]

JOB_STATUS_CHOICES = [
    ("queued", "Queued"),
    ("scanning", "Scanning"),
    ("in_review", "In review"),
    ("finalizing", "Finalizing"),
    ("complete", "Complete"),
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