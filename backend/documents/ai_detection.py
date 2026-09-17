"""
Optional AI-assisted PHI/PII detectors: Azure AI Language (FR-61, the
managed NER service the requirements name for the model part of detection)
and a Claude context detector for recall on free-text names/facilities that
the regex engine in detection.py misses. Both are opt-in via Django settings
(REDACTION_ENABLE_AZURE_LANGUAGE / REDACTION_ENABLE_AI) and off by default —
the rule engine alone is a complete, dependency-light detector.

Each detector runs over one block/cell of text at a time (matching
detect_spans()'s contract) and returns spans in the exact same shape
{start, end, category, confidence, detector}, so ingest.py can merge all
engines' output through detection.merge_spans() with no engine-specific
handling downstream. Category strings are the unified taxonomy from
categories.py (CATEGORY_META) — the same one the regex engine emits.
"""
from __future__ import annotations

import json
import os
import re

from .categories import CATEGORY_META
from .detection import _person_category

# Detected text that's an exact match for one of our own masking
# placeholders (e.g. an AI detector re-"finding" a literal "[PATIENT_NAME]"
# token left over from a prior pass) must never be treated as a fresh
# finding — see verify.py, which reuses this set for the same reason.
PLACEHOLDER_TOKENS = {meta["token"].strip("[]") for meta in CATEGORY_META.values()}


class DetectorConfigError(RuntimeError):
    """Raised when an AI detector is enabled but missing required config."""


_AZURE_CATEGORY_MAP = {
    "PhoneNumber": "phone",
    "Email": "email",
    "URL": "url",
    "Address": "street_address",
    "USSocialSecurityNumber": "ssn",
    "CreditCardNumber": "payment_card",
    "IPAddress": "ip_address",
    "Person": "person_name",
    "Organization": "facility_name",
}


class AzureLanguageDetector:
    """Azure AI Language PII entity recognition over one block of text.
    Azure's PII model only returns a generic "Person" category, so a person
    match is re-tagged patient/physician/guarantor/person by the same
    nearby-cue heuristic the regex engine uses (detection._person_category),
    keeping the two engines' name-role assignment consistent."""

    engine_name = "azure_ai_language"

    def __init__(self, endpoint: str, credential):
        try:
            from azure.ai.textanalytics import TextAnalyticsClient
        except ImportError as exc:
            raise RuntimeError("Install Azure support with: pip install -r requirements.txt") from exc
        self.client = TextAnalyticsClient(endpoint=endpoint, credential=credential)

    def detect(self, text: str) -> list[dict]:
        if not text.strip():
            return []
        result = self.client.recognize_pii_entities([text])[0]
        if result.is_error:
            raise RuntimeError(f"Azure Language failed: {result.message}")
        spans = []
        for entity in result.entities:
            category = _AZURE_CATEGORY_MAP.get(entity.category)
            if not category:
                continue
            start, end = int(entity.offset), int(entity.offset + entity.length)
            value = text[start:end]
            if value.strip("[]") in PLACEHOLDER_TOKENS:
                continue
            if category == "person_name":
                category = _person_category(text, start)
            spans.append({
                "start": start, "end": end, "category": category,
                "confidence": float(entity.confidence_score), "detector": self.engine_name,
            })
        return spans


def parse_claude_items(raw: str) -> list[dict]:
    """Extract JSON arrays from a Claude response even if it adds Markdown
    fences, prose, or self-corrections around them."""
    decoder = json.JSONDecoder()
    items: list[dict] = []
    found_array = False

    # Prefer fenced blocks when Claude uses Markdown.
    fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL)
    candidates = fenced_blocks or [raw]

    for candidate in candidates:
        position = 0
        while position < len(candidate):
            array_start = candidate.find("[", position)
            if array_start == -1:
                break
            try:
                value, consumed = decoder.raw_decode(candidate[array_start:])
            except json.JSONDecodeError:
                position = array_start + 1
                continue
            position = array_start + consumed
            if isinstance(value, list):
                found_array = True
                items.extend(item for item in value if isinstance(item, dict))

    if not found_array:
        # Do not include raw in the exception because it may contain PHI.
        raise RuntimeError("Claude response did not contain a valid JSON array")

    return items


_CLAUDE_ALLOWED_CATEGORIES = {
    "patient_name", "physician_name", "person_name", "guarantor_name",
    "facility_name", "employer", "street_address", "date_of_birth",
}

_CLAUDE_PROMPT_TEMPLATE = (
    "Find every occurrence of personally identifying information in this "
    "authorized medical document excerpt. Prioritize recall over precision. "
    "Include patient names, physicians, surgeons, nurses, relatives and "
    "family-history names, guarantors, next-of-kin, emergency contacts, "
    "employees named in 'Printed by' or similar fields, facilities, "
    "employers, and street addresses. Find repeated occurrences, including "
    "standalone surnames.\n\n"
    "Do not return medical conditions, medications, procedures, or ordinary "
    "ages. Never return masking placeholders or placeholder fragments, "
    "including PATIENT_NAME, PHYSICIAN, PERSON_NAME, FACILITY, EMPLOYER, "
    "GUARANTOR, ADDRESS, DOB, DATE, MRN, MEMBER_ID, or AGE_90_PLUS.\n\n"
    "Return a JSON array only. Each object must have exactly these keys: "
    "entity_type, text, confidence. Copy text exactly from the excerpt "
    "below. Do not infer or correct OCR text.\n\n"
    "Allowed entity_type values: patient_name, physician_name, person_name, "
    "guarantor_name, facility_name, employer, street_address, "
    "date_of_birth.\n\n"
    "TEXT:\n{text}"
)


class ClaudeDetector:
    """Context detector via Anthropic Claude, for names/facilities/addresses
    the regex engine's fixed patterns miss (e.g. unusual name formats).
    Exact quoted values are mapped back to block-relative offsets."""

    engine_name = "anthropic"

    def __init__(self, api_key: str, model: str):
        if not model:
            raise DetectorConfigError("ANTHROPIC_MODEL must be set when AI detection is enabled")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("Install AI support with: pip install -r requirements.txt") from exc

        workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
        client_options = {"api_key": api_key}
        if workspace_id:
            client_options["default_headers"] = {"anthropic-workspace-id": workspace_id}
        self.client = Anthropic(**client_options)
        self.model = model

    def detect(self, text: str) -> list[dict]:
        if not text.strip():
            return []
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            messages=[{"role": "user", "content": _CLAUDE_PROMPT_TEMPLATE.format(text=text)}],
        )
        raw = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        spans = []
        for item in parse_claude_items(raw):
            value = str(item.get("text", ""))
            category = str(item.get("entity_type", ""))
            if category not in _CLAUDE_ALLOWED_CATEGORIES:
                continue
            if len(value.strip()) < 2 or not re.search(r"[A-Za-z]", value):
                continue
            normalized = re.sub(r"[^A-Z0-9_-]", "", value.upper())
            if normalized in PLACEHOLDER_TOKENS:
                continue
            try:
                confidence = float(item.get("confidence", 0.85))
            except (TypeError, ValueError):
                confidence = 0.85
            for match in re.finditer(re.escape(value), text):
                spans.append({
                    "start": match.start(), "end": match.end(), "category": category,
                    "confidence": confidence, "detector": self.engine_name,
                })
        return spans


def build_detectors(settings) -> list:
    """Construct the enabled AI detectors from Django settings. Returns an
    empty list (the default) when nothing is enabled — callers should treat
    the rule engine in detection.py as sufficient on its own."""
    detectors = []

    if getattr(settings, "REDACTION_ENABLE_AZURE_LANGUAGE", False):
        endpoint = os.environ.get("AZURE_LANGUAGE_ENDPOINT", "")
        key = os.environ.get("AZURE_LANGUAGE_KEY", "")
        if not endpoint:
            raise DetectorConfigError("AZURE_LANGUAGE_ENDPOINT is required when REDACTION_ENABLE_AZURE_LANGUAGE=True")
        if key:
            from azure.core.credentials import AzureKeyCredential
            credential = AzureKeyCredential(key)
        else:
            # No static key configured — fall back to a managed identity
            # (FR-62: every inter-service call must use a user-assigned
            # managed identity, not a static key, in the Azure deployment).
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
        detectors.append(AzureLanguageDetector(endpoint, credential))

    if getattr(settings, "REDACTION_ENABLE_AI", False):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise DetectorConfigError("ANTHROPIC_API_KEY is required when REDACTION_ENABLE_AI=True")
        detectors.append(ClaudeDetector(api_key, os.environ.get("ANTHROPIC_MODEL", "")))

    return detectors
