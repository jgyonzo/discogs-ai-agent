"""Eval harness end-to-end (023 T018/T025): full runs over tmp datasets with
a scripted vision stub + FakeDiscogsClient — zero live calls, and the
production seams (extract_evidence → find_candidates) run unmodified."""

from __future__ import annotations

import json

from collection_agent.discogs.client import DiscogsServerError
from collection_agent.eval.harness import run_eval, run_replay
from collection_agent.eval.scoring import EvalSummary
from collection_agent.scan.vision import VisionExtractionError  # noqa: F401 (doc)

from tests.fixtures import discogs_payloads as payloads
from tests.fixtures.fake_client import FakeDiscogsClient
from tests.unit.test_eval_replay import RUN_ID, source_record, write_run
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


class TestReplayRun:
    """025 US1 (T007): end-to-end `run_replay` over a fixture source run —
    zero vision calls, production ladder unmodified, provenance +
    invariants 11–14 (contracts/amendment-023-eval-results-2.md)."""

    RUN = "20260711-222805Z-retained"

    def seed_source_run(self, settings) -> None:
        """A retained-source run exercising every partition branch:
        replayable hit / flippable miss / replayable discogs_error, plus
        no_evidence / vision_error / unlabeled carry-throughs."""
        write_run(settings, [
            source_record(image="hit.jpg", source="retained",
                          truth_release_id=101, outcome="hit", rank=1,
                          candidate_ids=[101], rungs_tried=["barcode"],
                          evidence={"barcode": "720642442524"}),
            source_record(image="flip.jpg", source="retained",
                          truth_release_id=102, outcome="miss",
                          candidate_ids=[999],
                          evidence={"catno": "SUB 15"}),
            source_record(image="err.jpg", source="retained",
                          truth_release_id=103, outcome="error",
                          error_kind="discogs_error", candidate_ids=None,
                          rungs_tried=None,
                          evidence={"artist": "A", "title": "T"}),
            source_record(image="ne.jpg", source="retained",
                          truth_release_id=104, outcome="no_evidence",
                          evidence=None, candidate_ids=None,
                          rungs_tried=None, evidence_kinds=None),
            source_record(image="ve.jpg", source="retained",
                          truth_release_id=105, outcome="error",
                          error_kind="vision_error", evidence=None,
                          candidate_ids=None, rungs_tried=None,
                          evidence_kinds=None),
            source_record(image="ul.jpg", source="retained",
                          truth_release_id=None, outcome="unlabeled",
                          evidence=None, vision_calls=0, candidate_ids=None,
                          rungs_tried=None, evidence_kinds=None),
        ], run_id=self.RUN)

    def scripted_client(self) -> FakeDiscogsClient:
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses.update({
            "barcode": payloads.search_page([payloads.search_result(101)]),
            "catno": payloads.search_page([payloads.search_result(102)]),
            "artist_title": payloads.search_page(
                [payloads.search_result(103), payloads.search_result(202)]
            ),
        })
        return discogs

    def test_replay_end_to_end(self, settings):
        self.seed_source_run(settings)
        before = (settings.eval_results_dir / self.RUN
                  / "results.jsonl").read_bytes()

        run_dir, summary = run_replay(
            self.scripted_client(), settings, replay_of=self.RUN
        )

        # (a) standard run dir, -replay id
        assert run_dir.name.endswith("-replay")
        assert (run_dir / "summary.json").exists()
        # (b) provenance + invariant 11/12
        assert summary.replay_of == self.RUN
        assert summary.source == "retained"
        assert summary.vision_calls == 0
        assert summary.dataset_snapshot_completeness is None
        records = read_results(run_dir)
        assert all(r.get("vision_calls", 0) == 0 for r in records)
        assert all("replayed" in r for r in records)
        # (c) denominator parity — one record per source record, same names
        assert summary.images_total == 6 and summary.limited is False
        assert {r["image"] for r in records} == {
            "hit.jpg", "flip.jpg", "err.jpg", "ne.jpg", "ve.jpg", "ul.jpg",
        }
        by_image = {r["image"]: r for r in records}
        # (d/e) replayed records scored fresh — incl. the original
        # discogs_error and the miss that flips under the rescripted search
        assert by_image["hit.jpg"]["outcome"] == "hit"
        assert by_image["flip.jpg"]["outcome"] == "hit"  # miss → hit
        assert by_image["err.jpg"]["outcome"] == "hit"   # error → hit
        assert all(by_image[i]["replayed"] is True
                   for i in ("hit.jpg", "flip.jpg", "err.jpg"))
        # carry-throughs preserve category (invariant 14)
        assert by_image["ne.jpg"] == {
            "image": "ne.jpg", "source": "retained", "truth_release_id": 104,
            "outcome": "no_evidence", "rungs_tried": [],
            "evidence_kinds": [], "candidate_ids": [],
            "replayed": False, "vision_calls": 0, "elapsed_s": 0.0,
        }
        assert by_image["ve.jpg"]["outcome"] == "error"
        assert by_image["ve.jpg"]["error_kind"] == "vision_error"
        assert by_image["ve.jpg"]["replayed"] is False
        assert by_image["ul.jpg"]["outcome"] == "unlabeled"
        assert summary.hits == 3 and summary.errors == 1
        assert summary.unlabeled == 1 and summary.no_evidence == 1
        # (i) the source run is read-only input
        after = (settings.eval_results_dir / self.RUN
                 / "results.jsonl").read_bytes()
        assert before == after

    def test_two_replays_are_identical(self, settings, monkeypatch):
        # SC-001: evidence inputs byte-identical ⇒ outcomes identical
        self.seed_source_run(settings)
        ids = iter(["20260711-999901Z-replay", "20260711-999902Z-replay"])
        monkeypatch.setattr(
            "collection_agent.eval.harness._run_id", lambda source: next(ids)
        )
        outcomes = []
        for _ in range(2):
            run_dir, _ = run_replay(
                self.scripted_client(), settings, replay_of=self.RUN
            )
            outcomes.append(
                [(r["image"], r["outcome"], r.get("rung"))
                 for r in read_results(run_dir)]
            )
        assert outcomes[0] == outcomes[1]

    def test_replay_of_a_replay_is_legal(self, settings):
        # amendment delta 2: replay records carry evidence, so a replay is
        # itself replayable and yields the same outcomes
        self.seed_source_run(settings)
        first_dir, first = run_replay(
            self.scripted_client(), settings, replay_of=self.RUN
        )
        second_dir, second = run_replay(
            self.scripted_client(), settings, replay_of=first_dir.name
        )
        assert second.replay_of == first_dir.name
        assert second.hits == first.hits == 3
        # non-replayable carry-throughs stay carried (ve.jpg has no
        # evidence in the replay output either)
        by_image = {r["image"]: r for r in read_results(second_dir)}
        assert by_image["ve.jpg"]["replayed"] is False

    def test_fresh_search_failure_is_this_replays_error(self, settings):
        self.seed_source_run(settings)

        class FailingClient(FakeDiscogsClient):
            def search_releases(self, params):
                raise DiscogsServerError("Discogs 5xx after retries")

        run_dir, summary = run_replay(
            FailingClient(instances=[], details={}), settings,
            replay_of=self.RUN,
        )
        by_image = {r["image"]: r for r in read_results(run_dir)}
        assert by_image["hit.jpg"]["outcome"] == "error"
        assert by_image["hit.jpg"]["error_kind"] == "discogs_error"
        assert by_image["hit.jpg"]["replayed"] is True
        assert summary.errors_by_kind["discogs_error"] == 3
        assert summary.errors == 4  # + the carried vision_error

    def test_limit_truncates_and_flags(self, settings):
        self.seed_source_run(settings)
        run_dir, summary = run_replay(
            self.scripted_client(), settings, replay_of=self.RUN, limit=2,
        )
        assert summary.limited is True and summary.images_total == 2
        assert len(read_results(run_dir)) == 2

    def test_gate_applies_through_rematerialization(self, settings):
        # US1×US2 interlock: recorded implausible barcode is cleared by the
        # CURRENT normalization; the catno rung fires instead (SC-002 shape)
        write_run(settings, [
            source_record(image="cybotron.jpg", truth_release_id=17859,
                          outcome="miss", candidate_ids=[999],
                          rungs_tried=["barcode"],
                          evidence={"artist": "Cybotron", "catno": "D-216",
                                    "barcode": "3070"}),
            source_record(image="gate-only.jpg", truth_release_id=1,
                          outcome="miss", candidate_ids=[],
                          rungs_tried=["barcode"],
                          evidence={"barcode": "3070"}),
        ], run_id="20260711-222805Z-discogs")
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses["catno"] = payloads.search_page(
            [payloads.search_result(17859)]
        )
        run_dir, summary = run_replay(
            discogs, settings, replay_of="20260711-222805Z-discogs"
        )
        by_image = {r["image"]: r for r in read_results(run_dir)}
        cyb = by_image["cybotron.jpg"]
        assert cyb["outcome"] == "hit" and cyb["rung"] == "catno"
        assert cyb["evidence"] == {"artist": "Cybotron", "catno": "D-216"}
        assert all("barcode" not in p for p in discogs.searches)
        # evidence emptied by the gate ⇒ honest no_evidence, still replayed
        gate_only = by_image["gate-only.jpg"]
        assert gate_only["outcome"] == "no_evidence"
        assert gate_only["replayed"] is True

    def test_miss_master_relation_recomputed_from_manifest(self, settings):
        write_manifest(settings.eval_dataset_dir, [
            header(), release_line(101, ["101_secondary1.jpg"],
                                   master_id=5309),
        ])
        write_run(settings, [
            source_record(image="101_secondary1.jpg", truth_release_id=101,
                          outcome="miss", candidate_ids=[],
                          evidence={"catno": "SUB 15"}),
        ], run_id="20260711-222805Z-discogs")
        discogs = FakeDiscogsClient(instances=[], details={})
        discogs.search_responses["catno"] = payloads.search_page(
            [payloads.search_result(999, master_id=5309)]
        )
        run_dir, summary = run_replay(
            discogs, settings, replay_of="20260711-222805Z-discogs"
        )
        rec = read_results(run_dir)[0]
        assert rec["outcome"] == "miss"
        assert rec["miss_master_relation"] == "same_master"
        assert summary.misses_same_master == 1


class TestReplayCli:
    """025 T011: arg exclusion, key-free replay, config errors."""

    def _patch(self, settings, monkeypatch, client=None):
        from collection_agent import cli

        monkeypatch.setattr(cli, "load_settings", lambda: settings)
        monkeypatch.setattr(
            "collection_agent.discogs.client.DiscogsClient",
            lambda *a, **k: client or FakeDiscogsClient(
                instances=[], details={}
            ),
        )
        return cli

    def test_replay_and_source_together_exit_config(self, settings, monkeypatch):
        cli = self._patch(settings, monkeypatch)
        assert cli.main(
            ["eval-run", "--replay", "x", "--source", "discogs"]
        ) == cli.EXIT_CONFIG

    def test_replay_needs_no_openai_key(self, settings, monkeypatch):
        # settings fixture carries no OPENAI_API_KEY: camera mode refuses,
        # replay runs (FR-001 — vision-free by construction)
        write_run(settings, [source_record()])
        client = FakeDiscogsClient(instances=[], details={})
        cli = self._patch(settings, monkeypatch, client=client)
        assert settings.openai_api_key is None
        assert cli.main(["eval-run"]) == cli.EXIT_CONFIG  # camera path
        assert cli.main(["eval-run", "--replay", RUN_ID]) == cli.EXIT_OK

    def test_unknown_run_id_exits_config(self, settings, monkeypatch):
        cli = self._patch(settings, monkeypatch)
        assert cli.main(
            ["eval-run", "--replay", "20990101-000000Z-discogs"]
        ) == cli.EXIT_CONFIG
        # fail-fast means no replay run dir was created
        created = [p for p in settings.eval_results_dir.iterdir()
                   if p.name.endswith("-replay")] \
            if settings.eval_results_dir.exists() else []
        assert created == []


