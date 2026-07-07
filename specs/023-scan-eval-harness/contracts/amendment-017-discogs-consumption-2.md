# Amendment 2 (023) to Contract: Discogs API Consumption (017)

017's `contracts/discogs-consumption.md` declares that any endpoint or field
not listed there is not consumed. Feature 022 added the first amendment
(`specs/022-phone-record-scan/contracts/amendment-017-discogs-consumption.md`:
`/database/search` read + add-to-collection write). Feature 023 adds **read
consumption only** — new fields on an already-contracted endpoint, plus image
binary downloads. The 017 file and 022 amendment are left untouched (repo
convention: amendments live in the amending feature's `contracts/`).

## Delta 1 — §2 Read endpoints: `GET /releases/{id}` gains fields consumed

The endpoint itself is already contracted (sync enrichment). 023's dataset
builder additionally consumes, per response:

| Field | Use |
|---|---|
| `images[].type` | `primary` / `secondary` — drives secondary-preferred selection (spec FR-003) |
| `images[].uri` | full-size image URL, used **verbatim** as the download source and recorded verbatim in the dataset manifest (019 discipline: never rewritten or constructed) |

The sync path continues to ignore `images[]`; the snapshot schema is
unchanged (research R1).

## Delta 2 — §2 Read endpoints: image binary download

| Request | When | Handling |
|---|---|---|
| `GET <images[].uri>` (absolute URL, typically `i.discogs.com`) | dataset build only (023), at most `COLLECTION_AGENT_EVAL_IMAGES_PER_RELEASE` (default 2) per release | issued through the same client `_request` path — settings User-Agent and auth header ride along; 404/403 (expired signed URI) → recorded as a failed download in the manifest, never retried within the run; non-`image/*` content-type → failed download |

**Licensing rule (normative)**: downloaded images are uploader-copyrighted.
They MUST live only under the component's gitignored `data/` tree, MUST NOT be
committed to any repository, and MUST NOT be redistributed or served beyond
the owner's machine. The dataset directory carries a `NOTICE.txt` stating
this; a guard test enforces the gitignore coverage.

## Delta 3 — §4 Rate-limit & failure policy: applies unchanged

Both the per-release fetches and the image downloads go through the shared
`_request` path (header-driven governor, 429 backoff, 401 abort, 5xx retry).
The image CDN sends no `X-Discogs-Ratelimit*` headers; the governor ignores
header-less responses by design, so API pacing stays driven by the API
responses interleaved with downloads. A full build over a 300–1k-release
snapshot is a one-sitting, minutes-scale job inside the 60 req/min budget.

## Delta 4 — §3 Write endpoints: explicitly none

023 adds **no** write consumption. The eval harness is structurally read-only:
the `eval/` package may not reference `add_to_collection`, `create_folder`, or
`move_instance` (AST guard test, research R6). §3's never-called-mutations
list remains fully in force.
