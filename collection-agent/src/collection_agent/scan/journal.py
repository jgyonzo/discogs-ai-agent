"""Append-only JSONL session journal (022, contracts/scan-journal-schema.md).

One file per server run: <scan_journal_dir>/<session_id>.jsonl. Each append
is flushed + fsync'd before the HTTP response is sent; an I/O failure raises
(loud, never a silent drop) and the caller reports the cycle as failed.
"""

from __future__ import annotations

import os
from pathlib import Path

from collection_agent.scan.models import ScanCycleOutcome


class JournalWriteError(Exception):
    """Raised when an outcome could not be durably appended."""


class ScanJournal:
    def __init__(self, journal_dir: Path, session_id: str):
        self._dir = journal_dir
        self.session_id = session_id
        self.path = journal_dir / f"{session_id}.jsonl"

    def append(self, outcome: ScanCycleOutcome) -> None:
        """Append one line and flush to disk; raises JournalWriteError on
        any I/O failure (the cycle must then surface as failed)."""
        line = outcome.model_dump_json(exclude_none=True)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise JournalWriteError(
                f"could not append to scan journal {self.path}: {exc}"
            ) from exc
