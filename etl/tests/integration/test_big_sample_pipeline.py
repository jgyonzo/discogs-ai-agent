"""Integration test: laptop-scale execution against the ~49,689-release real subset.

Validates US2 (Fase 3 — laptop-scale execution):
- Pipeline streams through the 191 MB / ~49,689-release real Discogs
  subset (FR-011 / SC-011).
- Manifest reports `step_metrics.parse_releases.peak_rss_bytes` under
  the configured cap (default 4 GiB).
- DuckDB COUNT(DISTINCT release_id) ≈ 49,689 (SC-013).
- Progress log lines arrive at the configured cadence (SC-012).

Gated per `research.md` R-06: skipped unless both
`DISCOGS_BIG_FIXTURE=1` is set AND the fixture file exists locally.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import duckdb
import pytest
import yaml
from click.testing import CliRunner

from discogs_etl.cli import cli


REPO_ROOT = Path(__file__).resolve().parents[3]
BIG_FIXTURE = REPO_ROOT / "etl" / "tests" / "fixtures" / "releases_sample_big_raw.xml"
EXPECTED_RELEASES = 49689  # well-formed releases in the head -1000000 slice
RSS_CAP_BYTES = 4 * (1 << 30)


pytestmark = pytest.mark.skipif(
    os.environ.get("DISCOGS_BIG_FIXTURE") != "1" or not BIG_FIXTURE.exists(),
    reason=(
        "big fixture not present or not opted in "
        "(set DISCOGS_BIG_FIXTURE=1 and ensure releases_sample_big_raw.xml exists)"
    ),
)


def _write_config(tmp_path: Path, *, snapshot_id: str = "discogs-big") -> Path:
    cfg = {
        "snapshot_id": snapshot_id,
        "paths": {
            "raw_dir": str(tmp_path / "data" / "raw" / "discogs"),
            "staging_dir": str(tmp_path / "data" / "staging"),
            "clean_dir": str(tmp_path / "data" / "clean"),
            "analytics_dir": str(tmp_path / "data" / "analytics"),
            "published_duckdb": str(tmp_path / "data" / "published" / "duckdb" / "discogs.duckdb"),
            "manifests_dir": str(tmp_path / "data" / "manifests"),
            "logs_dir": str(tmp_path / "data" / "logs"),
        },
        "limits": {
            "parser_batch_size": 50000,
            "log_progress_every": 10000,
            "peak_rss_cap_gib": 4,
            "dq_check_in_memory_threshold": 10_000_000,
        },
    }
    config_path = tmp_path / "base.yml"
    config_path.write_text(yaml.safe_dump(cfg))
    raw_dir = Path(cfg["paths"]["raw_dir"]) / snapshot_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    return config_path


def _stage(tmp_path: Path, snapshot_id: str) -> None:
    raw_dir = tmp_path / "data" / "raw" / "discogs" / snapshot_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BIG_FIXTURE, raw_dir / "releases.xml")


def test_big_sample_passes_with_bounded_rss(tmp_path: Path):
    """Real ~50k-release subset run: passed_with_warnings, bounded RSS, expected count."""
    config_path = _write_config(tmp_path)
    _stage(tmp_path, "discogs-big")

    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--config", str(config_path)])
    assert result.exit_code == 0, result.output

    # Read manifest.
    manifests = list((tmp_path / "data" / "manifests").glob("*.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text())
    assert manifest["quality_checks"]["status"] == "passed_with_warnings"
    warning_names = [w["name"] for w in manifest["quality_checks"]["warnings"]]
    assert "parse_releases.truncated_xml" in warning_names

    # SC-011: peak RSS recorded and bounded.
    parse_metrics = manifest["step_metrics"]["parse_releases"]
    assert parse_metrics["peak_rss_bytes"] > 0
    assert parse_metrics["peak_rss_bytes"] < RSS_CAP_BYTES, (
        f"peak RSS {parse_metrics['peak_rss_bytes']} exceeded cap {RSS_CAP_BYTES}"
    )
    # The cap-exceeded warning MUST NOT be in the manifest if RSS stayed bounded.
    assert "runtime.peak_rss_exceeds_cap" not in warning_names

    # SC-012: progress log arrived at cadence — at least 3 lines from parse_releases.
    log_text = (tmp_path / "data" / "logs" / f"{manifest['run_id']}.log").read_text()
    parse_progress_lines = [
        ln for ln in log_text.splitlines()
        if "parse_releases progress: n=" in ln
    ]
    assert len(parse_progress_lines) >= 3, (
        f"expected ≥3 parse_releases progress lines; got {len(parse_progress_lines)}"
    )

    # SC-013: distinct release count ≈ 49,689 (allow ±5 for any drops).
    db = tmp_path / "data" / "published" / "duckdb" / "discogs.duckdb"
    assert db.exists()
    con = duckdb.connect(str(db), read_only=True)
    try:
        n_distinct = con.execute(
            "SELECT COUNT(DISTINCT release_id) FROM release_fact"
        ).fetchone()[0]
        assert abs(n_distinct - EXPECTED_RELEASES) <= 5, (
            f"distinct release_id={n_distinct} not within ±5 of {EXPECTED_RELEASES}"
        )
        # release_unique_view sanity.
        n_view = con.execute("SELECT COUNT(*) FROM release_unique_view").fetchone()[0]
        assert n_view == n_distinct
    finally:
        con.close()
