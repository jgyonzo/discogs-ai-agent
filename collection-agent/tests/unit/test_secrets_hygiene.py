"""Secrets hygiene sweep (T036): the Discogs token must never appear in
logs, exception messages, settings repr, the snapshot file, or the journal
(FR-002; snapshot-schema invariant 5; consumption contract §1)."""

from __future__ import annotations

import ast
from pathlib import Path

from collection_agent.snapshot.sync import run_sync
from tests.fixtures.fake_client import FakeDiscogsClient

TOKEN = "test-token-not-real"
SRC = Path(__file__).resolve().parents[2] / "src" / "collection_agent"


def test_settings_repr_masks_token(settings):
    assert TOKEN not in repr(settings)
    assert TOKEN not in str(settings)
    assert TOKEN not in str(settings.discogs_user_token)  # SecretStr masks


def test_snapshot_and_journal_contain_no_token(settings, store):
    run_sync(FakeDiscogsClient(), store, settings)
    assert TOKEN not in store.path.read_text(encoding="utf-8")
    if store.journal_path.exists():
        assert TOKEN not in store.journal_path.read_text(encoding="utf-8")


def test_auth_error_message_has_no_token(settings):
    import httpx

    from collection_agent.discogs.client import DiscogsAuthError, DiscogsClient

    client = DiscogsClient(
        settings,
        transport=httpx.MockTransport(lambda r: httpx.Response(401, json={})),
    )
    try:
        client.get_identity()
        raise AssertionError("expected DiscogsAuthError")
    except DiscogsAuthError as exc:
        assert TOKEN not in str(exc)


def test_no_source_prints_or_logs_the_token():
    """Static check: no f-string / format call in the package interpolates the
    raw token (get_secret_value is only called to build the auth header)."""
    offenders: list[str] = []
    for py in SRC.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get_secret_value"
            ):
                offenders.append(f"{py.name}:{node.lineno}")
    # exactly one sanctioned call site: the Authorization header in client.py
    assert len(offenders) == 1 and offenders[0].startswith("client.py:"), (
        "get_secret_value() called outside the sanctioned auth-header site: "
        f"{offenders} — audit each new call site for leaks"
    )
