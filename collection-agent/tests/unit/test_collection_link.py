"""028 T019: collection_page_url — 019 single-site link discipline.

The `/user/` path shape may exist at EXACTLY one src site
(tools/common.py); the page renders the server-built value verbatim."""

from __future__ import annotations

from pathlib import Path

from collection_agent.tools.common import collection_page_url

_SRC = Path(__file__).resolve().parents[2] / "src" / "collection_agent"


def test_collection_url_shape(settings):
    assert (
        collection_page_url(settings, "test_user")
        == "https://www.discogs.com/user/test_user/collection"
    )


def test_web_base_setting_is_honored_and_trailing_slash_safe(settings):
    settings = settings.model_copy(
        update={"discogs_web_base_url": "https://discogs.example/"}
    )
    assert (
        collection_page_url(settings, "u")
        == "https://discogs.example/user/u/collection"
    )


def test_user_path_shape_exists_at_exactly_one_src_site():
    offenders = []
    for path in _SRC.rglob("*.py"):
        if "/user/" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    assert offenders == ["common.py"], (
        "the /user/ URL shape must live only in tools/common.py "
        f"(collection_page_url); found in: {offenders}"
    )


def test_static_page_never_builds_the_collection_url():
    page = (_SRC / "scan" / "static" / "index.html").read_text(encoding="utf-8")
    assert "/user/" not in page  # rendered from collection_url, never minted
