"""Labeled-image sources for the eval harness (023, contracts/eval-dataset.md).

Two sources:
- `discogs`: the builder's manifest is the ground truth (§1–2).
- `retained`: scan photos joined lazily against the 022 session journals —
  only a journaled confirmed add labels a photo; everything else is
  `unlabeled` (§3.1). Journals are READ here, never written (the read-only
  guard forbids importing scan.journal/scan.session; the JSONL is parsed
  directly).
"""

from __future__ import annotations

import json
from pathlib import Path

from collection_agent.eval.dataset import (
    ManifestRelease,
    load_manifest,
    newest_header,
)
from collection_agent.eval.scoring import EvalItem
from collection_agent.settings import Settings

_MIME_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "heic": "image/heic",
    "heif": "image/heif",
}


class SourceError(Exception):
    """Nothing to evaluate — the CLI maps this to a configuration error."""


def _mime_for(path: Path) -> str:
    return _MIME_BY_EXT.get(path.suffix.lower().lstrip("."), "image/jpeg")


def load_discogs_source(settings: Settings) -> tuple[list[EvalItem], str | None]:
    """Manifest-labeled items + the newest header's snapshot completeness."""
    dataset_dir = settings.eval_dataset_dir
    entries = load_manifest(dataset_dir)
    if not entries:
        raise SourceError(
            f"nothing to evaluate — no dataset manifest at {dataset_dir}; "
            "build one first: python -m collection_agent eval-dataset"
        )
    header = newest_header(entries)
    items: list[EvalItem] = []
    for entry in entries:
        if not isinstance(entry, ManifestRelease):
            continue
        for image in entry.images:
            if image.status != "downloaded" or not image.file:
                continue
            path = dataset_dir / image.file
            if not path.exists():
                continue  # manifest claims it, disk disagrees — skip, never guess
            items.append(EvalItem(
                image_path=path,
                mime=_mime_for(path),
                truth_release_id=entry.release_id,
                source="discogs",
                meta={"kind": image.kind},
            ))
    if not items:
        raise SourceError(
            f"nothing to evaluate — the manifest at {dataset_dir} has no "
            "downloaded images"
        )
    return items, (header.snapshot_completeness if header else None)


def _added_release_by_scan_id(journal_path: Path) -> dict[str, int]:
    """scan_id -> release_id for journaled confirmed adds. Missing or torn
    journal content degrades to {} (photos stay unlabeled, never mislabeled)."""
    if not journal_path.exists():
        return {}
    added: dict[str, int] = {}
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if raw.get("outcome") == "added" and raw.get("release_id") is not None:
            added[str(raw.get("scan_id"))] = int(raw["release_id"])
    return added


def load_retained_source(settings: Settings) -> list[EvalItem]:
    """Retention-dir photos labeled via the session journals (§3.1)."""
    retention_dir = settings.scan_retention_dir
    if not retention_dir.exists():
        raise SourceError(
            f"nothing to evaluate — no retained photos at {retention_dir}; "
            "run a scan session with COLLECTION_AGENT_SCAN_RETAIN_PHOTOS=true"
        )
    items: list[EvalItem] = []
    for session_dir in sorted(p for p in retention_dir.iterdir() if p.is_dir()):
        session_id = session_dir.name
        added = _added_release_by_scan_id(
            settings.scan_journal_dir / f"{session_id}.jsonl"
        )
        for photo in sorted(p for p in session_dir.iterdir() if p.is_file()):
            scan_id = photo.stem
            truth = None if scan_id.startswith("pending-") else added.get(scan_id)
            items.append(EvalItem(
                image_path=photo,
                mime=_mime_for(photo),
                truth_release_id=truth,
                source="retained",
                meta={"session_id": session_id, "scan_id": scan_id},
            ))
    if not items:
        raise SourceError(
            f"nothing to evaluate — {retention_dir} contains no photos"
        )
    return items
