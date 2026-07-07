"""Read-only guard for the eval package (023 T017, contracts/eval-results.md
§4, research R6): an eval run must be STRUCTURALLY incapable of writing to
Discogs or the scan session state. Static AST sweep, 013→014 precedent
(deterministic enforcement over prompt/code-review steering)."""

from __future__ import annotations

import ast
from pathlib import Path

EVAL_SRC = (
    Path(__file__).resolve().parents[2] / "src" / "collection_agent" / "eval"
)

FORBIDDEN_NAMES = {"add_to_collection", "create_folder", "move_instance"}
FORBIDDEN_MODULES = {
    "collection_agent.scan.journal",
    "collection_agent.scan.session",
}


def _violations() -> list[str]:
    found: list[str] = []
    for py in sorted(EVAL_SRC.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
                found.append(f"{py.name}:{node.lineno} references .{node.attr}")
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                found.append(f"{py.name}:{node.lineno} references {node.id}")
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in FORBIDDEN_MODULES:
                    found.append(f"{py.name}:{node.lineno} imports {module}")
                if any(alias.name in FORBIDDEN_NAMES for alias in node.names):
                    found.append(f"{py.name}:{node.lineno} imports a write method")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_MODULES:
                        found.append(f"{py.name}:{node.lineno} imports {alias.name}")
    return found


def test_eval_package_exists():
    assert EVAL_SRC.is_dir(), "eval package moved — update this guard"


def test_eval_package_has_no_write_capability():
    assert _violations() == [], (
        "the eval package gained a Discogs-write or scan-session reference — "
        "eval runs must stay structurally read-only (SC-006)"
    )
