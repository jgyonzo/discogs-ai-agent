"""Pure eval scoring + summary math (023 US2, contracts/eval-results.md §2–3).

No I/O, no clients — everything here is unit-testable offline. The summary
sum invariants are normative: hits + misses + no_evidence + errors +
unlabeled == images_total; errors are excluded from the identification-rate
denominator (provider unavailability is not a pipeline miss) but always
reported beside it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

SourceName = Literal["discogs", "retained"]
Outcome = Literal["hit", "miss", "no_evidence", "error", "unlabeled"]
ErrorKind = Literal["vision_error", "discogs_error"]
# 024: per-miss master relation — `unknown` covers BOTH "truth master
# unknown" and "no candidate masters to compare" (incl. zero candidates):
# "nothing to compare" is not the same claim as "compared and differed"
MasterRelation = Literal["same_master", "different", "unknown"]


class EvalItem(BaseModel):
    """One image to evaluate (built by eval/sources.py)."""

    image_path: Path
    mime: str
    truth_release_id: int | None  # None = unlabeled (retained source only)
    # 024: manifest ground truth; always None for the retained source (FR-014)
    truth_master_id: int | None = None
    source: SourceName
    meta: dict = Field(default_factory=dict)


class EvalResult(BaseModel):
    """One results.jsonl line (contract §2)."""

    image: str
    source: SourceName
    truth_release_id: int | None = None
    outcome: Outcome
    rank: int | None = None  # 1-based, set iff hit
    rung: str | None = None  # rung that produced the candidate list
    rungs_tried: list[str] = Field(default_factory=list)
    evidence_kinds: list[str] = Field(default_factory=list)
    candidate_ids: list[int] = Field(default_factory=list)
    # 024: set iff outcome == "miss" (amendment-023-eval-results §1)
    miss_master_relation: MasterRelation | None = None
    error_kind: ErrorKind | None = None
    detail: str | None = None
    # 024 (amendment-023-eval-results §1): compact extracted-evidence values,
    # byte-identical shape to the scan journal's `evidence` (022 FR-021) —
    # present iff a vision call produced non-empty evidence, so a
    # zero-candidate miss is diagnosable from the results file alone
    evidence: dict | None = None
    # 025 (amendment-023-eval-results-2 §3): present on EVERY record of a
    # replay run (True = ladder re-ran over recorded evidence, False =
    # carried through); absent on camera runs — invariant 12
    replayed: bool | None = None
    vision_calls: int = 0
    elapsed_s: float = 0.0


class EvalSummary(BaseModel):
    """summary.json (contract §3)."""

    run_id: str
    source: SourceName
    images_total: int
    evaluated: int
    hits: int
    misses: int
    no_evidence: int
    errors: int
    unlabeled: int
    identification_rate: float | None
    top1_rate: float | None
    hits_by_rung: dict[str, int]
    errors_by_kind: dict[str, int]
    # 024 (amendment-023-eval-results §2): miss split + practical rate.
    # Defaults keep 023-format summary files readable.
    misses_same_master: int = 0
    misses_different: int = 0
    misses_master_unknown: int = 0
    practical_rate: float | None = None
    vision_calls: int
    limited: bool
    dataset_snapshot_completeness: str | None = None
    # 025 (amendment-023-eval-results-2 §4): source run id, present iff the
    # run is a replay. Default keeps 023/024-format summaries readable.
    replay_of: str | None = None


def classify_miss_master(
    truth_master_id: int | None, candidate_master_ids: list[int | None]
) -> str:
    """024 FR-012 — pure local comparison, never a network request."""
    if truth_master_id is None:
        return "unknown"
    masters = [m for m in candidate_master_ids if m]
    if not masters:
        return "unknown"  # nothing to compare ≠ compared and differed
    return "same_master" if truth_master_id in masters else "different"


def score_search_outcome(
    truth_release_id: int,
    candidate_ids: list[int],
    rungs_tried: list[str],
    truth_master_id: int | None = None,
    candidate_master_ids: list[int | None] | None = None,
) -> dict:
    """Hit/miss + rank + producing rung for one completed pipeline pass;
    misses additionally carry their master relation (024)."""
    rung = rungs_tried[-1] if candidate_ids and rungs_tried else None
    if truth_release_id in candidate_ids:
        return {
            "outcome": "hit",
            "rank": candidate_ids.index(truth_release_id) + 1,
            "rung": rung,
            "miss_master_relation": None,
        }
    return {
        "outcome": "miss",
        "rank": None,
        "rung": rung,
        "miss_master_relation": classify_miss_master(
            truth_master_id, candidate_master_ids or []
        ),
    }


def summarize(
    results: list[EvalResult],
    run_id: str,
    source: SourceName,
    limited: bool,
    dataset_snapshot_completeness: str | None = None,
    replay_of: str | None = None,
) -> EvalSummary:
    counts = {o: 0 for o in ("hit", "miss", "no_evidence", "error", "unlabeled")}
    hits_by_rung: dict[str, int] = {}
    errors_by_kind: dict[str, int] = {}
    miss_relations = {"same_master": 0, "different": 0, "unknown": 0}
    top1 = 0
    vision_calls = 0
    for r in results:
        counts[r.outcome] += 1
        vision_calls += r.vision_calls
        if r.outcome == "hit":
            hits_by_rung[r.rung or "unknown"] = hits_by_rung.get(r.rung or "unknown", 0) + 1
            if r.rank == 1:
                top1 += 1
        if r.outcome == "miss":
            # 023-format records lack the field — count as unknown, never guess
            miss_relations[r.miss_master_relation or "unknown"] += 1
        if r.outcome == "error":
            kind = r.error_kind or "vision_error"
            errors_by_kind[kind] = errors_by_kind.get(kind, 0) + 1

    denominator = counts["hit"] + counts["miss"] + counts["no_evidence"]
    return EvalSummary(
        run_id=run_id,
        source=source,
        images_total=len(results),
        evaluated=counts["hit"] + counts["miss"] + counts["no_evidence"] + counts["error"],
        hits=counts["hit"],
        misses=counts["miss"],
        no_evidence=counts["no_evidence"],
        errors=counts["error"],
        unlabeled=counts["unlabeled"],
        identification_rate=(counts["hit"] / denominator) if denominator else None,
        top1_rate=(top1 / denominator) if denominator else None,
        hits_by_rung=hits_by_rung,
        errors_by_kind=errors_by_kind,
        misses_same_master=miss_relations["same_master"],
        misses_different=miss_relations["different"],
        misses_master_unknown=miss_relations["unknown"],
        # invariant 9: ≥ strict rate, equal iff no same-master near-misses
        practical_rate=(
            (counts["hit"] + miss_relations["same_master"]) / denominator
            if denominator else None
        ),
        vision_calls=vision_calls,
        limited=limited,
        dataset_snapshot_completeness=dataset_snapshot_completeness,
        replay_of=replay_of,
    )
