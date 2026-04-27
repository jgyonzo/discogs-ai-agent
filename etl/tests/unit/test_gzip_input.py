"""Unit tests for the gzip-aware input opener (FR-010)."""
from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from discogs_etl.io.input import ReleasesInput, open_releases_input


_PAYLOAD = b"<?xml version='1.0'?>\n<releases>\n<release id=\"1\"/>\n</releases>\n"


def test_only_uncompressed(tmp_path: Path):
    snap = tmp_path / "discogs-test"
    snap.mkdir()
    plain = snap / "releases.xml"
    plain.write_bytes(_PAYLOAD)

    ri = open_releases_input(snap)
    try:
        assert isinstance(ri, ReleasesInput)
        assert ri.is_gzipped is False
        assert ri.gz_and_plain_present is False
        assert ri.source_path == plain
        assert ri.file_obj.read() == _PAYLOAD
    finally:
        ri.file_obj.close()


def test_only_gzipped(tmp_path: Path):
    snap = tmp_path / "discogs-test"
    snap.mkdir()
    gz = snap / "releases.xml.gz"
    with gzip.open(gz, "wb") as f:
        f.write(_PAYLOAD)

    ri = open_releases_input(snap)
    try:
        assert ri.is_gzipped is True
        assert ri.gz_and_plain_present is False
        assert ri.source_path == gz
        # The bytes streaming through the GzipFile must round-trip the
        # uncompressed source byte-for-byte.
        assert ri.file_obj.read() == _PAYLOAD
    finally:
        ri.file_obj.close()


def test_both_present_uncompressed_wins(tmp_path: Path):
    snap = tmp_path / "discogs-test"
    snap.mkdir()
    plain = snap / "releases.xml"
    plain.write_bytes(_PAYLOAD)
    gz = snap / "releases.xml.gz"
    with gzip.open(gz, "wb") as f:
        f.write(_PAYLOAD)

    ri = open_releases_input(snap)
    try:
        assert ri.is_gzipped is False
        assert ri.gz_and_plain_present is True
        assert ri.source_path == plain
    finally:
        ri.file_obj.close()


def test_neither_present_raises(tmp_path: Path):
    snap = tmp_path / "discogs-test"
    snap.mkdir()
    with pytest.raises(FileNotFoundError):
        open_releases_input(snap)
