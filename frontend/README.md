# Discogs Analytics Frontend

Browser frontend for the Discogs analytics agent. Sends natural-language questions to the agent's HTTP API and renders the chart artifact, generated SQL, data preview, and run metadata in a chat-style UI.

Spec: [`specs/008-agent-frontend-v1/spec.md`](../specs/008-agent-frontend-v1/spec.md). The canonical run-and-test commands live in [`specs/008-agent-frontend-v1/quickstart.md`](../specs/008-agent-frontend-v1/quickstart.md).

## Boundaries

This component never reads DuckDB, Postgres, ETL files, or local artifacts directly, and never executes agent-generated Python or SQL. The chart artifact is rendered as opaque HTML inside a sandboxed `<iframe>`. All analytical work happens in the agent backend.

## Run locally

```bash
npm install        # First time
npm run dev        # Vite dev server on http://localhost:5173
```

Assumes the agent backend is reachable at the URL configured in `frontend/.env` (default `http://localhost:8000`). Start the agent and Postgres via `docker compose up agent-api postgres` from the repo root.

## Run in compose

From the repo root:

```bash
docker compose up --build
```

Brings up the full stack (`postgres`, `agent-api`, `frontend`). Frontend is reachable at `http://localhost:5173`.

## Run tests

```bash
npm test               # Unit + component + integration suites (Vitest)
npm run test:watch     # Watch mode
npm run typecheck      # tsc --noEmit
```

## Where things live

- `src/api/` — HTTP client + TypeScript domain types matching the agent's `/query` response.
- `src/components/` — React components (Header, ChatPanel, QueryInput, ResultPanel, ArtifactFrame, SqlViewer, DataPreviewTable, RunMetadata, ThreadControls, LoadingState, ErrorBanner, SuggestedQuestions).
- `src/hooks/` — `useAgentQuery` (reducer + submit thunk), `useThreadId` (localStorage-backed).
- `src/utils/` — `localStorage`, `errors` (translation table for user-facing messages).
- `src/data/` — curated demo questions.
- `tests/` — Vitest + React Testing Library + MSW.
