# Quickstart: verify 015-classifier-carryover

**Audience**: developer or reviewer validating that the 015 implementation lands correctly.
**Pre-requisites for live steps**: agent component is running locally via `docker-compose up agent-api postgres`; published DuckDB is mounted; OpenAI key is set in `.env`.

Verification procedure, not a development guide. Each step is grep-or-curl-checkable.

---

## Step 1 — New unit tests pass

```sh
cd agent
uv run pytest tests/unit/test_query_classifier.py -v
```

Expected: all pre-015 cases pass (5 from the original module — `test_simple_query_routes_to_simple`, `test_complex_query_routes_to_complex`, `test_price_query_is_unsupported`, `test_ambiguous_query_needs_clarification`, `test_techno_query_routes_to_simple_not_unsupported`) PLUS 3 new cases (`test_follow_up_with_carryover_routes_to_complex`, `test_follow_up_without_carryover_treats_as_first_turn`, `test_isolation_ambiguous_with_carryover_still_needs_clarification`). All 8 PASS.

Per spec SC-005, the 3 new tests are the unit-level proof of US1 + US2.

---

## Step 2 — Existing carryover-builder tests still pass

```sh
cd agent
uv run pytest tests/unit/test_carryover_builder.py -v
```

Expected: all pre-015 tests pass without modification. The `_carryover.py` module's existing logic (token-budget cap, turn-cap, oldest-first ordering) is unchanged by 015 — the only addition is the new public helper `load_carryover_for_state` (which has DB-binding, not unit-tested at this level).

---

## Step 3 — `{carryover_block}` placeholder present in router.md

```sh
grep -c "{carryover_block}" agent/src/discogs_agent/prompts/router.md
# Expected: 1
```

Also verify the new instruction text is present:

```sh
grep -c "USE the prior question text" agent/src/discogs_agent/prompts/router.md
# Expected: 1
```

And verify the canonical isolation-ambiguous examples are preserved:

```sh
grep -c "best labels" agent/src/discogs_agent/prompts/router.md
# Expected: at least 1 (the existing example in the clarification_needed bullet)
```

Per spec SC-004 + FR-004.

---

## Step 4 — `_load_carryover` no longer exists in `query_understanding.py`

```sh
grep -c "def _load_carryover" agent/src/discogs_agent/graph/nodes/query_understanding.py
# Expected: 0 (function moved to _carryover.py per the DRY refactor)

grep -c "def load_carryover_for_state" agent/src/discogs_agent/graph/nodes/_carryover.py
# Expected: 1 (the extracted public helper)
```

Per research §R2 + spec FR-006.

---

## Step 5 — Router node populates carryover state fields

```sh
grep -E "load_carryover_for_state|state\[.carryover_(preamble|turn_count).\]\s*=" \
  agent/src/discogs_agent/graph/nodes/router.py
# Expected: at least 3 matches (helper call + 2 state writes)
```

Per spec FR-001 + FR-007.

---

## Step 6 — `ClassifierInput.carryover_preamble` field exists

```sh
grep -A 5 "class ClassifierInput" agent/src/discogs_agent/tools/query_classifier.py \
  | grep -c "carryover_preamble"
# Expected: 1
```

And `_render_prompt` interpolates the placeholder:

```sh
grep "carryover_block=" agent/src/discogs_agent/tools/query_classifier.py
# Expected: 1 line — the .format() call passes carryover_block from payload.carryover_preamble
```

Per spec FR-002 + research §R6.

---

## Step 7 — Renumbered ETL pointer (015 → 016)

```sh
# OLD path no longer exists
test ! -f specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md && \
  echo "OK: successor-015-pointer.md removed"

# NEW path exists
test -f specs/013-filtered-aggregation-postmortem/contracts/successor-016-pointer.md && \
  echo "OK: successor-016-pointer.md present"

# Content references 016 (not 015)
grep -c "016-release-unique-view-materialization" \
  specs/013-filtered-aggregation-postmortem/contracts/successor-016-pointer.md
# Expected: at least 2 (title + provisional-naming section)

# Historical-context note records BOTH renumberings
grep -c "renumbered AGAIN to.*016" \
  specs/013-filtered-aggregation-postmortem/contracts/successor-016-pointer.md
# Expected: 1
```

Per spec FR-013 + SC-006.

---

## Step 8 — Upstream contract amendment applied

```sh
# 004/tools.md documents the new ClassifierInput field
grep -c "carryover_preamble" specs/004-agent-v1/contracts/tools.md
# Expected: at least 1
```

Per spec FR-011.

---

## Step 9 — Full agent test suite passes (no regressions)

```sh
cd agent
uv run pytest tests/unit tests/integration -q
# Expected: at least 151 passed, 3 skipped (post-014 baseline was 148 passed, 3 skipped;
# 015 adds 3 new passing tests).
```

Per spec SC-005.

---

## Step 10 — Live-infra: replay thread 9214f7fb-... (SC-001)

Requires `docker-compose up agent-api postgres` and an OpenAI key.

Replay the two-message sequence that triggered the bug:

```sh
# First, establish the prior turn (ranked-by-metric question).
THREAD=$(uuidgen)
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\":\"$THREAD\",\"user_query\":\"which is the label with most Electronic releases?\"}" \
  | jq '{status, complexity}'
# Expected: status=succeeded, complexity=complex (or simple)

# Then, the follow-up that pre-015 failed:
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\":\"$THREAD\",\"user_query\":\"and what is the second one?\"}" \
  | jq '{status, complexity}'
# Expected (POST-015): status=succeeded, complexity=simple or complex.
# Pre-015 this returned status=failed_clarification_needed.
```

Inspect the run record:

```sh
docker exec -i genai-pathway-final-project-yonzo-postgres-1 psql -U agent -d agent -c \
  "SELECT run_id, status, complexity, jsonb_typeof(metadata_json->'carryover') AS carryover_type
   FROM agent_runs
   WHERE thread_id = '$THREAD'
   ORDER BY started_at;"
```

Expected: 2 rows; the second row has `status = succeeded` (NOT `failed_clarification_needed`) AND `carryover_type = 'object'`.

---

## Step 11 — Live-infra: clarification_needed run has non-null carryover (SC-003)

Construct a thread where the 2nd turn genuinely needs clarification (e.g., a question that's ambiguous even with context). Then verify the persisted carryover.

```sh
THREAD=$(uuidgen)
# Turn 1 (succeeded, establishes context):
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\":\"$THREAD\",\"user_query\":\"Show releases by decade as a bar chart\"}" \
  > /dev/null

# Turn 2 (genuinely ambiguous despite carryover):
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\":\"$THREAD\",\"user_query\":\"What about the best ones?\"}" \
  | jq '{status, final_response}'
```

Inspect:

```sh
docker exec -i genai-pathway-final-project-yonzo-postgres-1 psql -U agent -d agent -c \
  "SELECT status, jsonb_pretty(metadata_json->'carryover') AS carryover
   FROM agent_runs
   WHERE thread_id = '$THREAD' ORDER BY started_at DESC LIMIT 1;"
```

Expected: `status = failed_clarification_needed` (the 2nd-turn question genuinely needs clarification), AND `carryover` is a non-null object with `turn_count >= 1`. **This is the key US2 outcome**: pre-015 this would have been `null`; post-015 it's an object showing the operator what context the classifier had.

---

## Step 12 — Live-infra: five-question follow-up regression probe (SC-002)

Five different follow-up shapes across distinct prior topics:

```sh
declare -a tests=(
  "which is the label with most Electronic releases?|and what is the second one?"
  "top 2 labels by Electronic releases|and the top 5?"
  "Show releases by decade for Rock|same but for jazz"
  "Show me releases in 2020|what about 2010?"
  "Show me top 5 artists|show me 10 instead"
)
for pair in "${tests[@]}"; do
  THREAD=$(uuidgen)
  q1="${pair%|*}"
  q2="${pair#*|}"
  echo "=== $q1 → $q2 ==="
  curl -s -X POST http://localhost:8001/query \
    -H "Content-Type: application/json" \
    -d "{\"thread_id\":\"$THREAD\",\"user_query\":\"$q1\"}" > /dev/null
  curl -s -X POST http://localhost:8001/query \
    -H "Content-Type: application/json" \
    -d "{\"thread_id\":\"$THREAD\",\"user_query\":\"$q2\"}" \
    | jq '{status}'
done
```

Expected for each: `status != "failed_clarification_needed"` (typically `"succeeded"`).

Per spec SC-002.

---

## Step 13 — Live-infra: regression guard — isolation-ambiguous still rejected (SC-004)

```sh
THREAD=$(uuidgen)
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\":\"$THREAD\",\"user_query\":\"What are the best labels?\"}" \
  | jq '{status, complexity}'
```

Expected: `status = failed_clarification_needed`, `complexity = clarification_needed`. The canonical isolation-ambiguous example must still bite — 015 narrows clarification_needed's behavior, doesn't disable it.

Per spec SC-004.

---

## Step 14 — Constitution + checklist re-validation

```sh
cat specs/015-classifier-carryover/checklists/requirements.md
```

All items should remain `[x]`. If any drifted to `[ ]` during implementation (e.g., a new clarification surfaced), update the spec and the checklist before merge.

---

## Roll-back

If 015 needs to be reverted post-merge:

- Revert the 5 code files: `_carryover.py` (drop the new helper), `router.py` (drop the load + state writes + ClassifierInput arg), `query_understanding.py` (restore the local `_load_carryover` function and the state writes), `query_classifier.py` (drop the `carryover_preamble` field + render line), `router.md` (remove placeholder + instruction text).
- Revert the test file: `test_query_classifier.py` (remove the 3 new test cases).
- Revert the contract amendment: `004/contracts/tools.md`.
- Re-rename `successor-016-pointer.md` → `successor-015-pointer.md` and revert the content edits.

Roll-back surface is moderate (~6 file reverts) but self-contained. No database migrations, no infra changes. Pre-015 behavior is restored.
