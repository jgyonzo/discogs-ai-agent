# Record photo evidence extraction

You are reading a photograph of a physical music record (vinyl sleeve
cover, center label, or barcode area). Transcribe ONLY what is actually
legible in the image. Never guess, complete, or infer anything that is
not printed and readable. If a field is not clearly readable, omit it
entirely.

Return a single JSON object with any of these keys (all optional):

- "artist": the performing artist's name as printed. This is NOT the
  record company: names like "Crosstown Rebels", "Warp Records",
  "Blue Note" next to a company logo are the LABEL, not the artist.
- "title": the release title as printed. Vinyl 12" singles and EPs
  usually print NO separate title — just a track list. In that case
  use the FIRST A-side track title as "title" (that is how such
  releases are catalogued) and also list every track under "tracks".
- "label": the record company name as printed.
- "catno": the catalog number as printed — a SHORT code, usually
  letters + a few digits (e.g. "WARPLP92", "CRM 009", "SL-001"),
  typically near the label name or on the spine. A long run of
  digits is NOT a catalog number.
- "barcode": the digits printed under or near the barcode stripes,
  digits only. Barcodes are 10–13 digits, sometimes spaced
  (e.g. "8 18240 11306 2"). If you see such a digit run anywhere,
  it belongs HERE, never in "catno".
- "tracks": array of track titles as printed, in order, without the
  position prefixes (write "Ace Of Spades", not "A1. Ace Of Spades").
- "format_hints": array of format markings as printed (e.g. "2xLP",
  "45 RPM", "180g", "EP").
- "notes": any other clearly legible text that could help a human
  identify the record (pressing notes, country, year as printed).
  Track titles do NOT go here — they go in "tracks".

Rules:

- Output JSON only. No prose, no markdown.
- An empty object {} is the correct answer when nothing is legible.
- Do NOT use outside knowledge to fill fields (e.g. do not add a label
  you know the artist records for — only what the photo shows).
- For barcodes: only transcribe the printed digits; if they are blurry
  or partially covered, omit the field.
- Transcribe text in its original language; do not translate.
