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
        assert [r for r, _ in evidence_rungs(FULL)] == [
            "barcode", "catno", "artist_title",
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
        assert tried == ["barcode", "catno", "artist_title"]


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
