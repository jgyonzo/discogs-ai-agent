# Quickstart: User-context tenancy seam (029)

This feature has no new command and no new screen. "Trying it" means two
things: confirming nothing changed for the owner, and running the tests that
exercise two users in one process.

## Run the suite

```bash
cd collection-agent
pip install -e ".[dev]"     # only if the venv is not set up yet
pytest                      # everything; no live API calls
```

Useful subsets while implementing (file names are indicative; `tasks.md` is
authoritative):

```bash
pytest tests/unit/test_rate_budget.py tests/unit/test_discogs_client_auth.py
pytest tests/unit/test_tenancy_ids.py tests/unit/test_tenancy_guards.py
pytest tests/integration/test_two_user_isolation.py
pytest tests/integration/test_local_context_regression.py
```

## Use the app exactly as before

```bash
python -m collection_agent serve        # or: scan
docker compose --profile collection up collection-agent
```

Same banner, same page, same files under `collection-agent/data/`. No
`data/users/` directory appears: it is created only when a non-implicit user
first writes, and no entry point serves one yet.

## Owner validation checklist

Record the date and any observation next to each item.

- [ ] **SC-001** — `pytest` passes. `git diff --stat main -- collection-agent/tests`
      lists only added files (no pre-existing test file modified), or each
      modified file is justified in `tasks.md`.
- [ ] **SC-002 (a)** — Before starting, save a listing of the data directory:
      `find collection-agent/data -maxdepth 2 | sort > /tmp/before.txt`.
- [ ] **SC-002 (b)** — `serve`; from the phone: scan one record and add it.
      The add reaches Discogs, the journal line appears under
      `data/scan-sessions/`, the snapshot is marked stale.
- [ ] **SC-002 (c)** — In the Chat tab: ask a question, then ask for a folder
      move, confirm the plan. The move executes; the snapshot is patched in
      place.
- [ ] **SC-002 (d)** — In the Collection tab: Sync. Progress shows; the result
      is `complete`. While it runs, a scan on the Scan tab still works.
- [ ] **SC-002 (e)** — `find collection-agent/data -maxdepth 2 | sort >
      /tmp/after.txt; diff /tmp/before.txt /tmp/after.txt` shows only the new
      session journal — no `users/` directory, nothing moved or renamed.
- [ ] **SC-002 (f)** — Console output during (b)–(d) looks like a pre-feature
      session: same banner, pacing notices only where they appeared before.
- [ ] **Token gate** — With `DISCOGS_USER_TOKEN` commented out in `.env`,
      `python -m collection_agent status` prints the same configuration error
      as before and exits 2. Restore the token.
- [ ] **Container** — `docker compose run --rm collection-agent status` reads
      the same snapshot as the host run.

SC-003 through SC-010 are automated; their evidence is the green test run of
the first item.
