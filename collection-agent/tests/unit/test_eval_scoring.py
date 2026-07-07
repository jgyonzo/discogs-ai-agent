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
        assert s == {
            "outcome": "hit", "rank": 1, "rung": "barcode",
            "miss_master_relation": None,  # 024: relation applies to misses only
        }

    def test_hit_rank_n(self):
        s = score_search_outcome(101, [202, 303, 101], ["barcode", "catno"])
        assert s["outcome"] == "hit" and s["rank"] == 3
        # the rung that produced the list is the LAST one tried
        assert s["rung"] == "catno"

    def test_miss_with_candidates_keeps_rung(self):
        s = score_search_outcome(101, [202], ["text"])
        assert s == {
            "outcome": "miss", "rank": None, "rung": "text",
            "miss_master_relation": "unknown",  # no truth master given
        }

    def test_miss_with_no_candidates_has_no_rung(self):
        s = score_search_outcome(101, [], ["barcode", "catno", "text"])
        assert s == {
            "outcome": "miss", "rank": None, "rung": None,
            "miss_master_relation": "unknown",
        }


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


class TestMissMasterClassification:
    """024 T018 (scoring half): FR-012 matrix + invariants 8–9."""

    def test_same_master(self):
        s = score_search_outcome(
            101, [202], ["catno"],
            truth_master_id=5309, candidate_master_ids=[5309],
        )
        assert s["miss_master_relation"] == "same_master"

    def test_different(self):
        s = score_search_outcome(
            101, [202, 303], ["catno"],
            truth_master_id=5309, candidate_master_ids=[777, None],
        )
        assert s["miss_master_relation"] == "different"

    def test_unknown_when_truth_master_missing(self):
        s = score_search_outcome(
            101, [202], ["catno"],
            truth_master_id=None, candidate_master_ids=[5309],
        )
        assert s["miss_master_relation"] == "unknown"

    def test_unknown_when_no_candidate_masters(self):
        # "nothing to compare" ≠ "compared and differed"
        s = score_search_outcome(
            101, [202], ["catno"],
            truth_master_id=5309, candidate_master_ids=[None, 0],
        )
        assert s["miss_master_relation"] == "unknown"

    def test_unknown_on_zero_candidates(self):
        s = score_search_outcome(
            101, [], ["catno"], truth_master_id=5309, candidate_master_ids=[],
        )
        assert s["miss_master_relation"] == "unknown"

    def test_hit_has_no_relation(self):
        s = score_search_outcome(
            101, [101], ["catno"],
            truth_master_id=5309, candidate_master_ids=[5309],
        )
        assert s["outcome"] == "hit" and s["miss_master_relation"] is None


class TestPracticalRateInvariants:
    def test_invariants_8_and_9(self):
        results = [
            result(outcome="hit", rank=1, rung="catno"),
            result(outcome="miss", miss_master_relation="same_master"),
            result(outcome="miss", miss_master_relation="same_master"),
            result(outcome="miss", miss_master_relation="different"),
            result(outcome="miss", miss_master_relation="unknown"),
            result(outcome="no_evidence"),
        ]
        s = summarize(results, "run", "discogs", limited=False)
        # invariant 8: buckets sum to misses
        assert (s.misses_same_master + s.misses_different
                + s.misses_master_unknown == s.misses == 4)
        # practical = (1 hit + 2 same-master) / (1+4+1)
        assert s.practical_rate == 3 / 6
        # invariant 9: practical ≥ strict, equal iff no same-master misses
        assert s.practical_rate > s.identification_rate == 1 / 6

    def test_practical_equals_strict_when_no_near_misses(self):
        results = [
            result(outcome="hit", rank=1, rung="text"),
            result(outcome="miss", miss_master_relation="unknown"),
        ]
        s = summarize(results, "run", "discogs", limited=False)
        assert s.practical_rate == s.identification_rate == 0.5

    def test_023_format_records_count_as_unknown(self):
        # a record without the field (old results file) never guesses
        results = [result(outcome="miss")]
        s = summarize(results, "run", "discogs", limited=False)
        assert s.misses_master_unknown == 1 and s.practical_rate == 0.0

    def test_023_format_result_record_still_validates(self):
        # FR-008: pre-024 line shape (no evidence/miss_master_relation keys)
        old = {
            "image": "x.jpg", "source": "discogs", "truth_release_id": 1,
            "outcome": "miss", "rungs_tried": ["catno"],
            "evidence_kinds": ["catno"], "candidate_ids": [2],
            "vision_calls": 1, "elapsed_s": 1.0,
        }
        r = EvalResult.model_validate(old)
        assert r.evidence is None and r.miss_master_relation is None

    def test_023_format_summary_still_validates(self):
        s = summarize([result(outcome="hit", rank=1, rung="text")],
                      "run", "discogs", limited=False)
        old = s.model_dump()
        for key in ("misses_same_master", "misses_different",
                    "misses_master_unknown", "practical_rate"):
            old.pop(key)
        from collection_agent.eval.scoring import EvalSummary
        assert EvalSummary.model_validate(old).practical_rate is None
