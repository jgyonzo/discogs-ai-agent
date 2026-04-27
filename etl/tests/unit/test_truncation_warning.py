"""Truncation handling in ReleaseStream (FR-001 / FR-002)."""
from __future__ import annotations

from pathlib import Path

import pytest

from discogs_etl.parsers.releases_parser import ReleaseStream, TruncationInfo


_GOOD_RELEASE = """<release id="42" status="Accepted">
  <title>Truncation Test Alpha</title>
  <released>2010-01-01</released>
  <data_quality>Correct</data_quality>
</release>
"""

_GOOD_RELEASE_2 = """<release id="43" status="Accepted">
  <title>Truncation Test Bravo</title>
  <released>2011-01-01</released>
</release>
"""


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_clean_xml_yields_no_truncation_info(tmp_path: Path):
    p = tmp_path / "ok.xml"
    _write(p, "<?xml version='1.0'?>\n<releases>\n"
              + _GOOD_RELEASE + _GOOD_RELEASE_2 + "</releases>\n")
    stream = ReleaseStream(p)
    records = list(stream)
    assert len(records) == 2
    assert stream.truncation_info is None


def test_truncated_xml_stops_cleanly_after_partial_emission(tmp_path: Path):
    """Two well-formed releases followed by a third truncated mid-element."""
    p = tmp_path / "trunc.xml"
    _write(p, "<?xml version='1.0'?>\n<releases>\n"
              + _GOOD_RELEASE + _GOOD_RELEASE_2
              + '<release id="44" status="Accepted"><title>Cut sho')
    stream = ReleaseStream(p)
    records = list(stream)
    # First two parse fine; the third fails mid-element.
    assert len(records) == 2
    assert stream.truncation_info is not None
    assert isinstance(stream.truncation_info, TruncationInfo)
    assert stream.truncation_info.last_release_id == 43
    assert stream.truncation_info.error_message  # non-empty


def test_truncation_with_zero_complete_releases(tmp_path: Path):
    """Even when no release is fully emitted, the parser must not raise."""
    p = tmp_path / "trunc_first.xml"
    _write(p, "<?xml version='1.0'?>\n<releases>\n<release id=\"99\"><titl")
    stream = ReleaseStream(p)
    records = list(stream)
    assert records == []
    assert stream.truncation_info is not None
    assert stream.truncation_info.last_release_id is None


def test_iter_releases_wrapper_returns_iterable_release_stream(tmp_path: Path):
    """The backward-compat wrapper still works for `for record in iter_releases(...)`."""
    from discogs_etl.parsers.releases_parser import iter_releases
    p = tmp_path / "wrap.xml"
    _write(p, "<?xml version='1.0'?>\n<releases>\n" + _GOOD_RELEASE + "</releases>\n")
    records = list(iter_releases(p))
    assert len(records) == 1
    assert records[0]["release"]["release_id_raw"] == "42"
