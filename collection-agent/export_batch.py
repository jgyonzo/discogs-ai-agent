"""Export one batch's matches to a review CSV with Discogs URLs.

Usage: .venv/bin/python collection-agent/export_batch.py Lote-Feb
Writes collection-agent/data/<batch>_review.csv (gitignored).

Optionally reads hand-authored per-row review notes from
`data/review_notes.csv` (gitignored, batch-specific — not part of this tool).
That file, if present, has two columns:

    raw_input,note

`raw_input` is matched leniently (bidi marks / dash spacing / case are
ignored), so you can write the keys in plain ASCII. Any row whose `raw_input`
matches gets its `note` copied into the exported review CSV. Absent the file,
the `note` column is simply left blank.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

from matcher import Matcher, split_artist_title

HERE = Path(__file__).resolve().parent
PENDING = HERE / "data" / "pending_discogs.csv"
NOTES_FILE = HERE / "data" / "review_notes.csv"

# Bidi/zero-width marks Discogs exports leave around separators.
_BIDI = re.compile(r"[​‎‏﻿]")


def note_key(s: object) -> str:
    """Tolerant key for the notes lookup: strip invisible marks, normalize any
    dash variant to '-', collapse whitespace, lowercase. Lets the notes file be
    written in readable ASCII instead of pixel-matching bidi marks and
    en-dashes in the raw rows."""
    s = _BIDI.sub("", "" if s is None else str(s))
    s = re.sub(r"\s*[-–—]\s*", " - ", s)  # any dash variant -> ' - ', spacing-agnostic
    return re.sub(r"\s+", " ", s).strip().lower()


def load_notes() -> dict[str, str]:
    """Load optional per-row review notes, keyed by `note_key(raw_input)`.

    Returns an empty dict if `data/review_notes.csv` doesn't exist — the notes
    are batch-specific research, not part of the tool, so running without them
    is the normal case for anyone else.
    """
    if not NOTES_FILE.exists():
        return {}
    ndf = pd.read_csv(NOTES_FILE).fillna("")
    return {note_key(r["raw_input"]): str(r["note"]) for _, r in ndf.iterrows()}


def url(release_id) -> str:
    return f"https://www.discogs.com/release/{int(release_id)}" if release_id else ""


def main(batch: str, k: int = 5, vinyl_only: bool = True) -> None:
    df = pd.read_csv(PENDING)
    rows = df[df["batch"] == batch].reset_index(drop=True)
    if rows.empty:
        raise SystemExit(f"No rows for {batch!r}. Batches: {sorted(df['batch'].unique())}")

    notes = load_notes()
    m = Matcher(fast_index=True)
    out = []
    for raw in rows["title"]:
        artist, title = split_artist_title(raw)
        res = m.match_one(artist, title, k=k, vinyl_only=vinyl_only)
        rec = {
            "batch": batch,
            "raw_input": raw,
            "parsed_artist": artist,
            "parsed_title": title,
            "note": notes.get(note_key(raw), ""),
        }
        if not res["matched"]:
            rec.update(matched_artist="", matched_title="", year="", country="",
                       label="", format="", score=0.0, ambiguous="",
                       release_id="", discogs_url="", alt_release_ids="",
                       confirmed="")
            out.append(rec)
            continue
        b = res["best"]
        cands = res["candidates"]
        alts = cands["release_id"].iloc[1:].tolist()
        rec.update(
            matched_artist=b["artist"],
            matched_title=b["title"],
            year=b["year"],
            country=b["country"],
            label=b["label"],
            format=b["fmt"],
            score=res["score"],
            ambiguous=res["ambiguous"],
            release_id=int(b["release_id"]),
            discogs_url=url(b["release_id"]),
            alt_release_ids=" ".join(str(int(x)) for x in alts),
            confirmed="",  # for you to fill: y / n / corrected release_id
        )
        out.append(rec)

    cols = ["batch", "raw_input", "parsed_artist", "parsed_title",
            "matched_artist", "matched_title", "year", "country", "label",
            "format", "score", "ambiguous", "release_id", "discogs_url",
            "alt_release_ids", "confirmed", "note"]
    odf = pd.DataFrame(out)[cols]
    dest = HERE / "data" / f"{batch}_review.csv"
    odf.to_csv(dest, index=False)
    print(f"Wrote {len(odf)} rows -> {dest}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Lote-Feb")
