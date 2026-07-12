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
        # 025: fixture barcode must be plausible (8+ digits) to occupy a rung
        ev = ScanEvidence(
            barcode="72064244", catno="SL-1", artist="A", title="T"
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


class TestBarcodePlausibilityGate:
    """025 FR-009/011/012 (amendment-022-scan-api-2): a sub-8-digit digit
    run is not a barcode — cleared, never moved to catno. Motivating live
    case: run 20260711-222805Z, image 17859_secondary1.jpeg (Cybotron) —
    vision emitted barcode "3070", which hijacked the barcode rung and
    suppressed the correctly-extracted catno "D-216"."""

    def test_live_cybotron_case_cleared_catno_survives(self):
        ev = ScanEvidence(artist="Cybotron", catno="D-216", barcode="3070")
        assert ev.barcode is None
        assert ev.catno == "D-216"  # never overwritten, never dropped
        assert ev.evidence_kinds[0] == "catno"  # ladder starts at catno now

    def test_seven_digits_cleared(self):
        assert ScanEvidence(barcode="1234567").barcode is None

    def test_exactly_eight_digits_kept(self):
        # UPC-E / EAN-8 are real — the boundary is plausible
        assert ScanEvidence(barcode="40123455").barcode == "40123455"

    def test_thirteen_digits_kept(self):
        assert ScanEvidence(barcode="5011166123457").barcode == "5011166123457"

    def test_separators_stripped_before_the_count(self):
        # digits-only normalization runs first: "3 0-70" is 4 digits
        assert ScanEvidence(barcode="3 0-70").barcode is None

    def test_cleared_value_never_moves_to_catno(self):
        ev = ScanEvidence(barcode="3070")  # no catno extracted
        assert ev.barcode is None and ev.catno is None

    def test_gate_only_evidence_is_empty(self):
        ev = ScanEvidence(barcode="3070")
        assert ev.is_empty and ev.evidence_kinds == []

    def test_gated_barcode_absent_from_compact_dump(self):
        # FR-012: no ghost barcode in journal/eval evidence payloads
        ev = ScanEvidence(artist="Cybotron", catno="D-216", barcode="3070")
        assert ev.compact_dump() == {"artist": "Cybotron", "catno": "D-216"}

    def test_composes_with_fr019_reclassification(self):
        # an 11-digit catno still reclassifies to barcode and, being ≥ 10
        # digits by construction, is never gated
        ev = ScanEvidence(catno="81824 11306")
        assert ev.barcode == "8182411306" and ev.catno is None

    def test_plausible_barcodes_byte_identical_to_pre_025(self):
        ev = ScanEvidence(barcode="5 011166-12345 7", catno="SL-1")
        assert ev.barcode == "5011166123457" and ev.catno == "SL-1"


class TestCandidateMasterId:
    """024 T004: master_id is verbatim-optional (amendment-022-scan-api §1)."""

    @staticmethod
    def _candidate(result, settings):
        from collection_agent.scan.search import _candidate_from_result
        from collection_agent.scan.search import pending_duplicate_checker

        return _candidate_from_result(result, settings, pending_duplicate_checker)

    def test_master_id_carried_verbatim(self, settings):
        from tests.fixtures.discogs_payloads import search_result

        c = self._candidate(search_result(101, master_id=5309), settings)
        assert c.master_id == 5309

    def test_absent_master_id_stays_none(self, settings):
        from tests.fixtures.discogs_payloads import search_result

        c = self._candidate(search_result(101), settings)
        assert c.master_id is None

    def test_zero_master_id_normalizes_to_none(self, settings):
        from tests.fixtures.discogs_payloads import search_result

        item = search_result(101)
        item["master_id"] = 0  # Discogs' "no master" sentinel
        assert self._candidate(item, settings).master_id is None


class TestCandidateLinks026:
    """026 T004: additive server-built link fields + VersionsResponse
    (amendment-022-scan-api-3 deltas 1/3)."""

    def test_link_fields_default_none_old_constructions_valid(self):
        # pre-026 Candidate constructions (no link kwargs) must stay valid
        c = Candidate(
            release_id=101,
            title="Test Artist - Test Record",
            duplicate=DuplicateStatus(state="unknown"),
        )
        assert c.release_page_url is None and c.master_page_url is None

    def test_link_fields_serialize(self):
        c = Candidate(
            release_id=101,
            title="T",
            release_page_url="https://www.discogs.com/release/101",
            master_page_url="https://www.discogs.com/master/5309",
            master_id=5309,
            duplicate=DuplicateStatus(state="unknown"),
        )
        dumped = c.model_dump()
        assert dumped["release_page_url"] == "https://www.discogs.com/release/101"
        assert dumped["master_page_url"] == "https://www.discogs.com/master/5309"

    def test_versions_response_shape(self):
        from collection_agent.scan.models import VersionsResponse

        r = VersionsResponse(scan_id="s-1", master_id=5309)
        assert r.candidates == [] and r.total_versions == 0 and r.message is None

    def test_scan_versions_max_default_and_alias(self, settings, tmp_path):
        from collection_agent.settings import Settings

        assert settings.scan_versions_max == 25
        overridden = Settings(
            _env_file=None,
            DISCOGS_USER_TOKEN="test-token-not-real",
            SNAPSHOT_PATH=tmp_path / "snapshot.json",
            COLLECTION_AGENT_SCAN_VERSIONS_MAX=7,
        )
        assert overridden.scan_versions_max == 7
