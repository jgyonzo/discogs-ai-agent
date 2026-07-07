# Amendment (024) to Contract: Eval Dataset Layout & Ground Truth (023)

023's `contracts/eval-dataset.md` stays authoritative; 024 adds one manifest
field, one reader rule, and one builder mode. Licensing/containment rules
(§4) are untouched and still guard-tested.

## Delta 1 — §1.1 `release` line: `master_id` (additive)

A `release` manifest line MAY carry `master_id` (integer): the truth
release's Discogs master id, taken from the release payload the builder
already fetches (zero extra requests during a normal build). Discogs
`master_id` of `0`/absent ⇒ the key is omitted ("no master"). 023-format
manifests (no `master_id` anywhere) remain fully valid.

## Delta 2 — §1.2 reader rule: newest line per release wins (normative)

When a release_id appears on multiple `release` lines, readers MUST treat
the NEWEST (last) line as authoritative — for status, images, and
`master_id`. This formalizes the 023 failed→retried duplicate-line case and
is what makes backfill lines supersede without ever rewriting the
append-only manifest.

## Delta 3 — §1.2 builder: `--backfill-masters` mode

`eval-dataset --backfill-masters`:

- iterates done releases (newest line `downloaded`/`no_images`) whose newest
  line lacks `master_id`;
- fetches release metadata only (governed; NO image downloads);
- appends a copy of the release's newest line with `master_id` set and
  `fetched_at` refreshed — image ground truth carried over verbatim;
- on fetch failure/404: counts it, appends nothing (the old line stays
  authoritative), continues — never guesses;
- appends its own `run_header` like any build invocation and honors
  `--limit`.

## Delta 4 — §3.1 retained-photo labels: unchanged

Retained photos still label by journal release_id only; they have NO master
ground truth in v1 (their eval misses classify `unknown` — see
amendment-023-eval-results).
