# Feature Specification: Agent Frontend V1

**Feature Branch**: `008-agent-frontend-v1`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "I want to start specifying what's described in this doc @docs/discogs_frontend_initial_spec.md"

## Overview

Today the Discogs analytics agent is reachable only via raw HTTP calls (`curl`, integration tests, IDE clients). At Demo Day this is unworkable: an evaluator cannot see the end-to-end loop — natural-language question → routed agent run → generated SQL → DuckDB execution → Plotly chart artifact — without watching the presenter type into a terminal.

This feature delivers a minimal browser-based interface that turns the existing agent into a demoable product. A user opens a page, types or clicks a question, and sees a chart appear with the generated SQL and a small data preview alongside it. The interface is a thin, demo-shaped presentation layer; it must not access DuckDB, Postgres, ETL files, or local artifacts directly, and it must not execute any agent-generated code. All analytical work continues to happen in the existing FastAPI agent backend.

The source brief (`docs/discogs_frontend_initial_spec.md`) inventories specific stack, file layout, and component-level recommendations. Those are inputs to planning; this specification captures only the user-facing behavior and scope boundaries that must hold regardless of the chosen stack.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Ask a question and see the chart (Priority: P1)

A demo viewer (presenter, evaluator, or first-time visitor) opens the frontend in a browser, types a natural-language question about the Discogs catalog (e.g., "Show releases by decade"), submits it, and within a few seconds sees an interactive chart rendered on the page along with the agent's textual response. They can read both without scrolling between tabs or tools.

**Why this priority**: This is the entire purpose of the feature. Without this slice, nothing else has any reason to exist. It is also the smallest end-to-end vertical that proves the whole pipeline works in a browser.

**Independent Test**: Start the local stack, open the frontend URL, type a known-good question, hit submit. Verify (a) a loading state appears immediately, (b) within a reasonable time the assistant text response is shown, (c) the returned chart artifact is visibly rendered on the page, and (d) input is re-enabled afterwards.

**Acceptance Scenarios**:

1. **Given** the backend is running and reachable, **When** a user submits a known-good question (e.g., "Show releases by decade as a bar chart"), **Then** the frontend displays the user's message, then the assistant's text reply and an interactive chart from the returned chart artifact within the page.
2. **Given** the backend is running, **When** a user submits a question that the agent cannot satisfy with a chart, **Then** the frontend displays the assistant's text reply and a non-blocking, non-technical empty-chart message (instead of failing the page).
3. **Given** the backend is unreachable, **When** a user submits a question, **Then** the frontend shows a concise, non-technical error message and re-enables the input — without exposing raw stack traces.

---

### User Story 2 — One-click curated demo questions (Priority: P2)

A presenter at Demo Day wants to walk through several pre-prepared analytical questions (decade trends, format comparison, top countries, label diversity, outliers, etc.) without typing under time pressure. They want each one as a clickable card; clicking either fills the input or runs immediately.

**Why this priority**: P1 already lets a user ask anything, but in front of an audience typos and on-the-fly typing are friction. Curated questions de-risk the live demo and showcase the variety of patterns the agent supports (simple aggregates, time series, format/category breakdowns, outlier detection, master-side joins).

**Independent Test**: Open the frontend with backend running. Confirm at least 5 curated questions are visible, grouped sensibly (e.g., by category). Click one — verify the question runs end-to-end and produces a chart, identical to typing it manually.

**Acceptance Scenarios**:

1. **Given** the frontend is open, **When** a user views the curated suggestions area, **Then** at least 5 demo questions are visible, each with a short title, category, and the question text.
2. **Given** the curated suggestions are visible, **When** a user clicks "Run" on one, **Then** the question is submitted to the agent in the current conversation and a chart appears on response.
3. **Given** the curated suggestions are visible, **When** a user clicks "Use" on one, **Then** the question text is placed in the input box for further editing and not yet submitted.

---

### User Story 3 — Multi-turn conversation and reset (Priority: P2)

A presenter wants to ask a follow-up like "Now only for UK" after running "What are the top 15 countries by number of releases?", and have the agent treat it as a continuation rather than an unrelated query. They also want a one-click "New conversation" control to clear the visible chat and start fresh.

**Why this priority**: The agent already supports light multi-turn carry-over (per the existing 004-agent-v1 design). Surfacing it in the UI is what makes the conversational nature of the agent legible to viewers. "New conversation" is necessary to keep the demo controllable across multiple takes.

**Independent Test**: Run a first question. Then submit a vague follow-up that only makes sense with prior context (e.g., "Now only for UK"). Verify the agent's response is contextually grounded. Click "New conversation" — verify the visible chat resets and a subsequent question is treated as a fresh conversation.

**Acceptance Scenarios**:

1. **Given** a successful first response, **When** the user submits a follow-up question without re-stating context, **Then** the next request continues the same conversation with the agent.
2. **Given** an active conversation with messages on screen, **When** the user clicks "New conversation", **Then** the visible chat clears, the active conversation identifier is forgotten in the browser, and the next submission starts a fresh conversation.
3. **Given** the user refreshes the browser tab during an active conversation, **When** the page reloads, **Then** the active conversation identifier is preserved so subsequent questions still continue that conversation (visible chat history may be empty, since chat persistence is out of scope for V1).

---

### User Story 4 — Inspect what the agent did (Priority: P3)

An evaluator wants to verify that the agent actually generated and ran SQL and is not faking results. They want to expand a panel to see the generated SQL, optionally a short preview of the resulting data, and small badges showing routing metadata (complexity, selected model, validation status).

**Why this priority**: This is a credibility and debugging feature, not a path-of-use feature. The demo works without it, but presenting it during Q&A is what differentiates "I built a chatbot" from "I built an agent that writes verifiable analytical code."

**Independent Test**: Run a successful query. Find and expand the SQL panel — verify the SQL is shown and copyable. Find the data preview — verify a small tabular preview is shown. Find the metadata badges — verify complexity, selected model, and validation are surfaced when the backend returned them.

**Acceptance Scenarios**:

1. **Given** a successful response with SQL, **When** the user expands the SQL panel, **Then** the generated SQL is shown in a readable format with a copy-to-clipboard control.
2. **Given** a successful response with a dataframe preview, **When** the user views the result panel, **Then** up to the first 20 rows are rendered as a simple table with horizontal scroll for wide rows.
3. **Given** the backend returned routing/validation metadata, **When** the user views the response, **Then** small badges show complexity, selected model, and validation status; missing fields are simply omitted (no "undefined" or empty placeholders).

---

### User Story 5 — Run the whole demo from one command (Priority: P3)

A new contributor (or the presenter on demo morning, on a fresh laptop) wants to start the entire stack — backend agent, database, frontend — using the existing local container stack, with no extra manual steps beyond what the project already documents for the backend.

**Why this priority**: The demo only happens if it boots reliably. The frontend must drop into the existing local container orchestration so that one documented command brings up the full stack. This is a packaging and operational concern, not a per-query feature.

**Independent Test**: From a clean checkout, run the documented one-command bring-up. Open the frontend URL. Verify the loading page renders, the curated questions are visible, and a sample question succeeds end-to-end without manually starting any process.

**Acceptance Scenarios**:

1. **Given** a fresh checkout with the local container runtime available, **When** the documented one-command bring-up is run, **Then** both backend and frontend services come up healthy and the frontend is reachable in a browser.
2. **Given** the frontend service is running, **When** the browser calls the agent endpoints under the same local origin policy, **Then** the calls are accepted by the backend (cross-origin policy permits the frontend's origin).
3. **Given** the user follows the project's quickstart, **When** they reach the "open the frontend" step, **Then** the documented URL responds and the demo flow described in US1 succeeds.

---

### Edge Cases

- **Backend unreachable on submit**: A concise, non-technical error message appears (e.g., "The agent is not reachable. Check that the local stack is running."). Input is re-enabled. No raw exception details are shown.
- **Backend reachable but the agent run fails or returns no chart**: The text response (if any) is shown, plus a small "no chart available" placeholder. No iframe error and no white screen.
- **Chart artifact URL fails to load in the embedded frame**: The frame area shows a fallback message; the rest of the response remains visible and usable.
- **Very long-running query**: A loading state remains visible; the input stays disabled; queued submissions are blocked. There is a documented timeout (the user-facing version is "the agent took too long" rather than a network code).
- **Empty dataframe preview**: The preview panel shows a "no data preview available" message rather than rendering an empty table.
- **Locally stored conversation identifier no longer recognized by the backend** (e.g., backend was reset): The next submission starts a new conversation transparently; the user sees no error.
- **Browser refresh mid-query**: The pending request is dropped (it was an in-flight network call). The visible chat may be empty after reload (chat history is not persisted in V1), but the active conversation identifier remains, so the next submission continues that conversation.
- **Response missing optional fields** (no chart, no SQL, no data preview, no routing metadata): The UI degrades gracefully — every optional panel hides itself when its field is absent.
- **Repeated rapid submissions**: While a query is in flight, the submit control is disabled; users cannot enqueue parallel submissions.

## Requirements *(mandatory)*

### Functional Requirements

**Core query loop**

- **FR-001**: Users MUST be able to submit a free-form natural-language question to the analytics agent from a browser-based interface.
- **FR-002**: System MUST display the conversation as a chronological sequence of user questions and assistant replies, visible on the same page.
- **FR-003**: System MUST render the chart artifact returned by the agent inline on the page so the user can read the chart without leaving the page or downloading anything.
- **FR-004**: System MUST tolerate optional response fields being absent (chart artifact, SQL, dataframe preview, routing metadata, validation metadata) and degrade gracefully without errors.

**Curated demo content**

- **FR-005**: System MUST present at least 5 curated example questions covering a meaningful spread of agent capabilities (e.g., simple aggregation, time-series, format comparison, geographic ranking, complex multi-join, outlier detection).
- **FR-006**: System MUST allow users to either insert a curated question into the input for editing, or run it immediately, with separate controls for each.

**Conversation control**

- **FR-007**: System MUST allow users to ask follow-up questions in the same conversation, so the agent receives the conversational context it expects.
- **FR-008**: System MUST allow users to start a new conversation with a single visible action that clears the on-screen chat and severs the active conversation identifier.
- **FR-009**: System MUST persist the active conversation identifier in browser-local storage so a page refresh does not silently break in-flight conversational continuity.
- **FR-010**: System MUST NOT persist full conversation message history in browser-local storage (V1 keeps only the active conversation identifier).

**Transparency / inspect-ability**

- **FR-011**: System MUST display the agent's generated SQL in a panel that the user can expand or collapse; the panel MUST be hidden when no SQL is available for the current response.
- **FR-012**: System MUST provide a copy-to-clipboard control on the SQL panel so the SQL can be pasted into a database tool.
- **FR-013**: System MUST display up to 20 rows of the resulting dataframe as a tabular preview when one is returned, with horizontal scrolling for wide rows.
- **FR-014**: System MUST display routing/run metadata (complexity tier, selected model, run identifier, conversation identifier, validation status) in a secondary, non-dominant area of the response when the backend returned those fields.

**Loading, error, and empty states**

- **FR-015**: System MUST show a clearly visible loading indicator while a query is being processed, and MUST disable the input and submit control until the response is received or has failed.
- **FR-016**: System MUST show a concise, non-technical, user-facing error message when the backend is unreachable, the request fails, or the response is malformed; raw stack traces or backend internal paths MUST NOT be shown.
- **FR-017**: System MUST show a recognizable empty state (e.g., welcome message and curated questions) before the first query of a session.

**Boundaries and security**

- **FR-018**: System MUST NOT execute any agent-generated Python code in the browser.
- **FR-019**: System MUST NOT execute or rewrite agent-generated SQL in the browser.
- **FR-020**: System MUST NOT directly access the project's analytical data stores (DuckDB, Postgres) or local data/artifact files; all data access goes through the agent's HTTP API.
- **FR-021**: System MUST render the agent's chart artifact in an isolated, sandboxed embedded context (no use of unsafe HTML injection patterns into the host page).
- **FR-022**: System MUST NOT contain or display backend secrets, model API keys, database credentials, or other privileged configuration.

**Backend integration**

- **FR-023**: Backend MUST permit cross-origin requests from the local frontend origin so the browser-based UI can call the agent's HTTP API.
- **FR-024**: Frontend MUST work against an existing agent HTTP API that exposes: a query submission endpoint accepting an optional conversation identifier and a message, returning a conversation identifier, run identifier, assistant text, an optional chart artifact reference, optional SQL, an optional dataframe preview, and optional routing/validation metadata; an artifact content endpoint serving the chart artifact for display; and a health endpoint.
- **FR-025**: System MUST work without optional inspection endpoints (e.g., reload-prior-conversation lookups). Such endpoints are deferred and not relied on in V1.

**Operational packaging**

- **FR-026**: System MUST be runnable as a service in the existing local container orchestration alongside the agent backend.
- **FR-027**: System MUST allow the backend's URL to be configured via environment variable so it can be pointed at different local environments without code changes.

### Non-Functional Requirements (out-of-scope guardrails)

The following are explicitly **NOT** part of V1 (they are documented here so future drift is detectable):

- **NF-001**: V1 does not implement authentication, user accounts, or per-user isolation.
- **NF-002**: V1 does not implement cross-session persistence of full conversation history.
- **NF-003**: V1 does not implement a saved-conversations browser, dashboard builder, or in-browser chart editing.
- **NF-004**: V1 does not implement client-side chart rendering from a CSV (Plotly.js in the browser, axis/chart-type pickers). The chart artifact is whatever the backend produces and the frontend renders verbatim.
- **NF-005**: V1 does not implement a public deployed version (the demo is local).

### Key Entities *(include if feature involves data)*

- **Conversation**: A sequence of user questions and assistant responses, identified by a stable conversation identifier issued by the agent backend on first submission. Owned by the backend; the frontend stores only the active identifier locally.
- **Chart Artifact**: A self-contained chart object produced by the agent, retrievable by an artifact identifier. Rendered inline by the frontend; never inspected, modified, or re-generated by the frontend.
- **Curated Question**: A pre-authored example question with a short title and a category, intended to drive a one-click demo flow. Static content shipped with the frontend (not authored by users).
- **Run Metadata**: Per-response descriptive information from the agent (e.g., complexity tier, selected model, validation status, run and conversation identifiers). Display-only; not used to drive any frontend logic.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can submit a question and see the resulting chart rendered for at least 5 of the curated demo questions, end-to-end, on a fresh local stack — with no console errors and no manual step beyond clicking the question.
- **SC-002**: 100% of the curated demo questions either render a chart or display a clearly labeled "no chart available" empty state — they MUST NOT crash the page or leave the user with a hung loading indicator.
- **SC-003**: A user can run a question end-to-end (submit → chart visible) within 15 seconds for the cheap-model path on the documented hardware, on a warmed-up backend.
- **SC-004**: A user can ask a follow-up question that depends on prior conversational context, and at least one curated multi-turn flow demonstrates the agent honoring that context (per the existing agent contextual carry-over behavior).
- **SC-005**: A user can clear the visible chat and start a fresh conversation in a single click, and the next submission starts a new conversation as confirmed by a new conversation identifier.
- **SC-006**: When the backend is unreachable, the frontend shows a non-technical error message within 10 seconds of submission, without showing raw stack traces or backend file paths, and re-enables the input.
- **SC-007**: A new contributor on a fresh checkout can bring up the full stack and reach the frontend's first successful query in under 10 minutes, following only the documented commands.
- **SC-008**: The frontend never reads from DuckDB, Postgres, ETL artifacts, or local data files directly — verifiable by code review and by the absence of any such dependency in the frontend's runtime configuration.
- **SC-009**: The frontend never executes agent-generated Python or SQL — verifiable by code review.
- **SC-010**: At least one curated complex question (e.g., label diversity, outlier detection) succeeds end-to-end during a representative demo run.

## Assumptions

- **Backend endpoints**: The agent backend already exposes a query endpoint (returning conversation identifier, run identifier, assistant text, optional chart artifact reference, optional SQL, optional dataframe preview, optional routing/validation metadata), an artifact content endpoint, and a health endpoint. The optional inspection endpoints (e.g., reload prior conversation by identifier) are not relied on in V1; if they exist they may be used as a non-load-bearing enhancement.
- **CORS**: Permitting the frontend's local origin is the only backend change this feature requires. No new agent capabilities, no schema changes, no new SQL safety rules.
- **Chart format**: The agent's chart artifact is a self-contained, browser-renderable chart object. The frontend treats it as opaque content to be rendered inline; the artifact's internal structure is the backend's contract.
- **Demo target**: Local-only. The success criteria are about Demo Day usability on a presenter's laptop, not a deployed production environment.
- **Browser**: A current evergreen desktop browser. Mobile responsiveness is a stretch (vertical-stack layout) and not gated.
- **Conversation persistence semantics**: V1 stores only the active conversation identifier client-side. On reload, the chat area starts empty even though the underlying conversation continues server-side. Restoring chat history visually on reload is future work and depends on the existing inspection endpoints.
- **Response shape tolerance**: Optional fields may be missing on any given response. The frontend treats absence as the legitimate signal that the panel should be hidden, never as an error.
- **Curated questions**: The exact wording and categorization of curated questions is left to implementation, guided by the source brief; the contract is "at least 5, covering a meaningful spread of agent capabilities."
- **Runtime stack**: Implementation choices (UI framework, build tool, styling, container packaging) are deferred to the planning phase. The source brief recommends a specific stack but the spec does not bind to it.
- **Out of scope**: CSV-based browser-side re-charting, in-browser chart editing, demo galleries with pre-rendered artifacts, deployed environments, authentication, and saved-conversation browsing are all explicitly future work, not V1.

## Dependencies

- **Existing agent backend (004-agent-v1 family)**: This feature consumes the agent's HTTP API. It does not change agent behavior, prompt design, SQL safety, sandbox policy, or persistence schema — except for adding cross-origin permission for the frontend's local origin.
- **Local container orchestration**: The feature ships as a service in the existing local container stack so the demo can be brought up with documented commands.
- **No data-layer dependency**: This feature does not depend on DuckDB, Postgres, or ETL artifact paths; that boundary is part of the feature's contract.
