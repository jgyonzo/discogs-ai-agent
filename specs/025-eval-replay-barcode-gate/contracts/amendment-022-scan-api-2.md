# Amendment 2 (025) to Contract: Scan API (022)

022's `contracts/scan-api.md` (as amended by 024) stays authoritative;
025 adds one rule to the evidence-normalization semantics (the paragraph
established by 022 addendum 1, FR-019/020). Wire shapes are unchanged.

## Delta 1 — Semantics: barcode plausibility gate (025 FR-009..012)

Appended to the FR-019/020 normalization semantics:

- A `barcode` whose digits-only value is shorter than 8 digits is not a
  barcode (real UPC-E/EAN-8 through EAN-13 are 8–13 digits): it is
  **cleared** from the evidence before any ladder or evidence-kind
  decision — the barcode rung cannot fire on it, `evidence_summary.kinds`
  and `evidence_summary.fields` never show it, and the journal's / eval's
  compact `evidence` payloads reflect the post-gate values (no ghost
  barcode anywhere downstream).
- The cleared value is **not** moved to `catno` — deliberately asymmetric
  with FR-019: a 10+-digit run is definitively a barcode, but a short
  digit run is not definitively a catalog number, and injecting it could
  hijack the catno rung the same way the implausible barcode hijacked the
  barcode rung (motivating live case: vision emitted `"barcode": "3070"`
  which suppressed the correctly-extracted catno `D-216`).
- Ordering: the gate applies **after** FR-019's catno→barcode
  reclassification, so a reclassified value (≥ 10 digits by construction)
  is never gated; the two rules compose without interaction.
- Barcodes of 8 or more digits, and all non-barcode evidence, are
  processed byte-identically to pre-025. Evidence whose only field was an
  implausible barcode becomes empty evidence and follows the existing
  no-match path (FR-012 of 022).
- The plausibility minimum is the domain constant
  `BARCODE_PLAUSIBLE_MIN_DIGITS = 8` (same posture as FR-019's
  `BARCODE_MIN_DIGITS = 10`: not deployment configuration). The vision
  prompt is unchanged.

The gate lives at the single shared evidence-normalization site, so the
phone scan page and the eval harness (camera and replay modes alike)
exhibit it identically.
