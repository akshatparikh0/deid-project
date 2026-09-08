"""
PHI detection engine.

This is a regex + keyword-context detector, not a trained NER model — it is
intentionally dependency-light (no spaCy/presidio model download required)
so the project installs and runs anywhere. It covers the highest-value,
highest-precision Safe Harbor identifiers (SSNs, dates, contact info,
labelled record/account numbers, addresses) with pattern-based matches, and
falls back to lower-confidence heuristics for names, biometrics, photos and
the open-ended "other" class. Swapping in a real NER pipeline later only
means replacing `detect_spans()` — every downstream piece (entities, rules,
export, audit) is detector-agnostic.

A "span" is a dict: {start, end, category, confidence, detector}, with
offsets relative to the block of text passed in.
"""
import re

_MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)

_STATE_ABBR = (
    r"AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|"
    r"MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY"
)

_STREET_SUFFIX = (
    r"Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd|Way|Court|Ct|"
    r"Place|Pl|Circle|Cir|Terrace|Ter|Highway|Hwy|Parkway|Pkwy"
)

_NAME_STOPWORDS = {
    "The", "This", "That", "These", "Those", "Please", "Thank", "Health",
    "Medical", "Clinical", "Referral", "Follow", "Continuing", "Study",
    "Patient", "Provider", "Plan", "Account", "Please", "Department",
    "Records", "Report", "Summary", "Attn", "Dear", "Sincerely", "Regards",
}

_TITLE_CUES = r"Dr\.|Mr\.|Mrs\.|Ms\.|Patient|Provider|Physician|Clinician|Attending|Referring|Seen by|Signed"

# (category, pattern, base_confidence, detector_label)
# Order = priority: earlier patterns win when spans overlap.
_PATTERNS = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), 0.99, "pattern"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 0.99, "pattern"),
    ("url", re.compile(r"\bhttps?://[^\s)>\]]+"), 0.97, "pattern"),
    ("ip", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"), 0.95, "pattern"),
    ("phone", re.compile(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"), 0.95, "pattern"),
    ("date", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"), 0.96, "pattern"),
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), 0.96, "pattern"),
    ("date", re.compile(rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}}\b"), 0.94, "pattern"),
    ("geo", re.compile(
        rf"\b\d{{1,6}}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){{0,3}}\s+(?:{_STREET_SUFFIX})\b"
        rf"(?:,?\s*(?:Apt|Suite|Ste|Unit)\.?\s*[A-Za-z0-9-]+)?"
        rf"(?:,\s*[A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)?,?\s*(?:{_STATE_ABBR})\s*\d{{5}}(?:-\d{{4}})?)?",
    ), 0.93, "pattern"),
    ("geo", re.compile(rf"\b[A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)?,\s*(?:{_STATE_ABBR})\s+\d{{5}}(?:-\d{{4}})?\b"), 0.9, "pattern"),
    ("mrn", re.compile(r"\b(?:MRN|Medical\s+Record\s+(?:No\.?|Number|#))\s*[:#]?\s*([A-Za-z0-9-]{4,})", re.I), 0.95, "pattern"),
    ("plan", re.compile(r"\b(?:Plan|Health\s+Plan)\s*(?:ID|No\.?|Number|#)?\s*[:#]?\s*([A-Za-z0-9-]{4,})", re.I), 0.9, "pattern"),
    ("account", re.compile(r"\b(?:Account|Acct)\s*(?:No\.?|Number|#)?\s*[:#]?\s*([A-Za-z0-9-]{4,})", re.I), 0.88, "pattern"),
    ("license", re.compile(r"\b(?:Licen[cs]e|Certificate)\s*(?:No\.?|Number|#)?\s*[:#]?\s*([A-Za-z0-9-]{4,})", re.I), 0.88, "pattern"),
    ("vehicle", re.compile(r"\b(?:Plate|Vehicle|License\s+Plate)\s*(?:No\.?|Number|#)?\s*[:#]?\s*([A-Za-z0-9-]{4,8})", re.I), 0.85, "pattern"),
    ("device", re.compile(r"\b(?:Device|Serial|Pump)\s*(?:No\.?|Number|S/N|#)?\s*[:#]?\s*([A-Za-z0-9-]{4,})", re.I), 0.85, "pattern"),
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

_TITLE_NAME = re.compile(
    rf"(?:{_TITLE_CUES})\s*[:\-]?\s+((?:[A-Z][A-Za-z'\-]*\.?\s*){{1,4}}"
    r"(?:,?\s*(?:MD|RN|DO|NP|PA|MSW)\b)?)"
)
_GENERIC_NAME = re.compile(
    r"\b([A-Z][a-z]+(?:\s[A-Z]\.)?\s[A-Z][a-z]+(?:\s(?:MD|RN|DO|NP|PA)\b)?)\b"
)


def _non_overlapping(spans):
    spans = sorted(spans, key=lambda s: (s["start"], -(s["end"] - s["start"])))
    accepted = []
    occupied = []
    for span in spans:
        if any(span["start"] < e and span["end"] > s for s, e in occupied):
            continue
        accepted.append(span)
        occupied.append((span["start"], span["end"]))
    return sorted(accepted, key=lambda s: s["start"])


def detect_spans(text):
    """Return a list of non-overlapping spans found in `text`, sorted by start offset."""
    candidates = []

    for category, pattern, confidence, detector in _PATTERNS:
        for m in pattern.finditer(text):
            start, end = m.span(1) if m.groups() else m.span()
            cat = category
            conf = confidence
            if category == "phone":
                window = text[max(0, m.start() - 20):m.start()]
                if _FAX_CONTEXT.search(window):
                    cat = "fax"
            candidates.append({"start": start, "end": end, "category": cat, "confidence": conf, "detector": detector})

    for rx, category, conf in (
        (_TITLE_NAME, "name", 0.92),
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
                "category": category, "confidence": conf, "detector": "heuristic" if category != "name" else "pattern",
            })

    for m in _GENERIC_NAME.finditer(text):
        start, end = m.span(1)
        first_word = text[start:end].split()[0].rstrip(".")
        if first_word in _NAME_STOPWORDS:
            continue
        candidates.append({"start": start, "end": end, "category": "name", "confidence": 0.62, "detector": "heuristic"})

    return _non_overlapping(candidates)
