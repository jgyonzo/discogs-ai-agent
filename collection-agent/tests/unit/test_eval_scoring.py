"""Scoring + summary math (023 US2 T015, contracts/eval-results.md §2–3).
Pure functions — no clients, no I/O."""

from __future__ import annotations

from pathlib import Path

from collection_agent.eval.scoring import (
    EvalResult,
    score_search_outcome,
    summarize,
)


def result(**overrides) -> EvalResult:
    base = dict(
        image="x.jpg", source="discogs", truth_release_id=101,
        outcome="miss", vision_calls=1,
    )
    base.update(overrides)
    return EvalResult(**base)


class TestScoreSearchOutcome:
    def test_hit_rank_1(self):
        s = score_search_outcome(101, [101, 202], ["barcode"])
        assert s == {"outcome": "hit", "rank": 1, "rung": "barcode"}

    def test_hit_rank_n(self):
        s = score_search_outcome(101, [202, 303, 101], ["barcode", "catno"])
        assert s["outcome"] == "hit" and s["rank"] == 3
        # the rung that produced the list is the LAST one tried
        assert s["rung"] == "catno"

    def test_miss_with_candidates_keeps_rung(self):
        s = score_search_outcome(101, [202], ["text"])
        assert s == {"outcome": "miss", "rank": None, "rung": "text"}

    def test_miss_with_no_candidates_has_no_rung(self):
        s = score_search_outcome(101, [], ["barcode", "catno", "text"])
        assert s == {"outcome": "miss", "rank": None, "rung": None}


class TestSummarize:
    def test_sum_invariants(self):
        results = [
            result(outcome="hit", rank=1, rung="barcode"),
            result(outcome="hit", rank=3, rung="catno"),
            result(outcome="miss"),
            result(outcome="no_evidence"),
            result(outcome="error", error_kind="vision_error"),
            result(outcome="error", error_kind="discogs_error"),
            result(
                outcome="unlabeled", source="retained",
                truth_release_id=None, vision_calls=0,
            ),
        ]
        s = summarize(results, "run", "retained", limited=False)
        # invariant 1: categories sum to images_total
        assert (s.hits + s.misses + s.no_evidence + s.errors + s.unlabeled
                == s.images_total == 7)
        # invariant 2: evaluated excludes unlabeled
        assert s.evaluated == 6
        # invariant 3: errors excluded from the rate denominator
        assert s.identification_rate == 2 / 4
        # invariant 4: top-1 over the same denominator
        assert s.top1_rate == 1 / 4
        # invariant 5: per-rung and per-kind maps sum to their counters
        assert sum(s.hits_by_rung.values()) == s.hits == 2
        assert s.hits_by_rung == {"barcode": 1, "catno": 1}
        assert sum(s.errors_by_kind.values()) == s.errors == 2
        # cost honesty: unlabeled photos cost nothing
        assert s.vision_calls == 6

    def test_zero_denominator_rates_are_none(self):
        results = [result(outcome="error", error_kind="vision_error")]
        s = summarize(results, "run", "discogs", limited=False)
        assert s.identification_rate is None and s.top1_rate is None

    def test_empty_run_is_all_zeroes(self):
        s = summarize([], "run", "discogs", limited=False)
        assert s.images_total == 0 and s.identification_rate is None

    def test_limited_flag_and_completeness_passthrough(self):
        s = summarize(
            [result(outcome="hit", rank=1, rung="text")],
            "run", "discogs", limited=True,
            dataset_snapshot_completeness="stale",
        )
        assert s.limited is True
        assert s.dataset_snapshot_completeness == "stale"

    def test_summary_json_roundtrip(self, tmp_path: Path):
        s = summarize(
            [result(outcome="hit", rank=1, rung="barcode")],
            "run", "discogs", limited=False,
        )
        p = tmp_path / "summary.json"
        p.write_text(s.model_dump_json(indent=1), encoding="utf-8")
        from collection_agent.eval.scoring import EvalSummary

        assert EvalSummary.model_validate_json(p.read_text()) == s
