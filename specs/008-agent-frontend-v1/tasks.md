# Tasks: Agent Frontend V1

**Input**: Design documents from `/specs/008-agent-frontend-v1/`
**Prerequisites**:
- Plan: [plan.md](./plan.md)
- Spec: [spec.md](./spec.md)
- Research: [research.md](./research.md) (R1–R5: packaging, CORS, iframe sandbox, error mapping, state)
- Data model: [data-model.md](./data-model.md) (frontend domain types + reducer state + localStorage shape)
- Contracts:
  - [contracts/api-consumption.md](./contracts/api-consumption.md) (which `/query` fields the frontend reads / ignores / maps)
  - [contracts/amendment-004-api-cors.md](./contracts/amendment-004-api-cors.md) (verbatim §8 insertion text for `004/contracts/api.md`)
  - [contracts/curated-questions.md](./contracts/curated-questions.md) (V1 set of 7 questions and their spread coverage)
- Quickstart: [quickstart.md](./quickstart.md)

**Tests**: included — Spec §28 ("Testing Strategy") explicitly requires Vitest + React Testing Library unit/component tests, MSW-backed integration tests, and a docker smoke check. SC-001, SC-002, SC-006, SC-008, SC-009, SC-010 are test-anchored.

**Components touched**:
- **NEW**: `frontend/` (entire component, third top-level alongside `etl/` and `agent/`).
- **MODIFIED**: `agent/src/discogs_agent/api.py`, `agent/src/discogs_agent/config.py`, `agent/.env.example`, `docker-compose.yml`, root `README.md`, `CLAUDE.md` SPECKIT block (already updated by `/speckit-plan`).
- **AMENDED**: `specs/004-agent-v1/contracts/api.md` (new §8).
- **NOT TOUCHED**: `etl/`. Zero edits.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in the same phase).
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5).
- File paths are absolute relative to the repo root and should be created/edited as named.

## Path Conventions

- New frontend component: `frontend/`
  - Source: `frontend/src/`
  - Tests: `frontend/tests/`
  - Static config: `frontend/{package.json,tsconfig.json,vite.config.ts,tailwind.config.ts,postcss.config.js,index.html,Dockerfile,README.md,.env.example,.gitignore}`
- Agent source (modified): `agent/src/discogs_agent/`
- Cross-feature contract amendment target: `specs/004-agent-v1/contracts/api.md`
- Compose orchestration: repo-root `docker-compose.yml`

---

## Phase 1: Setup

**Purpose**: Initialize the new `frontend/` component with its tooling, dependency manifests, and entry points. No business logic yet.

- [X] T001 Create the `frontend/` directory tree per [plan.md](./plan.md) §"Source Code". Empty subdirectories: `frontend/public/`, `frontend/src/{api,components,data,hooks,utils}/`, `frontend/tests/{mocks,unit,components,integration}/`. Add a placeholder `.gitkeep` only where Git would otherwise drop the empty directory.
- [X] T002 Initialize the Vite + React + TypeScript project at `frontend/` by writing the static config files: `frontend/package.json` (declaring runtime deps: `react@^18`, `react-dom@^18`, `lucide-react`, `clsx`; dev deps: `typescript@^5`, `vite@^5`, `@vitejs/plugin-react`, `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@types/react`, `@types/react-dom`, `msw`, `tailwindcss`, `postcss`, `autoprefixer`; scripts: `dev`, `build`, `preview`, `test`, `test:watch`, `typecheck`); `frontend/tsconfig.json` (strict, `module: "ESNext"`, `jsx: "react-jsx"`, `moduleResolution: "bundler"`); `frontend/vite.config.ts` (React plugin, dev server `host: true` and `port: 5173`); `frontend/index.html` (root `<div id="root">`, links `/src/main.tsx`); `frontend/src/main.tsx` (React 18 `createRoot` mounting `<App />`); a stub `frontend/src/App.tsx` returning a single `<h1>Discogs Analytics Agent</h1>` so `npm run dev` boots before any other tasks land.
- [X] T003 [P] Add Tailwind CSS plumbing: `frontend/tailwind.config.ts` (content globs covering `./index.html` and `./src/**/*.{ts,tsx}`); `frontend/postcss.config.js` (Tailwind + Autoprefixer); `frontend/src/index.css` with the `@tailwind base/components/utilities` directives; import `./index.css` in `frontend/src/main.tsx`. Smoke-verify by adding a Tailwind utility class to the stub `<h1>` from T002.
- [X] T004 [P] Wire up the Vitest + React Testing Library + MSW test environment: `frontend/vitest.config.ts` (test environment `jsdom`, `setupFiles: ["./tests/setup.ts"]`, globals on); `frontend/tests/setup.ts` (`@testing-library/jest-dom` import; `beforeAll` that boots an MSW server stub — full handlers added in T010); `frontend/tests/tsconfig.json` extending the root tsconfig with `types: ["vitest/globals", "@testing-library/jest-dom"]`. Verify `npm test` exits 0 with zero suites collected.
- [X] T005 [P] Add the per-component metadata files: `frontend/.gitignore` (covers `node_modules/`, `dist/`, `.env.local`, `.vite/`, `coverage/`); `frontend/.env.example` carrying `VITE_API_BASE_URL=http://localhost:8000`; `frontend/README.md` mirroring the structure of `agent/README.md` and `etl/README.md` (one-paragraph what-it-is + "Run locally" + "Run in compose" + "Run tests" sections, all referencing [quickstart.md](./quickstart.md) for the canonical commands).

**Checkpoint**: `cd frontend && npm install && npm run dev` boots and serves a Tailwind-styled stub page on `http://localhost:5173`. `npm test` exits 0. The component has its own dependency manifest (Constitution Principle VI satisfied for the new component).

---

## Phase 2: Foundational

**Purpose**: Cross-cutting infrastructure that EVERY user story depends on — domain types, the API client, the error translation table, the localStorage wrapper, the MSW mock backend, and the agent-side CORS plumbing. No story implementation begins until this phase is complete.

**⚠️ CRITICAL**: User stories cannot be implemented in any order before this phase finishes — they all import the API client, the types, or the utils.

- [X] T006 Define the frontend's TypeScript domain types in `frontend/src/api/types.ts`: `ChartArtifact`, `ResponseStatus` (the 5-value union), `RunMetadata`, `Carryover`, `ChatMessage` (the `UserMessage | AssistantMessage` discriminated union), `CuratedQuestion`, `AgentCapability`, `UserFacingError`, `QueryRequest`, `QueryResponse`, `ApiErrorEnvelope`, and the reducer types `AppState` + `Action`. Source of truth is [data-model.md](./data-model.md) §1, §2.1, §4 — those types must match field-for-field. Mark `code: null` on `QueryResponse` (V1 always sends `debug: false`); the comment must say "see contracts/api-consumption.md §3.1 — frontend ignores `code` regardless." Export everything as named exports; no default export.
- [X] T007 [P] Implement the localStorage wrapper at `frontend/src/utils/localStorage.ts` exposing `getCurrentThreadId(): string | null`, `setCurrentThreadId(id: string): void`, `clearCurrentThreadId(): void`. Single key constant `KEY = "discogs.frontend.currentThreadId"` per [data-model.md](./data-model.md) §3. All three functions wrap their `localStorage.*` call in `try { ... } catch { return null / no-op }` so private-mode browsers and `QuotaExceededError` failures degrade silently (FR-009 + data-model §3 invariant). Do NOT use `JSON.parse` — the value is a plain string UUID.
- [X] T008 [P] Implement the error-translation utility at `frontend/src/utils/errors.ts` exposing `translateHttpError(envelope: ApiErrorEnvelope): UserFacingError`, `translateNetworkError(err: unknown): UserFacingError`, `translateParseError(err: unknown): UserFacingError`. The dictionary mapping `error.code` → user-facing copy is verbatim from [research.md](./research.md) §R4 (table in §R4 "The mapping dictionary (V1)"). Unknown `error.code` falls back to the `internal_error` copy. Each translator drops `error.message`, `error.details`, and the original error object (do NOT include them in the returned `UserFacingError` — data-model §1.7 invariant). Each translator calls `console.warn`/`console.error` with the original payload so developers can still debug.
- [X] T009 Implement the API client at `frontend/src/api/client.ts` exposing `sendQuery(req: QueryRequest): Promise<QueryResponse>`, `toAbsoluteArtifactUrl(relativeUrl: string): string`, and `fetchHealth(): Promise<HealthResponse>` (last is optional in V1; stub OK). The implementation MUST: (a) read `import.meta.env.VITE_API_BASE_URL`, falling back to `http://localhost:8000` if undefined per Constitution VII.a; (b) `POST /query` with `Content-Type: application/json`, body `JSON.stringify(req)` — omitting `thread_id` from the body when it's null/undefined per [contracts/api-consumption.md](./contracts/api-consumption.md) §2; (c) on response: if `response.ok` and JSON is well-shaped, return it; if `response.status === 404` and parsed `error.code === "thread_not_found"`, clear `localStorage`, drop `thread_id` from `req`, retry exactly once — if the retry also fails, propagate normally per api-consumption §4 special case; (d) on non-OK HTTP, parse the error envelope and `throw translateHttpError(envelope)`; (e) on `TypeError` / abort / network failure, `throw translateNetworkError(err)`; (f) on JSON parse failure, `throw translateParseError(err)`. `toAbsoluteArtifactUrl` joins `${API_BASE_URL}${relativeUrl}` only when `relativeUrl.startsWith("/")` (defensive — agent might one day return absolute URLs). Depends on T006, T007, T008.
- [X] T010 [P] Add MSW mocked-backend handlers at `frontend/tests/mocks/handlers.ts` covering: success path `POST /query` returning the full `QueryResponse` shape from [contracts/api-consumption.md](./contracts/api-consumption.md) §3 with a generated `thread_id`/`run_id`, populated `chart_artifact`, `sql`, `dataframe_preview`, and `route`; controlled-failure path returning HTTP 200 with `status: "failed_unsupported"` and `chart_artifact: null`; HTTP 404 `thread_not_found` returning the standard error envelope; HTTP 500 `internal_error`; `GET /artifacts/:id` returning a tiny inline Plotly HTML stub (≤ 1 KB — enough that an iframe load test passes); `GET /health` returning `status: "ok"`. Wire the handlers into `frontend/tests/setup.ts` via `setupServer(...handlers).listen({ onUnhandledRequest: "error" })`. Helper: `frontend/tests/mocks/factories.ts` exposing `makeQueryResponse(overrides?)`, `makeAssistantMessage(overrides?)` so individual tests can construct shaped data without re-listing every required field. Depends on T006.
- [X] T011 [P] Add the `cors_allowed_origins` settings field to `agent/src/discogs_agent/config.py`: type `list[str]`, default `["http://localhost:5173", "http://localhost:3000"]`, env var name `CORS_ALLOWED_ORIGINS`. Use the same comma-separated-string-to-list `field_validator` pattern already in use in that file; follow the surrounding code style verbatim. Add a one-line docstring referencing [contracts/amendment-004-api-cors.md](./contracts/amendment-004-api-cors.md) §8.2. Per Constitution VII.a, do NOT hardcode the allowlist anywhere except as the default. Implementation note: field name landed as `CORS_ALLOWED_ORIGINS` (UPPER_CASE, matching surrounding fields like `CHEAP_MODEL`, `STRONG_MODEL`); the contract amendment used `settings.cors_allowed_origins` in prose, but the actual settings field follows the project's UPPER_CASE convention.
- [X] T012 Wire `fastapi.middleware.cors.CORSMiddleware` into `agent/src/discogs_agent/api.py` immediately after the `app = FastAPI(...)` line (line 33) and BEFORE the route module imports near line 42. Parameters per [contracts/amendment-004-api-cors.md](./contracts/amendment-004-api-cors.md) §8.3: `allow_origins=settings.CORS_ALLOWED_ORIGINS`, `allow_methods=["GET","POST","OPTIONS"]`, `allow_headers=["*"]`, `allow_credentials=False`, `max_age=600`. Add the import `from fastapi.middleware.cors import CORSMiddleware` to the top of the file. Depends on T011 (settings field must exist before the middleware reads from it).
- [X] T013 [P] Add `CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000` to the repo-root `.env.example` (the project keeps a single `.env.example` at the repo root, not under `agent/`). Comment line above it: `# Comma-separated origins permitted for browser-based requests (008-agent-frontend-v1)`.
- [X] T014 [P] Apply the contract amendment to `specs/004-agent-v1/contracts/api.md`: insert the verbatim §8 "Cross-origin policy" section from [contracts/amendment-004-api-cors.md](./contracts/amendment-004-api-cors.md) after the existing §7 "CLI mirror" and before any trailing horizontal rule / EOF. No edits to §1–§7. The insertion text in the amendment file is already final — copy directly without rephrasing.

**Checkpoint**: Types compile; `client.ts` unit-importable; MSW handlers respond from the test environment; the agent backend accepts cross-origin POSTs from `http://localhost:5173`. None of this is yet wired into a UI; that's where the user stories begin.

---

## Phase 3: User Story 1 — Ask a question and see the chart (Priority: P1) 🎯 MVP

**Goal**: A user opens the page, types a question, hits submit, sees the user message immediately, sees a loading state, and within a few seconds sees the assistant's text reply and an interactive chart rendered inline. This is the entire MVP.

**Independent Test**: With the agent stack reachable at `http://localhost:8000`, run `npm run dev`, open `http://localhost:5173`, type "Show releases by decade as a bar chart", hit submit. Verify (a) the user message appears immediately, (b) input is disabled with a visible loading indicator, (c) within ~10s the assistant text appears, (d) the chart artifact iframe paints. Spec acceptance scenario US1.1. Edge cases US1.2 (controlled-failure no-chart) and US1.3 (backend unreachable) are covered by the integration test (T028) using MSW handlers from T010.

### Implementation for User Story 1

- [X] T015 [US1] Implement the reducer + submit thunk at `frontend/src/hooks/useAgentQuery.ts`. Export `initialState: AppState` (per [data-model.md](./data-model.md) §2), `reducer(state, action): AppState` covering all 5 action types per data-model §2.1 transitions, and a `useAgentQuery()` hook that wraps `useReducer(reducer, initialState)` and returns `{ state, submit(message: string), newConversation() }`. The `submit` thunk: (a) builds a `UserMessage` with a freshly-generated UUID (use `crypto.randomUUID()` — supported in modern browsers and our target env per [plan.md](./plan.md) Target Platform); (b) dispatches `{type: "submit", userMessage}`; (c) calls `client.sendQuery({thread_id: state.threadId, message})`; (d) on success branches by `response.status`: `succeeded` → dispatch `responseSucceeded`, anything starting with `failed_` → dispatch `responseFailedControlled` per data-model §1.3; (e) on thrown `UserFacingError` → dispatch `responseError`. Forbidden-transition guards from data-model §2.2 must be enforced inside the reducer (no-op when invalid). Build the `AssistantMessage` from the `QueryResponse` inside the thunk (not the reducer). Always persist `response.thread_id` to localStorage via the util from T007 on both `responseSucceeded` and `responseFailedControlled`.
- [X] T016 [P] [US1] Create `frontend/src/components/Header.tsx`: a static header with the title "Discogs Analytics Agent" and the subtitle "Ask natural language questions about the Discogs releases dataset." (per spec §9.1). Tailwind-styled, no props, no state. Single export.
- [X] T017 [P] [US1] Create `frontend/src/components/LoadingState.tsx`: a small spinner + the label "Generating analysis..." per spec §20. Props: none (always-on when rendered; the parent decides when to mount it). Tailwind animation via `animate-spin` on a Lucide `<Loader2>` icon.
- [X] T018 [P] [US1] Create `frontend/src/components/ErrorBanner.tsx`: a dismissable banner. Props: `error: UserFacingError`, `onDismiss(): void`. Renders `error.copy` only — never reads `error.kind` for branching beyond an icon hint, never inspects any other field. Lucide `<AlertCircle>` icon. Spec FR-016 forbids exposing tracebacks, which the type system already enforces (data-model §1.7 invariant). Implementation note: `onDismiss` landed as **optional** since V1 has no explicit dismiss action in the reducer (the banner clears on the next submit per data-model §2.1); App.tsx renders the banner without a dismiss handler.
- [X] T019 [P] [US1] Create `frontend/src/components/QueryInput.tsx`: a single-line input + submit button. Props: `disabled: boolean`, `onSubmit(message: string): void`. Behavior: trim the input on submit, reject empty after trim with an inline hint, reject > 2000 chars per [contracts/api-consumption.md](./contracts/api-consumption.md) §2. Keyboard: Enter submits, Shift+Enter is reserved for a future multiline mode (V1 single-line — see spec §29). Aria-label "Ask a question about the Discogs catalog" so the input is screen-reader accessible (spec §29).
- [X] T020 [P] [US1] Create `frontend/src/components/ArtifactFrame.tsx`: renders the agent's chart artifact in a sandboxed iframe. Props: `artifact: ChartArtifact | null`. When `artifact` is null OR `artifact.type !== "plotly_html"`, render the empty placeholder per spec §15.2: "No chart yet. Ask a question or run one of the suggested questions." When `artifact` is non-null and Plotly: `<iframe src={toAbsoluteArtifactUrl(artifact.url)} sandbox="allow-scripts" title="Generated chart" className="w-full h-[600px]" />` per [research.md](./research.md) §R3. NEVER use `dangerouslySetInnerHTML` or `srcDoc`. NEVER add `allow-same-origin`. Spec FR-021 + research R3 are load-bearing here.
- [X] T021 [P] [US1] Create `frontend/src/components/ChatPanel.tsx`: renders the timeline of `ChatMessage[]`. Props: `messages: ChatMessage[]`. Each `UserMessage` renders right-aligned with a subtle background; each `AssistantMessage` renders left-aligned with the agent's `content` as plain-text wrapped paragraphs (no Markdown rendering in V1). Empty list → render the welcome state "Ask a question about the Discogs catalog, or pick one of the suggested questions to start." per spec FR-017. Use `key={message.id}` for stability. The container is a vertically-scrolling flex column with auto-scroll-to-bottom on new message (use a `useEffect` watching `messages.length`).
- [X] T022 [P] [US1] Create `frontend/src/components/ResultPanel.tsx`: composes `ArtifactFrame` only in this story (SqlViewer/DataPreviewTable/RunMetadata land in US4 and will be added by T046). Props: `current: AppState["current"]`. Renders a single column: `<ArtifactFrame artifact={current.artifact} />`. Will gain siblings in US4. Depends on T020 conceptually but the file resolution holds at integration time.
- [X] T023 [US1] Wire everything into `frontend/src/App.tsx`, replacing the T002 stub. The shell uses a three-zone Tailwind grid layout per spec §10: header on top spanning full width; below, a 2-column grid (chat panel left ~60%, result panel right ~40%) on `md+` screens, stacked vertically on `sm-`. The component calls `useAgentQuery()` from T015 and threads `state` and handlers through: `<Header />` always; `<ChatPanel messages={state.messages} />`; `<QueryInput disabled={state.pending} onSubmit={submit} />`; `{state.pending && <LoadingState />}`; `{state.error && <ErrorBanner error={state.error} />}`; `<ResultPanel current={state.current} />`. Keyboard-Enter submission is wired through `<QueryInput>` already from T019. Depends on T015–T022.

### Tests for User Story 1

> Spec §28 mandates these. Run `npm test` — all should pass against the MSW handlers from T010.

- [X] T024 [P] [US1] Unit test the API client at `frontend/tests/unit/client.test.ts`: success path returns the parsed `QueryResponse`; HTTP 500 throws a `UserFacingError` with `kind: "http"` and `copy === "Something went wrong on the agent side. Try again or rephrase."`; HTTP 404 `thread_not_found` triggers the silent retry — assert (a) localStorage was cleared, (b) the second request's body lacks `thread_id`, (c) the second response is returned as-is; network failure (force `fetch` to reject) throws `kind: "network"`; malformed JSON response throws `kind: "parse"`; the request body NEVER includes `thread_id` when the input had `null` or `undefined` (per api-consumption §2). Use `vi.spyOn(global, "fetch")` for fine-grained control here rather than going through MSW.
- [X] T025 [P] [US1] Unit test the error-translation table at `frontend/tests/unit/errors.test.ts`: every entry from the [research.md](./research.md) §R4 dictionary is asserted (one assertion per row); the unknown-code fallback returns the `internal_error` copy; `translateNetworkError` returns the network copy; `translateParseError` returns the parse copy; the returned `UserFacingError` has only `kind` and `copy` keys (verifies data-model §1.7 invariant — no `details`, no `originalError`, no `traceback`).
- [X] T026 [P] [US1] Component test `ArtifactFrame` at `frontend/tests/components/ArtifactFrame.test.tsx`: `artifact: null` renders the empty placeholder text and NOT an iframe; `artifact` with `type: "plotly_html"` renders an iframe whose `src` equals `${VITE_API_BASE_URL}${artifact.url}`, whose `sandbox` attribute equals exactly `"allow-scripts"` (NO `allow-same-origin`, NO other tokens), and whose `title` is set; `artifact` with an unknown `type` renders the empty placeholder. The sandbox-attribute assertion is load-bearing for FR-021 and SC-009 — this test prevents the iframe from being accidentally widened in a future refactor.
- [X] T027 [P] [US1] Component test `ChatPanel` at `frontend/tests/components/ChatPanel.test.tsx`: empty messages list renders the welcome state; one user + one assistant message renders both with appropriate roles in DOM order; `messages.length` change scrolls the container to the bottom (assert by checking the scroll target's `scrollTop` after a state update).
- [X] T028 [P] [US1] Integration test the full submit flow at `frontend/tests/integration/full-flow.test.tsx` using the MSW handlers from T010. Four scenarios: (a) **Success** — render `<App />`, type "Show releases by decade", click submit; assert user message appears immediately; await the assistant message; assert the iframe renders with the expected absolute artifact URL. (b) **Pending state** — hold the response open via a deferred promise; assert the input is disabled while pending and re-enables after resolution. (c) **Controlled failure** — override the `/query` handler to return `status: "failed_unsupported"` with `chart_artifact: null`; submit; assert the assistant text appears; assert the empty-chart placeholder renders; assert NO error banner. (d) **Backend unreachable** — make the `/query` handler reject with a network error; submit; assert the error banner with the "agent is not reachable" copy renders; assert the input is re-enabled. Implementation note: the disabled-state assertion was split into its own scenario because MSW resolves nearly instantly, so the original "submit then assert disabled" code raced the response.

**Checkpoint**: User Story 1 fully functional and testable independently. The MVP demo path (spec §34 step 1–3) works against the live backend; SC-001 (≥ 5 curated questions render charts) is not yet provable because curated questions land in US2 — for now, hand-typing succeeds.

---

## Phase 4: User Story 2 — One-click curated demo questions (Priority: P2)

**Goal**: A presenter sees ≥ 5 curated demo questions in the UI; clicking "Run" on any of them submits it end-to-end without typing.

**Independent Test**: Open `http://localhost:5173`. Verify ≥ 5 question cards are visible, each with a title, category, and full query text. Click "Use" on one → text appears in the input. Click "Run" on one → the query submits, a chart appears (US1 path reused). Spec acceptance scenarios US2.1–US2.3.

### Implementation for User Story 2

- [X] T029 [US2] Create the curated questions data file at `frontend/src/data/curatedQuestions.ts` exporting `curatedQuestions: readonly CuratedQuestion[]` containing all 7 entries from [contracts/curated-questions.md](./contracts/curated-questions.md) §1 (Q1 Releases by decade, Q2 Techno over time, Q3 Vinyl vs CD, Q4 Top countries, Q5 Label diversity, Q6 House outliers, Q7 Works with most versions). Field-for-field match required; the contract is normative. Use `as const` on the array literal so TypeScript widens types tightly.
- [X] T030 [US2] Create `frontend/src/components/SuggestedQuestions.tsx`: groups the curated questions by `category` and renders each as a card with title, description, and two buttons "Use" and "Run" per spec §22. Props: `onUse(query: string): void`, `onRun(query: string): void`, optional `disabled` (so the parent can lock the cards while a query is in flight) and optional `questions` override (for testing). Layout: vertical stack of category groups, each group has a small heading. Lucide icons: `<Pencil>` next to "Use", `<Play>` next to "Run". The groups render in the order categories first appear in the array (Trends → Styles → Formats → Geography → Labels → Advanced → Masters in the V1 set). Implementation note: icon swapped from `<Search>` (in original task wording) to `<Pencil>` — a Pencil reads more naturally as "edit/insert into the input" than a magnifying glass.
- [X] T031 [US2] Wire `SuggestedQuestions` into `App.tsx`. Placed as a left sidebar on `lg+` screens, stacked above the conversation on `md-` screens. Handlers: `onUse(q) => setInputText(q)` via lifted input state (QueryInput is now controlled via `value` + `onChange`); `onRun(q) => handleSubmit(q)` reusing the US1 submit thunk. The chat panel's empty-state remains visible until the first message arrives — the user isn't actively double-prompted because the sidebar uses a different visual register (cards on white) from the empty-state copy (centered text on slate). Layout: 3-column grid on `lg+` (`[20rem_1fr_1fr]` — fixed sidebar width, equal chat/result), single-column stacked on `md-`. Depends on T029, T030, and US1 wiring (T023).

### Tests for User Story 2

- [X] T032 [P] [US2] Component test `SuggestedQuestions` at `frontend/tests/components/SuggestedQuestions.test.tsx`: renders all 7 questions with their titles visible; "Use" button click calls `onUse` with the exact `query` text; "Run" button click calls `onRun` with the exact `query` text; questions are grouped by category (asserted via `getByRole("region", { name: category })` since each category section is a labeled region); empty data array renders nothing without crashing; custom `questions` prop overrides the default set; `disabled=true` disables every button.
- [X] T033 [P] [US2] Spread-coverage test at `frontend/tests/integration/curated-questions-spread.test.ts` per [contracts/curated-questions.md](./contracts/curated-questions.md) §5: asserts `curatedQuestions.length >= 5` (FR-005 floor); the union of all `demonstrates` arrays has size `>= 5` (the meaningful-spread interpretation); each entry has `title.length <= 40`, `description.length <= 100` (when present), `category` ∈ the 7-value enum, `query.length > 0`, `demonstrates.length > 0`. Plus a drop-one safety test (per contract §2): removing any single question from the set still covers ≥ 5 distinct capabilities.

**Checkpoint**: Spec acceptance US2.1–US2.3 hold. SC-001 ("at least 5 of the curated demo questions render charts end-to-end") becomes provable on the live stack — running each curated question through the live agent should produce a chart.

---

## Phase 5: User Story 3 — Multi-turn conversation and reset (Priority: P2)

**Goal**: Follow-up questions in the same conversation continue the agent context; "New conversation" clears the visible chat and starts fresh; the active conversation identifier survives a browser refresh.

**Independent Test**: Run a first question. Submit a follow-up like "Now only for UK" without re-stating context — the agent's response references the prior context. Click "New conversation" — the chat clears and `localStorage.discogs.frontend.currentThreadId` is removed. Refresh the page mid-conversation — the visible chat is empty (chat history is not persisted, FR-010), but the next submission continues the prior conversation (because the thread ID survived). Spec acceptance scenarios US3.1–US3.3.

### Implementation for User Story 3

- [ ] T034 [US3] Add the `threadId` field to `AppState` initialization in `frontend/src/hooks/useAgentQuery.ts`: read from `getCurrentThreadId()` (T007) once at module load — pass the read value into `initialState`. The `submit` thunk now reads `state.threadId` (already there from T015 design) and includes it in the request when non-null. The `responseSucceeded` and `responseFailedControlled` reducer cases write the response's `thread_id` back to the in-memory state AND call `setCurrentThreadId(...)` as a side effect — but reducers must be pure; do this side-effect inside the thunk, not in the reducer. This task is mostly about making the side-effects deterministic and adding the localStorage-mount-time read; the basic threading was already in T015's design. Update T015's tests if any rely on the previous null-only initialState.
- [ ] T035 [US3] Implement the `newConversation` reducer action in `useAgentQuery.ts` per [data-model.md](./data-model.md) §2.1: clears `messages`, `current`, `error`, `pending`, AND `threadId` (back to null). Side effect from the thunk: also call `clearCurrentThreadId()` (T007). Expose `newConversation(): void` from the `useAgentQuery` return object so the UI can wire a button to it.
- [ ] T036 [US3] Implement the `useThreadId` hook at `frontend/src/hooks/useThreadId.ts` exposing `{ threadId, setThreadId, clearThreadId }`. Internally: a `useState` initialized via `getCurrentThreadId()`; `setThreadId(id)` updates state AND calls `setCurrentThreadId(id)`; `clearThreadId()` updates state AND calls `clearCurrentThreadId()`. Used by `ThreadControls` (T037) for display purposes — it does NOT replace the in-reducer `state.threadId` from T034. Reason: the reducer is the source of truth for the live state; this hook is a small read-only mirror suitable for the read-mostly display badge. (Trade-off considered in [data-model.md](./data-model.md) §3 — single source of truth wins.)
- [ ] T037 [US3] Create `frontend/src/components/ThreadControls.tsx`: renders a "New conversation" button per spec §21.2 + a small read-only display of the truncated current thread ID (e.g., `thread: 9f6c…e1`). Props: `threadId: string | null`, `onNewConversation(): void`. The button is always enabled (data-model §2.1 — `newConversation` is valid in any state including INITIAL). When `threadId === null` the truncated-ID display reads "no active thread".
- [ ] T038 [US3] Wire `ThreadControls` into `App.tsx` near the header (top-right corner per spec §10 "Thread control"). Pass `threadId={state.threadId}` and `onNewConversation={newConversation}` from `useAgentQuery`. Depends on T035, T037.
- [ ] T039 [US3] Verify (and tighten if needed) the `thread_not_found` silent-retry path in `client.ts` from T009. Spec edge case: "the next submission starts a new conversation transparently; the user sees no error." When the agent returns 404 with `error.code === "thread_not_found"`, the client (a) calls `clearCurrentThreadId()`, (b) re-issues the request with `thread_id` omitted, (c) returns whatever the retry returns (success OR a different error). If the original implementation in T009 already covers this, audit-and-confirm; otherwise tighten it. The unit test from T024 already locks this behavior in.

### Tests for User Story 3

- [ ] T040 [P] [US3] Unit test `localStorage.ts` at `frontend/tests/unit/localStorage.test.ts`: `getCurrentThreadId()` returns null when key is unset; returns the stored string when set; returns null when `localStorage.getItem` throws (mock private-mode failure with `vi.spyOn`); `setCurrentThreadId(id)` writes the exact string with no JSON wrapping; `clearCurrentThreadId()` removes the key; all three are no-ops or return-null safe under any thrown exception (the data-model §3 invariant).
- [ ] T041 [P] [US3] Component test `ThreadControls` at `frontend/tests/components/ThreadControls.test.tsx`: renders truncated ID when `threadId` is set (assert the displayed text contains the first 4 chars of the UUID); renders "no active thread" when null; "New conversation" button click calls `onNewConversation` exactly once.
- [ ] T042 [P] [US3] Integration test multi-turn + reset at `frontend/tests/integration/multi-turn.test.tsx`: with MSW configured to echo back the request's `thread_id` (or generate one on first call and echo subsequently), (a) submit Q1, assert `localStorage.discogs.frontend.currentThreadId` is set; (b) submit Q2, assert the request body included the same `thread_id`; (c) click "New conversation", assert `messages` is empty AND `localStorage` key is cleared; (d) submit Q3, assert the request body did NOT include `thread_id` and the response's new `thread_id` lands in `localStorage`. Plus: simulate a `thread_not_found` 404 on the first attempt (MSW handler one-shot override), assert the retry was issued with no `thread_id` and the user never sees an error banner.

**Checkpoint**: Multi-turn works (acceptance US3.1); New Conversation resets cleanly (US3.2); refresh-survives-thread-id (US3.3) works because `getCurrentThreadId()` is read at module load — verifiable by manual reload in the live stack. SC-005 holds.

---

## Phase 6: User Story 4 — Inspect what the agent did (Priority: P3)

**Goal**: An evaluator can expand a panel to see the generated SQL (with copy button), see a small data preview, and see metadata badges (complexity / model / status / run id / thread id).

**Independent Test**: Run a query that returns SQL + data + metadata. Expand the SQL panel — SQL is shown, copy button works. Data preview shows up to 20 rows. Metadata badges show `complexity · selected_model · status` (skipping any null fields). Spec acceptance scenarios US4.1–US4.3.

### Implementation for User Story 4

- [ ] T043 [P] [US4] Create `frontend/src/components/SqlViewer.tsx`: a collapsible panel with the heading "Generated SQL" per spec §16, default-collapsed. Props: `sql: string | null`. When `sql` is null, render nothing (the whole panel is hidden — FR-011). When non-null: render a `<details>` element (no JS-controlled disclosure widget needed) wrapping a `<pre><code>` of the SQL plus a "Copy" button. The Copy button calls `navigator.clipboard.writeText(sql)` and flips an icon to a checkmark for ~1.5s before reverting. Lucide icons: `<ChevronDown>` (collapsed) / `<ChevronUp>` (expanded) and `<Copy>` / `<Check>`.
- [ ] T044 [P] [US4] Create `frontend/src/components/DataPreviewTable.tsx`: a horizontally-scrollable table per spec §17. Props: `rows: Record<string, unknown>[]`. Empty array → render the "no data preview available" placeholder (spec §17). Non-empty: render up to the first 20 rows; columns inferred from `Object.keys(rows[0])`; render values via `String(value)` for primitives, `JSON.stringify(value)` for objects/arrays (defensive — agent's V1 always returns primitives). Wrap in `overflow-x-auto` for wide tables. Apply `tabular-nums` to numeric-looking columns for readability.
- [ ] T045 [P] [US4] Create `frontend/src/components/RunMetadata.tsx`: a row of badges per spec §18. Props: `metadata: RunMetadata | null`. When null, render nothing. When non-null, render only the badges whose corresponding fields are present and non-null per [data-model.md](./data-model.md) §1.2 + §1.3 + US4 acceptance scenario 3: `complexity` (e.g. "simple"), `selected_model` (e.g. "gpt-4o-mini"; hidden when null), `status` (e.g. "succeeded"), `run_id` (truncated to first 6 chars + "…"), `thread_id` (truncated to first 6 chars + "…"). NEVER render "null" or "undefined" as badge text. Each badge is a small Tailwind pill with `bg-slate-100 text-slate-700`; the `status` badge is colored: green for `succeeded`, amber for `failed_clarification_needed`, red for `failed_safety` / `failed_validation`, slate for `failed_unsupported`.
- [ ] T046 [US4] Wire `SqlViewer`, `DataPreviewTable`, and `RunMetadata` into `ResultPanel.tsx` (modifying T022). Layout per spec §10 "Result Panel": ArtifactFrame on top; below it, RunMetadata as a thin badge row; below that, DataPreviewTable; below that, SqlViewer (collapsed by default). Pass `sql={current.sql}`, `rows={current.dataframePreview}`, `metadata={current.metadata}` from `current`. Each child component handles its own null/empty case so `ResultPanel` does no branching itself. Depends on T043, T044, T045.

### Tests for User Story 4

- [ ] T047 [P] [US4] Component test `SqlViewer` at `frontend/tests/components/SqlViewer.test.tsx`: `sql: null` renders nothing (assert `container.firstChild === null`); non-null SQL renders the `<details>` collapsed by default; clicking the summary expands it and the SQL text becomes visible; Copy button click calls `navigator.clipboard.writeText` with the exact SQL (use `vi.stubGlobal("navigator", ...)` or `vi.spyOn(navigator.clipboard, "writeText")`); the icon flips after click.
- [ ] T048 [P] [US4] Component test `DataPreviewTable` at `frontend/tests/components/DataPreviewTable.test.tsx`: empty array renders the "no data preview available" placeholder; 5 rows render with correct headers (inferred from row 0 keys) and 5 body rows; 25 rows render with only 20 body rows (cap); a row with a non-primitive value renders the JSON-stringified form.
- [ ] T049 [P] [US4] Component test `RunMetadata` at `frontend/tests/components/RunMetadata.test.tsx`: `null` renders nothing; full metadata renders all 5 badges with the expected text; `selected_model: null` hides only that badge (others remain); `status === "succeeded"` applies the green-tinted style (assert via `data-status` attribute or CSS class — cleaner than asserting on color).

**Checkpoint**: Spec US4 acceptance scenarios all pass. The result panel now mirrors spec §10's full layout. SC-010 ("at least one curated complex question succeeds end-to-end") becomes a live-stack verification gate — running Q5 (Label diversity) end-to-end should display a chart, the SQL, the data preview, and the metadata badges.

---

## Phase 7: User Story 5 — Run the whole demo from one command (Priority: P3)

**Goal**: A new contributor on a fresh checkout can run `docker compose up --build` and reach a working frontend at `http://localhost:5173`.

**Independent Test**: From a clean checkout, run `docker compose up --build`. Wait for healthy. Open `http://localhost:5173` in a browser. Verify the page renders, curated questions are visible, and a sample question (Q1) returns a chart. Spec acceptance scenarios US5.1–US5.3, SC-007.

### Implementation for User Story 5

- [ ] T050 [US5] Create `frontend/Dockerfile` for the Vite-dev-server packaging variant per [research.md](./research.md) §R1: base `node:20-alpine`; `WORKDIR /app`; `COPY package.json package-lock.json ./` then `RUN npm ci`; `COPY . .`; `EXPOSE 5173`; `CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]`. Add `frontend/.dockerignore` excluding `node_modules`, `dist`, `coverage`, `.env.local`, `.git`. Six-line Dockerfile is the goal; nginx-served static build is V1.1 per research R1 upgrade recipe — do NOT implement now.
- [ ] T051 [US5] Add the `frontend` service to the root `docker-compose.yml`. Insertion point: after the existing `agent-api` service block, before the `volumes:` section. Service spec: `build: { context: ./frontend, dockerfile: Dockerfile }`; `ports: - "5173:5173"`; `environment: VITE_API_BASE_URL: http://localhost:8000`; `depends_on: { agent-api: { condition: service_healthy } }`; `restart: unless-stopped`. NO `volumes:` mount of `./data/` or `./artifacts/` — the frontend physically cannot see those paths (Spec FR-020 + plan §"Constraints"). NO `tmpfs:` block — no analytical work happens here. Add a one-line comment above the service block: `# Demo Day frontend (008-agent-frontend-v1)`.
- [ ] T052 [US5] Update the repo-root `README.md` quickstart section to mention the new frontend service. Minimal change: add a "Frontend" subsection under "Run locally" linking to [quickstart.md](./quickstart.md) and stating the URL (`http://localhost:5173`). Match the prose style of the existing agent/ETL sections — terse, command-first, no marketing language.
- [ ] T053 [US5] Manual smoke check — run `docker compose up --build`, follow [quickstart.md](./quickstart.md) §3 end-to-end: §3.1 backend `/health` → ok; §3.2 frontend reachable on 5173 → 200; §3.3 click "Releases by decade" → chart renders, SQL panel reveals SQL, data preview shows rows, metadata badges show; §3.4 multi-turn follow-up + new-conversation reset; §3.5 stop agent → frontend shows the "agent unreachable" banner. Document the result in this task as PASS/FAIL with a one-paragraph note. This is verification-only — no code change. Its purpose is to lock SC-007 (under-10-minute first-success on a fresh checkout) and the SC-001/SC-006 live-stack assertions before the polish phase.

**Checkpoint**: One-command bring-up demonstrably works. The full Demo Day path from spec §34 is executable.

---

## Phase 8: Polish & Cross-cutting

**Purpose**: Final correctness sweeps that span all stories. These are gates, not features.

- [ ] T054 [P] Run `cd frontend && npm run typecheck` — must exit 0 with zero errors. Fix any drift between [data-model.md](./data-model.md) and the actual TypeScript types. Drift here is a real bug; do not silence with `as unknown as ...` or `@ts-ignore`.
- [ ] T055 [P] Run `cd frontend && npm test` — all unit, component, and integration suites must pass. Failing tests indicate either a real bug or an outdated expectation; fix the bug if it is one, update the test only if the spec or contract changed (and link to the change).
- [ ] T056 [P] Verify `frontend/package.json` has zero database / data-layer dependencies — no `pg`, `duckdb`, `mysql2`, `sqlite3`, `mongodb`, or any client library that could speak a database protocol. SC-008 is anchored on this. Implementation: a one-liner test at `frontend/tests/unit/no-db-deps.test.ts` that reads `package.json` and asserts the union of `dependencies` and `devDependencies` is disjoint from a hardcoded forbidden-set. Run as part of `npm test` from T055.
- [ ] T057 [P] Verify the iframe sandbox attribute regression guard (separate from T026). Add a static-analysis-style test at `frontend/tests/unit/no-unsafe-html.test.ts` that reads every `.tsx` file under `frontend/src/components/` and asserts none of them contain the substring `dangerouslySetInnerHTML`. SC-009 is anchored on this — FR-021 forbids the pattern. Implementation: `fs.readdirSync` + `fs.readFileSync` + a simple substring check. ≤ 30 lines.
- [ ] T058 Polish the empty / welcome state copy in `ChatPanel` and `ArtifactFrame`. Spec FR-017 + §9.1 wants a clear, recognizable empty state before the first query. Refine the copy if it currently reads as placeholder; adopt the strings from spec §9.1 and §15.2 verbatim. Verify keyboard accessibility per spec §29: Enter submits (T019 already covers); Shift+Enter is documented as reserved-for-future-multiline; the iframe has `title="Generated chart"` (T020 already covers); button text is clear (visible in all components).
- [ ] T059 Update the requirements checklist `specs/008-agent-frontend-v1/checklists/requirements.md` final section (the "Items requiring follow-up at plan time" subsection) to record what landed: the docker packaging variant chosen, how CORS was configured, and the explicit V1 decision NOT to use `GET /threads/{id}` for chat-restore-on-reload. This is a small audit-trail update so a reader of the checklist can see what was decided in the plan and what landed in implementation.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies. Start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1. **Blocks all user stories.**
- **Phase 3 (US1, P1)**: Depends on Phase 2. The MVP — finish before considering anything else done.
- **Phase 4 (US2, P2)**: Depends on Phase 2. Independent of US1 *implementation* but its independent test requires the US1 submit path to work end-to-end (US2's "Run" button reuses US1's submit). Practically: complete US1 first, then US2.
- **Phase 5 (US3, P2)**: Depends on Phase 2 + a bit of US1's reducer (T015 establishes the reducer; T034/T035 extend it). Practically: US1 first.
- **Phase 6 (US4, P3)**: Depends on Phase 2 + US1's `ResultPanel` (T022, modified by T046).
- **Phase 7 (US5, P3)**: Depends on US1, US2, US3, US4 all being implementation-complete (the smoke check at T053 verifies all five stories together).
- **Phase 8 (Polish)**: Depends on all desired stories being complete.

### User Story Dependencies (a sharper picture)

- **US1 (P1)** — no dependencies on other stories. The MVP.
- **US2 (P2)** — independently testable in isolation (the curated cards render and the buttons fire callbacks; T032 doesn't need US1's submit path). For end-to-end behavior in the live stack, depends on US1's submit path.
- **US3 (P2)** — independently testable in isolation (T040 + T041 do not need a working query path). For end-to-end behavior, depends on US1's submit path.
- **US4 (P3)** — independently testable in isolation. For end-to-end behavior, depends on US1's `ResultPanel` integration (T046 modifies it).
- **US5 (P3)** — implicitly depends on all others being implemented enough to hold up under T053's smoke check. Independent test (one-command bring-up) does not require any specific story but the resulting page must render the full UI to satisfy the spec.

### Within Each User Story

- Tests are written alongside (not strictly before) implementation in this codebase — Spec §28 mandates them but doesn't impose TDD ordering. The reducer tests (T015's behavior) are exercised by the integration test (T028) rather than by a separate reducer-only test (the reducer is the only state machine we have; testing it through the public submit/newConversation API is enough).
- Within US1: reducer (T015) → leaf components in parallel (T016–T022 [P]) → wiring (T023) → tests (T024–T028 [P]).
- Within US2: data file (T029) → component (T030) → wiring (T031) → tests (T032, T033 [P]).
- Within US3: reducer extensions (T034, T035) → hook (T036) → component (T037) → wiring (T038) → audit (T039) → tests (T040–T042 [P]).
- Within US4: leaf components in parallel (T043, T044, T045 [P]) → wiring (T046) → tests (T047–T049 [P]).
- Within US5: Dockerfile (T050) → compose service (T051) → README (T052) → smoke (T053).

### Parallel Opportunities

- **Phase 1**: T003, T004, T005 in parallel.
- **Phase 2**: T007, T008 in parallel; T010, T011, T013, T014 in parallel after T006; T012 after T011.
- **US1 implementation**: T016–T022 in parallel after T015; T024–T028 in parallel after T023.
- **US3 tests**: T040, T041, T042 in parallel.
- **US4 implementation**: T043, T044, T045 in parallel; T047–T049 in parallel after T046.
- **Cross-story parallelism**: once Phase 2 is done, US2 (T029–T033), US3 (T034–T042), US4 (T043–T049), US5 (T050–T053) can run on independent feature branches by different contributors. US1 should land first as it establishes the reducer + ResultPanel that other stories extend.

---

## Parallel Example: User Story 1

```bash
# After Phase 2 + T015 (reducer) lands, all leaf components in parallel:
Task: "Create Header.tsx in frontend/src/components/Header.tsx"
Task: "Create LoadingState.tsx in frontend/src/components/LoadingState.tsx"
Task: "Create ErrorBanner.tsx in frontend/src/components/ErrorBanner.tsx"
Task: "Create QueryInput.tsx in frontend/src/components/QueryInput.tsx"
Task: "Create ArtifactFrame.tsx in frontend/src/components/ArtifactFrame.tsx"
Task: "Create ChatPanel.tsx in frontend/src/components/ChatPanel.tsx"
Task: "Create ResultPanel.tsx in frontend/src/components/ResultPanel.tsx"

# Then sequentially: T023 wires App.tsx; then in parallel:
Task: "Unit test client.ts in frontend/tests/unit/client.test.ts"
Task: "Unit test errors.ts in frontend/tests/unit/errors.test.ts"
Task: "Component test ArtifactFrame in frontend/tests/components/ArtifactFrame.test.tsx"
Task: "Component test ChatPanel in frontend/tests/components/ChatPanel.test.tsx"
Task: "Integration test full submit flow in frontend/tests/integration/full-flow.test.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) — `frontend/` boots, `npm test` runs.
2. Phase 2 (Foundational) — types compile, client + utils unit-importable, MSW handlers respond, agent CORS in place.
3. Phase 3 (US1) — submit + chart render works end-to-end against the live agent and against MSW.
4. **STOP and VALIDATE**: open `http://localhost:5173`, type "Show releases by decade", confirm a chart renders. Spec acceptance US1.1 holds. SC-003 holds (response within ~10s).
5. This is a deployable, demoable MVP. Demo Day is feasible from this point even without US2-US5.

### Incremental Delivery

1. **MVP**: Setup + Foundational + US1.
2. **Demo polish**: Add US2 (curated questions). Now Demo Day is one-click.
3. **Conversational depth**: Add US3 (multi-turn + reset). Now follow-ups work.
4. **Inspector view**: Add US4 (SQL + preview + metadata). Now the demo also serves as a credibility argument.
5. **One-command bring-up**: Add US5 (Docker + README). Now any team member can demo.
6. **Final polish**: Phase 8 sweeps.

Each step ends with a checkpoint where the demo is shippable.

### Parallel Team Strategy

With multiple contributors:

1. Phase 1 + Phase 2 land first, ideally on a single short branch.
2. Once Phase 2 is merged:
   - Contributor A: US1 (the reducer + base UI) — lands first.
   - Contributor B: US2 (curated questions) — can start in parallel against the US1 stub UI but lands after US1 wiring.
   - Contributor C: US3 (multi-turn) — can start in parallel; touches the reducer.
   - Contributor D: US4 (SQL/preview/metadata) — can start in parallel; touches `ResultPanel`.
3. US5 (Docker + smoke) lands last, after merge-conflicts settle.
4. Phase 8 polish closes everything out.

---

## Notes

- `[P]` tasks = different files, no dependencies on incomplete tasks in the same phase.
- `[Story]` label maps task to a specific user story for traceability.
- File paths in task descriptions are absolute relative to the repo root (e.g., `frontend/src/components/Header.tsx`).
- Each story is independently *implementation*-testable in isolation per the within-story section above; for live-stack end-to-end behavior, US2/US3/US4 reuse US1's submit path.
- Tests here are explicitly mandated by Spec §28 — they are not optional.
- Constitution Principle VI (Two Components, One Contract) is extended to include the new `frontend/` component; the operational rules (own dependency manifest, no cross-component imports, no data-layer reaches) are enforced by T056 and T057. The PATCH-level constitution amendment recommended in [plan.md](./plan.md) §"Constitution Check" is **follow-up work**, not part of this task list.
- 59 tasks total across 8 phases. Setup: 5. Foundational: 9. US1: 14. US2: 5. US3: 9. US4: 7. US5: 4. Polish: 6.
