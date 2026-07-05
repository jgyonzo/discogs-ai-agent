"""Sync integration (T015): happy path, 429 backoff, interruption→resume,
404 warning, 5xx→partial. No live API — FakeDiscogsClient at the interface
level; httpx.MockTransport for the client-internal 429/backoff path."""

from __future__ import annotations

import json

import httpx
import pytest

from collection_agent.discogs.client import DiscogsClient
from collection_agent.discogs.ratelimit import RateLimitGovernor
from collection_agent.models import Completeness
from collection_agent.snapshot.sync import run_sync
from tests.fixtures.fake_client import FakeDiscogsClient


def test_full_sync_happy_path(settings, store):
    client = FakeDiscogsClient()
    meta = run_sync(client, store, settings)

    assert meta.completeness == Completeness.COMPLETE
    assert meta.instance_count == 5          # every copy counts (FR-025)
    assert meta.unique_release_count == 4    # one duplicate release
    assert meta.enriched_count == 4
    assert meta.collection_value.median == "US$250.00"

    snap = store.load()
    assert len(snap.records) == 5
    by_iid = {r.instance_id: r for r in snap.records}
    assert by_iid[9001].country == "UK"                # enrichment applied
    assert by_iid[9004].country == "UK"                # duplicate shares enrichment
    assert by_iid[9002].num_for_sale == 0
    assert by_iid[9001].my_rating == 4                 # real rating kept
    assert by_iid[9005].my_rating is None              # rating 0 → null
    assert by_iid[9005].year is None                   # year 0 → null
    assert by_iid[9001].videos[0].uri.startswith("https://www.youtube.com/")
    assert not store.journal_path.exists()             # cleared on complete


def test_enrichment_404_keeps_record_with_warning(settings, store):
    client = FakeDiscogsClient(release_failures={103: "404"})
    meta = run_sync(client, store, settings)

    assert meta.completeness == Completeness.COMPLETE  # 404 is warned, not failed
    assert any("404" in w for w in meta.sync_stats.warnings)
    rec = next(r for r in store.load().records if r.release_id == 103)
    assert rec.enriched_at is None and rec.country is None  # kept, not fabricated


def test_persistent_5xx_yields_partial(settings, store):
    client = FakeDiscogsClient(release_failures={102: "5xx"})
    meta = run_sync(client, store, settings)

    assert meta.completeness == Completeness.PARTIAL
    assert any("102" in w for w in meta.sync_stats.warnings)
    assert store.journal_path.exists()  # journal kept for resume


def test_interrupt_then_resume_without_refetch(settings, store):
    # interrupt after 2 successful enrichments
    client1 = FakeDiscogsClient(interrupt_after=2)
    meta1 = run_sync(client1, store, settings)
    assert meta1.completeness == Completeness.PARTIAL
    assert len(client1.release_fetches) == 2
    assert store.journal_path.exists()

    # resume: only the 2 missing releases are fetched
    client2 = FakeDiscogsClient()
    meta2 = run_sync(client2, store, settings)
    assert meta2.completeness == Completeness.COMPLETE
    assert len(client2.release_fetches) == 2  # 4 unique - 2 already journaled
    assert meta2.enriched_count == 4


def test_full_flag_refetches_everything(settings, store):
    client1 = FakeDiscogsClient()
    run_sync(client1, store, settings)
    client2 = FakeDiscogsClient()
    run_sync(client2, store, settings, full=True)
    assert len(client2.release_fetches) == 4  # journal ignored


# --- client-internal 429 backoff (httpx.MockTransport) ------------------------


def test_client_backs_off_on_429_and_succeeds(settings):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429,
                headers={"X-Discogs-Ratelimit": "60", "X-Discogs-Ratelimit-Remaining": "0"},
                json={"message": "too many requests"},
            )
        return httpx.Response(
            200,
            headers={"X-Discogs-Ratelimit": "60", "X-Discogs-Ratelimit-Remaining": "59"},
            json={"username": "test_user"},
        )

    sleeps: list[float] = []
    notices: list[str] = []
    governor = RateLimitGovernor(
        floor=2, notify=notices.append, sleep_fn=sleeps.append, rand_fn=lambda: 1.0
    )
    client = DiscogsClient(
        settings, governor=governor, transport=httpx.MockTransport(handler)
    )
    identity = client.get_identity()

    assert identity["username"] == "test_user"
    assert calls["n"] == 2                      # one retry
    assert sleeps and sleeps[0] == pytest.approx(2.0)  # base backoff, jitter=1.0x
    assert any("throttled" in n for n in notices)
    assert governor.remaining == 59


def test_governor_paces_when_budget_low(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"X-Discogs-Ratelimit": "60", "X-Discogs-Ratelimit-Remaining": "1"},
            json={"folders": []},
        )

    sleeps: list[float] = []
    governor = RateLimitGovernor(floor=2, sleep_fn=sleeps.append)
    client = DiscogsClient(
        settings, governor=governor, transport=httpx.MockTransport(handler)
    )
    client.get_folders("test_user")   # ingests remaining=1 (≤ floor)
    client.get_folders("test_user")   # must pace before this request
    assert sleeps, "expected pacing sleep when remaining ≤ floor"
    assert 0 < sleeps[0] <= 10.0


def test_auth_error_no_retry_no_token_leak(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid token"})

    from collection_agent.discogs.client import DiscogsAuthError

    client = DiscogsClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(DiscogsAuthError) as exc_info:
        client.get_identity()
    assert "test-token-not-real" not in str(exc_info.value)


def test_pagination_iterates_all_pages(settings):
    pages_served: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(dict(request.url.params).get("page", 1))
        pages_served.append(page)
        return httpx.Response(
            200,
            json={
                "pagination": {"page": page, "pages": 3, "per_page": 100, "items": 250, "urls": {}},
                "releases": [],
            },
        )

    client = DiscogsClient(settings, transport=httpx.MockTransport(handler))
    pages = list(client.iter_collection_pages("test_user"))
    assert len(pages) == 3
    assert pages_served == [1, 2, 3]
