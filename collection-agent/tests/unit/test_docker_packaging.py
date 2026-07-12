"""Packaging guards (027, contracts/docker-packaging.md §4).

Non-interference with the demo stack is a contract, not a promise: plain
`docker compose up` must start exactly the pre-027 service set, and the
collection-agent service must stay profile-gated, dependency-free, and
restart-free (a restart policy would turn a failed live startup validation
into an unbounded Discogs retry loop — spec FR-010). The compose file is
parsed structurally with stdlib only (research R4: no PyYAML — the
zero-new-dependencies streak holds); Dockerfile/.dockerignore hygiene is
grep-pinned (research R7: the build context must never carry `data/` or
`.env`).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPONENT_ROOT = REPO_ROOT / "collection-agent"

# The demo stack as it existed before 027 (spec FR-003/FR-004). A change to
# this set — in either direction, from any feature — is a contract violation
# unless docker-packaging.md is amended first.
EXPECTED_DEFAULT_SERVICES = {"postgres", "agent-api", "frontend"}


def _parse_services() -> dict[str, list[str]]:
    """Map each compose service name to its (stripped, comment-free) block lines.

    Deliberately structural, not YAML: service names are the two-space-
    indented keys under the top-level `services:` key in the hand-maintained
    compose file; everything more indented belongs to the preceding service.
    """
    text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    services: dict[str, list[str]] = {}
    in_services = False
    current: str | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            in_services = stripped == "services:"
            current = None
            continue
        if not in_services:
            continue
        if indent == 2 and stripped.endswith(":"):
            current = stripped[:-1]
            services[current] = []
        elif current is not None:
            services[current].append(stripped)
    return services


def _collection_agent_block() -> list[str]:
    services = _parse_services()
    assert "collection-agent" in services, (
        "docker-compose.yml lost the collection-agent service (027)"
    )
    return services["collection-agent"]


# --- contract §4 guard 1: the default service set is pinned -----------------


def test_default_service_set_is_exactly_the_demo_stack():
    services = _parse_services()
    unprofiled = {
        name
        for name, block in services.items()
        if not any(line.startswith("profiles:") for line in block)
    }
    assert unprofiled == EXPECTED_DEFAULT_SERVICES, (
        f"plain `docker compose up` would start {sorted(unprofiled)} instead "
        f"of {sorted(EXPECTED_DEFAULT_SERVICES)} — the default service set "
        "is contract-pinned (docker-packaging.md §2); gate new services "
        "behind a profile or amend the contract first"
    )


# --- contract §4 guard 2: the collection-agent service shape ----------------


def test_collection_agent_service_is_profile_gated():
    block = _collection_agent_block()
    profile_lines = [l for l in block if l.startswith("profiles:")]
    assert profile_lines and "collection" in profile_lines[0], (
        "collection-agent service must carry profiles: [\"collection\"] — "
        "without it, token-less demo users start a live-validating scan "
        "server on `docker compose up`"
    )


def test_collection_agent_mounts_component_data_and_publishes_8022():
    block = _collection_agent_block()
    assert "- ./collection-agent/data:/app/collection-agent/data" in block, (
        "the data bind mount is load-bearing (research R2): settings path "
        "defaults resolve to /app/collection-agent/data inside the "
        "container — without this exact mount, container state diverges "
        "from the host venv's"
    )
    assert any(l in ('- "8022:8022"', "- 8022:8022") for l in block), (
        "scan port 8022 must be published for LAN phones (spec FR-002)"
    )
    assert "- .env" in block, (
        "env_file must inject the repo-root .env (spec FR-007) — config "
        "must not be duplicated into environment: blocks"
    )


# --- contract §4 guard 3: isolation in both directions -----------------------


def test_no_dependency_edges_touch_collection_agent():
    services = _parse_services()
    ca_block = services.get("collection-agent", [])
    assert not any(l.startswith("depends_on") for l in ca_block), (
        "collection-agent must not depend on any service (spec FR-005)"
    )
    offenders = [
        name
        for name, block in services.items()
        if name != "collection-agent"
        and any("collection-agent" in line for line in block)
    ]
    assert not offenders, (
        f"existing services reference collection-agent: {offenders} — the "
        "demo stack must run without it (spec FR-005)"
    )


# --- contract §4 guard 3 (cont.): failure posture ----------------------------


def test_collection_agent_has_no_restart_policy():
    block = _collection_agent_block()
    assert not any(l.startswith("restart") for l in block), (
        "collection-agent must have NO restart policy: scan startup "
        "validates the Discogs folder LIVE and exits 2 on bad config — "
        "auto-restart converts that loud exit into an unbounded live-API "
        "retry loop (spec FR-010, research R3)"
    )


# --- contract §4 guard 4: Dockerfile hygiene ---------------------------------


def _dockerfile_text() -> str:
    return (COMPONENT_ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_copies_only_the_allowlist():
    copy_sources = set()
    for line in _dockerfile_text().splitlines():
        if line.startswith("COPY"):
            parts = line.split()
            copy_sources.add(parts[1])
    assert copy_sources == {"pyproject.toml", "src", "README.md"}, (
        f"Dockerfile COPYs {sorted(copy_sources)} — the image contents "
        "allowlist is exactly pyproject.toml/src/README.md "
        "(docker-packaging.md §1)"
    )


def test_dockerfile_never_references_secrets_or_data():
    text = _dockerfile_text()
    assert ".env" not in text, "Dockerfile must never reference .env"
    assert "data/" not in text, (
        "Dockerfile must never reference data/ — state stays on the host "
        "(spec FR-007)"
    )


def test_dockerfile_entrypoint_default_and_editable_install():
    text = _dockerfile_text()
    assert 'ENTRYPOINT ["python", "-m", "collection_agent"]' in text, (
        "entrypoint must be the component CLI (spec FR-001)"
    )
    assert 'CMD ["scan"]' in text, (
        "the image's default command is the scan service — the CLI's own "
        "default is chat, which would hang a headless container (spec FR-001)"
    )
    assert "pip install -e" in text, (
        "the install must be EDITABLE: settings.py anchors every data-path "
        "default to the source location (parents[2]); a site-packages "
        "install silently breaks all of them (research R2)"
    )


# --- contract §4 guard 5: .dockerignore hygiene ------------------------------


def test_dockerignore_excludes_personal_data_and_secrets():
    lines = [
        l.strip()
        for l in (COMPONENT_ROOT / ".dockerignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    for required in ("data/", ".env", ".venv/"):
        assert required in lines, (
            f".dockerignore lost `{required}` — the build context would "
            "carry personal collection data / secrets / a virtualenv to the "
            "Docker daemon (research R7, spec FR-007)"
        )
