"""Opt-in scan-photo retention (023 US3, contracts/eval-dataset.md §3).

Constructed by the scan server ONLY when COLLECTION_AGENT_SCAN_RETAIN_PHOTOS
is true — flag off means this module never runs and the scan flow is
byte-identical to 022 (FR-007). The uploaded bytes are saved under a
provisional `pending-<n>.<ext>` name immediately after the upload-size gate
(FR-008: before any identification outcome exists) and atomically renamed to
`<scan_id>.<ext>` once the cycle id is assigned — the journal-joinable key
the eval harness labels against.

Failure policy (FR-009, deliberate contrast with the journal's loud-500
rule): retention is diagnostics, not the audit record. Every I/O failure is
one loud log warning and the scan proceeds; nothing here may raise into the
request path.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger("collection_agent.scan.retention")

_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
    "image/gif": "gif",
}


def _ext_for(content_type: str | None) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    return _EXT_BY_MIME.get(mime, "jpg")


class PhotoRetainer:
    """One per scan-server run (like the session); thread-safe counter —
    scan handlers run in a threadpool (022 FR-023)."""

    def __init__(self, retention_dir: Path, session_id: str):
        self._session_dir = Path(retention_dir) / session_id
        self._lock = threading.Lock()
        self._counter = 0

    def save_pending(self, image_bytes: bytes, content_type: str | None) -> Path | None:
        """Persist the original upload bytes under a provisional name.
        Returns the handle for a later assign(), or None on failure."""
        with self._lock:
            self._counter += 1
            n = self._counter
        path = self._session_dir / f"pending-{n}.{_ext_for(content_type)}"
        try:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image_bytes)
            return path
        except OSError as exc:
            logger.warning(
                "photo retention failed (scan continues unaffected): %s", exc
            )
            return None

    def assign(self, handle: Path | None, scan_id: str) -> None:
        """Rename the pending file to its cycle id (atomic, same directory).
        A None handle (earlier save failed) is a silent no-op."""
        if handle is None:
            return
        try:
            os.rename(handle, handle.with_name(f"{scan_id}{handle.suffix}"))
        except OSError as exc:
            logger.warning(
                "photo retention rename failed (scan continues unaffected): %s",
                exc,
            )
