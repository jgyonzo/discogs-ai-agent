"""Static guard (Constitution VI; plan §Structure Decision):
- nothing under collection-agent/src imports etl/discogs_etl/discogs_agent
- collection_matcher and collection_agent never import each other
Mirrors agent/tests/unit/test_no_etl_imports.py."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

FORBIDDEN_EVERYWHERE = {"etl", "discogs_etl", "discogs_agent"}
FORBIDDEN_BY_PACKAGE = {
    "collection_matcher": {"collection_agent"},
    "collection_agent": {"collection_matcher"},
}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_forbidden_imports():
    violations: list[str] = []
    for py in SRC.rglob("*.py"):
        package = py.relative_to(SRC).parts[0]
        forbidden = FORBIDDEN_EVERYWHERE | FORBIDDEN_BY_PACKAGE.get(package, set())
        hits = _imported_roots(py) & forbidden
        if hits:
            violations.append(f"{py.relative_to(SRC)}: imports {sorted(hits)}")
    assert not violations, "cross-component imports found:\n" + "\n".join(violations)


def test_both_packages_present():
    # the guard is only meaningful if it actually scans both packages
    assert (SRC / "collection_matcher").is_dir()
    assert (SRC / "collection_agent").is_dir()
