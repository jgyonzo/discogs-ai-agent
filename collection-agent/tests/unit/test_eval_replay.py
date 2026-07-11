"""Replay source-run reader + partition (025 T004–T006,
contracts/amendment-023-eval-results-2.md §Delta 1/3). Pure local I/O —
no clients, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from collection_agent.eval.replay import ReplayItem, load_source_run
from collection_agent.eval.sources import SourceError

from tests.unit.test_eval_sources import header, release_line, write_manifest

RUN_ID = "20260711-222805Z-discogs"


def source_record(**overrides) -> dict:
    base = {
        "image": "101_secondary1.jpg", "source": "discogs",
        "truth_release_id": 101, "outcome": "miss",
        "rungs_tried": ["catno"], "evidence_kinds": ["catno"],
        "candidate_ids": [999], "evidence": {"catno": "SUB 15"},
        "vision_calls": 1, "elapsed_s": 2.0,
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def write_run(settings, records: list[dict | str], run_id: str = RUN_ID) -> Path:
    run_dir = settings.eval_results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        r if isinstance(r, str) else json.dumps(r) for r in records
    ]
    (run_dir / "results.jsonl").write_text(
        "".join(line + "\n" for line in lines), encoding="utf-8"
    )
    return run_dir


class TestReader:
    def test_parses_well_formed_run(self, settings):
        write_run(settings, [
            source_record(),
            source_record(image="102_secondary1.jpg", truth_release_id=102,
                          outcome="hit", rank=1, candidate_ids=[102]),
        ])
        items = load_source_run(settings, RUN_ID)
        assert [i.image for i in items] == [
            "101_secondary1.jpg", "102_secondary1.jpg",
        ]
        assert all(i.evidence == {"catno": "SUB 15"} for i in items)

    def test_blank_lines_skipped_unknown_fields_ignored(self, settings):
        rec = source_record()
        rec["future_field"] = {"x": 1}  # forward-compatible read
        run_dir = write_run(settings, [rec])
        with (run_dir / "results.jsonl").open("a", encoding="utf-8") as fh:
            fh.write("\n   \n")
        assert len(load_source_run(settings, RUN_ID)) == 1

    def test_torn_trailing_line_tolerated(self, settings):
        run_dir = write_run(settings, [source_record()])
        with (run_dir / "results.jsonl").open("a", encoding="utf-8") as fh:
            fh.write('{"image": "torn')  # interrupted append
        items = load_source_run(settings, RUN_ID)
        assert len(items) == 1  # complete record kept, torn line skipped

    def test_corrupt_mid_file_line_fails_fast(self, settings):
        # corrupt input ≠ interrupted run (analysis U1): never guess
        write_run(settings, [source_record(), "{not json}", source_record(
            image="102_secondary1.jpg", truth_release_id=102)])
        with pytest.raises(SourceError, match="corrupt"):
            load_source_run(settings, RUN_ID)

    def test_missing_run_dir_fails_fast_naming_the_id(self, settings):
        with pytest.raises(SourceError, match="20260101-000000Z-discogs"):
            load_source_run(settings, "20260101-000000Z-discogs")

    def test_missing_results_file_fails_fast(self, settings):
        (settings.eval_results_dir / RUN_ID).mkdir(parents=True)
        with pytest.raises(SourceError, match=RUN_ID):
            load_source_run(settings, RUN_ID)

    def test_empty_results_file_fails_fast(self, settings):
        write_run(settings, [])
        with pytest.raises(SourceError, match="no records"):
            load_source_run(settings, RUN_ID)

    def test_zero_replayable_records_fails_fast(self, settings):
        # a pre-024 run: records exist but none carry evidence
        old = source_record()
        old.pop("evidence")
        write_run(settings, [old])
        with pytest.raises(SourceError, match="no recorded evidence"):
            load_source_run(settings, RUN_ID)

    def test_record_missing_image_or_source_is_corrupt(self, settings):
        bad = source_record()
        bad.pop("image")
        write_run(settings, [bad, source_record()])
        with pytest.raises(SourceError, match="corrupt"):
            load_source_run(settings, RUN_ID)


class TestPartition:
    """R3 mapping: exactly one ReplayItem per source record; evidence ⇒
    replayable, everything else carried through by category (FR-003)."""

    def test_evidence_carrying_records_are_replayable(self, settings):
        write_run(settings, [
            source_record(outcome="hit", rank=1, candidate_ids=[101]),
            source_record(image="a.jpg", outcome="miss"),
            source_record(image="b.jpg", outcome="error",
                          error_kind="discogs_error", candidate_ids=None,
                          rungs_tried=None),  # post-vision search failure
        ])
        items = load_source_run(settings, RUN_ID)
        assert len(items) == 3
        assert all(i.evidence and i.carry_outcome is None for i in items)

    def test_carry_through_categories(self, settings):
        no_ev = source_record(image="ne.jpg", outcome="no_evidence",
                              evidence=None, candidate_ids=None,
                              rungs_tried=None, evidence_kinds=None)
        vis_err = source_record(image="ve.jpg", outcome="error",
                                error_kind="vision_error", evidence=None,
                                detail="provider down", candidate_ids=None,
                                rungs_tried=None, evidence_kinds=None)
        unlabeled = source_record(image="ul.jpg", outcome="unlabeled",
                                  truth_release_id=None, evidence=None,
                                  vision_calls=0, candidate_ids=None,
                                  rungs_tried=None, evidence_kinds=None)
        write_run(settings, [source_record(), no_ev, vis_err, unlabeled])
        by_image = {i.image: i for i in load_source_run(settings, RUN_ID)}
        assert len(by_image) == 4
        assert by_image["ne.jpg"].carry_outcome == "no_evidence"
        assert by_image["ve.jpg"].carry_outcome == "error"
        assert by_image["ve.jpg"].carry_error_kind == "vision_error"
        assert "carried through" in by_image["ve.jpg"].carry_detail
        assert by_image["ul.jpg"].carry_outcome == "unlabeled"

    def test_defensive_hit_without_evidence_carried_never_rescored(self, settings):
        # can't occur in a well-formed 024 run (invariant 10) — but if it
        # does, carry the category and say so, never silently re-score
        weird = source_record(outcome="hit", rank=1, candidate_ids=[101],
                              evidence=None)
        write_run(settings, [weird, source_record(image="ok.jpg")])
        by_image = {i.image: i for i in load_source_run(settings, RUN_ID)}
        item = by_image["101_secondary1.jpg"]
        assert item.carry_outcome == "hit" and item.evidence is None
        assert "without evidence" in item.carry_detail

    def test_evidence_with_unknown_truth_is_carried_unlabeled(self, settings):
        # evidence but no truth: nothing to score against — never guessed
        rec = source_record(image="ul2.jpg", truth_release_id=None,
                            outcome="unlabeled", source="retained",
                            vision_calls=0)
        write_run(settings, [rec, source_record(source="retained")])
        by_image = {i.image: i for i in load_source_run(settings, RUN_ID)}
        item = by_image["ul2.jpg"]
        assert item.carry_outcome == "unlabeled" and item.evidence is None

    def test_item_partition_is_exclusive(self):
        with pytest.raises(ValueError):
            ReplayItem(image="x.jpg", source="discogs",
                       evidence={"catno": "A1"}, carry_outcome="no_evidence")
        with pytest.raises(ValueError):
            ReplayItem(image="x.jpg", source="discogs")


class TestTruthMasterResolution:
    """R5: masters re-resolved from the local dataset manifest when
    available; absent/corrupt manifest or retained source ⇒ None."""

    def test_manifest_present_resolves_masters_newest_line_wins(self, settings):
        write_manifest(settings.eval_dataset_dir, [
            header(),
            release_line(101, ["101_secondary1.jpg"]),          # no master
            release_line(101, ["101_secondary1.jpg"], master_id=5309),  # backfilled
        ])
        write_run(settings, [source_record()])
        items = load_source_run(settings, RUN_ID)
        assert items[0].truth_master_id == 5309

    def test_manifest_absent_yields_none(self, settings):
        write_run(settings, [source_record()])
        assert load_source_run(settings, RUN_ID)[0].truth_master_id is None

    def test_corrupt_manifest_degrades_to_none(self, settings):
        settings.eval_dataset_dir.mkdir(parents=True, exist_ok=True)
        (settings.eval_dataset_dir / "manifest.jsonl").write_text(
            '{"type": "release", broken\n{"also": "broken"\n', encoding="utf-8"
        )
        write_run(settings, [source_record()])
        assert load_source_run(settings, RUN_ID)[0].truth_master_id is None

    def test_retained_source_records_never_get_masters(self, settings):
        write_manifest(settings.eval_dataset_dir, [
            header(), release_line(101, ["x.jpg"], master_id=5309),
        ])
        write_run(settings, [source_record(source="retained")])
        assert load_source_run(settings, RUN_ID)[0].truth_master_id is None
