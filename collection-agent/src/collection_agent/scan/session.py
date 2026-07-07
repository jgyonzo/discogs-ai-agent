"""In-memory scan session (022, data-model.md).

One per server run. Owns the seen-candidate allowlist (the write gate's
"only server-served candidates can be added" — research R9), the
session-added overlay for duplicate status, and the in-memory log mirrored
to the append-only journal with every recorded outcome.
"""

from __future__ import annotations

from datetime import datetime, timezone

from collection_agent.scan.journal import ScanJournal
from collection_agent.scan.models import Outcome, ScanCycleOutcome, Source


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ScanSession:
    def __init__(self, journal: ScanJournal, clock=_utc_now):
        self._clock = clock
        self.journal = journal
        self.session_id = journal.session_id
        self.seq = 0
        self.seen_release_ids: set[int] = set()
        self.added_release_ids: dict[int, int] = {}  # release_id -> copies added
        self.log: list[ScanCycleOutcome] = []
        self._closed_scan_ids: set[str] = set()

    @staticmethod
    def new_session_id(clock=_utc_now) -> str:
        return clock().strftime("%Y%m%d-%H%M%SZ")

    def next_scan_id(self) -> str:
        """Issue a cycle id for a new scan/search attempt."""
        self.seq += 1
        return f"{self.session_id}-{self.seq}"

    def register_candidates(self, release_ids: list[int]) -> None:
        self.seen_release_ids.update(release_ids)

    def is_known_candidate(self, release_id: int) -> bool:
        return release_id in self.seen_release_ids

    def record_add(self, release_id: int) -> None:
        self.added_release_ids[release_id] = (
            self.added_release_ids.get(release_id, 0) + 1
        )

    def is_closed(self, scan_id: str) -> bool:
        """True once a terminal outcome was journaled for this cycle
        (makes /api/skip idempotent per scan_id)."""
        return scan_id in self._closed_scan_ids

    def record_outcome(
        self,
        scan_id: str,
        outcome: Outcome,
        source: Source,
        evidence_kinds: list[str] | None = None,
        release_id: int | None = None,
        release_title: str | None = None,
        instance_id: int | None = None,
        duplicate_add: bool = False,
        detail: str | None = None,
        evidence: dict | None = None,
    ) -> ScanCycleOutcome:
        """Append one completed-cycle outcome to journal + log (together;
        journal failure propagates so the caller reports the cycle failed)."""
        entry = ScanCycleOutcome(
            ts=self._clock().strftime("%Y-%m-%dT%H:%M:%SZ"),
            seq=len(self.log) + 1,
            scan_id=scan_id,
            outcome=outcome,
            source=source,
            evidence_kinds=evidence_kinds or [],
            release_id=release_id,
            release_title=release_title,
            instance_id=instance_id,
            duplicate_add=duplicate_add,
            detail=detail,
            evidence=evidence or None,
        )
        self.journal.append(entry)  # journal first: log never lies about disk
        self.log.append(entry)
        self._closed_scan_ids.add(scan_id)
        return entry
