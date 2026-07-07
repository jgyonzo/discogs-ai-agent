"""Discogs-image eval dataset builder (023 US1, contracts/eval-dataset.md §1).

Walks the distinct release_ids of the local snapshot, re-fetches each
release via the already-contracted GET /releases/{id} (consuming its
`images[]` — amendment-017-discogs-consumption-2 §1), downloads up to a
settings-capped number of images per release (secondary preferred, FR-003)
through the governed client, and appends ground truth to an append-only
JSONL manifest. Resumable: finished releases are skipped, `failed` ones are
retried with fresh signed URIs (FR-005/SC-007). The manifest — never the
filename — is the authoritative label source (FR-004).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from collection_agent.discogs.client import DiscogsError
from collection_agent.settings import Settings

NOTICE_TEXT = """\
The images in this directory were downloaded from Discogs for LOCAL,
personal evaluation of the scan-identification pipeline only.

They are copyrighted by their Discogs uploaders. Do NOT commit them to any
repository, redistribute them, or serve them beyond this machine. This
directory is covered by the repository's `data/` gitignore rule
(see specs/023-scan-eval-harness/contracts/eval-dataset.md).
"""

MANIFEST_NAME = "manifest.jsonl"
NOTICE_NAME = "NOTICE.txt"


class DatasetError(Exception):
    """Build cannot proceed (no snapshot, corrupt manifest, …) — the CLI
    maps this to a configuration-error exit."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ManifestHeader(BaseModel):
    """One line per builder invocation (multiple headers are normal)."""

    type: str = "run_header"
    built_at: str
    snapshot_completeness: str
    snapshot_synced_at: str | None = None
    images_per_release: int


class ManifestImage(BaseModel):
    # `kind` is verbatim from images[].type — expected "primary"/"secondary",
    # tolerated as any string (never invented)
    kind: str
    source_uri: str
    file: str | None = None
    status: str  # "downloaded" | "failed"
    detail: str | None = None


class ManifestRelease(BaseModel):
    type: str = "release"
    release_id: int  # ground truth for every image in `images`
    status: str  # "downloaded" | "no_images" | "failed"
    images: list[ManifestImage] = Field(default_factory=list)
    fetched_at: str
    detail: str | None = None


ManifestEntry = ManifestHeader | ManifestRelease


def manifest_path(dataset_dir: Path) -> Path:
    return dataset_dir / MANIFEST_NAME


def load_manifest(dataset_dir: Path) -> list[ManifestEntry]:
    """Parse the manifest; a torn TRAILING line (crash mid-append) is
    ignored, any other unparseable line is a hard error (never guess)."""
    path = manifest_path(dataset_dir)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[ManifestEntry] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            if raw.get("type") == "run_header":
                entries.append(ManifestHeader.model_validate(raw))
            elif raw.get("type") == "release":
                entries.append(ManifestRelease.model_validate(raw))
            else:
                raise ValueError(f"unknown manifest line type: {raw.get('type')!r}")
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            if i == len(lines) - 1:
                continue  # torn trailing line from an interrupted append
            raise DatasetError(
                f"corrupt manifest line {i + 1} in {path}: {exc}"
            ) from exc
    return entries


def done_release_ids(entries: list[ManifestEntry]) -> set[int]:
    """Resume rule (contract §1.2): downloaded/no_images are done; failed
    releases are retried on the next run."""
    return {
        e.release_id
        for e in entries
        if isinstance(e, ManifestRelease) and e.status in ("downloaded", "no_images")
    }


def newest_header(entries: list[ManifestEntry]) -> ManifestHeader | None:
    headers = [e for e in entries if isinstance(e, ManifestHeader)]
    return headers[-1] if headers else None


def _append_line(path: Path, model: BaseModel) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(model.model_dump_json(exclude_none=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def select_images(images: list[dict], cap: int) -> list[dict]:
    """Secondary-preferred selection (FR-003): all secondaries first, then
    the primary, truncated to the cap. Order within a kind is Discogs'."""
    secondary = [i for i in images if i.get("type") != "primary"]
    primary = [i for i in images if i.get("type") == "primary"]
    return (secondary + primary)[:cap]


def _ext_from_uri(uri: str) -> str:
    suffix = Path(uri.split("?", 1)[0]).suffix.lower().lstrip(".")
    return suffix if suffix in ("jpg", "jpeg", "png", "webp", "gif") else "jpg"


def _process_release(
    client, dataset_dir: Path, release_id: int, cap: int
) -> ManifestRelease:
    try:
        payload = client.get_release(release_id)
    except DiscogsError as exc:
        return ManifestRelease(
            release_id=release_id, status="failed", fetched_at=_utc_now_iso(),
            detail=f"release fetch failed: {exc}",
        )
    if payload is None:
        return ManifestRelease(
            release_id=release_id, status="failed", fetched_at=_utc_now_iso(),
            detail="release not found (404)",
        )

    images = payload.get("images") or []
    if not images:
        return ManifestRelease(
            release_id=release_id, status="no_images", fetched_at=_utc_now_iso()
        )

    recorded: list[ManifestImage] = []
    ordinals: dict[str, int] = {}
    for img in select_images(images, cap):
        kind = str(img.get("type") or "secondary")
        uri = img.get("uri")
        if not uri:
            recorded.append(ManifestImage(
                kind=kind, source_uri="", status="failed", detail="image has no uri"
            ))
            continue
        try:
            data = client.download_image(uri)
            detail = None
        except DiscogsError as exc:
            data, detail = None, str(exc)
        if data is None:
            recorded.append(ManifestImage(
                kind=kind, source_uri=uri, status="failed",
                detail=detail or "download failed (expired URI or non-image payload)",
            ))
            continue
        ordinals[kind] = ordinals.get(kind, 0) + 1
        fname = f"{release_id}_{kind}{ordinals[kind]}.{_ext_from_uri(uri)}"
        # atomic write: a crash never leaves a corrupt image beside a
        # manifest claim (the manifest line lands only after the rename)
        tmp = dataset_dir / (fname + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dataset_dir / fname)
        recorded.append(ManifestImage(
            kind=kind, source_uri=uri, file=fname, status="downloaded"
        ))

    status = (
        "downloaded"
        if any(r.status == "downloaded" for r in recorded)
        else "failed"
    )
    return ManifestRelease(
        release_id=release_id, status=status, images=recorded,
        fetched_at=_utc_now_iso(),
    )


def build_dataset(
    client,
    store,
    settings: Settings,
    limit: int | None = None,
    images_per_release: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    """Run one build; returns counters for the CLI summary. Raises
    DatasetError when there is no snapshot to derive a worklist from."""
    snapshot = store.load()
    if snapshot is None:
        raise DatasetError(
            "no snapshot — run `python -m collection_agent sync` first"
        )
    cap = (
        images_per_release
        if images_per_release is not None
        else settings.eval_images_per_release
    )

    dataset_dir = settings.eval_dataset_dir
    dataset_dir.mkdir(parents=True, exist_ok=True)
    notice = dataset_dir / NOTICE_NAME
    if not notice.exists():
        notice.write_text(NOTICE_TEXT, encoding="utf-8")

    entries = load_manifest(dataset_dir)
    done = done_release_ids(entries)
    all_ids = sorted({r.release_id for r in snapshot.records})
    todo = [rid for rid in all_ids if rid not in done]
    if limit is not None:
        todo = todo[:limit]

    mpath = manifest_path(dataset_dir)
    _append_line(mpath, ManifestHeader(
        built_at=_utc_now_iso(),
        snapshot_completeness=snapshot.meta.completeness.value,
        snapshot_synced_at=snapshot.meta.synced_at,
        images_per_release=cap,
    ))

    stats = {
        "releases_total": len(all_ids),
        "skipped_done": len(all_ids) - len([r for r in all_ids if r not in done]),
        "processed": 0,
        "downloaded": 0,
        "no_images": 0,
        "failed": 0,
        "images_downloaded": 0,
    }
    for i, rid in enumerate(todo, start=1):
        line = _process_release(client, dataset_dir, rid, cap)
        _append_line(mpath, line)
        stats["processed"] += 1
        stats[line.status] += 1
        stats["images_downloaded"] += sum(
            1 for img in line.images if img.status == "downloaded"
        )
        if on_progress is not None:
            on_progress(i, len(todo))
    return stats
