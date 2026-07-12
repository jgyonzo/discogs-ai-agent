# Tasks: Dockerize the collection-agent

**Input**: Design documents from `/specs/027-dockerize-collection-agent/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R10), data-model.md, contracts/docker-packaging.md, quickstart.md

**Tests**: included — the spec makes the guard tests normative (FR-004 and contract §4), and the repo convention is deterministic enforcement over promises. No src/ code means no unit tests beyond the guards.

**Organization**: grouped by user story. US1 = containerized scan service, US2 = demo stack provably untouched, US3 = one-off/interactive modes. A hard cross-cutting invariant applies to every task: **zero changes under `collection-agent/src/`** (FR-009).

## Path Conventions

Component-owned infra lives in `collection-agent/`; the only file touched outside it is the repo-root `docker-compose.yml` (additive) and README docs. Guard tests: `collection-agent/tests/unit/` (they read repo-root files by path — 023 precedent).

---

## Phase 1: Setup (image foundations)

**Purpose**: the two new packaging files everything else builds on.

- [x] T001 [P] Create `collection-agent/.dockerignore` per contract §1 denylist: `data/`, `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `notebooks/`, `tests/` (research R7 — `data/` is 32 MB of personal/licensed content and must never reach the build context).
- [x] T002 [P] Create `collection-agent/Dockerfile` per contract §1 and research R1/R2: `FROM python:3.12-slim`; `PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1`; COPY exactly `pyproject.toml`, `src/`, `README.md` into `/app/collection-agent/`; `pip install -e /app/collection-agent` (**editable — load-bearing**, R2 path anchoring); no build-essential, no curl; `EXPOSE 8022`; `ENTRYPOINT ["python", "-m", "collection_agent"]`; `CMD ["scan"]`.

**Checkpoint**: both files exist; nothing depends on Docker yet.

---

## Phase 2: Foundational (image proves out)

**Purpose**: verify the image builds and is clean before wiring compose or writing guards against it.

- [x] T003 Build the image (`docker build -t collection-agent-027 collection-agent/`) and verify: build context upload is KB-scale (T001 effective); image contains only the COPY allowlist under `/app/collection-agent/` (no `data/` files, no `.env`); `docker run --rm collection-agent-027 status` runs the CLI (exit 2 without env is acceptable here — proves entrypoint + install work); `docker run --rm --entrypoint python collection-agent-027 -c "from collection_agent.settings import _COMPONENT_ROOT; print(_COMPONENT_ROOT)"` prints `/app/collection-agent` (R2 anchoring proof).

**Checkpoint**: image is stateless, entrypoint works, path anchoring confirmed — user stories can start.

---

## Phase 3: User Story 1 — Run the scan server as a containerized service (P1)

**Goal**: one compose command starts the scan server; phone scan-and-add lands in the same host `data/` files as a venv run.

**Independent Test**: quickstart step 4 — `docker compose --profile collection up collection-agent`, phone completes one scan-and-add, journal + stale mark appear under host `collection-agent/data/`.

- [x] T004 [US1] Add the `collection-agent` service to `docker-compose.yml` exactly per contract §2: `build.context: ./collection-agent`; `profiles: ["collection"]`; `env_file: [.env]`; `ports: ["8022:8022"]`; `volumes: ["./collection-agent/data:/app/collection-agent/data"]`; **no** `depends_on`, **no** `restart:`, **no** `healthcheck` (R3 failure posture); zero edits to the `postgres`/`agent-api`/`frontend` blocks and to the top-level `volumes:` key.
- [x] T005 [US1] Smoke-validate the service wiring (Docker, no phone): `docker compose --profile collection up collection-agent` with a valid `.env` → startup folder validation passes, uvicorn serves :8022, `curl -fs http://localhost:8022/` returns the scan page; stop; confirm any files created under `collection-agent/data/` are the pre-existing host files (mount, not copy). Then quickstart step 6: `docker compose --profile collection run --rm -e DISCOGS_USER_TOKEN= collection-agent scan` exits `2` once, no restart loop (SC-006, FR-010).
- [ ] T006 [US1] **Owner-only (live validation)**: quickstart step 4 / SC-001 — phone scan-and-add through the containerized server on the LAN; record session id + date in quickstart's owner checklist.

**Checkpoint**: scan service runs containerized against real host state; US1 deliverable complete (T006 may close post-merge per repo convention for owner-only live items).

---

## Phase 4: User Story 2 — The demo stack is provably untouched (P1)

**Goal**: plain `docker compose up` is byte-equivalent to pre-027; the invariant is enforced by tests, not review.

**Independent Test**: quickstart step 3 — token-less `.env`, `docker compose up -d` creates exactly `postgres`, `agent-api`, `frontend`; guard tests fail on any default-set drift.

- [x] T007 [US2] Create `collection-agent/tests/unit/test_docker_packaging.py` with a stdlib-only structural parser (research R4: two-space-indent service blocks; no PyYAML) and the compose guards from contract §4: (1) unprofiled service set == `{postgres, agent-api, frontend}` exactly; (2) `collection-agent` service exists with profile `collection`; (3) no `depends_on:` inside the `collection-agent` block and no other service block references `collection-agent`; (4) no `restart:` key in the `collection-agent` block.
- [x] T008 [US2] Extend `collection-agent/tests/unit/test_docker_packaging.py` with the hygiene grep-guards from contract §4: Dockerfile COPYs only `pyproject.toml`/`src`/`README.md`, contains no `.env` or `data/` reference, has `ENTRYPOINT ["python", "-m", "collection_agent"]` and `CMD ["scan"]`, and installs with `pip install -e` (editable — pins R2); `.dockerignore` contains `data/`, `.env`, `.venv/` entries.
- [x] T009 [US2] Validate the story end-to-end: `cd collection-agent && pytest tests/unit/test_docker_packaging.py -q` green; quickstart step 3 with a token-less `.env` → `docker compose ps --format '{{.Service}}'` lists exactly the three demo services and no `collection-agent` container exists (SC-002); mutate a copy of the compose file (add a bare service / drop the profile) and confirm the guards fail (guard sensitivity check — do not commit the mutation).

**Checkpoint**: non-interference is pinned by red/green tests; US2 complete and independently demonstrable.

---

## Phase 5: User Story 3 — One-off and interactive modes run containerized (P2)

**Goal**: `sync`/`status`/`chat`/`eval-*` run via `docker compose run --rm`, state-interchangeable with the host venv both directions, exit codes verbatim.

**Independent Test**: quickstart step 5 — containerized `sync` then host-venv `status` (and the reverse) report identical snapshot state.

- [x] T010 [US3] Validate one-off modes against real state (quickstart step 5): `docker compose run --rm collection-agent status` reads the owner's existing snapshot (created by the venv — host→container direction); confirm exit code propagation: `status` exit code matches snapshot completeness (0 complete / 3 partial), and a missing-token run exits 2 (FR-008 — codes verbatim through `compose run`).
- [x] T011 [US3] Validate interactivity + interrupt/resume (quickstart steps 5 & 7): `docker compose run --rm collection-agent chat` renders the prompt, answers one question from the snapshot, `/exit` → exit 0; start a containerized `sync`, Ctrl-C mid-run, re-run from the **host venv** → resumes from the journal (container→host direction; closes SC-003's bidirectional check).

**Checkpoint**: all six modes proven containerized; mixing container/venv within one workflow demonstrated.

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: documentation, full-suite verification, merged-state bookkeeping.

- [x] T012 [P] Update `collection-agent/README.md`: a "Run with Docker" section documenting the containerized form of every host command (contract §3 invocation table), the `--profile collection` opt-in, the phone-URL note (use the host's LAN IP, not the container banner — R8), the no-restart failure posture, and the Linux-host file-ownership caveat (R9). Host-venv instructions stay, unreplaced (FR-011).
- [x] T013 [P] Update the repo-root `README.md` docker-compose section: mention the opt-in `collection` profile in one or two lines (demo stack instructions unchanged).
- [x] T014 Full verification: `cd collection-agent && pytest` — all 536 pre-existing tests pass unmodified plus the new guards; `git diff main --stat -- collection-agent/src/` shows zero changes (SC-005); re-run the SC-004 image audit from quickstart step 2 on a fresh build.
- [x] T015 Write the 027 merged-state block into `CLAUDE.md` (replace the in-flight pointer; single-PR flow — feature + post-merge CLAUDE.md state land in ONE PR, owner decision 2026-07-07) and tick completed items in `quickstart.md`'s owner checklist that were validated pre-merge.
- [ ] T016 **Owner-only (live validation)**: remaining owner checklist items in `quickstart.md` — SC-001 phone scan (with T006), SC-003 bidirectional counts on the real collection, SC-004 audit sign-off, SC-006 loud-failure check; record dates/ids.

---

## Dependencies & Execution Order

```
Phase 1 (T001, T002 — parallel)
   └─▶ Phase 2 (T003 — needs both)
          └─▶ US1: T004 ─▶ T005 ─▶ T006 (owner)
                 └─▶ US2: T007 ─▶ T008 ─▶ T009   (guards assert the T004 service block)
                        └─▶ US3: T010 ─▶ T011     (needs image + compose wiring)
                               └─▶ Polish: T012/T013 [P] ─▶ T014 ─▶ T015 ─▶ T016 (owner)
```

- **US1 → US2 ordering**: the guards (T007) assert the service block T004 creates; writing them first would just make them red. US2 is still independently *testable* (its test criteria touch only the default stack).
- **Parallel opportunities**: T001 ∥ T002; T012 ∥ T013; within T007/T008 one file — sequential.
- **MVP scope**: Phases 1–4 (T001–T009). That ships a working containerized scan service with the non-interference invariant enforced — US3 is validation + docs on top of the same image.
- **Owner-only tasks**: T006, T016 — live LAN/phone validation; per repo convention these may close post-merge (022/023 precedent) but everything automatable closes pre-merge.

## Format validation

All tasks: checkbox ✓, sequential T001–T016 ✓, [P] only on independent-file tasks ✓, [US#] labels on story phases only ✓, exact file paths in every implementation task ✓.
