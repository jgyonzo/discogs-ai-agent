"""DiscogsClient.download_image (023 T006): governed absolute-URL GET,
None on expired/non-image payloads, governor untouched by header-less CDN
responses (amendment-017-discogs-consumption-2 §2, research R2)."""

from __future__ import annotations

import httpx

from collection_agent.discogs.client import DiscogsClient

IMAGE_URI = "https://i.discogs.com/abc123/release-724223.jpg"
JPEG = b"\xff\xd8\xff\xe0 fake jpeg bytes"


def _client(settings, handler) -> DiscogsClient:
    return DiscogsClient(settings, transport=httpx.MockTransport(handler))


def test_downloads_bytes_from_absolute_uri(settings):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )

    client = _client(settings, handler)
    assert client.download_image(IMAGE_URI) == JPEG
    # absolute URL sent as-is (not joined onto the API base_url)
    assert seen["url"] == IMAGE_URI
    assert seen["ua"] == settings.user_agent


def test_expired_uri_403_returns_none(settings):
    client = _client(settings, lambda r: httpx.Response(403, content=b"denied"))
    assert client.download_image(IMAGE_URI) is None


def test_missing_image_404_returns_none(settings):
    client = _client(settings, lambda r: httpx.Response(404, content=b""))
    assert client.download_image(IMAGE_URI) is None


def test_non_image_payload_returns_none(settings):
    client = _client(
        settings,
        lambda r: httpx.Response(
            200, content=b"<html>login</html>",
            headers={"content-type": "text/html"},
        ),
    )
    assert client.download_image(IMAGE_URI) is None


def test_headerless_cdn_response_leaves_governor_untouched(settings):
    """The image CDN sends no X-Discogs-Ratelimit* headers; the governor
    must keep whatever budget signal the API responses last gave it."""

    def handler(request):
        return httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )

    client = _client(settings, handler)
    client.governor.after_response(
        {"X-Discogs-Ratelimit": "60", "X-Discogs-Ratelimit-Remaining": "42"}
    )
    client.download_image(IMAGE_URI)
    assert client.governor.limit == 60
    assert client.governor.remaining == 42
