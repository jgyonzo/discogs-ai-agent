# Implementation Plan: Agent Frontend V1

**Branch**: `008-agent-frontend-v1` | **Date**: 2026-05-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-agent-frontend-v1/spec.md`

## Summary

Build a thin browser-based interface that turns the existing Discogs analytics agent into a demoable product. A user opens the page, types or clicks a question, and a chart appears inline alongside the agent's reply, the generated SQL, a small data preview, and routing badges. The frontend ships as a third component in this monorepo (alongside `etl/` and `agent/`), runs as a service in the existing local docker-compose stack, and depends only on the agent's already-shipped HTTP API (`POST /query`, `GET /artifacts/{id}`, `GET /health`) plus a single CORS allowance added to the agent.

The frontend never touches DuckDB, Postgres, ETL files, or local artifacts directly, and it never executes agent-generated Python or SQL. The chart artifact is rendered as opaque HTML inside a sandboxed `<iframe>`. All analytical work continues to happen in the agent.

The source brief at `docs/discogs_frontend_initial_spec.md` recommends React + Vite + TypeScript + Tailwind. This plan adopts that stack — the brief was written by the project author, the recommendations are sound for a single-page demo, and there's no benefit in deviating.

## Technical Context

**Language/Version**: TypeScript 5.x; Node.js 20 LTS for build tooling.
**Primary Dependencies**:
- `react` 18 + `react-dom` 18 (UI runtime)
- `vite` 5 (build / dev server)
- `tailwindcss` 3 (styling)
- `lucide-react` (icons; small, tree-shakeable)
- `clsx` (conditional className composition)
- `vitest` + `@testing-library/react` + `@testing-library/jest-dom` (unit + component tests)
- `msw` (Mock Service Worker — backs integration tests with a fake agent)

shadcn/ui is **not** adopted in V1 — it adds copy-into-source primitives that would inflate the change surface for a demo-shaped feature. We can hand-roll the handful of primitives needed (button, card, badge, collapsible) directly with Tailwind.

**Storage**: Browser `localStorage` only. Single key: `discogs.frontend.currentThreadId` (string). No frontend-side database, no IndexedDB, no service worker, no session cookie.

**Testing**:
- Vitest + React Testing Library for component tests.
- MSW for integration tests (frontend ↔ mocked agent), so we don't need the backend to run a frontend test pass.
- One Playwright-style end-to-end smoke test is **deferred** (V1 relies on the docker-compose smoke check from US5 instead).

**Target Platform**:
- Runtime: current evergreen desktop browsers (last 2 versions of Chrome, Firefox, Safari, Edge).
- Container: small Linux container running either Vite dev server (V1 default) or nginx serving a static build (V1.1 if time allows; chosen variant documented in `research.md`).
- Build host: any Node 20+ environment.

**Project Type**: Web application — a third top-level component (`frontend/`) joining `etl/` and `agent/`. The new component is intentionally thin: a single SPA that calls the agent's HTTP API.

**Performance Goals**:
- Initial bundle load < 2s on local cold cache.
- Chart artifact iframe paints within 1s of the chart artifact URL becoming available (Plotly inline-JS payloads are ~4 MB worst-case per the agent's existing tests).
- End-to-end query latency is dominated by the agent (`SC-003`: 15s budget for the cheap-model path on a warmed-up backend); frontend overhead negligible.

**Constraints**:
- The frontend MUST NOT read DuckDB, Postgres, or any project data file directly. (Spec FR-020. Statically verifiable: the frontend has no DB clients in its dependency manifest.)
- The frontend MUST NOT execute any agent-generated Python or SQL. (Spec FR-018, FR-019.)
- The chart artifact MUST be rendered in an isolated, sandboxed `<iframe>` — never via `dangerouslySetInnerHTML`. (Spec FR-021. The iframe `sandbox` attribute permits `allow-scripts` only, since Plotly's inline-JS needs to execute. `allow-same-origin` is **not** granted.)
- API base URL MUST be configurable via environment variable (`VITE_API_BASE_URL`) — no hardcoded URLs in source. (Spec FR-027 + Constitution VII.a.)
- No backend secrets, model API keys, database credentials, or admin tokens may live in frontend code or `.env` files committed to the repo. (Spec FR-022 + Constitution Secrets section.)

**Scale/Scope**:
- Local single-user demo. No multi-tenant concerns.
- One page, ~12-15 components, single bundle.
- Curated demo question set: 7 questions (one above the spec's `≥ 5` floor), covering simple aggregation, time series, format comparison, geographic ranking, label diversity, outlier detection, and master-grain joins (per the brief's recommended set).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Engaged? | Verdict |
|-----------|----------|---------|
| I — Layered, Contract-First Data Architecture | No | The frontend is two layers removed from the data layer. It does not consume any DuckDB layer; it consumes the agent's HTTP API. ✅ |
| II — Streaming, Bounded-Memory Processing | No | Pipeline-side principle; not engaged. The frontend never processes a dataset. ✅ |
| III — Reproducible Runs with Manifest & Logs | No | Pipeline-side principle. Not engaged. ✅ |
| IV — Data Quality Gates | No | Pipeline-side principle. Not engaged. ✅ |
| V — Agent-Friendly Analytics Surface | No | The frontend writes no SQL, defines no tables, performs no joins. The published-DuckDB surface area is unchanged. ✅ |
| VI — Two Components, One Contract | **Yes — extension** | This feature adds a **third** independently-deployable component to the monorepo. Principle VI's *operational rules* (own top-level directory, own dependency manifest, no cross-component imports, no reaching across the published-DuckDB boundary) extend cleanly to a third component: `frontend/` will have its own `package.json` and `Dockerfile`, will not import from `agent/` or `etl/`, and physically cannot read `data/` because it never has the volume mounted. The principle's *prose* ("This repository hosts two independently deployable components") is now empirically out of date. **Recommendation**: a PATCH-level constitution amendment after this feature lands, broadening Principle VI's framing from "two components" to "two or more components" without changing any operational rule. The amendment is **not** a prerequisite for this work; the operational rules already accommodate it. See "Constitution amendment recommendation" below. |
| VII.a — Configuration sources | Yes | The agent backend's URL is sourced from `import.meta.env.VITE_API_BASE_URL` (Vite-injected env var), with a development-only fallback to `http://localhost:8000` in the API client. No hardcoded URLs elsewhere. ✅ |
| VII.b — Prompt-authoring discipline | No | The frontend authors no prompts. The agent's prompts are unchanged by this feature. ✅ |
| VII.c — Read-only runtime mechanics | No (frontend); Touched (agent CORS) | The frontend has no read-only resources. The agent gains a CORS middleware permitting the local frontend origin — the backend's read-only DuckDB invariant is unchanged (CORS does not alter file-system access). ✅ |

**Gate result**: PASS. One extension-type item (Principle VI gains a third component) is documented and justified above; it does not block implementation.

**Component(s) touched**:
- **NEW**: `frontend/` (entire component).
- **MODIFIED**: `agent/src/discogs_agent/api.py` — add `CORSMiddleware` allowing the configured frontend origin(s). One-line wiring + one settings field. Documented as an amendment to `004/contracts/api.md` (see `contracts/amendment-004-api-cors.md`).
- **MODIFIED**: `docker-compose.yml` — add the `frontend` service and a depends-on edge from frontend → agent-api.
- **MODIFIED**: `CLAUDE.md` SPECKIT block — point at this plan.
- **NOT TOUCHED**: `etl/`. Zero edits.

### Constitution amendment recommendation

The constitution should be amended to reflect three components instead of two, in a follow-up change after this feature merges:

- **Version bump**: 1.2.0 → 1.2.1 (PATCH; framing/wording, no operational rule change).
- **Sections to update**:
  - Principle VI title/body: "two independently deployable components" → "two or more independently deployable components" (or equivalent), and inventory the third (`frontend/`).
  - Technical Constraints → Repository layout: extend the "working names `etl/` and `agent/`" sentence to include `frontend/`.
- **Why PATCH, not MINOR**: No new principle, no expanded operational rule. Existing rules ("each component has its own top-level directory and own dependency manifest, no cross-component imports") apply unchanged.
- **Why now-not-blocking**: The operational rules already permit the new component. Implementing the feature first lets the amendment cite a concrete second use of the rules (rather than amending speculatively).

This recommendation is captured here so it isn't lost; the amendment itself is **not** part of this feature's work.

## Project Structure

### Documentation (this feature)

```text
specs/008-agent-frontend-v1/
├── plan.md                                   # This file
├── research.md                               # Phase 0 — packaging, CORS, iframe, errors, state
├── data-model.md                             # Phase 1 — frontend domain types + storage
├── contracts/
│   ├── api-consumption.md                    # Which agent /query fields the frontend relies on
│   ├── amendment-004-api-cors.md             # Exact diff for 004/contracts/api.md (CORS)
│   └── curated-questions.md                  # The V1 curated question set (≥ 5)
├── checklists/
│   └── requirements.md                       # Already created by /speckit-specify
├── quickstart.md                             # Phase 1 — local dev + docker-compose bring-up
└── tasks.md                                  # Phase 2 (NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
frontend/                                     # NEW component (third in the monorepo)
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.ts
├── postcss.config.js
├── index.html
├── Dockerfile
├── README.md                                 # How to run this component (mirrors etl/agent READMEs)
├── public/                                   # Static assets (favicon, etc.)
└── src/
    ├── main.tsx                              # Vite entry
    ├── App.tsx                               # Layout, top-level state, query orchestration
    ├── index.css                             # Tailwind directives
    ├── api/
    │   ├── client.ts                         # fetch wrapper, env-driven base URL, error normalization
    │   └── types.ts                          # TS types matching agent /query response (see contracts/api-consumption.md)
    ├── components/
    │   ├── Header.tsx
    │   ├── ChatPanel.tsx
    │   ├── QueryInput.tsx
    │   ├── SuggestedQuestions.tsx
    │   ├── ResultPanel.tsx
    │   ├── ArtifactFrame.tsx                 # Sandboxed iframe rendering
    │   ├── SqlViewer.tsx                     # Collapsible, copy-to-clipboard
    │   ├── DataPreviewTable.tsx              # ≤ 20 rows
    │   ├── RunMetadata.tsx                   # Badges
    │   ├── ThreadControls.tsx                # New conversation
    │   ├── LoadingState.tsx
    │   └── ErrorBanner.tsx
    ├── data/
    │   └── curatedQuestions.ts               # The V1 question set (mirrors contracts/curated-questions.md)
    ├── hooks/
    │   ├── useThreadId.ts                    # localStorage-backed
    │   └── useAgentQuery.ts                  # submit + state machine
    └── utils/
        ├── localStorage.ts
        └── errors.ts                         # Translate agent error envelopes to user-facing strings

frontend/tests/                               # Co-located test setup
├── setup.ts                                  # vitest + RTL config
├── mocks/
│   └── handlers.ts                           # MSW: /query, /artifacts/:id, /health
├── unit/
│   ├── client.test.ts                        # fetch wrapper, error normalization
│   ├── localStorage.test.ts
│   └── errors.test.ts
├── components/
│   ├── ChatPanel.test.tsx
│   ├── ResultPanel.test.tsx
│   ├── SuggestedQuestions.test.tsx
│   └── ThreadControls.test.tsx
└── integration/
    └── full-flow.test.tsx                    # MSW-backed: type → submit → chart → SQL panel
```

```text
agent/src/discogs_agent/api.py                # MODIFIED — CORSMiddleware wiring
agent/src/discogs_agent/config.py             # MODIFIED — CORS_ALLOWED_ORIGINS settings field
specs/004-agent-v1/contracts/api.md           # AMENDED — new "Cross-origin policy" section (see contracts/amendment-004-api-cors.md)
docker-compose.yml                            # MODIFIED — new `frontend` service + depends_on agent-api
```

**Structure Decision**: New top-level `frontend/` component, mirroring the `etl/` and `agent/` pattern (own dependency manifest, own Dockerfile, own README, own tests). Co-located test directory under `frontend/tests/` to match each component's existing convention. The agent gets a single targeted edit (CORS) plus a documented amendment to `004/contracts/api.md`. The constitution is **not** amended in this feature; a follow-up PATCH amendment is recommended (see Constitution Check).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(No violations to justify. The Principle VI extension is documented and approved above, with a recommended follow-up amendment.)

## Phase 0 — Research

Five focused decisions. The full long-form is in [`research.md`](./research.md); the recap below is what the Constitution Check trail needs to know.

1. **Container packaging — dev-server vs static build**: ship V1 with the **Vite dev-server** running in the container (`npm run dev -- --host 0.0.0.0`), exposing port 5173. A production-like nginx-served static build is left as a stretch (`research.md` carries the upgrade recipe). Reason: dev-server has zero build-cache complexity, hot reload is useful during demo prep, and the perf delta on a single-user local demo is negligible. The feature is local-only (Spec NF-005), so the production-shape is not on the demo path.

2. **CORS configuration approach**: add `CORSMiddleware` in `agent/src/discogs_agent/api.py` (the existing FastAPI app object), with allowed origins driven by a new `CORS_ALLOWED_ORIGINS` settings field defaulting to `["http://localhost:5173", "http://localhost:3000"]`. Settings-sourced (Constitution VII.a). The middleware is permissive on methods (GET, POST, OPTIONS) and headers (`*`), but does **not** allow credentials (no cookies in V1). Documented as an amendment to `004/contracts/api.md` (`contracts/amendment-004-api-cors.md`).

3. **Iframe sandbox attributes**: `<iframe sandbox="allow-scripts" srcDoc={...} />` is the wrong pattern (we don't have the HTML inline; we have a URL). The frontend uses `<iframe src={artifactUrl} sandbox="allow-scripts" />`. `allow-same-origin` is **NOT** granted — the agent's chart artifacts are static HTML with inline JS and don't need to read cookies or call back to the parent origin. Reason: belt-and-braces isolation; if the agent ever served compromised HTML, the iframe couldn't cross-script the parent.

4. **Error message translation**: the agent's `/query` endpoint has *two* failure surfaces — controlled-failure HTTP-200 responses with `status: "failed_*"` (4 codes), and HTTP 4xx/5xx with the standard error envelope. The frontend maps both to user-facing copy via `utils/errors.ts`. Controlled-failures show the agent's `response` field verbatim (it's already user-friendly). HTTP errors map by `error.code` to a small dictionary of plain-language messages. No raw tracebacks ever shown.

5. **State management approach**: plain `useState` + a single `useReducer` for the chat-message timeline. No external store (no Redux, no Zustand, no Jotai). Reason: the spec is bounded — single page, single conversation in flight at a time, no cross-route persistence. `useReducer` is enough to keep the message-append logic atomic and testable.

**Output**: [`research.md`](./research.md) with the long-form decisions and the alternatives considered for each.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete (decisions 1–5 above resolved).

1. **Entities** → [`data-model.md`](./data-model.md). Frontend domain types only — no database. Covers `ChatMessage`, `Conversation`, `ChartArtifact`, `RunMetadata`, `CuratedQuestion`, plus the localStorage shape (`{ currentThreadId: string | null }`).

2. **Contracts** → three documents under [`contracts/`](./contracts/):

   a. **[`api-consumption.md`](./contracts/api-consumption.md)** — the contract from the *frontend's* side: which fields of `POST /query`'s 200-OK response the frontend reads, which it ignores, and the failure-mode mapping (controlled-failure HTTP-200 with `status: "failed_*"` vs. HTTP 4xx/5xx). This document is the load-bearing contract for "the frontend works against the agent as it actually exists today" (Spec FR-024). It explicitly does not modify the agent's contract; it captures the consumption shape.

   b. **[`amendment-004-api-cors.md`](./contracts/amendment-004-api-cors.md)** — the exact prose for a new "Cross-origin policy" subsection in `specs/004-agent-v1/contracts/api.md`. Documents (i) which origins are allowed by default, (ii) the env override (`CORS_ALLOWED_ORIGINS`), (iii) which methods and headers are permitted, and (iv) the explicit `allow_credentials = False` decision. Lands in 004's contract directory in the same change set, mirroring how 007 amended `004/contracts/code-generation.md §3.1`.

   c. **[`curated-questions.md`](./contracts/curated-questions.md)** — the V1 curated question set. Seven questions, each with title, category, query text, optional description, and a "demonstrates" tag indicating which agent capability it exercises (simple aggregate, time series, format comparison, geographic ranking, label diversity, outlier detection, master-grain join). The data file `frontend/src/data/curatedQuestions.ts` MUST mirror this contract.

3. **Quickstart** → [`quickstart.md`](./quickstart.md). Walks through:
   - Local dev: `cd frontend && npm install && npm run dev` + open `http://localhost:5173` (assumes the agent is already running).
   - Full-stack docker-compose: `docker compose up --build` and open `http://localhost:5173`.
   - Smoke test: how to verify the chart-rendering loop succeeds end-to-end.
   - Where the localStorage key lives and how to clear it.

4. **Agent context update** → update the SPECKIT block in `CLAUDE.md` to point at this plan and link to phase-1 artifacts. Pattern matches the 007 update — short paragraph + bulleted artifact links + retention of the priors-and-still-authoritative section.

**Output of Phase 1**: `data-model.md`, three files under `contracts/`, `quickstart.md`, and updated `CLAUDE.md` SPECKIT block.

## Re-check Constitution Check after Phase 1 design

Phase 1 produced:
- One new component directory tree (`frontend/`) — operational rules of Principle VI are satisfied (own dependency manifest, no cross-component imports, no data-layer reaches).
- One backend amendment (`agent/api.py` CORS) — covered by Principle VII.a (settings-sourced, no hardcoded origins).
- One contract amendment (`004/contracts/api.md`) — adding a section, not changing existing prose; same pattern as the 007 amendment to `004/contracts/code-generation.md`.
- No new principles engaged; no new violations; no new env-var-shaped surprises.

The PATCH-level constitution amendment recommendation (Principle VI prose: "two" → "two or more") still stands as **follow-up work**, not a prerequisite for this feature.

**Gate result (post-design)**: PASS. No new violations introduced.
