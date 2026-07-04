"""Fuzzy matcher: messy (artist, title) rows -> Discogs release candidates.

Experimental. Reads ONLY the ETL-published DuckDB
(`data/published/duckdb/discogs.duckdb`) — never the Discogs API, never
`etl/` or `agent/` source. The published catalog is treated as a logical,
read-only schema (Constitution Principle VI).

Matching strategy (v0):
  1. Normalize artist + title identically on both sides (query and catalog)
     so typos/casing/accents/punctuation don't sink an otherwise-good match.
  2. Score each candidate with Jaro-Winkler (DuckDB built-in, vectorized in
     C++ so it scales to the full ~19M-release dump) on artist and title,
     blended by `artist_weight`.
  3. Return the top-K candidates with a per-field score breakdown so the
     disambiguation step (which pressing?) can use year/country/format/label.

No write side here — that's deliberately out of scope for this notebook.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import duckdb
import pandas as pd

# The one data surface this tool is allowed to read.
_PUBLISHED_REL = Path("data/published/duckdb/discogs.duckdb")
# Per the 001 contract, `release_unique_view` is exactly one row per release.
_SOURCE_VIEW = "release_unique_view"

_PUNCT = re.compile(r"[^a-z0-9]+")


def find_published_duckdb(start: Path | None = None) -> Path:
    """Walk up from `start` (or cwd) to locate the published DuckDB."""
    here = (start or Path.cwd()).resolve()
    for base in (here, *here.parents):
        candidate = base / _PUBLISHED_REL
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Could not find {_PUBLISHED_REL} walking up from {here}. "
        "Run the ETL first (see repo README §Quickstart)."
    )


# Invisible marks Discogs exports / spreadsheets leave around the separator.
_BIDI = re.compile(r"[‎‏​﻿]")
# Separator is any dash variant (ASCII hyphen, en-dash, em-dash) — real lists
# mix all three — with optional surrounding whitespace.
_SEP = re.compile(r"\s*[-–—]\s*")


def split_artist_title(raw: object) -> tuple[str, str]:
    """Split a combined ``"ARTIST - Title"`` cell into ``(artist, title)``.

    Real-world DJ lists put both in one column with an unreliable separator
    (``"Danny- Keep"``, ``"A - B - C"``, en-dash ``"X ‎– Y"``). We strip bidi
    marks, then split on the *first* dash with optional surrounding spaces. No
    dash -> ``("", raw)`` so the matcher leans entirely on the title.
    """
    s = "" if raw is None else _BIDI.sub("", str(raw)).strip()
    parts = _SEP.split(s, maxsplit=1)
    if len(parts) == 2 and parts[0]:
        return parts[0].strip(), parts[1].strip()
    return "", s


def normalize(s: object) -> str:
    """Lowercase, strip accents, drop punctuation, collapse whitespace.

    MUST stay in lockstep with `_sql_norm` below — both sides of the
    comparison have to be normalized the same way or scores are garbage.
    """
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return _PUNCT.sub(" ", s.lower()).strip()


def _sql_norm(col: str) -> str:
    """DuckDB expression mirroring `normalize()` for a column."""
    return f"trim(regexp_replace(lower(strip_accents({col})),'[^a-z0-9]+',' ','g'))"


# Columns surfaced for every candidate (display + disambiguation signals).
_SELECT_COLS = f"""
    release_id,
    title,
    primary_artist_name AS artist,
    year, country,
    primary_format_group AS fmt,
    has_vinyl,
    primary_genre        AS genre,
    primary_label_name   AS label,
    {_sql_norm('primary_artist_name')} AS na,
    {_sql_norm('title')}               AS nt,
    {_sql_norm("primary_artist_name || ' ' || title")} AS nc
"""


class Matcher:
    """Fuzzy-match (artist, title) against the published Discogs catalog.

    Parameters
    ----------
    db_path:
        Path to the published DuckDB. Auto-located if omitted.
    fast_index:
        If True, materialize a normalized projection of the whole catalog
        into an in-memory table once (~6s, ~7 GB RAM) so each `search()` is
        sub-second. If False (default), scan the view per query (~5s each,
        no extra RAM). Use True for tight eval loops, False if memory-bound.
    """

    def __init__(self, db_path: str | Path | None = None, fast_index: bool = False):
        self.db_path = Path(db_path) if db_path else find_published_duckdb()
        self.fast_index = fast_index
        if fast_index:
            self.con = duckdb.connect()  # in-memory
            self.con.execute(f"ATTACH '{self.db_path}' AS src (READ_ONLY)")
            self.con.execute(
                f"CREATE TABLE catalog AS SELECT {_SELECT_COLS} "
                f"FROM src.{_SOURCE_VIEW}"
            )
            self._from = "catalog"
            self._src = "src."  # other published tables stay behind the attach
        else:
            self.con = duckdb.connect(str(self.db_path), read_only=True)
            self._from = f"(SELECT {_SELECT_COLS} FROM {_SOURCE_VIEW})"
            self._src = ""

    def src_table(self, name: str) -> str:
        """Qualify another published table (e.g. `release_label_bridge`) so it
        resolves in both modes — top-level when scanning the file, behind the
        `src` attach when `fast_index` is on."""
        return f"{self._src}{name}"

    def search(
        self,
        artist: str,
        title: str,
        k: int = 5,
        artist_weight: float = 0.4,
        vinyl_only: bool = False,
    ) -> pd.DataFrame:
        """Return the top-`k` candidate releases, best score first.

        `artist_weight` blends the artist vs. title similarity. Default 0.4
        leans on the title because the DJ's list is title-led and many rows
        are compilations (`artist = 'Various'`), where the title carries the
        signal.

        `vinyl_only` restricts candidates to releases that include a vinyl
        format (`has_vinyl`). For a crate of records that's the right default —
        it removes CD/cassette pressings and cuts the number of tied pressings
        you have to disambiguate.

        Scoring blends two views and keeps the better one, so it's robust to how
        the row was written:

        - *structured* — artist-vs-artist and title-vs-title, blended by
          `artist_weight`. Best when the `"ARTIST - Title"` split is clean.
        - *combined* — the whole query against the catalog's
          ``artist || ' ' || title``. Rescues rows with no separator
          (``"noah pred navigation ep"``) where the split dumps everything into
          the title and the structured score collapses.
        """
        qa, qt = normalize(artist), normalize(title)
        # The combined query is just the normalized whole row; when there was no
        # separator `artist` is empty and this is exactly `normalize(title)`.
        qc = normalize(f"{artist} {title}")
        aw, tw = artist_weight, 1.0 - artist_weight
        fmt_filter = "AND has_vinyl" if vinyl_only else ""
        sql = f"""
        SELECT release_id, title, artist, year, country, fmt, genre, label,
               round(greatest(
                   {aw}*jaro_winkler_similarity(na, $qa)
                       + {tw}*jaro_winkler_similarity(nt, $qt),
                   jaro_winkler_similarity(nc, $qc)
               ), 4) AS score,
               round(jaro_winkler_similarity(na, $qa), 4) AS artist_score,
               round(jaro_winkler_similarity(nt, $qt), 4) AS title_score,
               round(jaro_winkler_similarity(nc, $qc), 4) AS combined_score
        FROM {self._from}
        WHERE nt <> '' {fmt_filter}
        ORDER BY score DESC
        LIMIT {int(k)}
        """
        return self.con.execute(sql, {"qa": qa, "qt": qt, "qc": qc}).df()

    def match_one(self, artist: str, title: str, **kw) -> dict:
        """Convenience: best candidate + an `ambiguous` flag.

        `ambiguous` is True when the runner-up is within 0.02 of the top
        score — i.e. the matcher can't confidently pick a single pressing and
        a human (or a year/country/format/catno filter) should decide.
        """
        cands = self.search(artist, title, **kw)
        if cands.empty:
            return {"matched": False, "input": (artist, title)}
        top = cands.iloc[0]
        ambiguous = len(cands) > 1 and (top.score - cands.iloc[1].score) < 0.02
        return {
            "matched": True,
            "input": (artist, title),
            "release_id": int(top.release_id),
            "score": float(top.score),
            "ambiguous": bool(ambiguous),
            "best": top.to_dict(),
            "candidates": cands,
        }
