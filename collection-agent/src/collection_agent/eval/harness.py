"""Eval run loop (023 US2, contracts/eval-results.md).

Per image, the PRODUCTION seams run unmodified (FR-011): scan/vision.py::
extract_evidence (the injected LLM client comes from cli._build_llm_client,
so LangSmith tracing and the vision timeout apply) then scan/search.py::
find_candidates with the explicit-`unknown` pending_duplicate_checker.
One image's failure is a recorded `error` result, never a run abort
(FR-015). Results are appended incrementally so an interrupted run keeps
every completed line; the summary lands at the end.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from collection_agent.discogs.client import DiscogsError
from collection_agent.eval.scoring import (
    EvalItem,
    EvalResult,
    EvalSummary,
    score_search_outcome,
    summarize,
)
from collection_agent.eval.sources import (
    load_discogs_source,
    load_retained_source,
)
from collection_agent.scan.search import find_candidates, pending_duplicate_checker
from collection_agent.scan.vision import VisionExtractionError, extract_evidence
from collection_agent.settings import Settings

RESULTS_NAME = "results.jsonl"
SUMMARY_NAME = "summary.json"


def _run_id(source: str) -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ") + f"-{source}"


def evaluate_item(llm_client, discogs_client, settings: Settings, item: EvalItem) -> EvalResult:
    base = {
        "image": item.image_path.name,
        "source": item.source,
        "truth_release_id": item.truth_release_id,
    }
    if item.truth_release_id is None:
        # unlabeled: reported and counted, never evaluated — zero billable
        # calls for an unscorable image (contract §2)
        return EvalResult(**base, outcome="unlabeled")

    start = time.monotonic()
    try:
        image_bytes = item.image_path.read_bytes()
        evidence = extract_evidence(llm_client, settings, image_bytes, item.mime)
    except VisionExtractionError as exc:
        return EvalResult(
            **base, outcome="error", error_kind="vision_error",
            detail=str(exc), vision_calls=1,
            elapsed_s=time.monotonic() - start,
        )
    except OSError as exc:  # unreadable file: no call was made
        return EvalResult(
            **base, outcome="error", error_kind="vision_error",
            detail=f"could not read image: {exc}",
            elapsed_s=time.monotonic() - start,
        )

    evidence_kinds = list(evidence.evidence_kinds)
    if evidence.is_empty:
        return EvalResult(
            **base, outcome="no_evidence", vision_calls=1,
            elapsed_s=time.monotonic() - start,
        )

    try:
        candidates, _more, tried = find_candidates(
            discogs_client, settings, evidence, pending_duplicate_checker
        )
    except DiscogsError as exc:
        return EvalResult(
            **base, outcome="error", error_kind="discogs_error",
            detail=str(exc), evidence_kinds=evidence_kinds, vision_calls=1,
            elapsed_s=time.monotonic() - start,
        )

    candidate_ids = [c.release_id for c in candidates]
    scored = score_search_outcome(item.truth_release_id, candidate_ids, tried)
    return EvalResult(
        **base,
        outcome=scored["outcome"],
        rank=scored["rank"],
        rung=scored["rung"],
        rungs_tried=tried,
        evidence_kinds=evidence_kinds,
        candidate_ids=candidate_ids,
        vision_calls=1,
        elapsed_s=time.monotonic() - start,
    )


def run_eval(
    llm_client,
    discogs_client,
    settings: Settings,
    source: str,
    limit: int | None = None,
    notify: Callable[[str], None] = lambda _m: None,
) -> tuple[Path, EvalSummary]:
    """Evaluate one source; returns (run_dir, summary). Raises SourceError
    (from sources.py) when there is nothing to evaluate."""
    snapshot_completeness: str | None = None
    if source == "discogs":
        items, snapshot_completeness = load_discogs_source(settings)
    else:
        items = load_retained_source(settings)

    limited = limit is not None and len(items) > limit
    if limited:
        items = items[:limit]

    run_id = _run_id(source)
    run_dir = settings.eval_results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / RESULTS_NAME

    results: list[EvalResult] = []
    with results_path.open("a", encoding="utf-8") as fh:
        for i, item in enumerate(items, start=1):
            result = evaluate_item(llm_client, discogs_client, settings, item)
            fh.write(result.model_dump_json(exclude_none=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            results.append(result)
            notify(
                f"[{i}/{len(items)}] {result.image}: {result.outcome}"
                + (f" (rank {result.rank}, {result.rung})" if result.outcome == "hit" else "")
            )

    summary = summarize(
        results, run_id, source, limited,  # type: ignore[arg-type]
        dataset_snapshot_completeness=snapshot_completeness,
    )
    (run_dir / SUMMARY_NAME).write_text(
        summary.model_dump_json(indent=1), encoding="utf-8"
    )
    return run_dir, summary
