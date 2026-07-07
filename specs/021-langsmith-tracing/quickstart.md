# Quickstart: LangSmith Tracing for the Collection Agent

**Feature**: 021-langsmith-tracing

## 1. Configure (repo-root `.env`)

The repo `.env` already carries the LangSmith trio used by `agent/`; the
collection agent reuses those names and adds only an optional project name:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...          # from smith.langchain.com → Settings → API Keys
# LANGSMITH_ENDPOINT=...            # optional, defaults to the SDK endpoint
# COLLECTION_AGENT_LANGSMITH_PROJECT=discogs-collection-agent   # optional, this is the default
```

Nothing else is required. If `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` are
absent, the agent runs exactly as before — tracing is a strict no-op.

> The collection agent's traces land in their **own** LangSmith project
> (`discogs-collection-agent` by default) — deliberately separate from the
> `agent/` component's `LANGSMITH_PROJECT`.

## 2. Install & run

```bash
cd collection-agent
pip install -e .          # picks up the new langsmith dependency
python -m collection_agent chat
```

Have a short conversation, e.g.:

1. `how many records do I have?` (analytics turn)
2. `show my minimal records from 2005` (tool-listing turn)
3. `and the play links for the first one` (multi-tool turn)

## 3. Review traces

Open <https://smith.langchain.com>, select the `discogs-collection-agent`
project. Expect (≤ 60 s after each turn):

- **One root trace per turn**, named `run_turn`.
- Expanding a trace: the LLM call(s) with full request payloads — note the
  trailing transient language reminder on every request (wire truth; it is
  never in the persisted session) — and one tool span per tool execution,
  named after the tool (`filter_records`, `playlist_links`, …) with its
  arguments and returned payload.
- **Token usage** (prompt/completion/total) on every LLM call; per-trace
  totals in the project view.

## 4. Verify the no-op guarantee

```bash
cd collection-agent
env -u LANGSMITH_TRACING -u LANGSMITH_API_KEY pytest    # full suite, offline
```

All tests pass with no network access to LangSmith (the suite also scrubs
`LANGSMITH_*` itself via an autouse fixture, so a configured shell cannot
leak traces from tests).

Run chat once with the tracing vars commented out: behavior is identical to
`main`; no wrapper is installed on the OpenAI client.

## 5. Verify failure tolerance (SC-005)

Set `LANGSMITH_API_KEY` to a bogus value and chat: every turn must complete
normally (at most a background log notice about failed trace delivery).
Restore the real key afterwards.

## Acceptance mapping

| Spec item | Where verified |
|---|---|
| SC-001 3-turn trace shape | §2–§3 above (scripted conversation) |
| SC-002 token usage | §3 |
| SC-003 offline suite | §4 |
| SC-004 unconfigured identity | §4 (chat without vars) |
| SC-005 invalid-key tolerance | §5 |
| SC-006 ≤ 60 s visibility | §3 |

## Live validation (2026-07-07)

Owner-performed audits (T009, T013, T014, T018) against the real `.env`
LangSmith key and live OpenAI chat; all reported passing:

- **SC-001 / US1 sc.5 (T009)**: scripted 3-turn conversation ⇒ 3 root
  `run_turn` traces in the `discogs-collection-agent` project; LLM calls and
  tool spans nested with correct names/args/payloads; the trailing
  `LANGUAGE_REMINDER` visible on every traced request (wire truth).
- **SC-004 / SC-005 (T013)**: unconfigured chat behaves identically to
  `main` with nothing landing in LangSmith; bogus-key chat completes every
  turn normally.
- **SC-002 (T014)**: prompt/completion/total token counts present on every
  LLM run; per-trace totals visible in the project view (research R5 held —
  zero code needed).
- **SC-003 / SC-006 (T018)**: offline suite 223 passed with `LANGSMITH_*`
  scrubbed; traces appeared well inside the 60 s visibility bound.
