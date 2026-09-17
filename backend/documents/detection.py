"""
PHI detection engine.

This is a regex + keyword-context detector, not a trained NER model — it is
intentionally dependency-light (no spaCy/presidio model download required)
so the project installs and runs anywhere. It covers the highest-value,
highest-precision Safe Harbor identifiers (SSNs, dates, contact info,
labelled record/account numbers, addresses, credit card numbers) with
pattern-based matches, and falls back to lower-confidence heuristics for
names, facilities, biometrics, photos and the open-ended "other" class.
Swapping in a real NER pipeline later only means replacing `detect_spans()`
— every downstream piece (entities, rules, export, audit) is detector-agnostic.

A "span" is a dict: {start, end, category, confidence, detector}, with
offsets relative to the block of text passed in.

Callers processing a table row call `detect_spans` once per cell, passing
that cell's column header via `column_header` — this lets a bare value with
no inline label (e.g. a name or MRN sitting in its own table column) still
get caught, via `_header_candidate`, which is the one thing that reasons
about column context. Everything else in this module is offset-agnostic
plain-text pattern matching.
"""
import re

_MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)

_STATE_ABBR_LIST = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY"
).split()
_STATE_ABBR = "|".join(_STATE_ABBR_LIST)
_STATE_ABBR_SET = set(_STATE_ABBR_LIST)

_STREET_SUFFIX = (
    r"Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd|Way|Court|Ct|"
    r"Place|Pl|Circle|Cir|Terrace|Ter|Highway|Hwy|Parkway|Pkwy"
)

_NAME_STOPWORDS = {
    "The", "This", "That", "These", "Those", "Please", "Thank", "Health",
    "Medical", "Clinical", "Referral", "Follow", "Continuing", "Study",
    "Patient", "Provider", "Plan", "Account", "Please", "Department",
    "Records", "Report", "Summary", "Attn", "Dear", "Sincerely", "Regards",
    "Credit", "Social", "Date", "Name",
    # Common clinical note section headings — a bare two-capitalized-word
    # heading like "Family History" or "Past Surgical" (from "Past Surgical
    # History") reads as a name to the generic heuristic otherwise.
    "Consult", "Family", "Past", "Surgical", "History", "Physical", "Exam",
    "Review", "Systems", "Assessment", "Objective", "Subjective", "Problem",
    "Active", "Preoperative", "Postoperative", "Progress", "Vital", "Chief",
    "Present", "Illness", "ID",
    # More section/field labels seen in real EHR exports (problem/allergy/
    # medication/social-history sections) that otherwise read as a name.
    "List", "Diagnosis", "Prior", "Outpatient", "Sig", "Dispense", "Refill",
    "Tobacco", "Substance", "Topics", "Allergies", "Allergen", "Reactions",
    "Reaction", "Capillary", "Mental", "Comment", "Laterality", "Procedure",
    "Visit", "Orders", "Reason", "Location", "Facility", "Anesthesia",
}
# Relation words never legitimately appear as (part of) the name that
# follows one — e.g. two OCR'd "Sister" lines in a row must not let the
# second "Sister" be read as the first one's name. Checked case-
# insensitively against the *last* word of a candidate name span, since
# that's where a jumbled table row's next column tends to land (e.g.
# "Arthritis Sister" from a flattened Problem/Relation pair).
_RELATION_WORDS = {
    "mother", "father", "sister", "brother", "grandmother", "grandfather",
    "son", "daughter", "spouse", "aunt", "uncle", "cousin",
}
_COMMA_RIGHT_STOPWORDS = _STATE_ABBR_SET | {
    "MD", "RN", "DO", "NP", "PA", "MSW", "Jr", "Sr", "III", "II", "Inc",
    "LLC", "Ltd", "Esq",
}

_NAME_BODY = r"(?:[A-Z][A-Za-z'\-]*\.?\s*){1,4}(?:,?\s*(?:MD|RN|DO|NP|PA|MSW)\b)?"

_PATIENT_CUES = r"Patient(?:\s+Name)?|Pt\."
_PHYSICIAN_CUES = r"Dr\.|Physician|Provider|Clinician|Attending|Referring|Surgeon|Seen\s+by|Signed(?:\s+by)?"
_GUARANTOR_CUES = r"Guarantor|Responsible\s+Party|Next\s+of\s+Kin|Emergency\s+Contact"
_GENERIC_TITLE_CUES = r"Mr\.|Mrs\.|Ms\."
_RELATION_CUES = (
    r"Maternal\s+Grandmother|Paternal\s+Grandmother|Maternal\s+Grandfather|"
    r"Paternal\s+Grandfather|Mother|Father|Sister|Brother|Grandmother|"
    r"Grandfather|Son|Daughter|Spouse|Aunt|Uncle|Cousin"
)

_PATIENT_CONTEXT = re.compile(_PATIENT_CUES, re.I)
_PHYSICIAN_CONTEXT = re.compile(_PHYSICIAN_CUES, re.I)
_GUARANTOR_CONTEXT = re.compile(_GUARANTOR_CUES, re.I)

_FACILITY_SUFFIX = (
    r"Hospital|Medical\s+Center|Clinic|Health\s+System|Healthcare|Physicians|"
    r"Associates|Urgent\s+Care|Imaging\s+Center|Laboratory|Labs?|Practice"
)
_EMPLOYER_CUES = r"Employer|Employed\s+by"
_DOB_CONTEXT = re.compile(r"(?:dob|date\s+of\s+birth|birth\s*date|born)[\s:#-]*$", re.I)
_DOS_CONTEXT = re.compile(r"(?:dos|date\s+of\s+service|service\s+date|visit\s+date|encounter\s+date|seen\s+on)[\s:#-]*$", re.I)

# (category, pattern, base_confidence, detector_label)
# Priority (see _non_overlapping): higher confidence wins on overlap, then
# longer span, then earliest start — NOT source-list order.
#
# Categories here follow the unified taxonomy in categories.py (shared with
# the project configuration schema) rather than the raw HIPAA Safe Harbor
# identifier list — e.g. dates
# are split into date_of_birth/date_of_service/other_date so the first
# release's per-entity-type policy (FR-23 – FR-40) can keep the date of
# service unchanged while masking every other date.
_PATTERNS = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), 0.99, "pattern"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 0.99, "pattern"),
    ("url", re.compile(r"\bhttps?://[^\s)>\]]+"), 0.97, "pattern"),
    ("ip_address", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"), 0.95, "pattern"),
    ("phone", re.compile(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"), 0.95, "pattern"),
    # Dates default to "other_date"; a DOB/DOS cue immediately before the
    # match reclassifies it in detect_spans (context is variable-length, so
    # it can't be expressed as a fixed-width regex lookbehind).
    ("other_date", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"), 0.96, "pattern"),
    ("other_date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), 0.96, "pattern"),
    ("other_date", re.compile(rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}}\b"), 0.94, "pattern"),
    ("other_date", re.compile(r"\b\d{1,2}/\d{4}\b"), 0.9, "pattern"),  # month/year — bare year alone is Safe-Harbor-permitted and NOT matched here
    ("street_address", re.compile(
        rf"\b\d{{1,6}}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){{0,3}}\s+(?:{_STREET_SUFFIX})\b"
        rf"(?:,?\s*(?:Apt|Suite|Ste|Unit)\.?\s*[A-Za-z0-9-]+)?"
        rf"(?:,\s*[A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)?,?\s*(?:{_STATE_ABBR})\s*\d{{5}}(?:-\d{{4}})?)?",
    ), 0.93, "pattern"),
    ("street_address", re.compile(rf"\b[A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)?,\s*(?:{_STATE_ABBR})\s+\d{{5}}(?:-\d{{4}})?\b"), 0.9, "pattern"),
    ("zip_code", re.compile(r"\b(?:ZIP|Zip\s*Code|Postal\s*Code)\b\s*[:#]?\s*(\d{5}(?:-\d{4})?)\b", re.I), 0.88, "pattern"),
    ("mrn", re.compile(r"\b(?:MRN|Medical\s+Record\s+(?:No\.?|Number|#))\b\s*[:#]?\s*([A-Za-z0-9-]{4,})", re.I), 0.95, "pattern"),
    ("member_id", re.compile(r"\b(?:Member(?:\s+ID)?|Plan|Health\s+Plan)\b\s*(?:ID|No\.?|Number|#)?\s*[:#]?\s*([A-Za-z0-9-]{4,})", re.I), 0.9, "pattern"),
    ("account", re.compile(r"\b(?:Account|Acct)\b\s*(?:No\.?|Number|#)?\s*[:#]?\s*([A-Za-z0-9-]{4,})", re.I), 0.88, "pattern"),
    ("license", re.compile(r"\b(?:Licen[cs]e|Certificate)\b\s*(?:No\.?|Number|#)?\s*[:#]?\s*([A-Za-z0-9-]{4,})", re.I), 0.88, "pattern"),
    ("vehicle", re.compile(r"\b(?:Plate|Vehicle|License\s+Plate)\b\s*(?:No\.?|Number|#)?\s*[:#]?\s*([A-Za-z0-9-]{4,8})", re.I), 0.85, "pattern"),
    ("device_id", re.compile(r"\b(?:Device|Serial|Pump)\b\s*(?:No\.?|Number|S/N|#)?\s*[:#]?\s*([A-Za-z0-9-]{4,})", re.I), 0.85, "pattern"),
    ("employer", re.compile(rf"\b(?:{_EMPLOYER_CUES})\s*[:\-]\s*([A-Z][A-Za-z0-9 &,.'\-]{{2,60}})"), 0.85, "pattern"),
    ("facility_name", re.compile(r"\b(?:Facility|Location|Clinic|Site)\s*[:\-]\s*([A-Z][A-Za-z0-9 &,.'\-]{2,60})"), 0.88, "pattern"),
    ("facility_name", re.compile(
        rf"\b([A-Z][A-Za-z&'\-]+(?:\s+(?:of|the|and)?\s*[A-Z][A-Za-z&'\-]+){{0,4}}\s+(?:{_FACILITY_SUFFIX}))\b"
    ), 0.85, "pattern"),
    ("patient_name", re.compile(rf"(?:{_PATIENT_CUES})\s*[:\-]?\s+({_NAME_BODY})"), 0.9, "pattern"),
    ("physician_name", re.compile(rf"(?:{_PHYSICIAN_CUES})\s*[:\-]?\s+({_NAME_BODY})"), 0.9, "pattern"),
    ("guarantor_name", re.compile(rf"(?:{_GUARANTOR_CUES})\s*[:\-]?\s+({_NAME_BODY})"), 0.9, "pattern"),
    ("person_name", re.compile(rf"(?:{_GENERIC_TITLE_CUES})\s*[:\-]?\s+({_NAME_BODY})"), 0.85, "pattern"),
    ("person_name", re.compile(rf"\b(?:{_RELATION_CUES})\b\s+({_NAME_BODY})"), 0.8, "pattern"),
    ("age_over_89", re.compile(r"(?i)\bage[\s:]+(\d{1,3})\b"), 0.85, "pattern"),
]

_FAX_CONTEXT = re.compile(r"\bfax\b", re.I)

_BIOMETRIC_KEYWORDS = re.compile(
    r"[^.]*\b(?:fingerprint|thumbprint|biometric|retina(?:l)?\s+scan|iris\s+scan|voiceprint|palm\s+print)\b[^.]*\.?",
    re.I,
)
_PHOTO_KEYWORDS = re.compile(
    r"[^.]*\b(?:full-face\s+photo(?:graph)?|photograph(?:\s+attached)?|headshot|patient\s+photo)\b[^.]*\.?",
    re.I,
)
_OTHER_KEYWORDS = re.compile(
    r"\b(?:study\s+arm|enroll?ment|cohort|protocol|reference)\s+(?:code|id|number|no\.?)\s*[:#]?\s*[A-Za-z0-9-]{3,}",
    re.I,
)

_GENERIC_NAME = re.compile(
    # The middle-initial group's trailing period is optional — a middle
    # initial dropped its period entirely ("Nancie J Wintz") in a source
    # document that also runs several unrelated text fragments together
    # into one garbled block; period-less real text this could
    # over-trigger on (e.g. a stray single-letter list marker) is rarer
    # than missing the initial in scanned/reflowed medical records.
    r"\b([A-Z][a-z]+(?:\s[A-Z]\.?)?\s[A-Z][a-z]+(?:\s(?:MD|RN|DO|NP|PA)\b)?)\b"
)
_COMMA_NAME = re.compile(r"\b([A-Z][A-Za-z'\-]+),\s+([A-Z][A-Za-z'\-]+(?:\s[A-Z]\.?)?)\b")

# Credit/debit card numbers, brand-specific, with or without space/dash
# separators. Luhn-validated to keep false positives down against MRNs/
# phone-like digit runs of similar length.
_CC_PATTERNS = [
    re.compile(r"\b4\d{3}(?:[- ]?\d{4}){3}\b"),                 # Visa 16
    re.compile(r"\b5[1-5]\d{2}(?:[- ]?\d{4}){3}\b"),             # Mastercard 16
    re.compile(r"\b3[47]\d{2}[- ]?\d{6}[- ]?\d{5}\b"),           # Amex 15, grouped 4-6-5
    re.compile(r"\b3[47]\d{13}\b"),                              # Amex 15, no separators
    re.compile(r"\b6(?:011|5\d{2})(?:[- ]?\d{4}){3}\b"),         # Discover 16
    re.compile(r"\b30[0-5]\d[- ]\d{6}[- ]\d{4}\b"),              # Diners 14 (300-305), grouped
    re.compile(r"\b3[68]\d{2}[- ]\d{6}[- ]\d{4}\b"),             # Diners 14 (36/38), grouped
    re.compile(r"\b30[0-5]\d{11}\b"),                            # Diners 14 (300-305), no separators
    re.compile(r"\b3[68]\d{12}\b"),                              # Diners 14 (36/38), no separators
]


def _luhn_valid(digits):
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_HEADER_CATEGORY_MAP = [
    (re.compile(r"\bmrn\b|medical\s*record", re.I), "mrn"),
    (re.compile(r"\bdob\b|date\s+of\s+birth|birth\s*date", re.I), "date_of_birth"),
    (re.compile(r"date\s+of\s+service|service\s+date|visit\s+date|encounter\s+date", re.I), "date_of_service"),
    (re.compile(r"\bdate\b", re.I), "other_date"),
    (re.compile(r"guarantor|next\s+of\s+kin|emergency\s+contact|responsible\s+party", re.I), "guarantor_name"),
    (re.compile(r"physician|provider|surgeon|attending", re.I), "physician_name"),
    (re.compile(r"\bpatient\b", re.I), "patient_name"),
    (re.compile(r"employer", re.I), "employer"),
    (re.compile(r"^\s*age\s*$", re.I), "age_over_89"),
    (re.compile(r"\bname\b", re.I), "person_name"),
    (re.compile(r"facility|location|\bsite\b", re.I), "facility_name"),
    (re.compile(r"member\s*id|health\s*plan", re.I), "member_id"),
    (re.compile(r"\baccount\b", re.I), "account"),
    (re.compile(r"phone|telephone", re.I), "phone"),
    (re.compile(r"\bemail\b", re.I), "email"),
    (re.compile(r"\bzip\b|postal\s*code", re.I), "zip_code"),
    (re.compile(r"\baddress\b", re.I), "street_address"),
]
_BARE_YEAR = re.compile(r"^\d{4}$")
_DATE_HEADER_CATEGORIES = {"date_of_birth", "date_of_service", "other_date"}


def _non_overlapping(spans):
    """Resolve overlaps by confidence first (then length, then position) —
    a short, high-confidence, specific match (e.g. an SSN) must never be
    silently dropped in favor of a longer, low-confidence heuristic match
    (e.g. a generic two-capitalized-word name guess) covering the same text."""
    ordered = sorted(spans, key=lambda s: (-s["confidence"], -(s["end"] - s["start"]), s["start"]))
    accepted = []
    for span in ordered:
        if any(span["start"] < a["end"] and span["end"] > a["start"] for a in accepted):
            continue
        accepted.append(span)
    return sorted(accepted, key=lambda s: s["start"])


def merge_spans(*span_lists):
    """Resolve overlaps across spans from multiple detection engines (the
    regex/heuristic engine in this module, plus any enabled AI detectors —
    see ai_detection.py) using the same confidence-first priority as
    detect_spans() itself, so a high-confidence regex match is never
    silently displaced by a lower-confidence AI guess covering the same
    text, and vice versa."""
    candidates = [span for spans in span_lists for span in spans]
    return _non_overlapping(candidates)


def _person_category(text, start, default="person_name", window=40):
    context = text[max(0, start - window):start]
    if _PHYSICIAN_CONTEXT.search(context):
        return "physician_name"
    if _PATIENT_CONTEXT.search(context):
        return "patient_name"
    if _GUARANTOR_CONTEXT.search(context):
        return "guarantor_name"
    return default


def _header_candidate(text, column_header):
    """A bare value with no inline label, judged solely by which table
    column it sits in (e.g. an MRN or name in its own column with no label
    text next to it). Deliberately conservative: skips bare 4-digit years,
    since Safe Harbor permits a year alone to remain."""
    if not column_header:
        return None
    value = text.strip()
    if not value or not any(ch.isalnum() for ch in value):
        return None
    for pattern, category in _HEADER_CATEGORY_MAP:
        if pattern.search(column_header):
            if category in _DATE_HEADER_CATEGORIES and _BARE_YEAR.match(value):
                return None
            if category == "age_over_89":
                # A bare "Age" column is only PHI when the value itself is
                # above the Safe Harbor 89 threshold (FR-36/FR-37) — ages 89
                # and below are explicitly not identifiers and must pass
                # through unflagged.
                if not value.isdigit() or int(value) <= 89:
                    return None
            start = len(text) - len(text.lstrip())
            return {
                "start": start, "end": start + len(value),
                "category": category, "confidence": 0.75, "detector": "context",
            }
    return None


def detect_spans(text, column_header=None):
    """Return a list of non-overlapping spans found in `text`, sorted by
    start offset. `column_header` is the header of the table column this
    text is a cell from, if any — see module docstring."""
    candidates = []

    for category, pattern, confidence, detector in _PATTERNS:
        for m in pattern.finditer(text):
            start, end = m.span(1) if m.groups() else m.span()
            end = start + len(text[start:end].rstrip())  # name-body groups can trail whitespace
            if end <= start:
                continue
            if category in ("patient_name", "physician_name", "guarantor_name", "person_name"):
                # The name-body capture is shape-based ("one to four
                # capitalized words"), so a cue immediately followed by an
                # unrelated label word ("Patient ID:", "Patient Active
                # Problem List") reads the same as a real name — filter it
                # the same way the bare heuristics below do.
                words = text[start:end].split()
                first_word = words[0].rstrip(".,")
                last_word = words[-1].rstrip(".,").lower()
                if first_word in _NAME_STOPWORDS or last_word in _RELATION_WORDS:
                    continue
            cat = category
            conf = confidence
            if category == "phone":
                window = text[max(0, m.start() - 20):m.start()]
                if _FAX_CONTEXT.search(window):
                    cat = "fax"
            elif category == "other_date":
                # Fixed regexes can't express the variable-length "DOB:" /
                # "Date of service:" cue as a lookbehind, so resolve it here
                # against the text immediately preceding the match instead.
                window = text[max(0, m.start() - 30):m.start()]
                if _DOB_CONTEXT.search(window):
                    cat = "date_of_birth"
                elif _DOS_CONTEXT.search(window):
                    cat = "date_of_service"
            elif category == "age_over_89":
                # Safe Harbor only treats ages above 89 as an identifier
                # (FR-36); 89 and below must pass through unflagged.
                if int(text[start:end]) <= 89:
                    continue
            candidates.append({"start": start, "end": end, "category": cat, "confidence": conf, "detector": detector})

    for rx, category, conf in (
        (_BIOMETRIC_KEYWORDS, "biometric", 0.78),
        (_PHOTO_KEYWORDS, "photo", 0.8),
        (_OTHER_KEYWORDS, "other", 0.68),
    ):
        for m in rx.finditer(text):
            grp = 1 if rx.groups else 0
            start, end = m.span(grp)
            snippet = text[start:end].strip()
            if not snippet:
                continue
            trimmed = len(snippet) - len(snippet.lstrip())
            candidates.append({
                "start": start + trimmed, "end": start + len(snippet.rstrip()),
                "category": category, "confidence": conf, "detector": "heuristic",
            })

    for cc_pattern in _CC_PATTERNS:
        for m in cc_pattern.finditer(text):
            digits = re.sub(r"[- ]", "", m.group(0))
            if _luhn_valid(digits):
                candidates.append({
                    "start": m.start(), "end": m.end(),
                    "category": "payment_card", "confidence": 0.95, "detector": "pattern",
                })

    for m in _COMMA_NAME.finditer(text):
        right = m.group(2).rstrip(".")
        if m.group(1) in _NAME_STOPWORDS or right in _COMMA_RIGHT_STOPWORDS:
            continue
        start, end = m.span()
        category = _person_category(text, m.start())
        candidates.append({"start": start, "end": end, "category": category, "confidence": 0.75, "detector": "heuristic"})

    for m in _GENERIC_NAME.finditer(text):
        start, end = m.span(1)
        words = text[start:end].split()
        first_word = words[0].rstrip(".")
        last_word = words[-1].rstrip(".").lower()
        if first_word in _NAME_STOPWORDS or last_word in _RELATION_WORDS:
            continue
        # Skip parenthetical asides like "(Family Medicine)" or "(Right Knee)"
        # — a bare two-capitalized-word phrase in parens next to a name is
        # almost always a specialty/descriptor, not a second name.
        if text[:start].rstrip().endswith("(") and text[end:].lstrip().startswith(")"):
            continue
        category = _person_category(text, start)
        candidates.append({"start": start, "end": end, "category": category, "confidence": 0.62, "detector": "heuristic"})

    header_candidate = _header_candidate(text, column_header)
    if header_candidate:
        candidates.append(header_candidate)

    return _non_overlapping(candidates)
