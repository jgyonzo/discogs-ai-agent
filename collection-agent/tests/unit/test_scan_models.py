"""Scan domain models (022 T006): barcode normalization, is_empty,
evidence_kinds derivation, outcome literal validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from collection_agent.scan.models import (
    Candidate,
    DuplicateStatus,
    ScanCycleOutcome,
    ScanEvidence,
)


class TestScanEvidenceBarcode:
    def test_spaces_and_hyphens_stripped(self):
        ev = ScanEvidence(barcode="5 011166-12345 7")
        assert ev.barcode == "5011166123457"

    def test_plain_digits_kept(self):
        assert ScanEvidence(barcode="720642442524").barcode == "720642442524"

    def test_garbage_without_digits_becomes_none(self):
        assert ScanEvidence(barcode="no barcode visible").barcode is None

    def test_none_stays_none(self):
        assert ScanEvidence(barcode=None).barcode is None


class TestScanEvidenceEmptiness:
    def test_all_none_is_empty(self):
        assert ScanEvidence().is_empty

    def test_blank_strings_normalize_to_empty(self):
        assert ScanEvidence(artist="  ", title="").is_empty

    def test_format_hints_alone_still_empty(self):
        # format hints can't drive any search rung
        assert ScanEvidence(format_hints=["2xLP"]).is_empty

    def test_any_searchable_field_is_not_empty(self):
        assert not ScanEvidence(catno="SL-001").is_empty


class TestEvidenceKinds:
    def test_ladder_order_barcode_first(self):
        ev = ScanEvidence(
            barcode="123456", catno="SL-1", artist="A", title="T"
        )
        assert ev.evidence_kinds == ["barcode", "catno", "artist_title"]

    def test_artist_without_title_is_not_a_rung(self):
        assert ScanEvidence(artist="A").evidence_kinds == []

    def test_empty_evidence_no_kinds(self):
        assert ScanEvidence().evidence_kinds == []


class TestCandidate:
    def test_absent_fields_stay_absent(self):
        c = Candidate(
            release_id=1,
            title="A - T",
            duplicate=DuplicateStatus(state="unknown", reason="no snapshot"),
        )
        assert c.year is None and c.thumb_url is None and c.formats == []


class TestScanCycleOutcome:
    def test_valid_outcomes(self):
        for outcome in ("added", "skipped", "no_match", "failed"):
            ScanCycleOutcome(
                ts="2026-07-07T18:30:00Z",
                seq=1,
                scan_id="s-1",
                outcome=outcome,
                source="photo",
            )

    def test_invalid_outcome_rejected(self):
        with pytest.raises(ValidationError):
            ScanCycleOutcome(
                ts="2026-07-07T18:30:00Z",
                seq=1,
                scan_id="s-1",
                outcome="maybe",
                source="photo",
            )

    def test_invalid_source_rejected(self):
        with pytest.raises(ValidationError):
            ScanCycleOutcome(
                ts="2026-07-07T18:30:00Z",
                seq=1,
                scan_id="s-1",
                outcome="added",
                source="telepathy",
            )
