# CLI Contract Delta: Discogs ETL — Fase 2+3

**Authoritative for**: changes to the developer-facing CLI in this
spec. Read together with the Fase 1 contract at
`specs/001-discogs-etl/contracts/cli.md`, which remains authoritative
for everything not explicitly diffed here.

**Backward compatibility**: this spec adds **no new flags** and
**no new subcommands**. All Fase 1 invocations continue to work
unchanged (FR-020). The only observable behavior changes are
*inside* the run:

- The pipeline now accepts `releases.xml.gz` at the conventional raw
  path. Detection is automatic (suffix-based, see
  [research.md](../research.md) R-02). No flag change.
- Progress log lines emitted on per-release steps now include
  elapsed seconds and instantaneous releases/sec.
- A truncated XML input no longer aborts the run; the truncation
  surfaces as a manifest warning and the run continues to publish
  if all critical DQ checks otherwise pass (FR-001 / FR-002).
- Exit code on a truncated-but-otherwise-passing run is **0** (not
  1), because the run finalizes with
  `quality_checks.status = "passed_with_warnings"`.

## Configuration additions

The CLI itself is unchanged, but `--config <path>` now consumes two
new optional keys (with defaults wired in code):

```yaml
limits:
  peak_rss_cap_gib: 4                    # NEW (FR-011)
  dq_check_in_memory_threshold: 10000000 # NEW (FR-014)
```

Old `base.yml` files without these keys keep working — the defaults
are applied when the keys are absent.

## Reserved flags (still off-limits)

The Fase 1 reservation list is unchanged:

- `--with-masters` / `--with-artists` — reserved for Fase 4.
- `--auto-download` — reserved for Fase 5.

## Out of scope for this spec

- A `--gzip` opt-in flag — not needed because suffix detection is
  automatic.
- A `--peak-rss-cap` CLI override — set via `base.yml` only; CLI
  surface stays minimal.
- A `--dry-run` flag — still Fase 2/3 territory but not part of
  this spec's acceptance criteria.

## Verification

The Fase 1 integration tests (`test_sample_pipeline.py`) MUST
continue to pass unchanged (SC-003). The new
`test_real_sample_pipeline.py` and `test_big_sample_pipeline.py`
exercise the no-CLI-change-but-different-runtime-behavior surface.
