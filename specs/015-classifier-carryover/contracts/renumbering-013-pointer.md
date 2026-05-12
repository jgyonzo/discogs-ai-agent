# Renumbering: 013's successor pointer (015 → 016) — second renumbering

**Source feature**: `015-classifier-carryover`
**Target file**: `specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md` (renamed by 014 from `successor-014-pointer.md`)
**Operation**: rename + content edit.
**Spec FR**: FR-013.
**Predecessor**: 014's FR-018 (first renumbering of this same pointer doc; 014 → 015).

This document records the SECOND renumbering admin task on 013's deferred-ETL pointer. 013 originally reserved spec number `014` for the ETL-side rewrite of `release_unique_view`. 014 (`cross-grain-join-postmortem`) took 014, bumping the ETL follow-on to `015`. 015 (`classifier-carryover`, this spec) now takes 015, bumping the ETL follow-on to `016`.

---

## Step 1: File rename

```sh
git mv specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md \
        specs/013-filtered-aggregation-postmortem/contracts/successor-016-pointer.md
```

`git mv` (not `rm + add`) preserves file history under `git blame` — readers can trace the document back through both renumberings.

---

## Step 2: Content edits

Inside the renamed file, replace every occurrence of `015-release-unique-view-materialization` with `016-release-unique-view-materialization`. Specific lines (post-014 baseline):

| Location | Pre-015 text | Post-015 text |
|---|---|---|
| Document title (line 1) | `# Successor pointer: future ETL-component spec (\`015-release-unique-view-materialization\`)` | `# Successor pointer: future ETL-component spec (\`016-release-unique-view-materialization\`)` |
| Provisional naming section | `Spec number: \`015-release-unique-view-materialization\` (provisional; ...)` | `Spec number: \`016-release-unique-view-materialization\` (provisional; ...)` |
| All other references throughout the file | `015-release-unique-view-materialization` | `016-release-unique-view-materialization` |

---

## Step 3: Update the historical-context note

The existing note (added by 014's renumbering admin) reads:

```markdown
*Note: this document was originally drafted as `successor-014-pointer.md`
during 013's `/speckit-plan` phase, when "014" was the provisional spec
number for this deferred ETL fix. On 2026-05-10, the cross-grain-join
postmortem (`014-cross-grain-join-postmortem`) became the actual
occupant of 014, so the ETL follow-on was renumbered to "015" by 014's
FR-018. See
[`specs/014-cross-grain-join-postmortem/contracts/renumbering-013-pointer.md`](../../014-cross-grain-join-postmortem/contracts/renumbering-013-pointer.md)
for the renumbering record.*
```

Replace it with:

```markdown
*Note: this document was originally drafted as `successor-014-pointer.md`
during 013's `/speckit-plan` phase, when "014" was the provisional spec
number for this deferred ETL fix. On 2026-05-10, the cross-grain-join
postmortem (`014-cross-grain-join-postmortem`) took 014, so the ETL
follow-on was renumbered to "015" by 014's FR-018. On 2026-05-11, the
classifier-carryover spec (`015-classifier-carryover`) took 015, so
the ETL follow-on was renumbered AGAIN to "016" by 015's FR-013. See
[`specs/014-cross-grain-join-postmortem/contracts/renumbering-013-pointer.md`](../../014-cross-grain-join-postmortem/contracts/renumbering-013-pointer.md)
and
[`specs/015-classifier-carryover/contracts/renumbering-013-pointer.md`](../../015-classifier-carryover/contracts/renumbering-013-pointer.md)
for the two renumbering records.*
```

---

## Why this is the second renumbering of the same pointer

013 spec planning chose `014-release-unique-view-materialization` as the provisional spec name for the deferred ETL fix. The number `014` was the next sequential number after 013 — natural at the time. Subsequent specs that landed first kept taking the next-available sequential number, which forced the deferred-ETL pointer to bump each time:

- 013 reserved 014 → committed.
- 014 took 014 (the cross-grain join postmortem). 013's pointer renamed `successor-014` → `successor-015` (014's FR-018).
- 015 took 015 (this spec). 013's pointer renamed `successor-015` → `successor-016` (this FR-013).

If 016 takes the ETL fix (the originally-deferred work), the pointer eventually points at a real, opened spec. If a different spec takes 016 first, the pointer renames again to `successor-017`, etc. Each renumbering is administrative housekeeping; the deferred work itself is unchanged.

**Future-prevention consideration** (not in scope for 015): a future cleanup spec could rewrite 013's pointer to use a stable placeholder (e.g., `TBD-release-unique-view-materialization`) instead of a number, eliminating renumberings. Recorded in `research.md §R10` as a potential follow-up.

---

## What this is NOT

- It is NOT a re-deferral of the ETL fix. The 016 work remains deferred under the same conditions 013 specified. 015 only renumbers the pointer.
- It is NOT a modification of the deferred work's scope, acceptance criteria, or trigger conditions. The pointer's content is preserved verbatim except for the spec-number string.
- It is NOT a constitutional concern. The pointer document is descriptive (records a deferral), not normative. Renumbering it is housekeeping.

---

## Verification

After the rename + content edits land:

```sh
# OLD path no longer exists
test ! -f specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md

# NEW path exists
test -f specs/013-filtered-aggregation-postmortem/contracts/successor-016-pointer.md

# Content references 016 (not 015) for the ETL spec name
grep -q "016-release-unique-view-materialization" \
  specs/013-filtered-aggregation-postmortem/contracts/successor-016-pointer.md

# Historical-context note records BOTH renumberings
grep -q "originally drafted as.*successor-014-pointer" \
  specs/013-filtered-aggregation-postmortem/contracts/successor-016-pointer.md
grep -q "renumbered AGAIN to.*016" \
  specs/013-filtered-aggregation-postmortem/contracts/successor-016-pointer.md
```

All four checks MUST pass on the post-015 codebase.

---

## Implementation pointer

The rename + content edits land in 015's implementation commit. No code change associated with this contract — pure documentation maintenance, same shape as 014's renumbering admin.
