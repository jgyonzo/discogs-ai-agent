# Contract: Agent Tool Surface & Confirmation Protocol (017)

The LLM interacts with the collection **only** through these tools. Tools are
deterministic Python over the snapshot (reads) or the Discogs client
(writes). The LLM narrates tool output; it never computes counts, prices, or
links itself (FR-022). Adding a tool or attribute is a contract change —
update this file in the same change set.

## 1. Read tools (snapshot-served)

| Tool | Signature (conceptual) | Returns (see data-model §6) |
|---|---|---|
| `aggregate_by` | `(attribute: str)` | Aggregation: buckets `{value, count, pct}` + explicit unknown bucket + counting note. Backs FR-004 (genre), FR-005 (label), FR-007 (country) and any registry attribute. |
| `filter_records` | `(criteria: [{attribute, op, value}], limit?)` | Listing: matches (artist/title/year/…), count, `unsupported_criteria`, `truncated`. AND-combined (FR-011/012/013). |
| `top_n` | `(basis: "community_rating"\|"most_expensive"\|"rarest", n?)` | Ranking with `basis` text, thresholds used, and `excluded_missing_data` count (FR-006/008/010). |
| `media_links` | `(record_refs: [...])` | Per-record links with explicit `none` flag (FR-014/015/016). `record_refs` accept instance ids or the results of the previous listing ("those"). |
| `collection_value` | `()` | Discogs min/median/max + currency + basis (FR-009). |
| `snapshot_status` | `()` | sync age, completeness, counts, folder list (FR-003b). |

**Serving rules**: `partial` snapshot ⇒ every read tool prepends a
partial-data warning to its result. `stale` ⇒ staleness note. No snapshot ⇒
tools return a "sync required" signal the agent must surface (US1 scenario 8).
A synced but **empty** collection (0 instances) returns an explicit
empty-collection signal — never a zero-bucket distribution.

## 2. Sync tools

| Tool | Effect |
|---|---|
| `start_sync(full?: bool)` | runs/resumes the two-phase sync with progress; returns final meta. The CLI also exposes this outside conversation (`sync` subcommand). |

## 3. Attribute registry (extensibility contract — FR-013)

Single source of truth in `registry.py`; each entry declares
`name, aliases(en+es), kind(categorical|numeric|text), multi, extract(record),
unknown_label` (data-model §4).

**Launch set**: `genre, style, year, decade, label, country, artist, format,
folder, my_rating, community_rating, have, want, num_for_sale, lowest_price,
scarcity`.

**Ops by kind**: categorical → `eq, in`; numeric → `eq, lt, lte, gt, gte,
between, missing`; text → `contains, eq`. Multi-valued attributes match if
**any** value matches; aggregations over them count per-record-per-value and
say so.

**Extension rule (SC-003a)**: adding a filterable/aggregatable attribute =
adding **one registry entry** (+ its unit test). `aggregate_by`,
`filter_records`, and the system prompt pick it up automatically. Anything
requiring edits to tool code or prompt prose to add an attribute violates
this contract.

**Unknown attribute (FR-013a)**: `filter_records` returns the unmatched
criterion in `unsupported_criteria` together with the currently-supported
attribute names; the agent must name what it couldn't apply — silently
dropping a criterion is forbidden.

## 4. Write path — two-phase, runtime-gated (FR-017/018/019/020)

```text
LLM: propose_moves(record_refs, target_folder_name, create_if_missing)
        └─ dry-run: resolve instances, validate folder (live name check),
           build WritePlan{plan_id}, return human-readable summary
CLI RUNTIME (not the LLM): renders plan, prompts  "¿Confirmás? [y/N]"
        └─ 'y'  → execute_plan(plan_id)
        └─ else → plan cancelled, nothing sent to Discogs
execute_plan:
  1. create folder if planned (POST .../collection/folders)
  2. per move: live re-validate instance (folder/current state) →
     POST .../folders/{fid}/releases/{rid}/instances/{iid}
  3. collect per-item ok/failed(+reason); never abort remaining items
  4. patch snapshot (or mark stale) + report results table
```

**Normative guards**:
- `execute_plan` MUST NOT be callable as an LLM tool. It is invoked only by
  the CLI runtime after an interactive `y`. An unconfirmed write is
  *unreachable by construction*, not merely discouraged in the prompt.
- `plan_id` is single-use; a new `propose_moves` expires any pending plan;
  plans die with the session (never persisted).
- Folder `0` (All) is virtual and rejected as a move target; folder `1`
  (Uncategorized) is a real folder and a valid target. Folder creation
  rejects names colliding (case-insensitively) with an existing folder and
  offers the existing one instead.
- Live re-validation failure (instance moved/removed since sync) ⇒ that item
  fails with an explanatory reason; others proceed (FR-020, edge case
  "stale snapshot vs live actions").
- Every mutation goes through the same rate-limit governor as reads.

## 5. System prompt obligations (Constitution VII(b) analog)

The system prompt (`prompts/system.md`):
- MUST render the attribute list (names, aliases, kinds, ops) **dynamically
  from the registry** via a `{attribute_block}` placeholder. Static prose
  enumerating attributes, snapshot fields, or "what the collection contains"
  is forbidden.
- MUST instruct: mirror the user's language (es/en); always relay tool
  warnings (partial/stale/truncated/unsupported); state basis/criterion when
  presenting value, rating, or rarity results; never invent records, counts,
  prices, or links (only narrate tool output).
- MUST NOT promise capabilities outside this tool surface.

## 6. CLI surface

| Command | Behavior |
|---|---|
| `python -m collection_agent chat` | REPL. Banner shows snapshot age/state; offers sync when absent. Meta-commands: `/refresh`, `/status`, `/exit`. Write confirmations are REPL-level prompts (§4). |
| `python -m collection_agent sync [--full]` | run/resume sync non-interactively with progress + final meta summary. `--full` re-enriches all releases. |
| `python -m collection_agent status` | print SnapshotMeta (age, completeness, counts, warnings). |

Exit codes: `0` success; `1` unexpected error; `2` configuration error
(missing/invalid token); `3` sync ended partial.
