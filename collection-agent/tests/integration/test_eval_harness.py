"""Eval harness end-to-end (023 T018/T025): full runs over tmp datasets with
a scripted vision stub + FakeDiscogsClient — zero live calls, and the
production seams (extract_evidence → find_candidates) run unmodified."""

from __future__ import annotations

import json

from collection_agent.eval.harness import run_eval
from collection_agent.eval.scoring import EvalSummary
from collection_agent.scan.vision import VisionExtractionError  # noqa: F401 (doc)

from tests.fixtures import discogs_payloads as payloads
from tests.fixtures.fake_client import FakeDiscogsClient
from tests.unit.test_eval_sources import (
    SESSION,
    add_photo,
    header,
    journal_line,
    release_line,
    write_journal,
    write_manifest,
)
from tests.unit.test_scan_vision import StubVisionLLM

BARCODE_EVIDENCE = json.dumps(
    {"artist": "Alex Smoke", "title": "Simple Things", "barcode": "720642442524"}
)


def seed_dataset(settings, release_ids: list[int]) -> None:
    lines = [header()]
    for rid in release_ids:
        fname = f"{rid}_secondary1.jpg"
        lines.append(release_line(rid, [fname]))
    write_manifest(settings.eval_dataset_dir, lines)
    for rid in release_ids:
        (settings.eval_dataset_dir / f"{rid}_secondary1.jpg").write_bytes(
            b"\xff\xd8 fake jpeg " + str(rid).encode()
        )


def hit_search(release_id: int, extra: list[int] | None = None) -> dict:
    results = [payloads.search_result(r) for r in ([release_id] + (extra or []))]
    return {"barcode": payloads.search_page(results)}


def read_results(run_dir) -> list[dict]:
    lines = (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines if l.strip()]


class TestDiscogsSourceRun:
    def test_full_run_hits_and_files(self, settings):
        seed_dataset(settings, [101])
        llm = StubVisionLLM([BARCODE_EVIDENCE])
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses.update(hit_search(101, extra=[202]))

        run_dir, summary = run_eval(llm, discogs, settings, "discogs")

        assert summary.hits == 1 and summary.identification_rate == 1.0
        assert summary.top1_rate == 1.0
        assert summary.hits_by_rung == {"barcode": 1}
        assert summary.vision_calls == 1
        assert summary.dataset_snapshot_completeness == "complete"
        records = read_results(run_dir)
        assert records[0]["outcome"] == "hit" and records[0]["rank"] == 1
        assert records[0]["rungs_tried"] == ["barcode"]
        assert records[0]["candidate_ids"] == [101, 202]
        # summary.json parses back to the same model (contract §3)
        on_disk = EvalSummary.model_validate_json(
            (run_dir / "summary.json").read_text(encoding="utf-8")
        )
        assert on_disk == summary

    def test_vision_failure_is_error_record_run_completes(self, settings):
        seed_dataset(settings, [101, 102])
        llm = StubVisionLLM([RuntimeError("provider down"), BARCODE_EVIDENCE])
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses.update(hit_search(102))

        run_dir, summary = run_eval(llm, discogs, settings, "discogs")

        assert summary.errors == 1 and summary.hits == 1
        assert summary.errors_by_kind == {"vision_error": 1}
        # errors excluded from the denominator (contract §3 invariant 3)
        assert summary.identification_rate == 1.0
        assert summary.vision_calls == 2  # the failed call still billed
        outcomes = {r["image"]: r["outcome"] for r in read_results(run_dir)}
        assert outcomes == {
            "101_secondary1.jpg": "error", "102_secondary1.jpg": "hit",
        }

    def test_empty_evidence_is_no_evidence_and_no_search(self, settings):
        seed_dataset(settings, [101])
        llm = StubVisionLLM(["{}"])
        discogs = FakeDiscogsClient(instances=[], details={})
        _, summary = run_eval(llm, discogs, settings, "discogs")
        assert summary.no_evidence == 1
        assert discogs.searches == []  # ladder never ran

    def test_miss_records_rung_and_candidates(self, settings):
        seed_dataset(settings, [101])
        llm = StubVisionLLM([BARCODE_EVIDENCE])
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses.update(hit_search(999))  # wrong release
        run_dir, summary = run_eval(llm, discogs, settings, "discogs")
        assert summary.misses == 1 and summary.identification_rate == 0.0
        rec = read_results(run_dir)[0]
        assert rec["outcome"] == "miss" and rec["candidate_ids"] == [999]

    def test_limit_truncates_and_flags(self, settings):
        seed_dataset(settings, [101, 102, 103])
        llm = StubVisionLLM(["{}", "{}"])
        discogs = FakeDiscogsClient(instances=[], details={})
        run_dir, summary = run_eval(llm, discogs, settings, "discogs", limit=2)
        assert summary.limited is True and summary.images_total == 2
        assert len(read_results(run_dir)) == 2

    def test_incremental_results_survive_midrun_crash(self, settings):
        seed_dataset(settings, [101, 102])
        # provider errors are RECORDED (typed), so a hard crash must come
        # from outside the guarded seams: Ctrl-C during image 2's search
        llm = StubVisionLLM([BARCODE_EVIDENCE, BARCODE_EVIDENCE])

        class InterruptedClient(FakeDiscogsClient):
            def search_releases(self, params):
                if len(self.searches) >= 1:
                    raise KeyboardInterrupt
                return super().search_releases(params)

        discogs = InterruptedClient(instances=[], details={})
        discogs.search_responses.update(hit_search(101))
        try:
            run_eval(llm, discogs, settings, "discogs")
        except KeyboardInterrupt:
            pass  # the crash we simulated
        run_dirs = list(settings.eval_results_dir.iterdir())
        assert len(run_dirs) == 1
        records = read_results(run_dirs[0])
        assert len(records) == 1 and records[0]["outcome"] == "hit"

    def test_back_to_back_runs_get_distinct_dirs(self, settings, monkeypatch):
        seed_dataset(settings, [101])
        ids = iter(["20260707-190001Z-discogs", "20260707-190002Z-discogs"])
        monkeypatch.setattr(
            "collection_agent.eval.harness._run_id", lambda source: next(ids)
        )
        for _ in range(2):
            llm = StubVisionLLM(["{}"])
            run_eval(llm, FakeDiscogsClient(instances=[], details={}),
                     settings, "discogs")
        assert len(list(settings.eval_results_dir.iterdir())) == 2


class TestRetainedSourceRun:
    def test_labeled_scored_unlabeled_counted_free(self, settings):
        add_photo(settings, SESSION, f"{SESSION}-1.jpg")   # added -> labeled
        add_photo(settings, SESSION, f"{SESSION}-2.jpg")   # skipped -> unlabeled
        add_photo(settings, SESSION, "pending-1.jpg")      # never got a cycle
        write_journal(settings, SESSION, [
            journal_line(f"{SESSION}-1", "added", release_id=724223),
            journal_line(f"{SESSION}-2", "skipped"),
        ])
        llm = StubVisionLLM([BARCODE_EVIDENCE])  # exactly ONE call expected
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses.update(hit_search(724223))

        run_dir, summary = run_eval(llm, discogs, settings, "retained")

        assert summary.images_total == 3
        assert summary.hits == 1 and summary.unlabeled == 2
        assert summary.vision_calls == 1  # unlabeled photos are never billed
        assert summary.identification_rate == 1.0
        by_image = {r["image"]: r for r in read_results(run_dir)}
        assert by_image[f"{SESSION}-1.jpg"]["outcome"] == "hit"
        assert by_image[f"{SESSION}-2.jpg"]["outcome"] == "unlabeled"
        assert by_image["pending-1.jpg"]["outcome"] == "unlabeled"
        assert by_image[f"{SESSION}-2.jpg"].get("vision_calls", 0) == 0


class TestEvidenceInResults:
    """024 US2 (T010): every evaluated record diagnosable from the file
    alone (amendment-023-eval-results §1, invariant 10)."""

    def test_record_carries_compact_evidence(self, settings):
        seed_dataset(settings, [101])
        llm = StubVisionLLM([BARCODE_EVIDENCE])
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses.update(hit_search(101))
        run_dir, _ = run_eval(llm, discogs, settings, "discogs")
        rec = read_results(run_dir)[0]
        # journal-shaped compact dump: extracted values, empties omitted
        assert rec["evidence"] == {
            "artist": "Alex Smoke", "title": "Simple Things",
            "barcode": "720642442524",
        }

    def test_zero_candidate_miss_is_diagnosable(self, settings):
        seed_dataset(settings, [101])
        llm = StubVisionLLM([json.dumps({"catno": "VIS049"})])
        discogs = FakeDiscogsClient(instances=[], details={})  # all rungs empty
        run_dir, _ = run_eval(llm, discogs, settings, "discogs")
        rec = read_results(run_dir)[0]
        assert rec["outcome"] == "miss" and rec["candidate_ids"] == []
        # SC-003: WHAT was searched is in the record itself
        assert rec["evidence"] == {"catno": "VIS049"}
        assert rec["rungs_tried"] == ["catno"]

    def test_no_evidence_and_unlabeled_records_omit_evidence(self, settings):
        seed_dataset(settings, [101])
        llm = StubVisionLLM(["{}"])
        discogs = FakeDiscogsClient(instances=[], details={})
        run_dir, _ = run_eval(llm, discogs, settings, "discogs")
        assert "evidence" not in read_results(run_dir)[0]  # empty extraction

        add_photo(settings, SESSION, f"{SESSION}-9.jpg")  # unlabeled photo
        run_dir2, _ = run_eval(
            StubVisionLLM([]), FakeDiscogsClient(instances=[], details={}),
            settings, "retained",
        )
        rec = read_results(run_dir2)[0]
        assert rec["outcome"] == "unlabeled" and "evidence" not in rec

    def test_invariant_10_all_extracting_records_carry_evidence(self, settings):
        seed_dataset(settings, [101, 102])
        llm = StubVisionLLM([BARCODE_EVIDENCE, BARCODE_EVIDENCE])
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses.update(hit_search(101))
        run_dir, _ = run_eval(llm, discogs, settings, "discogs")
        for rec in read_results(run_dir):
            if rec.get("vision_calls", 0) >= 1 and rec["outcome"] in ("hit", "miss"):
                assert rec.get("evidence")


class TestPracticalRateEndToEnd:
    """024 US3 (T019): same-master classification + practical rate through
    the full harness (amendment-023-eval-results §2–3)."""

    def test_same_master_near_miss_classified_and_rated(self, settings):
        # manifest with truth master 5309; candidate is another pressing
        # of that master (wrong release id, same master)
        lines = [header()]
        line = release_line(101, ["101_secondary1.jpg"], master_id=5309)
        lines.append(line)
        write_manifest(settings.eval_dataset_dir, lines)
        (settings.eval_dataset_dir / "101_secondary1.jpg").write_bytes(b"jpg")

        llm = StubVisionLLM([BARCODE_EVIDENCE])
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses["barcode"] = payloads.search_page(
            [payloads.search_result(999, master_id=5309)]
        )
        run_dir, summary = run_eval(llm, discogs, settings, "discogs")

        rec = read_results(run_dir)[0]
        assert rec["outcome"] == "miss"
        assert rec["miss_master_relation"] == "same_master"
        assert summary.misses_same_master == 1
        assert summary.identification_rate == 0.0
        assert summary.practical_rate == 1.0  # right album on screen

    def test_023_manifest_yields_unknown_and_equal_rates(self, settings):
        # 023-format manifest (no master ids): misses classify unknown,
        # practical == strict — never guessed
        seed_dataset(settings, [101])
        llm = StubVisionLLM([BARCODE_EVIDENCE])
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses["barcode"] = payloads.search_page(
            [payloads.search_result(999, master_id=5309)]
        )
        run_dir, summary = run_eval(llm, discogs, settings, "discogs")
        assert read_results(run_dir)[0]["miss_master_relation"] == "unknown"
        assert summary.misses_master_unknown == 1
        assert summary.practical_rate == summary.identification_rate == 0.0
