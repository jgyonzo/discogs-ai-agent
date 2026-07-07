"""Scan journal + session (022 T012/T013): contract line shape, append-only
+ flush-per-event durability, unknown-key tolerance, loud I/O failure, and
ScanSession bookkeeping (allowlist, session adds, idempotent close)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from collection_agent.scan.journal import JournalWriteError, ScanJournal
from collection_agent.scan.models import ScanCycleOutcome
from collection_agent.scan.session import ScanSession


def _fixed_clock():
    return datetime(2026, 7, 7, 18, 30, 0, tzinfo=timezone.utc)


@pytest.fixture()
def journal(settings) -> ScanJournal:
    return ScanJournal(settings.scan_journal_dir, "20260707-183000Z")


@pytest.fixture()
def session(journal) -> ScanSession:
    return ScanSession(journal, clock=_fixed_clock)


class TestJournal:
    def test_line_shape_matches_contract(self, journal, session):
        scan_id = session.next_scan_id()
        session.record_outcome(
            scan_id, "added", "photo",
            evidence_kinds=["barcode"], release_id=101,
            release_title="Alex Smoke - Simple Things", instance_id=90002,
        )
        lines = journal.path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry == {
            "ts": "2026-07-07T18:30:00Z",
            "seq": 1,
            "scan_id": "20260707-183000Z-1",
            "outcome": "added",
            "source": "photo",
            "evidence_kinds": ["barcode"],
            "release_id": 101,
            "release_title": "Alex Smoke - Simple Things",
            "instance_id": 90002,
            "duplicate_add": False,
        }

    def test_append_only_earlier_lines_untouched(self, journal, session):
        session.record_outcome(session.next_scan_id(), "added", "photo",
                               release_id=101, release_title="A")
        first = journal.path.read_text(encoding="utf-8")
        session.record_outcome(session.next_scan_id(), "skipped", "photo",
                               release_id=102)
        after = journal.path.read_text(encoding="utf-8")
        assert after.startswith(first)  # byte-identical prefix
        assert len(after.splitlines()) == 2

    def test_readable_mid_session(self, journal, session):
        # flush-per-event: the file is complete after every outcome, without
        # any close/shutdown step (interruption guarantee, SC-007)
        session.record_outcome(session.next_scan_id(), "no_match", "photo")
        entry = json.loads(journal.path.read_text(encoding="utf-8"))
        assert entry["outcome"] == "no_match"

    def test_unknown_keys_tolerated_on_read_back(self, journal):
        journal.append(
            ScanCycleOutcome(
                ts="2026-07-07T18:30:00Z", seq=1, scan_id="s-1",
                outcome="added", source="photo",
            )
        )
        raw = json.loads(journal.path.read_text(encoding="utf-8"))
        raw["future_key"] = "ignored"
        parsed = ScanCycleOutcome.model_validate(raw)  # extra keys ignored
        assert parsed.outcome == "added"

    def test_io_failure_raises_loudly(self, settings):
        # a *file* where the journal dir should be -> mkdir/open fails
        blocker = settings.scan_journal_dir
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("not a directory")
        journal = ScanJournal(blocker, "s")
        with pytest.raises(JournalWriteError):
            journal.append(
                ScanCycleOutcome(
                    ts="t", seq=1, scan_id="s-1", outcome="added",
                    source="photo",
                )
            )


class TestScanSession:
    def test_scan_ids_monotonic(self, session):
        assert session.next_scan_id() == "20260707-183000Z-1"
        assert session.next_scan_id() == "20260707-183000Z-2"

    def test_allowlist(self, session):
        session.register_candidates([101, 102])
        assert session.is_known_candidate(101)
        assert not session.is_known_candidate(999)

    def test_session_add_counts(self, session):
        session.record_add(101)
        session.record_add(101)
        assert session.added_release_ids == {101: 2}

    def test_closed_scan_ids_for_idempotent_skip(self, session):
        scan_id = session.next_scan_id()
        assert not session.is_closed(scan_id)
        session.record_outcome(scan_id, "skipped", "photo")
        assert session.is_closed(scan_id)

    def test_log_mirrors_journal(self, session, journal):
        session.record_outcome(session.next_scan_id(), "failed", "photo",
                               detail="Discogs 5xx")
        assert len(session.log) == 1
        assert session.log[0].detail == "Discogs 5xx"
        assert len(journal.path.read_text(encoding="utf-8").splitlines()) == 1

    def test_journal_failure_does_not_pollute_log(self, settings):
        blocker = settings.scan_journal_dir
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("not a directory")
        session = ScanSession(ScanJournal(blocker, "s"), clock=_fixed_clock)
        with pytest.raises(JournalWriteError):
            session.record_outcome(session.next_scan_id(), "added", "photo")
        assert session.log == []  # journal-first: log never lies about disk
