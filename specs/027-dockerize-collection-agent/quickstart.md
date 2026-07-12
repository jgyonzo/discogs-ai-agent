# Quickstart: Dockerize the collection-agent

**Feature**: `027-dockerize-collection-agent` · **Date**: 2026-07-12

Prerequisites: Docker Desktop running; repo-root `.env` populated
(`DISCOGS_USER_TOKEN`, `OPENAI_API_KEY`); no host Python needed for any
container step.

## 1. Automated checks (no Docker needed)

```bash
cd collection-agent && pytest
```

Expected: all pre-existing 536 tests pass unmodified, plus the new packaging
guards (default-service-set pin, profile presence, isolation, Dockerfile and
`.dockerignore` hygiene). `git diff main --stat -- collection-agent/src/`
shows zero changes (SC-005).

## 2. Build the image

```bash
docker compose --profile collection build collection-agent
```

Expected: build succeeds; the context upload is small (KBs — `data/` and
`.venv/` excluded). Image audit (SC-004):

```bash
docker run --rm --entrypoint sh <image> -c \
  'ls /app/collection-agent && ! ls /app/.env /app/collection-agent/.env 2>/dev/null && ! find /app/collection-agent/data -type f 2>/dev/null | grep .'
grep -rE "DISCOGS_USER_TOKEN=|OPENAI_API_KEY=|sk-" <(docker history --no-trunc <image>) && echo LEAK || echo clean
```

Expected: only `pyproject.toml`, `src`, `README.md` (plus install metadata)
under `/app/collection-agent`; no `.env`; no data files; `clean`.

## 3. Demo stack is untouched (SC-002)

```bash
docker compose up -d
docker compose ps --format '{{.Service}}' | sort
```

Expected: exactly `agent-api`, `frontend`, `postgres` — no
`collection-agent` container created, even with a token-less `.env`.
Tear down: `docker compose down`.

## 4. Scan server as a service (SC-001)

```bash
docker compose --profile collection up collection-agent
```

Expected: startup log shows the live folder validation passing, then uvicorn
serving on `0.0.0.0:8022`. From a phone on the same Wi-Fi, open
`http://<host-LAN-IP>:8022` (the Mac's LAN address — not the URL in the
container banner). Complete one scan-and-add:

- the add lands in Discogs (verify on the site);
- a new journal file appears on the **host** at
  `collection-agent/data/scan-sessions/<session>.jsonl` with the `added` line;
- the host snapshot is marked stale (`python -m collection_agent status`
  from the venv, or step 5's containerized `status`).

## 5. One-off modes + state interchangeability (SC-003)

```bash
# containerized sync writes the same host snapshot the venv reads
docker compose run --rm collection-agent sync
docker compose run --rm collection-agent status
cd collection-agent && source .venv/bin/activate && python -m collection_agent status
```

Expected: both `status` invocations report the same completeness and counts
(same file). Reverse direction: run `sync` from the venv, then the
containerized `status` — identical. Interactive chat:

```bash
docker compose run --rm collection-agent chat
```

Expected: prompt renders, a question answers from the snapshot, `/exit`
works, exit code 0.

## 6. Loud config failure (SC-006)

```bash
docker compose --profile collection run --rm -e DISCOGS_USER_TOKEN= collection-agent scan
echo $?
```

Expected: a human-readable configuration error, exit code `2`, and — because
the service carries no restart policy — a single exit, never a retry loop
(check `docker compose ps -a`: one exited container).

## 7. Interrupt/resume across the boundary

Start `docker compose run --rm collection-agent sync`, Ctrl-C mid-run, then
re-run from the **host venv**. Expected: sync resumes from the journal
exactly as an all-host workflow does.

---

## Owner live-validation checklist (T-owner)

- [ ] **SC-001** phone scan-and-add through the containerized server; journal
      line + stale mark verified on host *(date, session id)*
- [ ] **SC-002** `docker compose up` with token-less `.env` → exactly the
      three demo services *(date)*
- [ ] **SC-003** container-sync → venv-status AND venv-sync →
      container-status, identical counts *(date)*
- [ ] **SC-004** image audit clean: no secrets, no data, no `.env` *(date)*
- [ ] **SC-006** empty-token scan start exits 2, no restart loop *(date)*
- [ ] Interrupt/resume across the boundary (step 7) *(date)*
