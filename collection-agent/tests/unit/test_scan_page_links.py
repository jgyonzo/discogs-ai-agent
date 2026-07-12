"""026 T009/T011: scan-page link discipline (amendment-022-scan-api-3
delta 1, FR-007/009).

The page renders ONLY server-built `*_page_url` fields — it never mints a
Discogs URL from an identifier (019's invented-URL incident class), every
outbound anchor opens a new tab with noopener, and link/add affordances
are structurally distinct (anchors navigate, buttons never do).
"""

from __future__ import annotations

import re
from pathlib import Path

_PAGE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "collection_agent"
    / "scan"
    / "static"
    / "index.html"
)


def _page_text() -> str:
    return _PAGE.read_text(encoding="utf-8")


def test_no_hardcoded_discogs_host():
    # VII(a): the web base lives in settings (DISCOGS_WEB_BASE_URL), served
    # inside the link fields — the static page must not know the host
    assert "discogs.com" not in _page_text().lower()


def test_no_client_side_url_minting():
    # the page must never assemble /release/{id} or /master/{id} itself —
    # any such fragment means an identifier is being pasted into a URL
    text = _page_text()
    assert "/release/" not in text
    assert "/master/" not in text


def test_page_renders_only_server_built_link_fields():
    text = _page_text()
    assert "release_page_url" in text
    assert "master_page_url" in text


def test_every_anchor_is_new_tab_noopener():
    text = _page_text()
    anchors = re.findall(r"<a\s[^>]*", text)
    assert anchors, "expected outbound anchors on the page"
    for a in anchors:
        assert 'target="_blank"' in a, a
        assert 'rel="noopener noreferrer"' in a, a


def test_buttons_never_navigate():
    text = _page_text()
    for btn in re.findall(r"<button\s[^>]*", text):
        assert "href" not in btn, btn
    # no scripted navigation paths either — links are real anchors only
    assert "window.open" not in text
    assert "location.assign" not in text
    assert "location.href" not in text
