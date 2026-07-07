"""PhotoRetainer semantics (023 US3 T022, contracts/eval-dataset.md §3):
pending save → atomic rename, extension mapping, original bytes preserved,
loud-but-non-fatal failures (FR-008/FR-009)."""

from __future__ import annotations

import logging

from collection_agent.scan.retention import PhotoRetainer

SESSION = "20260707-160209Z"
BYTES = b"\xff\xd8 original upload bytes, never re-encoded"


def make_retainer(tmp_path) -> PhotoRetainer:
    return PhotoRetainer(tmp_path / "scan-photos", SESSION)


class TestSaveAndAssign:
    def test_pending_then_rename_to_scan_id(self, tmp_path):
        r = make_retainer(tmp_path)
        handle = r.save_pending(BYTES, "image/jpeg")
        assert handle is not None and handle.name == "pending-1.jpg"
        assert handle.read_bytes() == BYTES  # original bytes, no re-encode

        r.assign(handle, f"{SESSION}-1")
        session_dir = tmp_path / "scan-photos" / SESSION
        assert not handle.exists()
        assert (session_dir / f"{SESSION}-1.jpg").read_bytes() == BYTES

    def test_counter_increments_per_upload(self, tmp_path):
        r = make_retainer(tmp_path)
        h1 = r.save_pending(BYTES, "image/jpeg")
        h2 = r.save_pending(BYTES, "image/png")
        assert h1.name == "pending-1.jpg" and h2.name == "pending-2.png"

    def test_extension_mapping(self, tmp_path):
        r = make_retainer(tmp_path)
        cases = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/heic": ".heic",
            "image/jpeg; charset=binary": ".jpg",
            "application/octet-stream": ".jpg",  # tolerant default
            None: ".jpg",
        }
        for mime, ext in cases.items():
            handle = r.save_pending(BYTES, mime)
            assert handle.suffix == ext, f"{mime} -> {handle.suffix}"


class TestFailurePolicy:
    def test_unwritable_dir_warns_and_returns_none(self, tmp_path, caplog):
        blocker = tmp_path / "scan-photos"
        blocker.write_text("a file where the dir should be")  # mkdir will fail
        r = PhotoRetainer(blocker, SESSION)
        with caplog.at_level(logging.WARNING, "collection_agent.scan.retention"):
            handle = r.save_pending(BYTES, "image/jpeg")
        assert handle is None
        assert any("retention failed" in m for m in caplog.messages)

    def test_assign_none_handle_is_silent_noop(self, tmp_path):
        make_retainer(tmp_path).assign(None, f"{SESSION}-1")  # must not raise

    def test_assign_missing_file_warns_not_raises(self, tmp_path, caplog):
        r = make_retainer(tmp_path)
        ghost = tmp_path / "scan-photos" / SESSION / "pending-9.jpg"
        with caplog.at_level(logging.WARNING, "collection_agent.scan.retention"):
            r.assign(ghost, f"{SESSION}-9")  # never raises into the scan flow
        assert any("rename failed" in m for m in caplog.messages)

    def test_flag_off_construction_never_touches_fs(self, tmp_path):
        PhotoRetainer(tmp_path / "scan-photos", SESSION)  # constructor only
        assert not (tmp_path / "scan-photos").exists()
