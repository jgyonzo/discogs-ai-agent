"""020 US1 playlist_links: resolution reuse, skip reasons, dedup,
single-link payload, over-capacity interim, completeness partition
(SC-003), warnings envelope."""

from __future__ import annotations

import pytest

from collection_agent.agent import AgentSession
from collection_agent.models import Completeness, MediaLink
from collection_agent.tools.playlist import make_playlist_tools
from tests.conftest import make_record, make_snapshot


def yt(vid: str) -> MediaLink:
    return MediaLink(uri=f"https://www.youtube.com/watch?v={vid}", title=vid)


V1, V2, V3, V4 = "aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc", "ddddddddddd"


@pytest.fixture()
def playlist_snapshot():
    return make_snapshot([
        make_record(1, title="Simple Things", artist="Alex Smoke",
                    videos=[yt(V1), yt(V2)]),
        make_record(2, title="Navigation EP", artist="Noah Pred", videos=[]),
        make_record(3, title="Blue Album", artist="Jazz Cat", videos=[yt(V3)]),
        make_record(4, title="Broken Link", artist="Bad Meta",
                    videos=[MediaLink(uri="https://vimeo.com/12345678")]),
        make_record(5, title="Repress", artist="Alex Smoke",
                    videos=[yt(V1)]),  # duplicate of record 1's first video
    ])


@pytest.fixture()
def tool(settings, store, playlist_snapshot):
    store.save(playlist_snapshot)
    (t,) = make_playlist_tools(settings, store)
    return t


def run(tool, session=None, **kwargs):
    return tool.fn(session or AgentSession(), tool.params_model(**kwargs))


def assert_partition(res, requested_instance_ids):
    """SC-003: every resolved record is covered by a link XOR skipped."""
    covered = {r["instance_id"] for link in res["links"] for r in link["records"]}
    skipped = {r["instance_id"] for r in res["skipped_records"]}
    assert covered | skipped == set(requested_instance_ids)
    assert covered & skipped == set()


# --- resolution (reuses media/organize semantics) -----------------------------


def test_resolution_by_id_name_and_last_listing(tool):
    assert run(tool, record_refs=["1"])["covered_record_count"] == 1
    res = run(tool, record_refs=["jazz cat blue album"])
    assert res["links"][0]["records"][0]["instance_id"] == 3

    session = AgentSession()
    session.last_listing_instance_ids = [3, 1]
    res = run(tool, session, use_last_listing=True)
    assert [r["instance_id"] for r in res["links"][0]["records"]] == [3, 1]


def test_no_refs_and_no_listing_is_an_error(tool):
    res = run(tool, use_last_listing=True)
    assert res["error"] == "no_records_resolved"
    assert "no previous listing" in str(res["not_found"])


def test_nothing_specified_is_an_error(tool):
    assert run(tool)["error"] == "no_records_specified"


def test_unknown_refs_reported_not_fabricated(tool):
    res = run(tool, record_refs=["totally unknown record"])
    assert res["error"] == "no_records_resolved"
    assert res["not_found"] == ["totally unknown record"]


def test_no_snapshot_blocks(settings, store):
    (t,) = make_playlist_tools(settings, store)
    assert run(t, record_refs=["1"])["error"] == "sync_required"


# --- skips, dedup, link contents (FR-002/003/004) -----------------------------


def test_skip_reasons_both_kinds(tool):
    res = run(tool, record_refs=["1", "2", "4"])
    reasons = {r["instance_id"]: r["reason"] for r in res["skipped_records"]}
    assert reasons == {2: "no_videos", 4: "unresolvable_uri"}
    assert_partition(res, [1, 2, 4])


def test_duplicate_video_included_once_with_note(tool):
    res = run(tool, record_refs=["1", "5"])
    (link,) = res["links"]
    assert link["url"].count(V1) == 1
    assert res["total_videos"] == 2  # V1, V2 — not 3
    assert any("included once" in n for n in res["duplicate_notes"])
    # record 5 is covered (its video IS in the link), contributing 0 own ids
    assert {r["instance_id"] for r in link["records"]} == {1, 5}
    assert_partition(res, [1, 5])


def test_single_link_payload_shape(tool):
    res = run(tool, record_refs=["1", "3"], suggested_name="discogs-minimal")
    (link,) = res["links"]
    assert link["url"] == (
        f"https://www.youtube.com/watch_videos?video_ids={V1},{V2},{V3}"
    )
    assert link["index"] == 1 and link["video_count"] == 3
    assert link["label"] == "link 1 — records 1–2 (3 videos)"
    assert res["link_count"] == 1 and res["total_videos"] == 3
    assert res["covered_record_count"] == 2
    assert res["suggested_name"] == "discogs-minimal"
    assert "Save playlist" in res["save_hint"]
    assert "nothing was created or saved" in res["detail"].lower()
    assert res["videos_per_record"] == "all"


def test_all_skipped_yields_no_link(tool):
    res = run(tool, record_refs=["2", "4"])
    assert res["links"] == [] and res["link_count"] == 0
    assert "no play link" in res["detail"].lower()
    assert "search" in res["detail"].lower()  # never offer substitutes
    assert_partition(res, [2, 4])


def test_ids_in_listing_order(tool):
    session = AgentSession()
    session.last_listing_instance_ids = [3, 1]
    res = run(tool, session, use_last_listing=True)
    assert f"video_ids={V3},{V1},{V2}" in res["links"][0]["url"]


# --- capacity: chunked, labeled, complete (US2, FR-005) -----------------------


def small_cap_tool(store, tmp_path, snapshot, cap):
    from collection_agent.settings import Settings

    settings = Settings(
        _env_file=None,
        DISCOGS_USER_TOKEN="test-token-not-real",
        SNAPSHOT_PATH=tmp_path / "snapshot.json",
        YOUTUBE_PLAYLIST_MAX_IDS=cap,
    )
    store.save(snapshot)
    (t,) = make_playlist_tools(settings, store)
    return t


def test_over_capacity_chunks_record_aligned(store, tmp_path, playlist_snapshot):
    t = small_cap_tool(store, tmp_path, playlist_snapshot, cap=2)
    res = run(t, record_refs=["1", "3"])  # rec 1: V1,V2 · rec 3: V3 — cap 2
    assert res["link_count"] == 2 and len(res["links"]) == 2
    first, second = res["links"]
    assert f"video_ids={V1},{V2}" in first["url"]
    assert f"video_ids={V3}" in second["url"]
    assert first["label"] == "link 1 — record 1 (2 videos)"
    assert second["label"] == "link 2 — record 2 (1 videos)"
    assert res["total_videos"] == 3  # jointly complete, nothing dropped
    assert "split across the labeled links" in res["detail"]
    assert_partition(res, [1, 3])


def test_links_disjoint_and_jointly_complete(store, tmp_path, playlist_snapshot):
    t = small_cap_tool(store, tmp_path, playlist_snapshot, cap=1)
    res = run(t, record_refs=["1", "3", "5"])  # V1,V2,V3 (V1 deduped from rec 5)
    all_ids = [
        link["url"].split("video_ids=")[1].split(",") for link in res["links"]
    ]
    flat = [v for chunk in all_ids for v in chunk]
    assert flat == [V1, V2, V3]  # order, no overlap, no loss
    assert all(len(chunk) == 1 for chunk in all_ids)
    assert_partition(res, [1, 3, 5])


def test_oversized_single_record_splits_with_note(store, tmp_path):
    snap = make_snapshot([
        make_record(9, title="Video Dense", artist="Max",
                    videos=[yt(f"{i:011d}".replace("0", "e", 1)) for i in range(5)]),
    ])
    t = small_cap_tool(store, tmp_path, snap, cap=2)
    res = run(t, record_refs=["9"])
    assert res["link_count"] == 3  # 2+2+1
    assert any("more videos than fit one link" in n for n in res["duplicate_notes"])
    assert_partition(res, [9])


def test_within_cap_still_single_link(tool):
    res = run(tool, record_refs=["1", "3"])  # 3 videos, default cap 50
    assert res["link_count"] == 1  # no gratuitous chunking


# --- one video per record (US3, FR-006) ---------------------------------------


def test_first_mode_takes_first_stored_video_per_record(tool):
    res = run(tool, record_refs=["1", "3"], videos_per_record="first")
    (link,) = res["links"]
    assert f"video_ids={V1},{V3}" in link["url"]  # V2 (rec 1's 2nd) excluded
    assert res["total_videos"] == 2
    assert all(r["video_count"] == 1 for r in link["records"])
    assert res["videos_per_record"] == "first"
    assert_partition(res, [1, 3])


def test_first_mode_skip_reporting_unchanged(tool):
    res = run(tool, record_refs=["1", "2", "4"], videos_per_record="first")
    reasons = {r["instance_id"]: r["reason"] for r in res["skipped_records"]}
    assert reasons == {2: "no_videos", 4: "unresolvable_uri"}
    assert_partition(res, [1, 2, 4])


def test_omitted_mode_defaults_to_all(tool):
    res = run(tool, record_refs=["1"])
    assert res["videos_per_record"] == "all"
    assert res["total_videos"] == 2  # both of record 1's videos


def test_first_mode_dedup_still_applies(tool):
    # records 1 and 5 share the same FIRST video (V1)
    res = run(tool, record_refs=["1", "5"], videos_per_record="first")
    (link,) = res["links"]
    assert link["url"].count(V1) == 1 and res["total_videos"] == 1
    assert any("included once" in n for n in res["duplicate_notes"])
    assert_partition(res, [1, 5])


# --- warnings envelope (ground rule 2) ----------------------------------------


def test_partial_snapshot_warning_passes_through(settings, store, playlist_snapshot):
    snap = playlist_snapshot.model_copy(deep=True)
    snap.meta.completeness = Completeness.PARTIAL
    snap.meta.enriched_count = 1
    store.save(snap)
    (t,) = make_playlist_tools(settings, store)
    res = run(t, record_refs=["1"])
    assert any("PARTIAL" in w for w in res["warnings"])
