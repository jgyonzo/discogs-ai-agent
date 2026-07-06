"""Env-driven configuration (Constitution VII(a): no hardcoded runtime values).

Every model id, path, threshold, and identity string the runtime uses comes
from here — sourced from the environment / repo-root `.env` via
pydantic-settings. The Discogs token is a secret: it must never be logged,
echoed, or persisted to the snapshot.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# component root = collection-agent/ (this file lives in src/collection_agent/)
_COMPONENT_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _COMPONENT_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # repo-root .env is the project-standard secret location; a
        # component-local .env (if present) takes precedence.
        env_file=(str(_REPO_ROOT / ".env"), str(_COMPONENT_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Discogs ---
    discogs_user_token: SecretStr = Field(
        validation_alias=AliasChoices("DISCOGS_USER_TOKEN", "DISCOGS_TOKEN")
    )
    discogs_username: str | None = Field(default=None, alias="DISCOGS_USERNAME")
    user_agent: str = Field(
        default="DiscogsCollectionAgent/0.1 +https://github.com/jgyonzo/genai-pathway-final-project-yonzo",
        validation_alias=AliasChoices("COLLECTION_AGENT_USER_AGENT", "DISCOGS_USER_AGENT"),
    )
    discogs_base_url: str = Field(
        default="https://api.discogs.com", alias="DISCOGS_BASE_URL"
    )
    # human-facing site, not the API — release_page_url (019) builds
    # listing release_url fields from it
    discogs_web_base_url: str = Field(
        default="https://www.discogs.com", alias="DISCOGS_WEB_BASE_URL"
    )

    # --- YouTube play links (020) ---
    # human-facing site for tool-built play links (youtube_links.py builds
    # them); the agent never calls YouTube — it only emits URLs the user
    # opens in a browser
    youtube_web_base_url: str = Field(
        default="https://www.youtube.com", alias="YOUTUBE_WEB_BASE_URL"
    )
    # observed play-link capacity; requests above it are chunked
    youtube_playlist_max_ids: int = Field(
        default=50, alias="YOUTUBE_PLAYLIST_MAX_IDS"
    )

    # --- LLM ---
    collection_agent_model: str = Field(
        default="gpt-4o-mini", alias="COLLECTION_AGENT_MODEL"
    )
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")

    # --- Snapshot ---
    snapshot_path: Path = Field(
        default=_COMPONENT_ROOT / "data" / "snapshot.json", alias="SNAPSHOT_PATH"
    )

    # --- Rate limiting ---
    rate_limit_floor: int = Field(default=2, alias="RATE_LIMIT_FLOOR")

    # --- Rarity thresholds (research R9; surfaced in every rarity answer) ---
    rarity_max_for_sale: int = Field(default=2, alias="RARITY_MAX_FOR_SALE")
    rarity_want_have_ratio: float = Field(default=2.0, alias="RARITY_WANT_HAVE_RATIO")
    rarity_min_have: int = Field(default=10, alias="RARITY_MIN_HAVE")

    # --- Answer shaping ---
    filter_result_limit: int = Field(default=50, alias="FILTER_RESULT_LIMIT")


def load_settings() -> Settings:
    """Load settings; raises pydantic ValidationError if required vars missing."""
    return Settings()  # type: ignore[call-arg]
