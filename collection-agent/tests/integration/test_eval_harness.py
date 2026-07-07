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
