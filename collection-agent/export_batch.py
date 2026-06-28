"""Export one batch's matches to a review CSV with Discogs URLs.

Usage: .venv/bin/python collection-agent/export_batch.py Lote-Feb
Writes collection-agent/data/<batch>_review.csv (gitignored).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from matcher import Matcher, split_artist_title

HERE = Path(__file__).resolve().parent
PENDING = HERE / "data" / "pending_discogs.csv"

# Hand-authored review notes for rows the matcher can't settle on its own,
# keyed by the exact raw_input string.
NOTES = {
    "Javonnete - People on earth":
        "Top auto-match (John Lemke) is WRONG. No Javonntte title 'People On "
        "Earth' exists; 'People Of Earth' is the label (PoEM). Likely "
        "Javonntte - Way Back, release 11393073 (PoEM 008, 2018).",
    "Album sampler - ":
        "Blank/unmatchable: no artist or title on the row. Need info off the "
        "sleeve/label to match.",
    "In Flagranti - Alpha blocker":
        "Only candidate is 'Additional Alpha Blocker' [2007, US]. No release "
        "titled exactly 'Alpha Blocker' - verify this is your record.",
    "Sleepwalker - Sleepwalker":
        "Matched 'Sleep Walker' (Japanese jazz-funk band) [2003, Japan]. "
        "Confirm that's the act you mean.",
    # --- Lote-57 ---
    "fetisch & me black palms":
        "CORRECT despite low score: real title is the full A/B side "
        "'Diskotecktonik / Black Palms'. Fetisch, release 1249243 "
        "[2008, Germany, Gigolo, vinyl].",
    "Mink - salmon ep":
        "No 'Mink' match. Closest title is Salmon - Salmon EP, release "
        "680602 [2006, Germany, Raum...musik] - artist differs, verify.",
    "alex under el encuentro":
        "No Alex Under release titled 'El Encuentro' in the catalog. "
        "Auto-match (Azul Terio) is wrong. Likely a track name or a "
        "pressing not in this dump.",
    "pacifics technics ep 1":
        "No 'Pacifics - Technics EP' in the catalog. Auto-match is wrong. "
        "Check the exact artist/label on the sleeve.",
    "pacifics technics ep 2":
        "No 'Pacifics - Technics EP' in the catalog. Auto-match is wrong. "
        "Check the exact artist/label on the sleeve.",
    "jichael mackson - fluff in the bellybutton":
        "No Jichael Mackson release titled 'Fluff In The Bellybutton'. "
        "Likely a track name - check which EP it's on (his catalog: Baff, "
        "Catch 22, Plex EP, etc.).",
}


def url(release_id) -> str:
    return f"https://www.discogs.com/release/{int(release_id)}" if release_id else ""


def main(batch: str, k: int = 5, vinyl_only: bool = True) -> None:
    df = pd.read_csv(PENDING)
    rows = df[df["batch"] == batch].reset_index(drop=True)
    if rows.empty:
        raise SystemExit(f"No rows for {batch!r}. Batches: {sorted(df['batch'].unique())}")

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
            note=NOTES.get(raw, ""),
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
