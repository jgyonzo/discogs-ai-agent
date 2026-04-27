"""Gzip-aware input opener for the releases XML.

Detects ``releases.xml`` vs ``releases.xml.gz`` in a snapshot directory.
Per spec ``002-etl-scaleup`` and ``research.md`` R-02:
- If both files exist, the uncompressed file wins and the caller is
  notified via ``gz_and_plain_present=True`` so prepare_sources can
  emit a manifest warning.
- Detection is suffix-based; no magic-byte sniffing.
- Decompression is streaming (``gzip.GzipFile`` reads in chunks) so the
  pipeline never extracts the full file to disk.
"""
from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


@dataclass
class ReleasesInput:
    """Result of resolving the releases input in a snapshot directory."""
    file_obj: BinaryIO
    source_path: Path
    is_gzipped: bool
    gz_and_plain_present: bool


def open_releases_input(snapshot_dir: str | Path) -> ReleasesInput:
    """Resolve and open the releases XML for a snapshot directory.

    Looks for ``releases.xml`` first; falls back to ``releases.xml.gz``.
    Raises FileNotFoundError if neither is present.
    """
    snap = Path(snapshot_dir)
    plain = snap / "releases.xml"
    gz = snap / "releases.xml.gz"

    if plain.exists():
        return ReleasesInput(
            file_obj=plain.open("rb"),
            source_path=plain,
            is_gzipped=False,
            gz_and_plain_present=gz.exists(),
        )
    if gz.exists():
        return ReleasesInput(
            file_obj=gzip.GzipFile(filename=str(gz), mode="rb"),
            source_path=gz,
            is_gzipped=True,
            gz_and_plain_present=False,
        )
    raise FileNotFoundError(
        f"no releases.xml or releases.xml.gz found in {snap}"
    )
