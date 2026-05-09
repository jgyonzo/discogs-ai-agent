# Quickstart: Agent Frontend V1

**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

This document walks through three flows: local-dev (frontend only, against an already-running agent), full-stack docker-compose, and the end-to-end smoke test. It is the executable companion to Spec US5 (one-command bring-up) and to the SC-007 success metric (under-10-minute first-success path on a fresh checkout).

---

## 0. Prerequisites

| Tool | Required version | Purpose |
|------|-----------------|---------|
| Node.js | 20.x LTS | Vite + dev server + tests |
| `npm` | shipped with Node 20 | Dependency manager |
| Docker Desktop (or compose-compatible runtime) | recent | Full-stack bring-up |
| The published DuckDB | Existing project artifact | Mounted by `agent-api` per existing compose |
| `.env` at repo root | Existing project file | OpenAI key, etc. — unchanged from 004/005/007 |

The frontend has no other dependencies. There's no separate database, no separate cache, no separate broker.

---

## 1. Local dev — frontend only

For UI iteration when the agent is already running (e.g., started via `docker compose up agent-api postgres`):

```bash
cd frontend
npm install                                    # First time only
npm run dev
# → Local:   http://localhost:5173/
```

Open `http://localhost:5173`. The page renders with curated questions visible; the input box is enabled.

The frontend reads `VITE_API_BASE_URL` from `frontend/.env` (a per-component `.env`, not the repo-root one). If absent, it falls back to `http://localhost:8000`. To point at a different agent:

```bash
echo 'VITE_API_BASE_URL=http://localhost:8001' > frontend/.env.local
# Restart `npm run dev` to pick up env changes
```

---

## 2. Full-stack docker-compose

The one-command bring-up:

```bash
docker compose up --build
```

This starts (in dependency order):

1. `postgres` (existing) — agent's session/run store.
2. `agent-api` (existing) — Now also serves CORS preflights from the frontend's origin.
3. `frontend` (NEW in this feature) — Vite dev-server inside the container, listening on `0.0.0.0:5173`, with `VITE_API_BASE_URL=http://localhost:8000`.

Open `http://localhost:5173`. The page should render within 1-2s. Click any curated question, click "Run" — the chart appears within 5-15s for the cheap-model path (per SC-003).

To bring up only the new piece (assuming the rest is running):

```bash
docker compose up --build frontend
```

---

## 3. End-to-end smoke test

Three checks. All should pass on a fresh checkout against a working agent.

### 3.1 Backend reachable

```bash
curl -fs http://localhost:8000/health | jq .
```

Should print a JSON object with `status: "ok"`. If it doesn't, the agent isn't ready — fix that first; the frontend can't help.

### 3.2 Frontend serving

```bash
curl -fs -o /dev/null -w "%{http_code}\n" http://localhost:5173
# → 200
```

Should print `200`. If not, `frontend` service didn't start — check `docker compose logs frontend`.

### 3.3 End-to-end chart render

In a browser at `http://localhost:5173`:

1. Click the **Releases by decade** card → click **Run**.
2. Within ~10s the assistant message appears: "Generated a chart of releases by decade."
3. The chart pane shows a bar chart by decade.
4. The SQL panel (collapsed) reveals the generated `SELECT decade, COUNT(*)...` query.
5. The data preview shows the first ~5 decade rows.
6. The metadata badges show: `simple · gpt-4o-mini · succeeded`.

If steps 2-6 all hold, the demo path is working. Spec SC-001 requires this for ≥ 5 of the curated questions.

### 3.4 Conversation continuity

In the same browser:

1. After Q1 succeeds, type `Now only show data after 1990` and hit Enter.
2. The assistant should issue a new chart filtered to 1990+. The agent's contextual carry-over (multi-turn — see CLAUDE.md "Resolved scope decisions") makes this work without re-stating the metric.
3. Click **New conversation**. The chat clears. The chart pane shows the welcome state.
4. Type the same follow-up `Now only show data after 1990` again. The agent will respond with a clarification request (no prior context to carry over) — Spec US3 acceptance scenario 2 verified.

### 3.5 Error path

Stop the agent (`docker compose stop agent-api`) and submit any question:

- The frontend displays "The agent is not reachable. Check that the local stack is running." within 10s.
- The input is re-enabled.
- No raw stack trace anywhere in the page.

This satisfies SC-006.

---

## 4. Where things live

### 4.1 localStorage

Single key: `discogs.frontend.currentThreadId`. Inspect it via DevTools → Application → Local Storage → `http://localhost:5173`.

Manually clearing it:

```js
localStorage.removeItem("discogs.frontend.currentThreadId");
```

is equivalent to clicking "New conversation" (the button does this plus dispatching a reducer action).

### 4.2 Configuration

| What | Where | Default |
|------|-------|---------|
| `VITE_API_BASE_URL` | `frontend/.env`, `frontend/.env.local`, or compose env block | `http://localhost:8000` |
| Curated question set | `frontend/src/data/curatedQuestions.ts` | The seven entries from `contracts/curated-questions.md` |
| Iframe sandbox attrs | `frontend/src/components/ArtifactFrame.tsx` | `sandbox="allow-scripts"` (no `allow-same-origin`) |

The agent-side configuration (CORS allowlist) is documented in `contracts/amendment-004-api-cors.md` and lands in `agent/.env.example` as `CORS_ALLOWED_ORIGINS`.

### 4.3 Run the test suite

```bash
cd frontend
npm test                         # Vitest, single run
npm run test:watch               # Vitest, watch mode
npm run typecheck                # tsc --noEmit
npm run lint                     # ESLint (if configured)
```

The unit + component + integration suites should all pass on a clean checkout. MSW handlers under `frontend/tests/mocks/` mock the agent for the integration suite, so the agent does not need to be running for `npm test`.

---

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Page loads, click Run, nothing happens | Backend unreachable | `docker compose logs agent-api` — is it healthy? Check `/health`. |
| `Failed to fetch` / CORS error in console | Agent CORS not configured for this origin | Confirm `CORS_ALLOWED_ORIGINS` includes `http://localhost:5173` (or your origin). Default should already cover this. |
| Chart iframe shows browser default error page | Artifact URL 404, or `chart_artifact.url` is wrong | Confirm `agent/.env` has `ARTIFACTS_DIR` set; `docker compose logs agent-api` for path-resolution errors. |
| `npm install` fails | Node version mismatch | Confirm Node 20 LTS (`node --version`). |
| `docker compose up frontend` fails on `npm ci` | `package-lock.json` not committed | `cd frontend && npm install` first to generate it. |
| Refresh-during-query hangs | Browser dropped the in-flight fetch | Expected; submit again. The conversation continues because `thread_id` is in localStorage. |
| New conversation doesn't actually clear | localStorage write failed (e.g., browser private mode) | The chat clears in-memory but won't persist; submit will start a new conversation regardless. |
