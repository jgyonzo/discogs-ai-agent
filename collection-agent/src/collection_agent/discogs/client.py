"""Thin Discogs API client (contracts/discogs-consumption.md).

- Auth: `Authorization: Discogs token=<token>` header ONLY (never query
  string — it leaks into logs). The token never appears in logs, exceptions,
  or the snapshot.
- Every request carries the settings-sourced User-Agent.
- Every request passes through the RateLimitGovernor (pacing + 429 backoff).
- Failure policy (§4): 401 → DiscogsAuthError (no retry); 404 → None where
  the contract says "kept without enrichment"; 5xx → up to 3 retries with
  backoff, then DiscogsServerError; 429 → backoff and retry (not a failure).

Only the endpoints listed in the consumption contract exist here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx

from collection_agent.discogs.ratelimit import RateLimitGovernor
from collection_agent.settings import Settings

MAX_5XX_RETRIES = 3
MAX_429_RETRIES = 8


class DiscogsError(Exception):
    """Base class; messages must never contain the token."""


class DiscogsAuthError(DiscogsError):
    pass


class DiscogsServerError(DiscogsError):
    pass


class DiscogsClient:
    def __init__(
        self,
        settings: Settings,
        governor: RateLimitGovernor | None = None,
        notify: Callable[[str], None] | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self._settings = settings
        self.governor = governor or RateLimitGovernor(
            floor=settings.rate_limit_floor, notify=notify
        )
        token = settings.discogs_user_token.get_secret_value()
        self._http = httpx.Client(
            base_url=settings.discogs_base_url,
            headers={
                "Authorization": f"Discogs token={token}",
                "User-Agent": settings.user_agent,
                "Accept": "application/vnd.discogs.v2.discogs+json",
            },
            timeout=30.0,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    # -- core request path ---------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        retries_5xx = 0
        retries_429 = 0
        while True:
            self.governor.before_request()
            try:
                resp = self._http.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                # network-level failure: no token in message (httpx errors
                # carry the URL, and our auth travels in a header).
                raise DiscogsError(f"network error calling {method} {path}: {exc}") from None
            self.governor.after_response(resp.headers)

            if resp.status_code == 429:
                retries_429 += 1
                if retries_429 > MAX_429_RETRIES:
                    raise DiscogsServerError(
                        f"still throttled after {MAX_429_RETRIES} backoffs: {method} {path}"
                    )
                self.governor.on_429()
                continue
            if resp.status_code == 401:
                raise DiscogsAuthError(
                    "Discogs rejected the token (401). Regenerate it at "
                    "https://www.discogs.com/settings/developers and update .env."
                )
            if resp.status_code >= 500:
                retries_5xx += 1
                if retries_5xx > MAX_5XX_RETRIES:
                    raise DiscogsServerError(
                        f"Discogs 5xx after {MAX_5XX_RETRIES} retries: "
                        f"{method} {path} -> {resp.status_code}"
                    )
                self.governor.on_429()  # same bounded backoff behavior
                continue
            return resp

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self._request("GET", path, params=params)
        resp.raise_for_status()
        return resp.json()

    # -- read endpoints (sync) ------------------------------------------------

    def get_identity(self) -> dict[str, Any]:
        return self._get_json("/oauth/identity")

    def get_folders(self, username: str) -> list[dict[str, Any]]:
        data = self._get_json(f"/users/{username}/collection/folders")
        return data.get("folders", [])

    def iter_collection_pages(
        self, username: str, per_page: int = 100
    ) -> Iterator[dict[str, Any]]:
        """Yield raw page payloads from folder 0 (= All) until exhausted."""
        page = 1
        while True:
            data = self._get_json(
                f"/users/{username}/collection/folders/0/releases",
                params={"page": page, "per_page": per_page},
            )
            yield data
            pagination = data.get("pagination", {})
            if page >= int(pagination.get("pages", 1)):
                return
            page += 1

    def get_release(self, release_id: int) -> dict[str, Any] | None:
        """Release detail; None on 404 (caller records a warning)."""
        resp = self._request("GET", f"/releases/{release_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_collection_value(self, username: str) -> dict[str, Any]:
        return self._get_json(f"/users/{username}/collection/value")

    def get_release_instances(
        self, username: str, release_id: int
    ) -> list[dict[str, Any]]:
        """Instances of a release in the collection (US4 execute-time
        re-validation). Empty list when the release is no longer owned."""
        resp = self._request(
            "GET", f"/users/{username}/collection/releases/{release_id}"
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("releases", [])

    # -- write endpoints (US4 only; called by the confirmed write path) -------

    def create_folder(self, username: str, name: str) -> dict[str, Any]:
        resp = self._request(
            "POST", f"/users/{username}/collection/folders", json={"name": name}
        )
        resp.raise_for_status()
        return resp.json()

    def move_instance(
        self,
        username: str,
        folder_id: int,
        release_id: int,
        instance_id: int,
        target_folder_id: int,
    ) -> None:
        resp = self._request(
            "POST",
            f"/users/{username}/collection/folders/{folder_id}"
            f"/releases/{release_id}/instances/{instance_id}",
            json={"folder_id": target_folder_id},
        )
        resp.raise_for_status()
