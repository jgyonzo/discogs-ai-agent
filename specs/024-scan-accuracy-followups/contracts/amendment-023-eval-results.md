# Amendment (024) to Contract: Eval Run Results & Summary (023)

023's `contracts/eval-results.md` stays authoritative; 024 adds record
fields, summary fields, and three invariants. The strict metrics'
definitions are UNCHANGED (spec SC-005); everything here is additive, and
023-format results files remain valid.

## Delta 1 — §2 result record: new fields

| Field | Rule |
|---|---|
| `evidence` | compact extracted-evidence values — byte-identical shape to the scan journal's `evidence` (022 FR-021: extracted values only, empties omitted). Present iff a vision call produced non-empty evidence; `no_evidence` records omit it (empty dump); `unlabeled` and pre-vision `error` records carry none. |
| `miss_master_relation` | present iff `outcome == "miss"`: `same_master` (truth master known ∧ some candidate's `master_id` equals it) · `different` (truth master known ∧ ≥1 candidate carried a master id ∧ none equal) · `unknown` (truth master unknown ∨ no candidate master ids to compare — includes zero-candidate misses). Never involves network requests. |

## Delta 2 — §3 summary: new fields

```json
{"misses_same_master": 4, "misses_different": 2, "misses_master_unknown": 25,
 "practical_rate": 0.61}
```

`practical_rate = (hits + misses_same_master) / (hits + misses + no_evidence)`
— the SAME denominator as `identification_rate`; `null` when the denominator
is 0. The strict rate stays the primary, headline metric; the practical rate
is always reported beside it, never instead of it.

## Delta 3 — §3 invariants 8–10 (normative, unit-tested)

8. `misses_same_master + misses_different + misses_master_unknown == misses`
9. `practical_rate ≥ identification_rate` when both non-null; equal iff
   `misses_same_master == 0`
10. every record with `vision_calls ≥ 1` and non-empty extraction carries
    `evidence`

Invariants 1–7 are unchanged and still hold.

## Delta 4 — §4 read-only guarantee: unchanged

Master classification is pure local comparison; the eval package's AST
guard and its forbidden-reference list are untouched.
