"""Cadence-aware progress reporter for per-iteration steps."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass


@dataclass
class ProgressMetrics:
    elapsed_seconds: float
    releases_per_sec: float
    n_done: int


class ProgressReporter:
    """Logs progress every ``cadence`` iterations with elapsed + instant rate.

    Usage:
        reporter = ProgressReporter(logger, "parse_releases", cadence=10000)
        for i, item in enumerate(stream, start=1):
            ...
            reporter.report_iteration(i)
        metrics = reporter.final()  # also emits a final summary line
    """

    def __init__(self, logger: logging.Logger, step_name: str, cadence: int) -> None:
        self.logger = logger
        self.step_name = step_name
        self.cadence = max(1, int(cadence))
        self._t_start = time.monotonic()
        self._t_last = self._t_start
        self._n_last = 0
        self._n_seen = 0

    def report_iteration(self, n_done: int) -> None:
        """Call after each successful iteration with the running total."""
        self._n_seen = n_done
        if n_done % self.cadence != 0:
            return
        now = time.monotonic()
        elapsed = now - self._t_start
        delta_n = n_done - self._n_last
        delta_t = max(now - self._t_last, 1e-9)
        instant_rate = delta_n / delta_t
        self.logger.info(
            "%s progress: n=%d elapsed=%.2fs rate=%.0f/s",
            self.step_name, n_done, elapsed, instant_rate,
        )
        self._t_last = now
        self._n_last = n_done

    def final(self) -> ProgressMetrics:
        """Emit a final summary line and return ProgressMetrics for the manifest."""
        elapsed = max(time.monotonic() - self._t_start, 1e-9)
        rate = self._n_seen / elapsed if self._n_seen > 0 else 0.0
        self.logger.info(
            "%s progress: final n=%d elapsed=%.2fs avg_rate=%.0f/s",
            self.step_name, self._n_seen, elapsed, rate,
        )
        return ProgressMetrics(
            elapsed_seconds=elapsed,
            releases_per_sec=rate,
            n_done=self._n_seen,
        )
