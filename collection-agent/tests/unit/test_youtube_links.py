"""020 youtube_links helpers: deterministic id parsing (accepted URL
shapes, defensive rejects), single-source URL builder (settings base,
order preserved)."""

from __future__ import annotations

import pytest

from collection_agent.youtube_links import (
    build_watch_videos_url,
    chunk_record_videos,
    video_id_from_uri,
)

VID = "dQw4w9WgXcQ"  # canonical 11-char id


# --- parser: accepted shapes -------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://www.youtube.com/watch?v={VID}&signature=DO-NOT-TOUCH&t=42",
        f"https://youtube.com/watch?list=PL123&v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://music.youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?t=30",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube.com/live/{VID}",
        f"  https://www.youtube.com/watch?v={VID}  ",  # stray whitespace
    ],
)
def test_parser_accepts_youtube_shapes(uri):
    assert video_id_from_uri(uri) == VID


# --- parser: defensive rejects (never guess — FR-002) ------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "https://soundcloud.com/artist/track",
        "https://vimeo.com/12345678",
        f"https://evil.example.com/watch?v={VID}",  # id-shaped but wrong host
        "https://www.youtube.com/watch",  # no v param
        "https://www.youtube.com/watch?v=too-short",
        f"https://www.youtube.com/playlist?list={VID}",  # playlist, not video
        "https://www.youtube.com/",
        "not a uri at all",
        "",
    ],
)
def test_parser_rejects_unresolvable(uri):
    assert video_id_from_uri(uri) is None


# --- builder ------------------------------------------------------------------


def test_builder_joins_ids_in_order_on_base():
    url = build_watch_videos_url(["aaaaaaaaaaa", "bbbbbbbbbbb"], "https://www.youtube.com")
    assert url == "https://www.youtube.com/watch_videos?video_ids=aaaaaaaaaaa,bbbbbbbbbbb"


def test_builder_base_from_settings_and_trailing_slash_tolerated(settings):
    assert settings.youtube_web_base_url == "https://www.youtube.com"  # default
    url = build_watch_videos_url([VID], "https://yt.example.test/")
    assert url == f"https://yt.example.test/watch_videos?video_ids={VID}"


def test_builder_refuses_empty_list():
    with pytest.raises(ValueError):
        build_watch_videos_url([], "https://www.youtube.com")


# --- chunker (US2, FR-005) ------------------------------------------------


def ids(n: int, tag: str) -> list[str]:
    return [f"{tag}{i:010d}"[:11].ljust(11, "x") for i in range(n)]


def assert_invariants(pairs, cap, chunks):
    """Disjoint, jointly complete, ordered, ≤ cap, record-aligned."""
    flat = [v for c in chunks for _, piece in c["entries"] for v in piece]
    expected = [v for _, vids in pairs for v in vids]
    assert flat == expected  # complete + order preserved + disjoint
    for c in chunks:
        assert 1 <= c["video_count"] <= cap
        assert c["video_count"] == sum(len(p) for _, p in c["entries"])
        for rec, piece in c["entries"]:
            # record-aligned: partial pieces only for records marked split
            original = dict(pairs)[rec]
            if piece and piece != original:
                assert rec in c["split"]


def test_within_cap_is_one_chunk():
    pairs = [("a", ids(3, "a")), ("b", ids(2, "b"))]
    chunks = chunk_record_videos(pairs, cap=10)
    assert len(chunks) == 1
    assert_invariants(pairs, 10, chunks)


def test_boundary_never_splits_a_record():
    pairs = [("a", ids(3, "a")), ("b", ids(3, "b")), ("c", ids(3, "c"))]
    chunks = chunk_record_videos(pairs, cap=7)
    assert [c["video_count"] for c in chunks] == [6, 3]  # b doesn't split at 7
    assert all(c["split"] == [] for c in chunks)
    assert_invariants(pairs, 7, chunks)


def test_oversized_record_splits_with_flag_and_tail_stays_open():
    pairs = [("big", ids(12, "g")), ("after", ids(2, "f"))]
    chunks = chunk_record_videos(pairs, cap=5)
    assert [c["video_count"] for c in chunks] == [5, 5, 4]  # 2-tail + after
    assert "big" in chunks[0]["split"] and "big" in chunks[2]["split"]
    assert ("after", ids(2, "f")) in chunks[2]["entries"]
    assert_invariants(pairs, 5, chunks)


def test_zero_id_records_ride_along_without_consuming_capacity():
    pairs = [("a", ids(2, "a")), ("dup", []), ("b", ids(1, "b"))]
    chunks = chunk_record_videos(pairs, cap=3)
    assert len(chunks) == 1
    assert ("dup", []) in chunks[0]["entries"]
    assert chunks[0]["video_count"] == 3


def test_trailing_zero_id_record_joins_last_chunk():
    pairs = [("a", ids(2, "a")), ("b", ids(2, "b")), ("dup", [])]
    chunks = chunk_record_videos(pairs, cap=2)
    assert len(chunks) == 2
    assert ("dup", []) in chunks[-1]["entries"]


def test_cap_below_one_rejected():
    with pytest.raises(ValueError):
        chunk_record_videos([("a", ids(1, "a"))], cap=0)


def test_url_shape_exists_only_in_the_helper():
    """019 single-source discipline: no other source file spells the
    watch_videos path (tests and the helper itself excepted)."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "collection_agent"
    offenders = [
        p
        for p in src.rglob("*.py")
        if p.name != "youtube_links.py"
        and "watch_videos?" in p.read_text(encoding="utf-8")  # the URL literal;
        # calling build_watch_videos_url elsewhere is fine — spelling the
        # query-string shape is not
    ]
    assert offenders == []
