# Discogs API v2.0 — Reference

> Condensed, implementation-focused reference for the Discogs API v2.0,
> distilled from <https://www.discogs.com/developers/>. Covers the base
> URL, authentication tiers, rate limiting, pagination, and every
> Database/Search endpoint (plus a summary of Marketplace, Inventory,
> and User endpoints). Written to be usable directly when building
> features in this repo — see the "How this maps to this project"
> section at the end.

---

## 1. Overview

- **What it is:** A RESTful, JSON interface to Discogs data. Read
  Database objects (Artists, Releases, Masters, Labels), and — when
  authenticated as a user — manage Collections, Wantlists, Lists, and
  Marketplace listings/orders.
- **Base URL:** `https://api.discogs.com`
- **Format:** JSON (`Content-Type: application/json`). All requests
  must be HTTPS.
- **Only one version exists: `v2`.** You can pin it via the `Accept`
  header (see §6).
- **Licensing:** Some data is CC0 (No Rights Reserved), some is
  "restricted data" per the API Terms of Use. The **monthly data
  dumps** are CC0.
- **Quickstart:**
  ```bash
  curl https://api.discogs.com/releases/249504 --user-agent "FooBarApp/3.0"
  ```

### 1.1 Required: `User-Agent` header

Every request **must** send a unique, descriptive `User-Agent` string
(ideally RFC 1945-style). This is not optional — **a missing or generic
User-Agent commonly yields an empty response**, and abusive/obscure
agents may be silently blocked.

Good examples:

```
AwesomeDiscogsBrowser/0.1 +http://adb.example.com
LibraryMetadataEnhancer/0.3 +http://example.com/lime
MyDiscogsClient/1.0 +http://mydiscogsclient.org
```

Bad (rejected/blocked): raw `curl/...`, spoofed browser `Mozilla/5.0 ...`,
or vague `my app`. **Make yours unique** so Discogs can contact you
instead of silently blocking.

---

## 2. Authentication

Four tiers exist. Pick based on whether you need image URLs, a higher
rate limit, and/or to act as a specific user.

| Credentials in request | Rate limit | Image URLs? | Authenticated as user? |
|---|---|---|---|
| **None** (anonymous) | 🐢 Low tier (25/min) | ❌ No | ❌ No |
| **Consumer key + secret only** | 🐰 High tier (60/min) | ✔️ Yes | ❌ No |
| **Full OAuth 1.0a** (access token/secret) | 🐰 High tier | ✔️ Yes | ✔️ Yes — on behalf of any user 🌍 |
| **Personal access token** | 🐰 High tier | ✔️ Yes | ✔️ Yes — token holder only 👩 |

Key takeaways:
- Key/secret **unlocks image URLs** (unavailable to anonymous requests)
  and **raises your rate limit**, but does **not** identify you as a
  particular user. Private/user-scoped resources (orders, private
  inventory fields, private collections) require a **token** option.
- Register apps / generate tokens at **Developer Settings**:
  <https://www.discogs.com/settings/developers>. Never disclose your
  Consumer Secret.

### 2.1 Discogs Auth (simplest — recommended for read-only / own-account)

Requires HTTPS (you're transmitting the key/secret or token). Three ways
to present credentials:

**Query string — key/secret:**
```bash
curl "https://api.discogs.com/database/search?q=Nirvana&key=foo123&secret=bar456"
```

**Query string — personal access token:**
```bash
curl "https://api.discogs.com/database/search?q=Nirvana&token=abcxyz123456"
```

**`Authorization` header (preferred over query string):**
```bash
curl "https://api.discogs.com/database/search?q=Nirvana" \
  -H "Authorization: Discogs key=foo123, secret=bar456"
# or
curl "https://api.discogs.com/database/search?q=Nirvana" \
  -H "Authorization: Discogs token=abcxyz123456"
```

### 2.2 OAuth 1.0a (act on behalf of arbitrary users)

Use only if others log into your app on their behalf. Use an OAuth
library. Discogs recommends the **PLAINTEXT** signature method over
HTTPS (`oauth_signature = "<consumer_secret>&"`).

OAuth endpoints:
- Request token: `GET https://api.discogs.com/oauth/request_token`
- Authorize (browser redirect): `https://www.discogs.com/oauth/authorize?oauth_token=<request_token>`
- Access token: `POST https://api.discogs.com/oauth/access_token`
- Identity check: `GET https://api.discogs.com/oauth/identity`

Flow:
1. Get consumer key/secret from Developer Settings (once per app).
2. `GET /oauth/request_token` with an `Authorization: OAuth ...` header
   (`oauth_consumer_key`, `oauth_nonce`, `oauth_signature`,
   `oauth_signature_method="PLAINTEXT"`, `oauth_timestamp`,
   `oauth_callback`). → returns `oauth_token`, `oauth_token_secret`,
   `oauth_callback_confirmed`.
3. Redirect the user to the Authorize page; on approval they get a
   **verifier** (delivered to your callback URL if configured).
4. `POST /oauth/access_token` with the request token + `oauth_verifier`.
   → returns the **access token** + **access token secret**. These do
   **not expire** (unless the user revokes access) — persist them.
   ⚠️ The request token + verifier expire **15 minutes** after issue.
5. Sign all subsequent requests with the access token/secret. Verify
   via `GET /oauth/identity`.

---

## 3. Rate Limiting

- Throttled **per source IP**, by a **moving average over a 60-second
  window**. If no requests are made for 60s, the window resets.
- **60 requests/min** authenticated, **25 requests/min** unauthenticated
  (with some exceptions).
- Identify yourself with a unique User-Agent to get the maximum rate.
- Response headers to track your budget:

| Header | Meaning |
|---|---|
| `X-Discogs-Ratelimit` | Total requests allowed in the 1-minute window |
| `X-Discogs-Ratelimit-Used` | Requests made in the current window |
| `X-Discogs-Ratelimit-Remaining` | Requests still available in the window |

Throttle locally against the global limit. Discogs may change these
limits at any time.

---

## 4. Pagination

Collection endpoints are paginated. Defaults to **50 items/page**;
`per_page` max is **100**.

**Query params:** `page` (1-based), `per_page` (≤ 100).

```
GET https://api.discogs.com/artists/1/releases?page=2&per_page=75
```

Responses include a `Link` header (`rel=next|prev|first|last`) **and** a
`pagination` object in the body:

```json
{
  "pagination": {
    "page": 2,
    "pages": 30,
    "items": 2255,
    "per_page": 75,
    "urls": {
      "first": "https://api.discogs.com/artists/1/releases?page=1&per_page=75",
      "prev":  "https://api.discogs.com/artists/1/releases?page=1&per_page=75",
      "next":  "https://api.discogs.com/artists/1/releases?page=3&per_page=75",
      "last":  "https://api.discogs.com/artists/1/releases?page=30&per_page=75"
    }
  },
  "releases": [ ... ]
}
```

(`urls` may omit `prev`/`next` at the boundaries, and is `{}` when there
is a single page.)

---

## 5. HTTP Status Codes

| Code | Meaning |
|---|---|
| `200 OK` | Success; data in body. |
| `201 Continue` | POST created a resource; new ID in body. |
| `204 No Content` | Success, empty body. |
| `401 Unauthorized` | Resource requires authentication. |
| `403 Forbidden` | Authenticated but not permitted (e.g. editing another user). |
| `404 Not Found` | Resource doesn't exist. |
| `405 Method Not Allowed` | Verb unsupported (e.g. `PUT /artists/1` — read-only). |
| `422 Unprocessable Entity` | Well-formed but semantically wrong (bad/missing param, malformed JSON). Check body. |
| `500 Internal Server Error` | Server error; body `message` has an error code for Support. Also seen on search as `"Query time exceeded. Please try a simpler query."` / `"Malformed query?"`. |

Errors return a JSON body: `{"message": "Release not found."}`.

---

## 6. Versioning & Media Types

Pin the version via the `Accept` header. Three text-formatting variants
(controls how text fields like notes/profiles are rendered):

- `application/vnd.discogs.v2.html+json`
- `application/vnd.discogs.v2.plaintext+json`
- `application/vnd.discogs.v2.discogs+json` ← **default** (also used if
  `Accept` is missing or unrecognized)

**JSONP:** append `?callback=<name>`; since JSONP can't read headers, the
response wraps status into the payload:
`callback({"meta": {"status": 200}, "data": { ... }})`.

---

## 7. Database Endpoints

Base: `https://api.discogs.com`. All Database reads are `GET`. Rating
`PUT`/`DELETE` require user auth.

### 7.1 Release — `GET /releases/{release_id}{?curr_abbr}`

A specific physical/digital object released by one or more artists.

- `release_id` (number, **required**) — e.g. `249504`
- `curr_abbr` (string, optional) — currency for marketplace figures.
  One of: `USD GBP EUR CAD AUD JPY CHF MXN BRL NZD SEK ZAR`. Defaults to
  the authenticated user's currency.

Key response fields:

| Field | Notes |
|---|---|
| `id`, `title`, `year`, `released`, `released_formatted` | `year` is int; `released` is a string ("1987"). |
| `country`, `notes`, `data_quality` | `data_quality` e.g. `"Correct"`, `"Needs Vote"`. |
| `artists[]`, `extraartists[]` | each: `id`, `name`, `anv`, `join`, `role`, `tracks`, `resource_url`. |
| `labels[]`, `companies[]` | `catno`, `entity_type`, `entity_type_name`, `id`, `name`, `resource_url`. |
| `formats[]` | `name`, `qty`, `descriptions[]` (e.g. `["7\"","Single","45 RPM"]`). |
| `genres[]`, `styles[]` | genre is broad, style is granular. |
| `tracklist[]` | `position`, `title`, `duration`, `type_` (`track`/`heading`), optional `extraartists[]`. |
| `identifiers[]` | `{type, value}` e.g. Barcode. |
| `images[]` | `type` (`primary`/`secondary`), `uri`, `uri150`, `resource_url`, `width`, `height`. **Requires auth to fetch.** |
| `videos[]` | `uri`, `title`, `description`, `duration`, `embed`. |
| `master_id`, `master_url` | Link to the parent master, if any. |
| `community` | `have`, `want`, `rating {average, count}`, `status`, `submitter`, `contributors[]`, `data_quality`. |
| `lowest_price`, `num_for_sale` | Marketplace summary. |
| `estimated_weight`, `format_quantity`, `date_added`, `date_changed`, `uri`, `resource_url`, `thumb`, `series[]` | — |

404 body: `{"message": "Release not found."}`.

### 7.2 Release Rating (by user)

- `GET /releases/{release_id}/rating/{username}` — one user's rating.
  → `{"username","release_id","rating"}` (rating 1–5).
- `PUT /releases/{release_id}/rating/{username}` — set rating. Body:
  `rating` (int 1–5). **Auth as the user required.**
- `DELETE /releases/{release_id}/rating/{username}` — remove rating.
  **Auth as the user required.**

### 7.3 Community Release Rating — `GET /releases/{release_id}/rating`

Average + count across all users:
`{"rating": {"count": 47, "average": 4.19}, "release_id": 249504}`.

### 7.4 Release Stats — `GET /releases/{release_id}/stats`

Community collection/wantlist counts:
`{"num_have": 2315, "num_want": 467}`.

### 7.5 Master Release — `GET /masters/{master_id}`

A set of similar releases sharing a "main release" (usually the
earliest). `master_id` (number, required) — e.g. `1000`.

Key fields: `id`, `title`, `year`, `main_release`, `main_release_url`,
`versions_url`, `artists[]`, `genres[]`, `styles[]`, `tracklist[]`,
`images[]`, `videos[]`, `num_for_sale`, `lowest_price`, `data_quality`,
`uri`, `resource_url`. 404 body: `{"message": "Master Release not found."}`.

### 7.6 Master Versions — `GET /masters/{master_id}/versions{?page,per_page}`

All releases that are versions of a master. Accepts pagination, plus
filters/sorts:

- `format`, `label`, `released` (year), `country` — filters.
- `sort` — one of `released`, `title`, `format`, `label`, `catno`,
  `country`.
- `sort_order` — `asc` | `desc`.

Each `versions[]` item: `id`, `title`, `format`, `label`, `catno`,
`country`, `released`, `status`, `major_formats[]`, `thumb`,
`resource_url`, and `stats.{user,community}.{in_collection,in_wantlist}`.

### 7.7 Artist — `GET /artists/{artist_id}`

A person/group who contributed to releases. `artist_id` (number,
required) — e.g. `108713`.

Key fields: `id`, `name`, `profile`, `namevariations[]`, `realname`,
`urls[]`, `images[]`, `members[]` (each `{id, name, active, resource_url}`),
`groups[]`, `aliases[]`, `data_quality`, `releases_url`, `uri`,
`resource_url`. 404 body: `{"message": "Artist not found."}`.

### 7.8 Artist Releases — `GET /artists/{artist_id}/releases{?sort,sort_order}`

Releases **and masters** credited to the artist. Paginated.

- `sort` — one of `year`, `title`, `format`.
- `sort_order` — `asc` | `desc`.

Each `releases[]` item: `id`, `title`, `type` (`master`|`release`),
`role` (e.g. `Main`), `year`, `artist`, `format`, `label`, `thumb`,
`resource_url`, and (for masters) `main_release`.

### 7.9 Label — `GET /labels/{label_id}`

A label, company, studio, location, or other entity. `label_id` (number,
required) — e.g. `1`.

Key fields: `id`, `name`, `profile`, `contact_info`, `urls[]`,
`images[]`, `sublabels[]` (`{id, name, resource_url}`),
`parent_label`, `data_quality`, `releases_url`, `uri`, `resource_url`.
404 body: `{"message": "Label not found."}`.

### 7.10 Label Releases — `GET /labels/{label_id}/releases{?page,per_page}`

Releases on the label. Paginated. Each `releases[]` item: `id`, `title`,
`artist`, `catno`, `format`, `year`, `status`, `thumb`, `resource_url`.

---

## 8. Search — `GET /database/search`

> **Requires authentication** (any tier: key/secret or token). Accepts
> pagination.

Full signature:

```
GET /database/search?q={query}&type=&title=&release_title=&credit=
    &artist=&anv=&label=&genre=&style=&country=&year=&format=
    &catno=&barcode=&track=&submitter=&contributor=
```

All parameters are optional strings; combine them freely (they AND
together). `page`/`per_page` apply.

| Param | Searches | Example |
|---|---|---|
| `q` | Free-text query (all fields) | `nirvana` |
| `type` | Result type: `release`, `master`, `artist`, `label` | `release` |
| `title` | Combined "Artist Name - Release Title" | `nirvana - nevermind` |
| `release_title` | Release titles | `nevermind` |
| `credit` | Release credits | `kurt` |
| `artist` | Artist names | `nirvana` |
| `anv` | Artist name variation | `nirvana` |
| `label` | Label names | `dgc` |
| `genre` | Genres | `rock` |
| `style` | Styles | `grunge` |
| `country` | Release country | `canada` |
| `year` | Release year | `1991` |
| `format` | Format | `album` |
| `catno` | Catalog number | `DGCD-24425` |
| `barcode` | Barcode | `7 2064-24425-2 4` |
| `track` | Track titles | `smells like teen spirit` |
| `submitter` | Submitter username | `milKt` |
| `contributor` | Contributor usernames | `jerome99` |

Example:
```
GET https://api.discogs.com/database/search?release_title=nevermind&artist=nirvana&per_page=3&page=1
```

Each `results[]` item (fields vary by type): `id`, `type`, `title`,
`thumb`, `country`, `year`, `format[]`, `label[]`, `genre[]`, `style[]`,
`barcode[]`, `catno`, `uri`, `resource_url`,
`community {want, have}`.

Search-specific `500` bodies:
`{"message": "Query time exceeded. Please try a simpler query."}` and
`{"message": "An internal server error occurred. (Malformed query?)"}`.

---

## 9. Images

`images[]` entries appear on Release/Master/Artist/Label responses as
**fully-qualified, signed HTTPS URLs** (host `api-img.discogs.com`).

- **Fetching image bytes requires authentication** (OAuth or Discogs
  Auth with key/secret or token) **and counts against rate limits**.
- **Never edit the URL** — they're signed; changing any part (e.g. the
  ID) breaks the signature and yields 404. Just fetch the object and use
  the URL verbatim.
- Anonymous requests receive **no** image URLs at all.

---

## 10. Marketplace, Inventory & User Endpoints (summary)

These require user auth (OAuth or personal token) and are mostly outside
this project's scope. Listed for completeness.

### 10.1 Marketplace

| Verb | Path | Purpose |
|---|---|---|
| `GET` | `/marketplace/listings/{listing_id}{?curr_abbr}` | Get a listing |
| `POST` | `/marketplace/listings/{listing_id}{?curr_abbr}` | Edit a listing (owner) |
| `DELETE` | `/marketplace/listings/{listing_id}{?curr_abbr}` | Delete a listing (owner) |
| `POST` | `/marketplace/listings{?release_id,condition,sleeve_condition,price,comments,allow_offers,status,external_id,location,weight,format_quantity}` | Create a listing |
| `GET` | `/marketplace/orders/{order_id}` | Get an order (seller) |
| `POST` | `/marketplace/orders/{order_id}` | Edit an order (seller) |
| `GET` | `/marketplace/orders{?status,created_after,created_before,sort,sort_order}` | List orders (seller) |
| `GET`/`POST` | `/marketplace/orders/{order_id}/messages` | Order message thread |
| `GET` | `/marketplace/fee/{price}` and `/marketplace/fee/{price}/{currency}` | Fee for a listing price |
| `GET` | `/marketplace/price_suggestions/{release_id}` | Suggested prices by condition (auth + seller settings) |
| `GET` | `/marketplace/stats/{release_id}{?curr_abbr}` | Release marketplace stats (auth optional) |

### 10.2 Inventory Export / Upload

| Verb | Path | Purpose |
|---|---|---|
| `POST` | `/inventory/export` | Request a CSV export of your inventory |
| `GET` | `/inventory/export` | List recent exports |
| `GET` | `/inventory/export/{id}` | Export status |
| `GET` | `/inventory/export/{id}/download` | Download the CSV |
| `POST` | `/inventory/upload/add` · `/change` · `/delete` | Bulk add/change/delete via CSV |
| `GET` | `/inventory/upload` · `/inventory/upload/{id}` | Upload history / status |
| `GET` | `/users/{username}/inventory{?status,sort,sort_order}` | A seller's inventory |

### 10.3 User Identity, Profile, Collection, Wantlist, Lists

| Verb | Path | Purpose |
|---|---|---|
| `GET` | `/oauth/identity` | Who am I (OAuth) |
| `GET` | `/users/{username}` | Public profile |
| `POST` | `/users/{username}` | Edit profile (self) |
| `GET` | `/users/{username}/submissions` | User submissions |
| `GET` | `/users/{username}/contributions{?sort,sort_order}` | User contributions |
| `GET`/`POST` | `/users/{username}/collection/folders` | List / create collection folders |
| `GET`/`POST`/`DELETE` | `/users/{username}/collection/folders/{folder_id}` | Get / rename / delete folder |
| `GET` | `/users/{username}/collection/folders/{folder_id}/releases` | Releases in a folder |
| `GET` | `/users/{username}/collection/releases/{release_id}` | Instances of a release in the collection |
| `POST` | `/users/{username}/collection/folders/{folder_id}/releases/{release_id}` | Add release to folder |
| `POST`/`DELETE` | `.../releases/{release_id}/instances/{instance_id}` | Move / remove an instance |
| `GET`/`POST` | `/users/{username}/collection/fields[/...]` | Custom collection fields & values |
| `GET` | `/users/{username}/collection/value` | Min/median/max collection value |
| `GET` | `/users/{username}/wants` | Wantlist |
| `PUT`/`POST`/`DELETE` | `/users/{username}/wants/{release_id}{?notes,rating}` | Add / edit / remove wantlist item |
| `GET` | `/users/{username}/lists` | User's public lists |
| `GET` | `/lists/{list_id}` | Items in a list |

---

## 11. How this maps to this project

This repo's **ETL** component is built on the **monthly CC0 data dumps**
(the authoritative source for `release_fact`, `master_fact`, the bridge
tables, etc. — see the `specs/*/contracts/duckdb-schema.md` files), not
on live API calls. The live API is complementary and useful for:

- **Enrichment / freshness:** pulling fields the dumps lack or that
  change often — community `have`/`want`, `rating`, `lowest_price`,
  `num_for_sale`, marketplace stats — via `GET /releases/{id}`,
  `/releases/{id}/stats`, `/releases/{id}/rating`.
- **Resolving IDs:** `GET /database/search` (typed: `release`, `master`,
  `artist`, `label`) to map free text → Discogs IDs before hitting the
  object endpoints. **Search requires auth.**
- **Images:** only via authenticated requests; URLs are signed and must
  be used verbatim.

Practical guardrails if/when we call the live API:

1. **Always set a unique `User-Agent`** (empty responses otherwise).
2. **Use a token or key/secret** — raises the limit to 60/min and
   unlocks images; anonymous is 25/min and image-less.
3. **Respect `X-Discogs-Ratelimit-*` headers**; throttle locally to the
   60-second moving window.
4. **Page with `per_page` ≤ 100**; follow the `pagination.urls`/`Link`
   header rather than constructing page URLs by hand.
5. **Handle `429`/`500` gracefully** — search can 500 on overly complex
   queries; back off and simplify.
6. Keep API secrets out of the repo (env/settings, mirroring the
   existing `CORS_ALLOWED_ORIGINS` / OpenAI-key pattern).

---

*Source: <https://www.discogs.com/developers/> (Discogs API v2.0).
Compiled for internal reference; verify against the live docs before
relying on exact response shapes, as Discogs may change them.*
