"""Evidence-replay source for the eval harness (025 US1,
contracts/amendment-023-eval-results-2.md).

A replay re-evaluates a prior run's per-image records using ONLY locally
recorded data: the 024 `evidence` field is both the replayability
predicate and the ladder input, and `truth_release_id` is the scoring
truth. No images are read, no vision/LLM call is ever made, and the
source run directory is read-only input. Reader tolerance mirrors the
023 manifest reader: a torn TRAILING line (interrupted append) is
skipped; any other undecodable line is corrupt input and fails fast —
never guessed around. Truth master ids are re-resolved from the local
dataset manifest when it exists (the relation depends on the FRESH
candidates, so it can never be copied from the source record); a
missing/corrupt manifest degrades to `unknown` buckets, and retained-
source records never get masters (023/024 FR-014 rule).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, model_validator

from collection_agent.eval.dataset import (
    DatasetError,
    load_manifest,
    newest_release_lines,
)
from collection_agent.eval.scoring import Outcome, SourceName
from collection_agent.eval.sources import SourceError
from collection_agent.settings import Settings


class ReplayItem(BaseModel):
    """One unit of replay work (data-model.md §2): either replayable
    (`evidence` set — the ladder re-runs) or carried through
    (`carry_outcome` set — the original category is preserved, no search
    work). Exactly one of the two is set."""

    image: str
    source: SourceName
    truth_release_id: int | None = None
    truth_master_id: int | None = None
    evidence: dict | None = None
    carry_outcome: Outcome | None = None
    carry_error_kind: str | None = None
    carry_detail: str | None = None

    @model_validator(mode="after")
    def _replayable_xor_carried(self) -> "ReplayItem":
        if (self.evidence is None) == (self.carry_outcome is None):
            raise ValueError(
                "a ReplayItem carries either evidence or a carry-through "
                "outcome, never both and never neither"
            )
        return self


def _parse_records(results_path: Path, run_id: str) -> list[dict]:
    """JSONL records; blank lines skipped, torn trailing line tolerated,
    anything else corrupt (analysis U1: corrupt ≠ interrupted)."""
    lines = results_path.read_text(encoding="utf-8").splitlines()
    records: list[dict] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            if not isinstance(raw, dict) or not raw.get("image") or not raw.get("source"):
                raise ValueError("record lacks image/source")
        except (json.JSONDecodeError, ValueError) as exc:
            if i == len(lines) - 1:
                continue  # torn trailing line from an interrupted run
            raise SourceError(
                f"corrupt results line {i + 1} in run {run_id}: {exc}"
            ) from exc
        records.append(raw)
    return records


def _truth_masters(settings: Settings) -> dict[int, int]:
    """release_id -> master_id from the local dataset manifest
    (newest-line-wins). Absent or unreadable manifest degrades to {} —
    miss buckets fall back to `unknown`, never guessed (R5)."""
    try:
        entries = load_manifest(settings.eval_dataset_dir)
    except DatasetError:
        return {}
    return {
        rid: line.master_id
        for rid, line in newest_release_lines(entries).items()
        if line.master_id
    }


def _to_item(record: dict, masters: dict[int, int]) -> ReplayItem:
    """R3 partition: evidence + truth ⇒ replayable; everything else is
    carried through under its original outcome category."""
    source = record["source"]
    truth = record.get("truth_release_id")
    base = {
        "image": record["image"],
        "source": source,
        "truth_release_id": truth,
    }
    evidence = record.get("evidence")
    if truth is None:
        # nothing to score against — never guessed (unlabeled rule)
        return ReplayItem(**base, carry_outcome="unlabeled")
    if evidence:
        return ReplayItem(
            **base,
            evidence=evidence,
            # retained-source records never get masters (FR-014 rule)
            truth_master_id=masters.get(truth) if source == "discogs" else None,
        )
    outcome = record.get("outcome")
    if outcome == "error":
        return ReplayItem(
            **base,
            carry_outcome="error",
            carry_error_kind=record.get("error_kind") or "vision_error",
            carry_detail="carried through from source run (not replayable: "
            "no recorded evidence)",
        )
    if outcome in ("hit", "miss"):
        # defensive: impossible in a well-formed 024 run (invariant 10) —
        # preserve the category and say so, never silently re-score
        return ReplayItem(
            **base,
            carry_outcome=outcome,
            carry_detail=f"carried through from source run: {outcome} "
            "recorded without evidence",
        )
    return ReplayItem(**base, carry_outcome="no_evidence")


def load_source_run(settings: Settings, run_id: str) -> list[ReplayItem]:
    """Parse one prior run into replay items, one per complete record
    (denominator parity, FR-003). Raises SourceError — mapped to a
    configuration-error exit by the CLI — BEFORE any run directory is
    created (fail-fast, FR-006)."""
    run_dir = settings.eval_results_dir / run_id
    results_path = run_dir / "results.jsonl"
    if not results_path.exists():
        raise SourceError(
            f"nothing to replay — no results.jsonl for run {run_id} under "
            f"{settings.eval_results_dir}"
        )
    records = _parse_records(results_path, run_id)
    if not records:
        raise SourceError(f"nothing to replay — run {run_id} has no records")
    masters = _truth_masters(settings)
    items = [_to_item(r, masters) for r in records]
    if not any(item.evidence for item in items):
        raise SourceError(
            f"nothing to replay — run {run_id} has no recorded evidence "
            "(pre-024 runs cannot be replayed)"
        )
    return items
