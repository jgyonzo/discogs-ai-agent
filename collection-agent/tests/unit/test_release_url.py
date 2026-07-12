"""019 release_page_url helper: id-space invariant (release_id, never
instance_id), settings-sourced base (VII(a)), copies share one URL
(data-model §2). 026 adds the id-based core + master_page_url and the
single-URL-shape-site guard (amendment-022-scan-api-3 delta 1)."""

from __future__ import annotations

import re
from pathlib import Path

from collection_agent.settings import Settings
from collection_agent.tools.common import (
    master_page_url,
    release_page_url,
    release_page_url_for_id,
)

from tests.conftest import make_record


def test_url_uses_release_id_not_instance_id(settings):
    rec = make_record(instance_id=987654321, release_id=1234)
    url = release_page_url(settings, rec)
    assert url == "https://www.discogs.com/release/1234"
    assert "987654321" not in url


def test_base_url_comes_from_settings(tmp_path):
    settings = Settings(
        _env_file=None,
        DISCOGS_USER_TOKEN="test-token-not-real",
        SNAPSHOT_PATH=tmp_path / "snapshot.json",
        DISCOGS_WEB_BASE_URL="https://web.example.test",
    )
    rec = make_record(instance_id=7, release_id=42)
    assert release_page_url(settings, rec) == "https://web.example.test/release/42"


def test_default_web_base_differs_from_api_base(settings):
    assert settings.discogs_web_base_url == "https://www.discogs.com"
    assert settings.discogs_base_url == "https://api.discogs.com"


def test_trailing_slash_in_base_is_tolerated(tmp_path):
    settings = Settings(
        _env_file=None,
        DISCOGS_USER_TOKEN="test-token-not-real",
        SNAPSHOT_PATH=tmp_path / "snapshot.json",
        DISCOGS_WEB_BASE_URL="https://www.discogs.com/",
    )
    rec = make_record(instance_id=7, release_id=42)
    assert release_page_url(settings, rec) == "https://www.discogs.com/release/42"


def test_copies_of_same_release_share_url(settings):
    a = make_record(instance_id=1, release_id=500)
    b = make_record(instance_id=2, release_id=500)
    assert release_page_url(settings, a) == release_page_url(settings, b)


# -- 026: id-based core + master_page_url ------------------------------------


def test_record_helper_delegates_to_id_core(settings):
    rec = make_record(instance_id=7, release_id=42)
    assert release_page_url(settings, rec) == release_page_url_for_id(settings, 42)


def test_master_page_url_shape(settings):
    assert master_page_url(settings, 5309) == "https://www.discogs.com/master/5309"


def test_master_page_url_base_from_settings(tmp_path):
    settings = Settings(
        _env_file=None,
        DISCOGS_USER_TOKEN="test-token-not-real",
        SNAPSHOT_PATH=tmp_path / "snapshot.json",
        DISCOGS_WEB_BASE_URL="https://web.example.test/",
    )
    assert master_page_url(settings, 9) == "https://web.example.test/master/9"


def test_url_shapes_have_exactly_one_code_site_each():
    """020-precedent grep guard: the f-string URL shapes live ONLY in
    tools/common.py — every other module (scan/search.py included) must
    call the builders, never re-mint the shape."""
    src_root = (
        Path(__file__).resolve().parents[2] / "src" / "collection_agent"
    )
    release_sites: list[Path] = []
    master_sites: list[Path] = []
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"/release/\{", text):
            release_sites.append(path)
        if re.search(r"/master/\{", text):
            master_sites.append(path)
    assert [p.name for p in release_sites] == ["common.py"], release_sites
    assert [p.name for p in master_sites] == ["common.py"], master_sites
