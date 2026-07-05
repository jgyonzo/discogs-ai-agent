"""Interface-level fake of DiscogsClient for sync/organize integration tests.

Replays fixture payloads; injectable failures:
- `release_failures`: release_id → "404" | Exception to raise
- `interrupt_after`: raise KeyboardInterrupt after N successful release fetches
- counters (`release_fetches`, `moves`, `created_folders`) for assertions
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from collection_agent.discogs.client import DiscogsServerError

from tests.fixtures import discogs_payloads as payloads


class FakeDiscogsClient:
    def __init__(
        self,
        instances: list[dict[str, Any]] | None = None,
        details: dict[int, dict[str, Any]] | None = None,
        username: str = "test_user",
        release_failures: dict[int, Any] | None = None,
        interrupt_after: int | None = None,
        page_size: int = 3,
    ):
        if instances is None or details is None:
            instances, details = payloads.default_collection()
        self._instances = instances
        self._details = details
        self._username = username
        self._release_failures = release_failures or {}
        self._interrupt_after = interrupt_after
        self._page_size = page_size

        self.release_fetches: list[int] = []
        self.moves: list[tuple[int, int, int, int]] = []  # (folder, release, instance, target)
        self.created_folders: list[str] = []
        self._next_folder_id = 100

    # -- read interface -------------------------------------------------------

    def get_identity(self) -> dict[str, Any]:
        return payloads.identity(self._username)

    def get_folders(self, username: str) -> list[dict[str, Any]]:
        return payloads.folders()

    def get_collection_value(self, username: str) -> dict[str, Any]:
        return payloads.collection_value()

    def iter_collection_pages(
        self, username: str, per_page: int = 100
    ) -> Iterator[dict[str, Any]]:
        chunks = [
            self._instances[i : i + self._page_size]
            for i in range(0, len(self._instances), self._page_size)
        ] or [[]]
        for i, chunk in enumerate(chunks, start=1):
            yield payloads.collection_page(chunk, page=i, pages=len(chunks))

    def get_release(self, release_id: int) -> dict[str, Any] | None:
        if (
            self._interrupt_after is not None
            and len(self.release_fetches) >= self._interrupt_after
        ):
            raise KeyboardInterrupt
        failure = self._release_failures.get(release_id)
        if failure == "404":
            self.release_fetches.append(release_id)
            return None
        if isinstance(failure, Exception):
            raise failure
        if failure == "5xx":
            raise DiscogsServerError(f"Discogs 5xx after retries: GET /releases/{release_id} -> 503")
        self.release_fetches.append(release_id)
        return self._details[release_id]

    # -- write interface --------------------------------------------------------

    def create_folder(self, username: str, name: str) -> dict[str, Any]:
        self.created_folders.append(name)
        self._next_folder_id += 1
        return {"id": self._next_folder_id, "name": name, "count": 0}

    def move_instance(
        self,
        username: str,
        folder_id: int,
        release_id: int,
        instance_id: int,
        target_folder_id: int,
    ) -> None:
        self.moves.append((folder_id, release_id, instance_id, target_folder_id))

    def close(self) -> None:
        pass
