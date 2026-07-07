"""Containment guard (023 T003, contracts/eval-dataset.md §4, FR-006/SC-005).

Downloaded Discogs images and retained scan photos are uploader-copyrighted
and must never become trackable by git. Two static invariants pin that:
(1) the repo-root .gitignore keeps an active, un-negated `data/` rule for
collection-agent paths; (2) every eval directory default resolves under
collection-agent/data/ so that rule actually covers them.
"""

from __future__ import annotations

from pathlib import Path

from collection_agent.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPONENT_DATA = REPO_ROOT / "collection-agent" / "data"

_EVAL_ENV_VARS = (
    "COLLECTION_AGENT_EVAL_DATASET_DIR",
    "COLLECTION_AGENT_EVAL_RESULTS_DIR",
    "COLLECTION_AGENT_SCAN_RETENTION_DIR",
)


def _gitignore_lines() -> list[str]:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


def test_gitignore_keeps_the_data_rule():
    lines = _gitignore_lines()
    assert "data/" in lines, (
        ".gitignore lost its blanket `data/` rule — collection-agent/data/ "
        "(snapshot, journals, eval images) would become trackable"
    )


def test_gitignore_never_reincludes_collection_agent_data():
    negations = [l for l in _gitignore_lines() if l.startswith("!")]
    offenders = [
        l for l in negations
        if "collection-agent" in l or l in ("!data/", "!data/**")
    ]
    assert not offenders, (
        f".gitignore re-includes collection-agent data paths: {offenders} — "
        "eval images must stay untracked (uploader copyright)"
    )


def test_eval_dir_defaults_resolve_under_component_data(monkeypatch, tmp_path):
    # scrub any developer-shell overrides so we test the true defaults
    for var in _EVAL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None, DISCOGS_USER_TOKEN="test-token-not-real")
    for p in (s.eval_dataset_dir, s.eval_results_dir, s.scan_retention_dir):
        assert COMPONENT_DATA in Path(p).resolve().parents, (
            f"{p} defaults outside collection-agent/data/ — it would escape "
            "the gitignore `data/` rule"
        )
