"""Integration test: full pipeline against the 404-release real sample.

Validates US1 (Fase 2 — real-data robustness):
- Pipeline survives the in-repo truncated 404-release Discogs excerpt
  (FR-001, FR-002).
- Truncation surfaces as a manifest warning, not a failure.
- DuckDB COUNT(DISTINCT release_id) = 404 (SC-001).
- UTF-8 round-trip of '⅓' in format_description_summary (FR-003 / SC-002).
- step_metrics populated for every step (data-model.md / FR-013).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import duckdb
import yaml
from click.testing import CliRunner

from discogs_etl.cli import cli


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_RAW = REPO_ROOT / "etl" / "tests" / "fixtures" / "releases_sample_raw.xml"


def _write_config(tmp_path: Path, *, snapshot_id: str = "discogs-test") -> Path:
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
            "parser_batch_size": 1000,
            "log_progress_every": 100,
            "peak_rss_cap_gib": 4,
            "dq_check_in_memory_threshold": 10_000_000,
        },
    }
    config_path = tmp_path / "base.yml"
    config_path.write_text(yaml.safe_dump(cfg))
    raw_dir = Path(cfg["paths"]["raw_dir"]) / snapshot_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    return config_path


def _stage(fixture: Path, tmp_path: Path, snapshot_id: str) -> None:
    raw_dir = tmp_path / "data" / "raw" / "discogs" / snapshot_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture, raw_dir / "releases.xml")


def test_real_sample_passes_with_warnings_404_releases(tmp_path: Path):
    """The 404-release truncated raw sample yields passed_with_warnings + DB."""
    config_path = _write_config(tmp_path)
    _stage(FIXTURE_RAW, tmp_path, "discogs-test")

    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--config", str(config_path)])
    # FR-002: truncated input is exit 0 + passed_with_warnings, not incomplete.
    assert result.exit_code == 0, result.output

    # Read the (single) manifest.
    manifests = list((tmp_path / "data" / "manifests").glob("*.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text())

    # SC-001 / SC-002: status with warnings, truncation surfaced.
    assert manifest["quality_checks"]["status"] == "passed_with_warnings"
    warning_names = [w["name"] for w in manifest["quality_checks"]["warnings"]]
    assert "parse_releases.truncated_xml" in warning_names

    # FR-013: step_metrics populated for parse_releases.
    assert "step_metrics" in manifest
    pr = manifest["step_metrics"].get("parse_releases", {})
    assert pr.get("peak_rss_bytes", 0) > 0

    # SC-001: DuckDB published; distinct count matches well-formed releases.
    db = tmp_path / "data" / "published" / "duckdb" / "discogs.duckdb"
    assert db.exists()
    con = duckdb.connect(str(db), read_only=True)
    try:
        n_distinct = con.execute(
            "SELECT COUNT(DISTINCT release_id) FROM release_fact"
        ).fetchone()[0]
        assert n_distinct == 404, f"expected 404 distinct releases, got {n_distinct}"

        # SC-002: UTF-8 round-trip — at least one descriptionsummary contains '⅓'.
        n_unicode = con.execute(
            "SELECT COUNT(*) FROM release_fact "
            "WHERE format_description_summary LIKE '%⅓%'"
        ).fetchone()[0]
        assert n_unicode >= 1, "expected at least one '⅓' in format_description_summary"
    finally:
        con.close()
