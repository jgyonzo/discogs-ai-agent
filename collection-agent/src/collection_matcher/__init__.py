"""collection_matcher — offline fuzzy matcher against the ETL-published DuckDB.

Moved mechanically from the collection-agent/ root (matcher.py,
review_batch.py, export_batch.py); behavior unchanged. Read-only and
offline: no Discogs API, no imports from etl/ or agent/, and no imports
from the sibling collection_agent package.
"""

from .matcher import Matcher, normalize, split_artist_title

__all__ = ["Matcher", "normalize", "split_artist_title"]
