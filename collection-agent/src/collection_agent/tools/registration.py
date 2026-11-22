"""Story-tool registration shared by the terminal and web runtimes (028).

Extracted verbatim from cli.py's 017-era `_register_story_tools` so the
`chat` REPL and the web chat agent register the IDENTICAL tool set
(agent-tools contract §1–§2; 028 amendment delta 13 only varies
`start_sync`, which is registered by each runtime, not here). Missing
modules are skipped so the base CLI stays usable mid-feature.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore


def register_story_tools(
    agent,
    settings: Settings,
    store: SnapshotStore,
    organize_client_factory: Callable[[], Any] | None = None,
) -> None:
    """`organize_client_factory` reaches ONLY `make_organize_tools` (its
    live folder check); None keeps 017's default live-client behavior."""
    try:
        from collection_agent.tools.analytics import make_analytics_tools

        for tool in make_analytics_tools(settings, store):
            agent.register(tool)
    except ImportError:
        pass
    try:
        from collection_agent.tools.browse import make_browse_tools

        for tool in make_browse_tools(settings, store):
            agent.register(tool)
    except ImportError:
        pass
    try:
        from collection_agent.tools.media import make_media_tools

        for tool in make_media_tools(settings, store):
            agent.register(tool)
    except ImportError:
        pass
    try:
        from collection_agent.tools.organize import make_organize_tools

        for tool in make_organize_tools(
            settings, store, client_factory=organize_client_factory
        ):
            agent.register(tool)
    except ImportError:
        pass
    try:
        from collection_agent.tools.playlist import make_playlist_tools

        for tool in make_playlist_tools(settings, store):
            agent.register(tool)
    except ImportError:
        pass
