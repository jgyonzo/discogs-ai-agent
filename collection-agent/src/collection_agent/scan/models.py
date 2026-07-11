"""Scan-domain models (022, data-model.md).

`ScanEvidence` is best-effort reading of a photo — never displayed as
fact, only used to drive search. `Candidate` fields are copied VERBATIM
from Discogs search results (FR-005; 019 discipline: nothing is ever
constructed or backfilled). `ScanCycleOutcome` is the journal line
(contracts/scan-journal-schema.md).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# FR-019 (addendum 1): a separator-stripped digit run this long is a
# barcode, never a catalog number
BARCODE_MIN_DIGITS = 10

EvidenceKind = Literal["barcode", "catno", "artist_title", "text"]
Outcome = Literal["added", "skipped", "no_match", "failed"]
Source = Literal["photo", "manual_search"]


class ScanEvidence(BaseModel):
    """Structured best-effort reading of one photo. All fields optional;
    all-None is a legal outcome (routes to no-match, FR-012)."""

    artist: str | None = None
    title: str | None = None
    label: str | None = None
    catno: str | None = None
    barcode: str | None = None
    # addendum 1: track titles as printed — searchable evidence (a 12"
    # single's lead track doubles as its release title), unlike `notes`
    tracks: list[str] = Field(default_factory=list)
    format_hints: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("barcode", mode="before")
    @classmethod
    def _normalize_barcode(cls, v: object) -> str | None:
        """Keep digits only; a 'barcode' with no digits is no barcode."""
        if v is None:
            return None
        digits = "".join(ch for ch in str(v) if ch.isdigit())
        return digits or None

    @field_validator("artist", "title", "label", "catno", "notes", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def _reclassify_barcode_in_catno(self) -> "ScanEvidence":
        """FR-019 (addendum 1, live finding F1): the vision step twice put
        barcode digits in `catno`. A 10+-digit run (after stripping
        spaces/hyphens/dots) can never match a catalog number — treat it
        as barcode evidence and clear the catno."""
        if self.catno:
            stripped = self.catno.translate(str.maketrans("", "", " -."))
            if stripped.isdigit() and len(stripped) >= BARCODE_MIN_DIGITS:
                if not self.barcode:
                    self.barcode = stripped
                self.catno = None
        return self

    @property
    def is_empty(self) -> bool:
        return not (
            self.artist
            or self.title
            or self.label
            or self.catno
            or self.barcode
            or self.tracks
        )

    def compact_dump(self) -> dict[str, object]:
        """Journal payload (FR-021): extracted values only, no None/empty."""
        return {
            k: v
            for k, v in self.model_dump().items()
            if v not in (None, "", [])
        }

    @property
    def evidence_kinds(self) -> list[EvidenceKind]:
        """Which search rungs this evidence can drive (FR-004 ladder order)."""
        kinds: list[EvidenceKind] = []
        if self.barcode:
            kinds.append("barcode")
        if self.catno:
            kinds.append("catno")
        if self.artist and self.title:
            kinds.append("artist_title")
        return kinds


class DuplicateStatus(BaseModel):
    """Computed locally from snapshot + session (FR-009/010); never guessed."""

    state: Literal["in_collection", "not_in_collection", "unknown"]
    copies: int = 0
    added_this_session: bool = False
    reason: str | None = None


class Candidate(BaseModel):
    """One release offered to the owner. Every display field verbatim from
    a Discogs search-result item; absent source keys stay None/[]."""

    release_id: int
    title: str
    year: str | None = None
    country: str | None = None
    formats: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    catno: str | None = None
    thumb_url: str | None = None
    discogs_uri: str | None = None
    # 024: verbatim from the search result's master_id; Discogs sends 0 for
    # master-less releases — normalized to None, never constructed
    master_id: int | None = None
    duplicate: DuplicateStatus


class ScanCycleOutcome(BaseModel):
    """One journal line (contracts/scan-journal-schema.md). Append-only."""

    ts: str
    seq: int
    scan_id: str
    outcome: Outcome
    source: Source
    evidence_kinds: list[str] = Field(default_factory=list)
    release_id: int | None = None
    release_title: str | None = None
    instance_id: int | None = None
    duplicate_add: bool = False
    detail: str | None = None
    # FR-021 (addendum 1): compact extracted evidence values (photo) or
    # {"q": ...} (manual search); never the image
    evidence: dict[str, object] | None = None


# -- API wire models (contracts/scan-api.md) ---------------------------------


class EvidenceSummary(BaseModel):
    kinds: list[str] = Field(default_factory=list)
    fields: dict[str, object] = Field(default_factory=dict)


class ScanResponse(BaseModel):
    scan_id: str
    source: Source
    evidence_summary: EvidenceSummary
    candidates: list[Candidate] = Field(default_factory=list)
    more_matches: bool = False
    message: str | None = None


class AddRequest(BaseModel):
    scan_id: str
    release_id: int
    confirm_duplicate: bool = False


class AddResponse(BaseModel):
    status: Literal["added", "needs_duplicate_confirmation", "rejected", "failed"]
    detail: str | None = None
    release_id: int | None = None
    instance_id: int | None = None
    duplicate: DuplicateStatus | None = None


class SkipRequest(BaseModel):
    scan_id: str
    release_id: int | None = None


class SessionResponse(BaseModel):
    session_id: str
    entries: list[ScanCycleOutcome] = Field(default_factory=list)
