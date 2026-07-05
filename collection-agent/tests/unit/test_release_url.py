"""019 release_page_url helper: id-space invariant (release_id, never
instance_id), settings-sourced base (VII(a)), copies share one URL
(data-model §2)."""

from __future__ import annotations

from collection_agent.settings import Settings
from collection_agent.tools.common import release_page_url

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
