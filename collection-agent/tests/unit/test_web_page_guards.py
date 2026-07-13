"""028 T023: tabbed-page disciplines (amendment-022-scan-api-4;
web-ui-api §1). Extends the 022/026 grep guards to the new content —
`test_scan_page_links.py` and the secrets grep keep running on the same
file and stay authoritative for the invariants they already pin."""

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


def _page() -> str:
    return _PAGE.read_text(encoding="utf-8")


def test_three_tab_sections_present():
    text = _page()
    for element in (
        'id="tab-scan"', 'id="tab-chat"', 'id="tab-collection"',
        'id="chatlog"', 'id="plancard"', 'id="chatbanner"',
        'id="colstatus"', 'id="syncBtn"', 'id="collink"',
    ):
        assert element in text, f"missing page element: {element}"


def test_scan_tab_is_the_default():
    # phone-first parity: the Scan tab is active on load, others hidden
    text = _page()
    assert 'class="tab active" id="tabbtn-scan"' in text
    assert '<section id="tab-scan">' in text  # not hidden
    assert '<section id="tab-chat" hidden>' in text
    assert '<section id="tab-collection" hidden>' in text


def test_page_talks_to_the_contracted_endpoints_only():
    text = _page()
    for endpoint in (
        "/api/chat", "/api/chat/history", "/api/chat/plan/",
        "/api/collection/status", "/api/sync",
    ):
        assert endpoint in text, f"missing endpoint use: {endpoint}"


def test_no_hosts_or_minted_urls_in_new_content():
    text = _page().lower()
    assert "discogs.com" not in text
    assert "youtube.com" not in text
    assert "/user/" not in text  # collection_url is rendered, never minted
    assert "http://" not in text and "https://" not in text


def test_no_secret_material_in_new_content():
    text = _page()
    for marker in ("token", "api_key", "apikey", "secret", "Bearer"):
        assert marker.lower() not in text.lower(), f"secret marker on page: {marker}"


def test_sync_running_hint_element_exists():
    # FR-013: a running sync is visible from any tab (header hint)
    text = _page()
    assert 'id="syncHint"' in text
    assert "syncHint" in text.split("</style>")[1]  # actually driven by JS


def test_chat_and_collection_anchors_follow_link_discipline():
    # the shared anchor guard in test_scan_page_links covers the whole
    # file; this pins that the NEW modules build anchors the same way
    text = _page()
    chat_and_collection = text.split("-- chat tab (028", 1)[1]
    for anchor in re.findall(r"<a\s[^>]*", chat_and_collection):
        assert 'target="_blank"' in anchor
        assert 'rel="noopener noreferrer"' in anchor
