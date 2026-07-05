"""Snapshot persistence (contracts/snapshot-schema.md).

- Atomic writes: serialize to `<path>.tmp`, then `os.replace` — a crash
  mid-write can never corrupt an existing snapshot.
- Enrichment journal at `<path>.sync.tmp.json`: release_id → enrichment
  fields, written incrementally during sync so an interrupted sync resumes
  instead of restarting.
- Completeness lifecycle: complete | partial | stale (see data-model.md
  state machine). A partial snapshot is never presented as complete —
  that's enforced at the serving layer (tools/common.py) using `meta`.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from collection_agent.models import Completeness, Snapshot


class SnapshotStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.journal_path = self.path.with_name(self.path.name + ".sync.tmp.json")

    # -- snapshot ------------------------------------------------------------

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> Snapshot | None:
        """Load + validate; returns None when no snapshot exists."""
        if not self.path.exists():
            return None
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return Snapshot.model_validate(raw)

    def save(self, snapshot: Snapshot) -> None:
        """Atomic write: tmp file + os.replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(
            snapshot.model_dump_json(indent=1), encoding="utf-8"
        )
        os.replace(tmp, self.path)

    def mark_stale(self) -> None:
        """Flip a complete snapshot to stale (after a live write succeeded)."""
        snap = self.load()
        if snap is None:
            return
        if snap.meta.completeness == Completeness.COMPLETE:
            snap.meta.completeness = Completeness.STALE
            self.save(snap)

    def patch_moved_instances(
        self, moves: list[tuple[int, int]], new_folder: tuple[int, str] | None = None
    ) -> None:
        """Patch instance→folder assignments in place after successful moves.

        moves: list of (instance_id, target_folder_id).
        new_folder: (folder_id, name) when the write created a folder.
        Keeps the snapshot `complete` (patched in place, per data-model
        state machine: "or patched in place: stays complete").
        """
        snap = self.load()
        if snap is None:
            return
        by_instance = dict(moves)
        for rec in snap.records:
            if rec.instance_id in by_instance:
                rec.folder_id = by_instance[rec.instance_id]
        if new_folder is not None:
            fid, name = new_folder
            if all(f.folder_id != fid for f in snap.folders):
                from collection_agent.models import Folder

                snap.folders.append(Folder(folder_id=fid, name=name, count=0))
        # folder counts are as-of-sync; recompute cheap ones from records
        counts: dict[int, int] = {}
        for rec in snap.records:
            counts[rec.folder_id] = counts.get(rec.folder_id, 0) + 1
        for f in snap.folders:
            if f.folder_id != 0:  # folder 0 = All (virtual)
                f.count = counts.get(f.folder_id, 0)
        self.save(snap)

    # -- enrichment journal ----------------------------------------------------

    def load_journal(self) -> dict[int, dict[str, Any]]:
        """release_id → enrichment dict from a previous (possibly interrupted) sync."""
        if not self.journal_path.exists():
            return {}
        try:
            raw = json.loads(self.journal_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}  # torn write: treat as no journal, sync re-fetches
        return {int(k): v for k, v in raw.items()}

    def save_journal(self, journal: dict[int, dict[str, Any]]) -> None:
        """Atomic journal write (same tmp+replace discipline)."""
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.journal_path.with_name(self.journal_path.name + ".tmp")
        tmp.write_text(
            json.dumps({str(k): v for k, v in journal.items()}), encoding="utf-8"
        )
        os.replace(tmp, self.journal_path)

    def clear_journal(self) -> None:
        self.journal_path.unlink(missing_ok=True)

    # -- helpers ---------------------------------------------------------------

    def sync_age(self, now: dt.datetime | None = None) -> dt.timedelta | None:
        snap = self.load()
        if snap is None:
            return None
        synced = dt.datetime.fromisoformat(snap.meta.synced_at.replace("Z", "+00:00"))
        now = now or dt.datetime.now(dt.timezone.utc)
        return now - synced


def utcnow_iso() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
