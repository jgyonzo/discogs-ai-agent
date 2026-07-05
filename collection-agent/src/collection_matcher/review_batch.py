"""Run one batch from pending_discogs.csv through the matcher and print a
review queue (worst-confidence first) plus the top candidates per row.

Usage (from collection-agent/): python -m collection_matcher.review_batch Lote-Feb
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from collection_matcher.matcher import Matcher, split_artist_title

# component root = collection-agent/ (this file lives in src/collection_matcher/)
COMPONENT_ROOT = Path(__file__).resolve().parents[2]
PENDING = COMPONENT_ROOT / "data" / "pending_discogs.csv"

pd.set_option("display.max_colwidth", 40)
pd.set_option("display.width", 200)


def main(batch: str, k: int = 5, vinyl_only: bool = True) -> None:
    df = pd.read_csv(PENDING)
    rows = df[df["batch"] == batch].reset_index(drop=True)
    if rows.empty:
        raise SystemExit(f"No rows for batch {batch!r}. "
                         f"Batches: {sorted(df['batch'].unique())}")

    m = Matcher(fast_index=True)
    results = []
    for raw_title in rows["title"]:
        artist, title = split_artist_title(raw_title)
        res = m.match_one(artist, title, k=k, vinyl_only=vinyl_only)
        if not res["matched"]:
            results.append({"raw": raw_title, "artist": artist, "title": title,
                            "score": 0.0, "ambiguous": True, "release_id": None,
                            "match": "(no candidates)", "candidates": None})
            continue
        b = res["best"]
        results.append({
            "raw": raw_title, "artist": artist, "title": title,
            "score": res["score"], "ambiguous": res["ambiguous"],
            "release_id": res["release_id"],
            "match": f"{b['artist']} - {b['title']} [{b['year']}, {b['country']}, {b['label']}]",
            "candidates": res["candidates"],
        })

    rdf = pd.DataFrame(results)
    n = len(rdf)
    hi = rdf[(rdf["score"] >= 0.95) & (~rdf["ambiguous"])]
    print(f"\n=== {batch}: {n} rows ===")
    print(f"High-confidence (score>=0.95 & unambiguous): {len(hi)}")
    print(f"Need review: {n - len(hi)}\n")

    review = rdf.sort_values(["ambiguous", "score"], ascending=[False, True])
    print("REVIEW QUEUE (worst first):")
    print(review[["score", "ambiguous", "raw", "match"]].to_string(index=False))


if __name__ == "__main__":
    batch = sys.argv[1] if len(sys.argv) > 1 else "Lote-Feb"
    main(batch)
