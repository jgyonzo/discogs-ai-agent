# Implementation Plan: Dockerize the collection-agent

**Branch**: `027-dockerize-collection-agent` | **Date**: 2026-07-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/027-dockerize-collection-agent/spec.md`

## Summary

Package the collection-agent as one container image (all six CLI modes via
`ENTRYPOINT python -m collection_agent`, default `scan`) and wire the scan
server into the repo compose file as an **opt-in** service
(`profiles: ["collection"]`, port 8022, `env_file: .env`, one bind mount of
`collection-agent/data/`). The load-bearing discovery (research R2): the
component's Settings anchor every path default to the *installed source
location* (`settings.py:17`, `Path(__file__).resolve().parents[2]`), so an
editable install at `/app/collection-agent` makes every default resolve
inside the data mount — satisfying state interchangeability (FR-006) and
zero source changes (FR-009) simultaneously, with no env overrides and no
new Settings fields. Non-interference with the demo stack is enforced, not
promised: stdlib-only guard tests pin the default compose service set, the
profile, the no-`depends_on`/no-`restart` isolation, and the Dockerfile/
`.dockerignore` hygiene. Deliberate failure posture: no restart policy, so
a failed live startup validation exits loudly once (exit 2) instead of
retry-looping against Discogs (FR-010). New contract:
`contracts/docker-packaging.md`. Zero Python source changes; zero new
Python dependencies; two new files (`collection-agent/Dockerfile`,
`collection-agent/.dockerignore`), one compose service block, one guard-test
module, README additions.

## Technical Context

**Language/Version**: Python 3.12 (image `python:3.12-slim`; component `requires-python >=3.12`)
**Primary Dependencies**: none added — existing manifest (fastapi/uvicorn/openai/httpx/pydantic(-settings)/rich/langsmith + matcher's duckdb/pandas/rapidfuzz) is wheel-complete on slim (research R1). Docker Engine + Compose v2 (profiles support) as host tooling.
**Storage**: unchanged — component-local files under `collection-agent/data/`, bind-mounted `./collection-agent/data:/app/collection-agent/data` (research R2)
**Testing**: pytest, `cd collection-agent && pytest`; 536 existing tests MUST pass unmodified; new stdlib-only packaging guards (research R4) — suite stays offline, no Docker daemon required by any test
**Target Platform**: Docker Desktop on macOS (owner's machine, arm64) as target of record; any Linux Docker host secondarily (root-owned-files caveat documented, research R9)
**Project Type**: packaging/infrastructure for an existing multi-mode CLI + LAN HTTP service — no application code
**Performance Goals**: none new — vision/search latencies are the process's own; image build is local-dev-scale (context KBs after `.dockerignore`, R7)
**Constraints**: demo-stack default service set byte-stable (FR-003/004/005); no secrets/personal data in image or context (FR-007); exit codes 0/1/2/3 verbatim through `docker compose run` (FR-008); no restart policy on the service (FR-010)
**Scale/Scope**: single-owner LAN deployment; ~4 new/edited infra files + 1 test module + README; no `src/` changes

## Constitution Check

*GATE: evaluated against constitution v1.2.1. Components touched:
`collection-agent` (packaging only) + the repo-root `docker-compose.yml`
(shared orchestration file; additive, profile-gated).*

| Principle | Engaged? | Assessment |
|---|---|---|
| I. Layered, contract-first data | No | No data layer touched. The packaging gets its own NEW contract (`docker-packaging.md`) in the contract-first spirit; no existing contract amended. |
| II. Bounded memory | No | No processing paths changed. |
| III. Reproducible runs | No | No pipeline execution added; sync/eval journaling and resume are unchanged inside the container (quickstart step 7 verifies). |
| IV. Data quality gates | No | No layer outputs. |
| V. Agent-friendly surface | No | No analytics surface change. |
| VI. Components & Contracts | **Yes — core** | PASS. Packaging preserves every rule: no cross-component imports (none added); component keeps its own manifest (image builds from `collection-agent/pyproject.toml` alone; build context cannot see siblings); component runs end-to-end with no other component's process (no `depends_on` either direction, guard-tested). The compose file is shared orchestration, not coupling — services coexist without contract contact (frontend precedent), and the default-service-set guard turns non-interference into an enforced invariant. `collection_matcher` remains read-only over the published DuckDB and is explicitly NOT containerized as a workflow (FR-012). |
| VII(a). Config from settings | **Yes** | PASS. Zero new Settings fields; no config value duplicated into compose `environment:` blocks (R5 — `.env` stays the single source); Dockerfile ENV sets only Python hygiene flags (`PYTHONUNBUFFERED` etc.), never app config. The R2 layout choice exists precisely so that no path setting needs a hardcoded container override. |
| VII(b). Prompt authoring | No | No prompts touched. |
| VII(c). Read-only mechanics | **Yes (consequence documented)** | PASS. The one mount is deliberately read-write (journals/snapshot/eval writes). The image's *stateless* rootfs is the read-only-adjacent constraint: all write paths the runtime performs (snapshot, journals, retention, eval) resolve under the mount via R2's anchoring — documented in the contract §1/§2 so no write lands in a container layer and silently vanishes on restart. |
| Secrets constraint | **Yes** | PASS. `.env` never enters build context (context = `collection-agent/`; R7 denylist as defense in depth) or image layers; runtime injection via compose `env_file` (agent-api precedent). Guard-tested + SC-004 audit. |
| Workflow gates | Yes | This plan includes the Constitution Check; phases commit artifacts before the next phase; component touched is stated above. |

**Initial gate: PASS (no violations; Complexity Tracking empty).**
**Post-Phase-1 re-check: PASS** — design artifacts introduce no new
dependencies, no source changes, no contract amendments; the one new
contract is additive.

## Project Structure

### Documentation (this feature)

```text
specs/027-dockerize-collection-agent/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 — R1–R10 (image, path anchoring, gating, guards…)
├── data-model.md        # Phase 1 — packaging entities & invariants
├── quickstart.md        # Phase 1 — validation steps + owner checklist
├── contracts/
│   └── docker-packaging.md   # NEW contract: image / compose / invocation / guards
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 (/speckit-tasks — not created by /speckit-plan)
```

### Source Code (repository root)

```text
docker-compose.yml                     # EDIT (additive): collection-agent service, profile-gated
collection-agent/
├── Dockerfile                         # NEW — python:3.12-slim, editable install, ENTRYPOINT/CMD
├── .dockerignore                      # NEW — data/, .env, .venv/, caches, notebooks, tests
├── README.md                          # EDIT — containerized command forms + phone-URL note
├── pyproject.toml                     # unchanged (no new deps)
├── src/                               # unchanged — zero edits (FR-009, SC-005)
└── tests/
    └── unit/
        └── test_docker_packaging.py   # NEW — guards: default service set, profile,
                                       #   isolation, Dockerfile/.dockerignore hygiene
```

**Structure Decision**: infrastructure files live inside the component
directory (its Dockerfile, its `.dockerignore`, its guard tests — Principle
VI: each component owns its packaging); the only file touched outside it is
the shared `docker-compose.yml`, additively, plus repo/component README
documentation. The guard tests live in `collection-agent/tests/unit/` and
read the repo-root compose file by path — the 023 precedent (that suite
already pins the repo-root `.gitignore`).

## Complexity Tracking

No constitution violations — table intentionally empty.
