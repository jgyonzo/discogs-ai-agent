"""Candidate pipeline (022 T018 + US2 T024): precision ladder, fallback on
zero results, dedup, cap + more_matches, and the 019-style verbatim audit —
every displayed field byte-equal to the fake payload, absent stays absent."""

from __future__ import annotations

from collection_agent.scan.models import ScanEvidence
from collection_agent.scan.search import (
    evidence_rungs,
    find_candidates,
    find_candidates_text,
)

from tests.fixtures import discogs_payloads as payloads
from tests.fixtures.fake_client import FakeDiscogsClient


FULL = ScanEvidence(
    barcode="720642442524", catno="SL-1", label="Some Label",
    artist="Alex Smoke", title="Simple Things",
)


class TestLadder:
    def test_rung_order_strongest_first(self):
        # addendum 1 (FR-020): the composed free-text fallback is last
        assert [r for r, _ in evidence_rungs(FULL)] == [
            "barcode", "catno", "artist_title", "text",
        ]

    def test_catno_includes_label_when_present(self):
        params = dict(evidence_rungs(FULL))["catno"]
        assert params == {"catno": "SL-1", "label": "Some Label"}

    def test_barcode_hit_stops_the_ladder(self, settings):
        client = FakeDiscogsClient()
        client.search_responses["barcode"] = payloads.search_page(
            [payloads.search_result(101)]
        )
        candidates, _more, tried = find_candidates(client, settings, FULL)
        assert [c.release_id for c in candidates] == [101]
        assert tried == ["barcode"]
        assert len(client.searches) == 1

    def test_zero_result_rung_falls_through(self, settings):
        client = FakeDiscogsClient()  # barcode + catno rungs return empty
        client.search_responses["artist_title"] = payloads.search_page(
            [payloads.search_result(102)]
        )
        candidates, _more, tried = find_candidates(client, settings, FULL)
        assert [c.release_id for c in candidates] == [102]
        assert tried == ["barcode", "catno", "artist_title"]

    def test_lower_rung_never_runs_when_evidence_absent(self, settings):
        client = FakeDiscogsClient()
        find_candidates(client, settings, ScanEvidence(barcode="12345"))
        assert [list(p.keys())[0] for p in client.searches] == ["barcode"]

    def test_all_rungs_empty_returns_no_candidates(self, settings):
        candidates, more, tried = find_candidates(
            FakeDiscogsClient(), settings, FULL
        )
        assert candidates == [] and more is False
        assert tried == ["barcode", "catno", "artist_title", "text"]


class TestShaping:
    def test_dedup_by_release_id(self, settings):
        client = FakeDiscogsClient()
        client.search_responses["barcode"] = payloads.search_page(
            [payloads.search_result(101), payloads.search_result(101),
             payloads.search_result(102)]
        )
        candidates, _more, _ = find_candidates(client, settings, FULL)
        assert [c.release_id for c in candidates] == [101, 102]

    def test_cap_and_more_matches(self, settings):
        results = [payloads.search_result(100 + i) for i in range(12)]
        client = FakeDiscogsClient()
        client.search_responses["barcode"] = payloads.search_page(
            results, items=40
        )
        candidates, more, _ = find_candidates(client, settings, FULL)
        assert len(candidates) == settings.scan_candidates_max
        assert more is True

    def test_exact_page_no_more_matches(self, settings):
        client = FakeDiscogsClient()
        client.search_responses["barcode"] = payloads.search_page(
            [payloads.search_result(101)]
        )
        _, more, _ = find_candidates(client, settings, FULL)
        assert more is False


class TestVerbatim:
    """019 discipline: displayed values byte-equal to the payload; absent
    keys stay absent; URLs never constructed."""

    def test_fields_verbatim(self, settings):
        item = payloads.search_result(
            101, title="Alex Smoke - Simple Things", year="2005",
            country="UK", formats=["Vinyl", "2xLP"], labels=["Soma"],
            catno="SOMA CD038",
            thumb="https://i.discogs.com/abc.jpg",
            uri="/Alex-Smoke-Simple-Things/release/101",
        )
        client = FakeDiscogsClient()
        client.search_responses["barcode"] = payloads.search_page([item])
        candidates, _, _ = find_candidates(client, settings, FULL)
        c = candidates[0]
        assert c.title == item["title"]
        assert c.year == item["year"]
        assert c.country == item["country"]
        assert c.formats == item["format"]
        assert c.labels == item["label"]
        assert c.catno == item["catno"]
        assert c.thumb_url == item["thumb"]
        assert c.discogs_uri == item["uri"]

    def test_absent_fields_stay_absent(self, settings):
        item = payloads.search_result(
            101, omit={"year", "country", "catno", "thumb", "cover_image", "uri"}
        )
        client = FakeDiscogsClient()
        client.search_responses["barcode"] = payloads.search_page([item])
        candidates, _, _ = find_candidates(client, settings, FULL)
        c = candidates[0]
        assert c.year is None and c.country is None and c.catno is None
        assert c.thumb_url is None and c.discogs_uri is None

    def test_cover_image_fallback_is_verbatim_too(self, settings):
        item = payloads.search_result(101, omit={"thumb"})
        client = FakeDiscogsClient()
        client.search_responses["barcode"] = payloads.search_page([item])
        candidates, _, _ = find_candidates(client, settings, FULL)
        assert candidates[0].thumb_url == item["cover_image"]

    def test_placeholder_duplicate_status_is_unknown(self, settings):
        client = FakeDiscogsClient()
        client.search_responses["barcode"] = payloads.search_page(
            [payloads.search_result(101)]
        )
        candidates, _, _ = find_candidates(client, settings, FULL)
        assert candidates[0].duplicate.state == "unknown"


class TestManualSearch:
    def test_free_text_rung(self, settings):
        client = FakeDiscogsClient()
        client.search_responses["q"] = payloads.search_page(
            [payloads.search_result(103)]
        )
        candidates, more = find_candidates_text(
            client, settings, "Rhythim Is Rhythim Nude Photo"
        )
        assert [c.release_id for c in candidates] == [103]
        assert more is False
        assert client.searches[0]["q"] == "Rhythim Is Rhythim Nude Photo"


class TestDuplicateStatus:
    """US2 T024: snapshot-state × presence matrix + session overlay
    (data-model.md rules; FR-009/010)."""

    def _checker(self, store, session_adds=None):
        from collection_agent.scan.search import snapshot_duplicate_checker

        class _FakeSession:
            def __init__(self, adds):
                self.added_release_ids = adds or {}

        return snapshot_duplicate_checker(store, _FakeSession(session_adds))

    def test_complete_snapshot_presence_counts_instances(
        self, store, complete_snapshot
    ):
        store.save(complete_snapshot)
        check = self._checker(store)
        dup = check(1)  # release 1 has instances 1 and 4 (two copies)
        assert dup.state == "in_collection"
        assert dup.copies == 2
        assert dup.added_this_session is False
        assert dup.reason is None

    def test_complete_snapshot_absence_is_not_in_collection(
        self, store, complete_snapshot
    ):
        store.save(complete_snapshot)
        assert self._checker(store)(999).state == "not_in_collection"

    def test_missing_snapshot_is_unknown(self, store):
        dup = self._checker(store)(1)
        assert dup.state == "unknown"
        assert dup.reason == "no snapshot"

    def test_stale_snapshot_absence_degrades_to_unknown(
        self, store, stale_snapshot
    ):
        store.save(stale_snapshot)
        dup = self._checker(store)(999)
        assert dup.state == "unknown"
        assert dup.reason == "snapshot stale"

    def test_partial_snapshot_absence_degrades_to_unknown(
        self, store, partial_snapshot
    ):
        store.save(partial_snapshot)
        assert self._checker(store)(999).state == "unknown"

    def test_stale_snapshot_presence_still_shows_count(
        self, store, stale_snapshot
    ):
        store.save(stale_snapshot)
        dup = self._checker(store)(1)
        assert dup.state == "in_collection"
        assert dup.copies == 2
        assert "as of last sync" in dup.reason

    def test_session_add_overlays_any_snapshot_state(self, store):
        # no snapshot at all, but added this session -> in_collection
        dup = self._checker(store, session_adds={101: 1})(101)
        assert dup.state == "in_collection"
        assert dup.copies == 1
        assert dup.added_this_session is True

    def test_session_adds_stack_on_snapshot_copies(
        self, store, complete_snapshot
    ):
        store.save(complete_snapshot)
        dup = self._checker(store, session_adds={1: 1})(1)
        assert dup.copies == 3  # 2 snapshot instances + 1 this session
        assert dup.added_this_session is True

    def test_unreadable_snapshot_degrades_to_unknown(self, store, settings):
        settings.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        settings.snapshot_path.write_text("{ corrupt json", encoding="utf-8")
        dup = self._checker(store)(1)
        assert dup.state == "unknown"
        assert dup.reason == "no snapshot"


class TestComposedFallback:
    """FR-020 (addendum 1): free-text rung from partial evidence, fired
    only when structured rungs are absent or all returned zero."""

    def test_compose_query_full(self):
        from collection_agent.scan.search import compose_query

        ev = ScanEvidence(artist="dj silversurfer", title="Ace Of Spades",
                          label="Crosstown Rebels")
        assert compose_query(ev) == (
            "dj silversurfer Ace Of Spades Crosstown Rebels"
        )

    def test_compose_query_lead_track_substitutes_title(self):
        from collection_agent.scan.search import compose_query

        ev = ScanEvidence(artist="frankie flowerz",
                          tracks=["The Key", "Steppin' In"],
                          label="CROSSTOWNREBELS")
        assert compose_query(ev) == "frankie flowerz The Key CROSSTOWNREBELS"

    def test_compose_query_none_when_only_codes(self):
        from collection_agent.scan.search import compose_query

        assert compose_query(ScanEvidence(barcode="720642442524")) is None

    def test_live_cycle_1_label_only_now_searches(self, settings):
        # addendum 1 F2: label-only evidence never queried Discogs
        client = FakeDiscogsClient()
        client.search_responses["q"] = payloads.search_page(
            [payloads.search_result(501)]
        )
        ev = ScanEvidence(label="Crosstown Rebels")
        candidates, _more, tried = find_candidates(client, settings, ev)
        assert tried == ["text"]
        assert client.searches[0]["q"] == "Crosstown Rebels"
        assert [c.release_id for c in candidates] == [501]

    def test_live_cycle_2_falls_through_to_text(self, settings):
        # barcode rung (reclassified digits) empty -> composed q rung hits
        client = FakeDiscogsClient()
        client.search_responses["q"] = payloads.search_page(
            [payloads.search_result(502)]
        )
        ev = ScanEvidence(artist="dj silversurfer", label="CROSSTOWNREBELS",
                          catno="81824 11306",
                          tracks=["Ace Of Spades", "Dirty Dishes"])
        candidates, _more, tried = find_candidates(client, settings, ev)
        assert tried == ["barcode", "text"]
        assert client.searches[-1]["q"] == (
            "dj silversurfer Ace Of Spades CROSSTOWNREBELS"
        )
        assert [c.release_id for c in candidates] == [502]

    def test_structured_hit_prevents_fallback(self, settings):
        client = FakeDiscogsClient()
        client.search_responses["barcode"] = payloads.search_page(
            [payloads.search_result(101)]
        )
        ev = ScanEvidence(artist="A", title="T", barcode="720642442524")
        _, _, tried = find_candidates(client, settings, ev)
        assert tried == ["barcode"]

    def test_all_rungs_including_text_empty(self, settings):
        ev = ScanEvidence(artist="A", title="T", barcode="720642442524")
        _, _, tried = find_candidates(FakeDiscogsClient(), settings, ev)
        assert tried == ["barcode", "artist_title", "text"]
