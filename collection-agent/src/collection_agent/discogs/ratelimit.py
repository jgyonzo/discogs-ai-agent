"""Header-driven Discogs rate-limit governor (contracts/discogs-consumption.md §4).

Discogs throttles per source IP over a 60-second moving window and reports
the budget on every response:

    X-Discogs-Ratelimit            total allowed per window
    X-Discogs-Ratelimit-Used       used in the current window
    X-Discogs-Ratelimit-Remaining  remaining in the current window

Policy:
- After every response, ingest the headers.
- Before every request, if the last-known remaining budget is at or below
  the settings-sourced floor, pace: sleep long enough for the moving window
  to free budget instead of slamming into a 429.
- On an actual 429, exponential backoff with jitter (base 2 s, cap 60 s),
  surfacing a "throttled, continuing…" notice — never a failure.

`sleep_fn`/`rand_fn` are injectable so tests never actually sleep.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping

BACKOFF_BASE_S = 2.0
BACKOFF_CAP_S = 60.0
WINDOW_S = 60.0


class RateLimitGovernor:
    def __init__(
        self,
        floor: int = 2,
        notify: Callable[[str], None] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        rand_fn: Callable[[], float] = random.random,
    ):
        self.floor = max(0, floor)
        self._notify = notify or (lambda _msg: None)
        self._sleep = sleep_fn
        self._rand = rand_fn
        self._limit: int | None = None
        self._remaining: int | None = None
        self._consecutive_429 = 0

    # -- observability -----------------------------------------------------
    @property
    def limit(self) -> int | None:
        return self._limit

    @property
    def remaining(self) -> int | None:
        return self._remaining

    # -- lifecycle hooks ----------------------------------------------------
    def before_request(self) -> None:
        """Pace when the known remaining budget is at/below the floor."""
        if self._remaining is None or self._limit is None:
            return  # no signal yet — first request
        if self._remaining > self.floor:
            return
        # The window is a 60 s moving average: one request's budget frees up
        # roughly every WINDOW_S / limit seconds. Sleep enough slots to climb
        # back above the floor (bounded — this is pacing, not backoff).
        slots = (self.floor - self._remaining) + 1
        delay = min((WINDOW_S / max(self._limit, 1)) * slots, 10.0)
        self._notify(
            f"rate limit budget low ({self._remaining}/{self._limit}); "
            f"pacing {delay:.1f}s…"
        )
        self._sleep(delay)

    def after_response(self, headers: Mapping[str, str]) -> None:
        """Ingest X-Discogs-Ratelimit* headers (case-insensitive mapping)."""
        limit = _int_header(headers, "X-Discogs-Ratelimit")
        remaining = _int_header(headers, "X-Discogs-Ratelimit-Remaining")
        if limit is not None:
            self._limit = limit
        if remaining is not None:
            self._remaining = remaining
        self._consecutive_429 = 0

    def on_429(self) -> float:
        """Exponential backoff with jitter; returns the delay actually slept."""
        self._consecutive_429 += 1
        delay = min(
            BACKOFF_BASE_S * (2 ** (self._consecutive_429 - 1)), BACKOFF_CAP_S
        )
        delay = delay * (0.5 + self._rand() / 2)  # jitter in [0.5x, 1.0x]
        self._notify(f"throttled by Discogs (429), continuing in {delay:.1f}s…")
        self._sleep(delay)
        return delay


def _int_header(headers: Mapping[str, str], name: str) -> int | None:
    # httpx headers are case-insensitive; plain dicts in tests may not be.
    raw = headers.get(name) or headers.get(name.lower())
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
