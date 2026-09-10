from django.test import SimpleTestCase

from documents.detection import detect_spans


def _categories(text, column_header=None):
    spans = detect_spans(text, column_header=column_header)
    return [(text[s["start"]:s["end"]], s["category"], s["detector"]) for s in spans]


class SsnAndCreditCardTests(SimpleTestCase):
    def test_ssn_detected(self):
        spans = _categories("SSN on file: 489-36-8350")
        self.assertIn(("489-36-8350", "ssn", "pattern"), spans)

    def test_visa_and_mastercard_detected_as_other(self):
        self.assertIn(("4929-3813-3266-4295", "other", "pattern"), _categories("4929-3813-3266-4295"))
        self.assertIn(("5370-4638-8881-3020", "other", "pattern"), _categories("5370-4638-8881-3020"))

    def test_amex_and_diners_no_separator_detected(self):
        # From the DLP test fixture — 15-digit Amex and 14-digit Diners, no separators.
        self.assertIn(("345389698201044", "other", "pattern"), _categories("345389698201044"))
        self.assertIn(("30204861594838", "other", "pattern"), _categories("30204861594838"))

    def test_luhn_invalid_number_rejected(self):
        # Same shape as a Visa card but fails the Luhn checksum.
        bad = "4929-3813-3266-4291"
        self.assertNotIn("other", [cat for _, cat, _ in _categories(bad)])


class NameSplitTests(SimpleTestCase):
    def test_patient_cue_tags_patient_name(self):
        spans = _categories("Patient: Susan Davis presents for a follow-up.")
        self.assertIn(("Susan Davis", "patient_name", "pattern"), spans)

    def test_physician_cue_tags_physician_name(self):
        spans = _categories("Provider: Jane Doe (Family Medicine)")
        self.assertIn(("Jane Doe", "physician_name", "pattern"), spans)
        self.assertNotIn("Family Medicine", [v for v, c, _ in spans])

    def test_dr_title_tags_physician_name(self):
        spans = _categories("Seen by Dr. Alan Whitfield, MD on 03/14/2026.")
        self.assertIn(("Dr. Alan Whitfield, MD", "physician_name", "pattern"), spans)

    def test_bare_name_with_no_context_is_generic(self):
        spans = _categories("Robert Aragon 489-36-8350")
        self.assertIn(("Robert Aragon", "name", "heuristic"), spans)

    def test_relation_cue_tags_generic_name(self):
        spans = _categories("Sister Margaret Ellery has arthritis.")
        cats = [(v, c) for v, c, _ in spans]
        self.assertIn(("Margaret Ellery", "name"), cats)

    def test_comma_format_name(self):
        spans = _categories("SMITH, JOHN is a 45 y.o. male.")
        cats = [(v, c) for v, c, _ in spans]
        self.assertIn(("SMITH, JOHN", "name"), cats)

    def test_comma_format_excludes_city_state(self):
        spans = _categories("Referred to a clinic in Seattle, WA for follow-up.")
        values = [v for v, c, _ in spans]
        self.assertNotIn("Seattle, WA", values)


class FacilityTests(SimpleTestCase):
    def test_facility_label(self):
        spans = _categories("Location: Cedar Grove Medical Center")
        self.assertIn(("Cedar Grove Medical Center", "facility", "pattern"), spans)

    def test_facility_suffix_without_label(self):
        spans = _categories("Transferred to Northgate Regional Medical Center for surgery.")
        cats = [c for v, c, _ in spans if "Medical Center" in v]
        self.assertIn("facility", cats)


class DateBoundaryTests(SimpleTestCase):
    def test_full_date_detected(self):
        self.assertIn(("03/14/2026", "date", "pattern"), _categories("Visit on 03/14/2026."))

    def test_month_year_detected(self):
        self.assertIn(("7/2023", "date", "pattern"), _categories("Surgery date: 7/2023"))

    def test_bare_year_not_flagged(self):
        # Safe Harbor permits a bare year to remain — only month/day
        # elements (or month+year) directly tied to an individual must go.
        spans = _categories("Diagnosis year: 2014")
        self.assertEqual(spans, [])


class ColumnHeaderContextTests(SimpleTestCase):
    def test_bare_name_in_name_column_detected(self):
        spans = _categories("Dorothy Whitcombe", column_header="Name")
        self.assertEqual(spans, [("Dorothy Whitcombe", "name", "context")])

    def test_bare_year_in_age_of_onset_column_not_flagged(self):
        self.assertEqual(_categories("40", column_header="Age of Onset"), [])

    def test_relation_column_not_flagged(self):
        self.assertEqual(_categories("Sister", column_header="Relation"), [])

    def test_problem_column_not_flagged(self):
        self.assertEqual(_categories("Hypertension", column_header="Problem"), [])

    def test_month_year_in_date_column_detected(self):
        spans = _categories("7/2023", column_header="Date")
        self.assertEqual([(v, c) for v, c, _ in spans], [("7/2023", "date")])


class OverlapPriorityTests(SimpleTestCase):
    def test_high_confidence_short_span_not_swallowed_by_long_heuristic(self):
        # "reference ... id ..." trips the broad _OTHER_KEYWORDS
        # sentence-grabber, which used to span (and suppress) the SSN
        # sitting right after it, since the old rule was "longest span
        # wins" rather than "highest confidence wins".
        text = "Reference ID 489-36-8350 enrollment cohort study."
        spans = _categories(text)
        self.assertIn(("489-36-8350", "ssn", "pattern"), spans)

    def test_only_one_span_covers_the_ssn_region(self):
        text = "Reference ID 489-36-8350 enrollment cohort study."
        spans = detect_spans(text)
        overlapping = [s for s in spans if s["start"] < 24 and s["end"] > 13]
        self.assertEqual(len(overlapping), 1)
        self.assertEqual(overlapping[0]["category"], "ssn")
