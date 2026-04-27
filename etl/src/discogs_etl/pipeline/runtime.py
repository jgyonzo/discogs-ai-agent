"""Runtime telemetry helpers (peak RSS measurement)."""
from __future__ import annotations

import resource
import sys


def peak_rss_bytes() -> int:
    """Return the cumulative process peak RSS in bytes.

    Uses ``resource.getrusage(RUSAGE_SELF).ru_maxrss`` and normalizes the
    platform-specific unit:

    - macOS (Darwin): ``ru_maxrss`` is already bytes.
    - Linux: ``ru_maxrss`` is kilobytes (POSIX). Multiply by 1024.

    The value is monotonically non-decreasing over the life of the
    process — it tracks the high-water mark of resident memory.
    """
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(raw)
    return int(raw) * 1024
