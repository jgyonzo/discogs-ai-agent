# Quickstart: Title-Aware Record Location (Postmortem)

**Feature**: 018-title-locate-postmortem

## Prerequisites

- `cd collection-agent && uv sync` (or the venv you already use for 017)
- A synced snapshot at `collection-agent/data/snapshot.json` (for the live
  replay only; tests never touch the network)

## Run the tests (no live API calls)

```bash
cd collection-agent
pytest                       # full suite — all pre-existing tests must stay green
pytest tests/unit/test_registry.py -k title   # new title-matching tests
pytest tests/unit/test_filters.py             # artist+title AND filter
```

## Verify the prompt surface

```bash
cd collection-agent
python -c "
from collection_agent.settings import Settings
from collection_agent.registry import build_registry, render_attribute_block
print(render_attribute_block(build_registry(Settings())))
" | grep title
```

Expected: a `title` line (kind `text`; ops `contains, eq`; aliases
incl. `título`) rendered automatically — no hand-written prose.

## Replay the incident (live snapshot, chat)

```bash
cd collection-agent
python -m collection_agent chat
```

Ask, in order:

1. `can you locate Guido Schneider - Focus On 2xLP?`
   → must find **Focus On Guido Schneider (2006)** (artist + title
   substring after stripping "2xLP").
2. `can you locate Troy Pierce - gone astral 2x12?`
   → must NOT answer "not in your collection" from a truncated list;
   expected path: title match fails ("astral" ≠ "astray") → artist-only
   retry lists 4 records → agent surfaces **Gone Astray EP** as the match
   (or presents the 4 candidates).
3. `Dj minx - A walk in the park?` → **A Walk In The Park EP (2004)**.
4. `Click box - Espaco tempo?` → **Espaço E Tempo (2008)** (diacritic
   folding).

Success = zero false "not in your collection" answers (SC-001).
