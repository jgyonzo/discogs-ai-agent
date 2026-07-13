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


def test_chat_working_indicator_and_link_rendering():
    """Replay addendum 2 (2026-07-12 live validation): no feedback after
    submitting a prompt, and raw markdown in bubbles. Pin the wiring: a
    typing indicator is shown for turns and plan execution, and the
    linkified anchors built via createElement carry the same new-tab +
    noopener discipline as every literal anchor on the page."""
    text = _page()
    chat_module = text.split("-- chat tab (028", 1)[1].split("-- collection tab", 1)[0]
    assert "showWorking" in chat_module
    assert 'showWorking("Thinking")' in chat_module
    assert 'showWorking("Executing moves")' in chat_module
    assert "msg.typing" in text  # the pulse style exists
    assert 'a.target = "_blank"' in chat_module
    assert 'a.rel = "noopener noreferrer"' in chat_module


def test_header_snapshot_badge_refreshes_after_state_changes():
    """Replay addendum 1 (2026-07-12 live validation): the header badge was
    set once at page load and kept reading "stale" after a completed sync.
    Pin the wiring: the collection module re-renders `snapstate` on every
    status load, and both the chat turn path and the scan add path ping
    the shared refresh hook."""
    text = _page()
    collection_module = text.split("-- collection tab (028", 1)[1]
    assert "snapstate" in collection_module
    assert "_refreshStatus = loadStatus" in collection_module
    chat_module = text.split("-- chat tab (028", 1)[1].split("-- collection tab", 1)[0]
    assert "_refreshStatus" in chat_module
    scan_module = text.split("-- chat tab (028", 1)[0]
    assert "_refreshStatus" in scan_module  # post-add staleness, same class


def test_chat_and_collection_anchors_follow_link_discipline():
    # the shared anchor guard in test_scan_page_links covers the whole
    # file; this pins that the NEW modules build anchors the same way
    text = _page()
    chat_and_collection = text.split("-- chat tab (028", 1)[1]
    for anchor in re.findall(r"<a\s[^>]*", chat_and_collection):
        assert 'target="_blank"' in anchor
        assert 'rel="noopener noreferrer"' in anchor
