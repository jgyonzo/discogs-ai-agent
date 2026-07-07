"""020 (agent-tools amendment delta 10): prompt ground rules for play
links — sourcing, honest saving, capability surface. Asserts on stable
phrases, not exact prose (018 test style)."""

from __future__ import annotations

from collection_agent.agent import render_system_prompt
from collection_agent.registry import build_registry


def prompt(settings) -> str:
    return render_system_prompt(build_registry(settings))


def test_play_links_sourced_only_from_playlist_links(settings):
    p = prompt(settings)
    assert "playlist_links" in p
    # play links join the release_url / media_links sourcing clause family
    assert "release_url" in p and "media_links" in p
    low = p.lower()
    assert "video ids" in low  # named as forbidden URL material
    assert "construct" in low or "build" in low  # the prohibition verb


def test_saving_is_honest_and_on_site(settings):
    low = " ".join(prompt(settings).lower().split())  # unwrap line breaks
    assert "save" in low and "site" in low
    assert "suggested_name" in prompt(settings) or "save_hint" in prompt(settings)
    # never claim account-side creation (T018 replay finding 2: the LLM
    # opened with "I've created multiple YouTube playlists")
    assert "never claim" in low
    assert "created" in low and "saved" in low
    assert "play links" in low and "never as playlists you created" in low


def test_capability_surface(settings):
    low = " ".join(prompt(settings).lower().split())  # unwrap line breaks
    # supported: playlist requests via play links (so "not supported" must
    # no longer blanket-name YouTube playlists)
    assert "youtube playlists), say it's not supported" not in low
    # unsupported: account-side saving/editing and YouTube search
    assert "youtube search" in low
    assert "saving or editing playlists" in low
    # no substitute-video offers for videoless records
    assert "substitute" in low


def test_replay_hardening_clauses(settings):
    """T018 replay findings 3–5 (second-account gpt-4o-mini drift): the
    model flipped to Spanish on an English question, chose first-mode
    unprompted, and dropped the skip report."""
    low = " ".join(prompt(settings).lower().split())
    # language: keyed to the user's most recent message; prompt Spanish ≠ signal
    assert "most recent message" in low
    assert "not a signal" in low
    # mode: all videos by default, first only on explicit request
    assert "explicitly" in low and "never choose it yourself" in low
    # skips: always reported with count and reason
    assert "always report" in low and "reason" in low


def test_attribute_block_still_registry_rendered(settings):
    """VII(b) analog: the playlist prompt edits added no schema prose."""
    p = prompt(settings)
    assert "{attribute_block}" not in p  # resolved
    assert "`genre`" in p  # registry content present, not hand-written
