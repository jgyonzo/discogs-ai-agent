"""Aggregate CheckResult lists into manifest-friendly status."""
from __future__ import annotations

from typing import Iterable

from ..pipeline.manifest import CheckResult, QualityStatus


def derive_status(
    results: Iterable[CheckResult],
    *,
    has_freestanding_warnings: bool = False,
) -> QualityStatus:
    """Compute the run-level quality_checks.status.

    Inputs:
    - ``results``: per-§12 CheckResult sequence.
    - ``has_freestanding_warnings``: True if the manifest already contains
      warnings that are NOT tied to a CheckResult (e.g.,
      ``parse_releases.truncated_xml``,
      ``normalize_release_entities.unmapped_format_names``,
      ``runtime.peak_rss_exceeds_cap``). Per the manifest contract,
      these still flip the status to ``passed_with_warnings``.

    Precedence: any critical-failed check forces ``failed``; otherwise
    any warning-failed check OR any free-standing warning yields
    ``passed_with_warnings``; otherwise ``passed``.
    """
    has_critical_fail = False
    has_warning_fail = False
    for r in results:
        if not r.passed:
            if r.severity == "critical":
                has_critical_fail = True
            elif r.severity == "warning":
                has_warning_fail = True
    if has_critical_fail:
        return "failed"
    if has_warning_fail or has_freestanding_warnings:
        return "passed_with_warnings"
    return "passed"
