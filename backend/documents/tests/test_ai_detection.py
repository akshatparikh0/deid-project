"""
Unit tests for the optional AI-assisted detectors (ai_detection.py). Both
API clients are mocked — nothing here makes a network call — covering
category mapping onto the unified taxonomy, block-relative offset mapping,
and placeholder-token filtering (so a detector never re-flags its own
[PATIENT_NAME]-style output as a fresh finding).
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from documents.ai_detection import (
    AzureLanguageDetector,
    ClaudeDetector,
    DetectorConfigError,
    build_detectors,
    parse_claude_items,
)


class ParseClaudeItemsTests(SimpleTestCase):
    def test_plain_json_array(self):
        items = parse_claude_items('[{"entity_type": "patient_name", "text": "Jane Doe"}]')
        self.assertEqual(items, [{"entity_type": "patient_name", "text": "Jane Doe"}])

    def test_fenced_json_block(self):
        raw = 'Here is the result:\n```json\n[{"entity_type": "person_name", "text": "A"}]\n```\nDone.'
        items = parse_claude_items(raw)
        self.assertEqual(items, [{"entity_type": "person_name", "text": "A"}])

    def test_prose_around_array_with_no_fence(self):
        raw = 'Sure, here you go: [{"entity_type": "employer", "text": "Acme"}] — hope that helps.'
        items = parse_claude_items(raw)
        self.assertEqual(items, [{"entity_type": "employer", "text": "Acme"}])

    def test_no_array_raises(self):
        with self.assertRaises(RuntimeError):
            parse_claude_items("I could not find any identifiers.")


class AzureLanguageDetectorTests(SimpleTestCase):
    def _detector(self, entities):
        detector = object.__new__(AzureLanguageDetector)
        result = SimpleNamespace(is_error=False, entities=entities)
        detector.client = SimpleNamespace(recognize_pii_entities=lambda docs: [result])
        return detector

    def test_person_is_retagged_by_nearby_cue(self):
        text = "Patient: Maria Vasquez presented today."
        entity = SimpleNamespace(category="Person", offset=9, length=13, confidence_score=0.94)
        spans = self._detector([entity]).detect(text)
        self.assertEqual(spans, [{
            "start": 9, "end": 22, "category": "patient_name",
            "confidence": 0.94, "detector": "azure_ai_language",
        }])

    def test_known_category_mapping(self):
        text = "Call (415) 555-0138 for records."
        entity = SimpleNamespace(category="PhoneNumber", offset=5, length=15, confidence_score=0.9)
        spans = self._detector([entity]).detect(text)
        self.assertEqual(spans[0]["category"], "phone")

    def test_unmapped_category_is_dropped(self):
        text = "Reference code 12345"
        entity = SimpleNamespace(category="Quantity", offset=15, length=5, confidence_score=0.8)
        self.assertEqual(self._detector([entity]).detect(text), [])

    def test_placeholder_text_is_never_reflagged(self):
        text = "Patient: [PATIENT_NAME] presented today."
        entity = SimpleNamespace(category="Person", offset=9, length=14, confidence_score=0.9)
        self.assertEqual(self._detector([entity]).detect(text), [])

    def test_azure_error_response_raises(self):
        detector = object.__new__(AzureLanguageDetector)
        result = SimpleNamespace(is_error=True, message="quota exceeded")
        detector.client = SimpleNamespace(recognize_pii_entities=lambda docs: [result])
        with self.assertRaises(RuntimeError):
            detector.detect("some text")

    def test_empty_text_short_circuits_without_a_call(self):
        calls = []
        detector = object.__new__(AzureLanguageDetector)
        detector.client = SimpleNamespace(recognize_pii_entities=lambda docs: calls.append(docs) or [])
        self.assertEqual(detector.detect("   "), [])
        self.assertEqual(calls, [])


class ClaudeDetectorTests(SimpleTestCase):
    def _detector(self, response_text):
        detector = object.__new__(ClaudeDetector)
        detector.model = "test-model"
        response = SimpleNamespace(content=[SimpleNamespace(type="text", text=response_text)])
        detector.client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: response))
        return detector

    def test_exact_text_is_mapped_to_block_offsets(self):
        text = "Guarantor: Robert Vasquez is listed as next of kin."
        raw = '[{"entity_type": "guarantor_name", "text": "Robert Vasquez", "confidence": 0.92}]'
        spans = self._detector(raw).detect(text)
        self.assertEqual(spans, [{
            "start": 11, "end": 25, "category": "guarantor_name",
            "confidence": 0.92, "detector": "anthropic",
        }])

    def test_disallowed_category_is_dropped(self):
        text = "Diagnosis: hypertension"
        raw = '[{"entity_type": "diagnosis", "text": "hypertension", "confidence": 0.9}]'
        self.assertEqual(self._detector(raw).detect(text), [])

    def test_placeholder_fragment_is_dropped(self):
        text = "The value [FACILITY] appears here."
        raw = '[{"entity_type": "facility_name", "text": "[FACILITY]", "confidence": 0.8}]'
        self.assertEqual(self._detector(raw).detect(text), [])

    def test_repeated_value_produces_a_span_for_each_occurrence(self):
        text = "Jane Doe called. Later, Jane Doe called again."
        raw = '[{"entity_type": "person_name", "text": "Jane Doe", "confidence": 0.88}]'
        spans = self._detector(raw).detect(text)
        self.assertEqual(len(spans), 2)
        self.assertEqual([text[s["start"]:s["end"]] for s in spans], ["Jane Doe", "Jane Doe"])


class BuildDetectorsTests(SimpleTestCase):
    def test_nothing_enabled_returns_empty_list(self):
        settings = SimpleNamespace(REDACTION_ENABLE_AZURE_LANGUAGE=False, REDACTION_ENABLE_AI=False)
        self.assertEqual(build_detectors(settings), [])

    def test_azure_enabled_without_endpoint_raises(self):
        settings = SimpleNamespace(REDACTION_ENABLE_AZURE_LANGUAGE=True, REDACTION_ENABLE_AI=False)
        with self.assertRaises(DetectorConfigError):
            build_detectors(settings)

    def test_claude_enabled_without_api_key_raises(self):
        settings = SimpleNamespace(REDACTION_ENABLE_AZURE_LANGUAGE=False, REDACTION_ENABLE_AI=True)
        with self.assertRaises(DetectorConfigError):
            build_detectors(settings)
