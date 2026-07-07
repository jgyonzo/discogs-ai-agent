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


class TestBarcodeInCatnoReclassification:
    """FR-019 (addendum 1): the live session's vision replies put barcode
    digit runs in catno — replayed here verbatim (session 20260707-130810Z)."""

    def test_live_cycle_2_payload(self):
        ev = ScanEvidence(
            artist="dj silversurfer",
            label="CROSSTOWNREBELS",
            catno="81824 11306",
        )
        assert ev.catno is None
        assert ev.barcode == "8182411306"

    def test_live_cycle_4_payload(self):
        ev = ScanEvidence(
            artist="frankie flowerz",
            label="CROSSTOWNREBELS",
            catno="8 00505 200413",
        )
        assert ev.catno is None
        assert ev.barcode == "800505200413"

    def test_live_cycle_3_short_numeric_catno_kept(self):
        # "009" is a plausible catno fragment, not a barcode
        ev = ScanEvidence(artist="CROSSTOWN REBELS", catno="009")
        assert ev.catno == "009"
        assert ev.barcode is None

    def test_lettered_catno_kept(self):
        assert ScanEvidence(catno="WARPLP92").catno == "WARPLP92"
        assert ScanEvidence(catno="CRM 009").catno == "CRM 009"

    def test_nine_digits_stays_catno(self):
        assert ScanEvidence(catno="123456789").catno == "123456789"

    def test_existing_barcode_wins_junk_catno_dropped(self):
        ev = ScanEvidence(barcode="720642442524", catno="81824 11306")
        assert ev.barcode == "720642442524"
        assert ev.catno is None

    def test_dotted_digit_run_reclassified(self):
        ev = ScanEvidence(catno="8.18240.11306")
        assert ev.barcode == "81824011306" and ev.catno is None


class TestTracksEvidence:
    def test_tracks_count_as_evidence(self):
        ev = ScanEvidence(tracks=["Ace Of Spades", "Dirty Dishes"])
        assert not ev.is_empty
        assert ev.evidence_kinds == []  # no structured rung, fallback only

    def test_compact_dump_drops_empty(self):
        ev = ScanEvidence(artist="A", catno=None, tracks=[], notes="")
        assert ev.compact_dump() == {"artist": "A"}

    def test_compact_dump_keeps_values(self):
        ev = ScanEvidence(artist="A", barcode="720642442524",
                          tracks=["The Key"])
        dumped = ev.compact_dump()
        assert dumped == {
            "artist": "A", "barcode": "720642442524", "tracks": ["The Key"],
        }
