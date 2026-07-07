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


class EvalItem(BaseModel):
    """One image to evaluate (built by eval/sources.py)."""

    image_path: Path
    mime: str
    truth_release_id: int | None  # None = unlabeled (retained source only)
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
    error_kind: ErrorKind | None = None
    detail: str | None = None
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
    vision_calls: int
    limited: bool
    dataset_snapshot_completeness: str | None = None


def score_search_outcome(
    truth_release_id: int, candidate_ids: list[int], rungs_tried: list[str]
) -> dict:
    """Hit/miss + rank + producing rung for one completed pipeline pass."""
    rung = rungs_tried[-1] if candidate_ids and rungs_tried else None
    if truth_release_id in candidate_ids:
        return {
            "outcome": "hit",
            "rank": candidate_ids.index(truth_release_id) + 1,
            "rung": rung,
        }
    return {"outcome": "miss", "rank": None, "rung": rung}


def summarize(
    results: list[EvalResult],
    run_id: str,
    source: SourceName,
    limited: bool,
    dataset_snapshot_completeness: str | None = None,
) -> EvalSummary:
    counts = {o: 0 for o in ("hit", "miss", "no_evidence", "error", "unlabeled")}
    hits_by_rung: dict[str, int] = {}
    errors_by_kind: dict[str, int] = {}
    top1 = 0
    vision_calls = 0
    for r in results:
        counts[r.outcome] += 1
        vision_calls += r.vision_calls
        if r.outcome == "hit":
            hits_by_rung[r.rung or "unknown"] = hits_by_rung.get(r.rung or "unknown", 0) + 1
            if r.rank == 1:
                top1 += 1
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
        vision_calls=vision_calls,
        limited=limited,
        dataset_snapshot_completeness=dataset_snapshot_completeness,
    )
