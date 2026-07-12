"""DiscogsClient scan methods (022 T009): search_releases and
add_to_collection through the governed _request path, via MockTransport —
no live calls, no real sleeps."""

from __future__ import annotations

import httpx
import pytest

from collection_agent.discogs.client import (
    DiscogsAuthError,
    DiscogsClient,
    DiscogsServerError,
)
from collection_agent.discogs.ratelimit import RateLimitGovernor

from tests.fixtures import discogs_payloads as payloads


def _client(settings, handler) -> DiscogsClient:
    return DiscogsClient(
        settings,
        governor=RateLimitGovernor(floor=0, sleep_fn=lambda _s: None),
        transport=httpx.MockTransport(handler),
    )


class TestSearchReleases:
    def test_path_params_and_auth_header(self, settings):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = request.url
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(
                200, json=payloads.search_page([payloads.search_result(101)])
            )

        client = _client(settings, handler)
        data = client.search_releases({"barcode": "720642442524", "per_page": 8})
        assert seen["url"].path == "/database/search"
        assert seen["url"].params["barcode"] == "720642442524"
        assert seen["url"].params["type"] == "release"  # forced, not optional
        assert seen["auth"] == "Discogs token=test-token-not-real"
        assert data["results"][0]["id"] == 101

    def test_429_backs_off_then_succeeds(self, settings):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, json={})
            return httpx.Response(200, json=payloads.search_page([]))

        client = _client(settings, handler)
        assert client.search_releases({"q": "x"})["results"] == []
        assert calls["n"] == 2

    def test_401_raises_auth_error(self, settings):
        client = _client(settings, lambda r: httpx.Response(401, json={}))
        with pytest.raises(DiscogsAuthError):
            client.search_releases({"q": "x"})

    def test_5xx_exhausts_retries(self, settings):
        client = _client(settings, lambda r: httpx.Response(503, json={}))
        with pytest.raises(DiscogsServerError):
            client.search_releases({"q": "x"})


class TestAddToCollection:
    def test_post_path_and_instance_payload(self, settings):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            return httpx.Response(
                201, json=payloads.add_instance_response(90002, 101, folder_id=1)
            )

        client = _client(settings, handler)
        data = client.add_to_collection("test_user", 1, 101)
        assert seen["method"] == "POST"
        assert seen["path"] == "/users/test_user/collection/folders/1/releases/101"
        assert data["instance_id"] == 90002

    def test_add_401_raises_auth_error_without_token_in_message(self, settings):
        client = _client(settings, lambda r: httpx.Response(401, json={}))
        with pytest.raises(DiscogsAuthError) as exc_info:
            client.add_to_collection("test_user", 1, 101)
        assert "test-token-not-real" not in str(exc_info.value)

    def test_add_5xx_exhausts_retries(self, settings):
        client = _client(settings, lambda r: httpx.Response(500, json={}))
        with pytest.raises(DiscogsServerError):
            client.add_to_collection("test_user", 1, 101)


class TestGetMasterVersions:
    """026 T013 (amendment-017-discogs-consumption-4): one governed GET of
    /masters/{id}/versions — page 1, caller-supplied per_page, no filters."""

    def test_path_params_and_auth_header(self, settings):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = request.url
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(
                200,
                json=payloads.versions_page([payloads.version_item(201)]),
            )

        client = _client(settings, handler)
        data = client.get_master_versions(5309, per_page=25)
        assert seen["url"].path == "/masters/5309/versions"
        assert seen["url"].params["page"] == "1"
        assert seen["url"].params["per_page"] == "25"
        # exactly the two pagination params — no filters, no sorts
        assert set(seen["url"].params.keys()) == {"page", "per_page"}
        assert seen["auth"] == "Discogs token=test-token-not-real"
        assert data["versions"][0]["id"] == 201

    def test_429_backs_off_then_succeeds(self, settings):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, json={})
            return httpx.Response(200, json=payloads.versions_page([]))

        client = _client(settings, handler)
        assert client.get_master_versions(5309, per_page=25)["versions"] == []
        assert calls["n"] == 2

    def test_401_raises_auth_error(self, settings):
        client = _client(settings, lambda r: httpx.Response(401, json={}))
        with pytest.raises(DiscogsAuthError):
            client.get_master_versions(5309, per_page=25)

    def test_5xx_exhausts_retries(self, settings):
        client = _client(settings, lambda r: httpx.Response(503, json={}))
        with pytest.raises(DiscogsServerError):
            client.get_master_versions(5309, per_page=25)
