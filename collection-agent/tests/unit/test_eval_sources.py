"""Eval sources (023 T016 discogs / T024 retained): manifest-labeled items,
journal-joined labels, unlabeled rules (contracts/eval-dataset.md §2, §3.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from collection_agent.eval.sources import (
    SourceError,
    load_discogs_source,
    load_retained_source,
)


# -- discogs source ----------------------------------------------------------


def write_manifest(dataset_dir: Path, lines: list[dict]) -> None:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    with (dataset_dir / "manifest.jsonl").open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")


def header(completeness: str = "complete") -> dict:
    return {
        "type": "run_header", "built_at": "2026-07-07T18:00:00Z",
        "snapshot_completeness": completeness, "images_per_release": 2,
    }


def release_line(release_id: int, files: list[str | None], status="downloaded") -> dict:
    return {
        "type": "release", "release_id": release_id, "status": status,
        "fetched_at": "2026-07-07T18:00:05Z",
        "images": [
            {
                "kind": "secondary", "source_uri": f"https://i/{release_id}-{i}",
                "file": f, "status": "downloaded" if f else "failed",
            }
            for i, f in enumerate(files)
        ],
    }


class TestDiscogsSource:
    def test_yields_only_downloaded_images_with_manifest_truth(self, settings):
        d = settings.eval_dataset_dir
        write_manifest(d, [
            header(),
            release_line(101, ["101_secondary1.jpg", None]),
            release_line(102, [], status="no_images"),
        ])
        (d / "101_secondary1.jpg").write_bytes(b"jpeg")
        items, completeness = load_discogs_source(settings)
        assert completeness == "complete"
        assert len(items) == 1
        assert items[0].truth_release_id == 101
        assert items[0].mime == "image/jpeg"
        assert items[0].source == "discogs"

    def test_manifest_file_missing_on_disk_is_skipped(self, settings):
        d = settings.eval_dataset_dir
        write_manifest(d, [
            header(),
            release_line(101, ["gone.jpg", "here.png"]),
        ])
        (d / "here.png").write_bytes(b"png")
        items, _ = load_discogs_source(settings)
        assert [i.image_path.name for i in items] == ["here.png"]
        assert items[0].mime == "image/png"

    def test_newest_header_wins(self, settings):
        d = settings.eval_dataset_dir
        write_manifest(d, [
            header("complete"),
            release_line(101, ["a.jpg"]),
            header("stale"),
        ])
        (d / "a.jpg").write_bytes(b"jpeg")
        _, completeness = load_discogs_source(settings)
        assert completeness == "stale"

    def test_missing_dataset_is_actionable(self, settings):
        with pytest.raises(SourceError, match="eval-dataset"):
            load_discogs_source(settings)

    def test_manifest_with_no_downloaded_images_is_actionable(self, settings):
        write_manifest(settings.eval_dataset_dir, [
            header(), release_line(101, [], status="no_images"),
        ])
        with pytest.raises(SourceError, match="no.*downloaded images"):
            load_discogs_source(settings)


# -- retained source ----------------------------------------------------------


def write_journal(settings, session_id: str, entries: list[dict]) -> None:
    settings.scan_journal_dir.mkdir(parents=True, exist_ok=True)
    with (settings.scan_journal_dir / f"{session_id}.jsonl").open(
        "w", encoding="utf-8"
    ) as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def add_photo(settings, session_id: str, name: str) -> Path:
    session_dir = settings.scan_retention_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    p = session_dir / name
    p.write_bytes(b"photo-bytes")
    return p


def journal_line(scan_id: str, outcome: str, release_id: int | None = None) -> dict:
    line = {
        "ts": "2026-07-07T16:02:09Z", "seq": 1, "scan_id": scan_id,
        "outcome": outcome, "source": "photo",
    }
    if release_id is not None:
        line["release_id"] = release_id
    return line


SESSION = "20260707-160209Z"


class TestRetainedSource:
    def test_confirmed_add_labels_the_photo(self, settings):
        add_photo(settings, SESSION, f"{SESSION}-1.jpg")
        write_journal(settings, SESSION, [
            journal_line(f"{SESSION}-1", "added", release_id=724223),
        ])
        items = load_retained_source(settings)
        assert items[0].truth_release_id == 724223
        assert items[0].source == "retained"
        assert items[0].meta == {"session_id": SESSION, "scan_id": f"{SESSION}-1"}

    def test_skipped_and_no_match_cycles_are_unlabeled(self, settings):
        add_photo(settings, SESSION, f"{SESSION}-1.jpg")
        add_photo(settings, SESSION, f"{SESSION}-2.jpg")
        write_journal(settings, SESSION, [
            journal_line(f"{SESSION}-1", "skipped"),
            journal_line(f"{SESSION}-2", "no_match"),
        ])
        assert [i.truth_release_id for i in load_retained_source(settings)] \
            == [None, None]

    def test_pending_photo_is_unlabeled_even_with_added_journal(self, settings):
        add_photo(settings, SESSION, "pending-1.jpg")
        write_journal(settings, SESSION, [
            journal_line(f"{SESSION}-1", "added", release_id=101),
        ])
        assert load_retained_source(settings)[0].truth_release_id is None

    def test_missing_journal_means_unlabeled(self, settings):
        add_photo(settings, SESSION, f"{SESSION}-1.jpg")
        assert load_retained_source(settings)[0].truth_release_id is None

    def test_multiple_sessions_merge(self, settings):
        other = "20260708-090000Z"
        add_photo(settings, SESSION, f"{SESSION}-1.jpg")
        add_photo(settings, other, f"{other}-1.jpg")
        write_journal(settings, SESSION, [
            journal_line(f"{SESSION}-1", "added", release_id=101),
        ])
        write_journal(settings, other, [
            journal_line(f"{other}-1", "added", release_id=202),
        ])
        items = load_retained_source(settings)
        assert sorted(i.truth_release_id for i in items) == [101, 202]

    def test_empty_retention_dir_is_actionable(self, settings):
        with pytest.raises(SourceError, match="RETAIN_PHOTOS"):
            load_retained_source(settings)
