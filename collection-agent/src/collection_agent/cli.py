"""CLI: chat / sync / status (contracts/agent-tools.md §6).

Exit codes: 0 success · 1 unexpected error · 2 configuration error
(missing/invalid token) · 3 sync ended partial.

The write-confirmation gate lives HERE, not in the LLM (§4): when a turn
leaves a pending WritePlan on the session, the REPL renders it and prompts
y/N itself; only an interactive "y" executes. `execute_plan` is not an LLM
tool, so unconfirmed writes are unreachable by construction.
"""

from __future__ import annotations

import argparse
import sys

from pydantic import ValidationError
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.table import Table

from collection_agent.models import Completeness, PlanState, SnapshotMeta
from collection_agent.settings import Settings, load_settings
from collection_agent.snapshot.store import SnapshotStore

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2
EXIT_PARTIAL = 3

console = Console()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="collection_agent",
        description="Conversational agent over your live Discogs collection.",
    )
    sub = parser.add_subparsers(dest="command")
    chat_p = sub.add_parser("chat", help="interactive conversation (default)")
    sync_p = sub.add_parser("sync", help="run/resume the collection sync")
    sync_p.add_argument("--full", action="store_true", help="re-enrich all releases")
    sub.add_parser("status", help="print snapshot state")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except ValidationError as exc:
        missing = ", ".join(str(e["loc"][0]) for e in exc.errors())
        console.print(
            f"[red]configuration error:[/red] missing/invalid env: {missing}. "
            "Set them in the repo-root .env (see collection-agent/README.md)."
        )
        return EXIT_CONFIG

    command = args.command or "chat"
    try:
        if command == "sync":
            return _cmd_sync(settings, full=args.full)
        if command == "status":
            return _cmd_status(settings)
        return _cmd_chat(settings)
    except KeyboardInterrupt:
        console.print("\n[dim]bye[/dim]")
        return EXIT_OK


# --- sync -----------------------------------------------------------------


def _run_sync_with_progress(settings: Settings, full: bool) -> SnapshotMeta:
    # imported lazily: keeps `status` cheap and tests patchable
    from collection_agent.discogs.client import DiscogsClient
    from collection_agent.snapshot.sync import run_sync

    store = SnapshotStore(settings.snapshot_path)
    client = DiscogsClient(settings, notify=lambda m: console.print(f"[yellow]{m}[/yellow]"))
    try:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            tasks: dict[str, int] = {}

            def on_progress(phase: str, done: int, total: int) -> None:
                if phase not in tasks:
                    tasks[phase] = progress.add_task(phase, total=total)
                progress.update(tasks[phase], completed=done, total=total)

            return run_sync(
                client,
                store,
                settings,
                full=full,
                on_progress=on_progress,
                notify=lambda m: console.print(f"[yellow]{m}[/yellow]"),
            )
    finally:
        client.close()


def _cmd_sync(settings: Settings, full: bool) -> int:
    from collection_agent.discogs.client import DiscogsAuthError

    try:
        meta = _run_sync_with_progress(settings, full)
    except DiscogsAuthError as exc:
        console.print(f"[red]{exc}[/red]")
        return EXIT_CONFIG
    _print_meta(meta)
    return EXIT_OK if meta.completeness == Completeness.COMPLETE else EXIT_PARTIAL


def _cmd_status(settings: Settings) -> int:
    store = SnapshotStore(settings.snapshot_path)
    snap = store.load()
    if snap is None:
        console.print("no snapshot — run: [bold]python -m collection_agent sync[/bold]")
        return EXIT_OK
    _print_meta(snap.meta)
    return EXIT_OK


def _print_meta(meta: SnapshotMeta) -> None:
    t = Table(show_header=False, box=None)
    t.add_row("user", meta.username)
    t.add_row("synced_at", meta.synced_at)
    t.add_row("completeness", meta.completeness.value)
    t.add_row("instances", str(meta.instance_count))
    t.add_row("unique releases", str(meta.unique_release_count))
    t.add_row("enriched", str(meta.enriched_count))
    v = meta.collection_value
    t.add_row("value (Discogs est.)", f"min {v.minimum} · median {v.median} · max {v.maximum}")
    if meta.sync_stats.warnings:
        t.add_row("warnings", "\n".join(meta.sync_stats.warnings[:10]))
    console.print(t)


# --- chat -------------------------------------------------------------------


def _build_agent(settings: Settings, store: SnapshotStore):
    from openai import OpenAI

    from collection_agent.agent import Agent
    from collection_agent.registry import build_registry
    from collection_agent.tools.base import make_base_tools

    registry = build_registry(settings)
    # the OpenAI SDK only reads os.environ; our key comes from the repo .env
    # via pydantic-settings, so pass it explicitly.
    agent = Agent(
        registry=registry,
        model=settings.collection_agent_model,
        llm_client=OpenAI(api_key=settings.openai_api_key.get_secret_value()),
    )
    for tool in make_base_tools(store, lambda full: _run_sync_with_progress(settings, full)):
        agent.register(tool)
    _register_story_tools(agent, settings, store)
    return agent


def _register_story_tools(agent, settings: Settings, store: SnapshotStore) -> None:
    """Register US1–US4 tools as their modules land (each module exposes
    make_tools(...)); missing modules are skipped so the base CLI stays usable
    mid-feature."""
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

        for tool in make_organize_tools(settings, store):
            agent.register(tool)
    except ImportError:
        pass
    try:
        from collection_agent.tools.playlist import make_playlist_tools

        for tool in make_playlist_tools(settings, store):
            agent.register(tool)
    except ImportError:
        pass


def _cmd_chat(settings: Settings) -> int:
    if settings.openai_api_key is None:
        console.print(
            "[red]configuration error:[/red] OPENAI_API_KEY is not set (needed for chat)."
        )
        return EXIT_CONFIG

    store = SnapshotStore(settings.snapshot_path)
    snap = store.load()
    if snap is None:
        console.print(
            "[bold]No collection snapshot yet.[/bold] A sync reads your whole "
            "collection from Discogs (minutes-scale, rate-limited)."
        )
        if _ask("Sync now? [y/N] "):
            code = _cmd_sync(settings, full=False)
            if code == EXIT_CONFIG:
                return code
    else:
        age = store.sync_age()
        hours = f"{age.total_seconds() / 3600:.1f}h ago" if age else "unknown"
        console.print(
            f"[dim]snapshot: {snap.meta.instance_count} records · "
            f"{snap.meta.completeness.value} · synced {hours} · "
            f"/refresh to re-sync · /status · /exit[/dim]"
        )

    agent = _build_agent(settings, store)
    console.print("[bold]Ask about your collection[/bold] (es/en):")

    while True:
        try:
            user_text = console.input("[bold cyan]> [/bold cyan]").strip()
        except EOFError:
            return EXIT_OK
        if not user_text:
            continue
        if user_text in ("/exit", "/quit"):
            return EXIT_OK
        if user_text == "/status":
            _cmd_status(settings)
            continue
        if user_text == "/refresh":
            _cmd_sync(settings, full=False)
            continue

        answer = agent.run_turn(user_text)
        # soft_wrap: never insert hard newlines — a wrapped play link (020
        # T018 replay finding) breaks terminal cmd+click URL detection at the
        # line break, silently truncating the playlist to the first line's ids
        console.print(answer, soft_wrap=True)
        _maybe_confirm_pending_plan(agent, settings, store)


def _maybe_confirm_pending_plan(agent, settings: Settings, store: SnapshotStore) -> None:
    """The runtime confirmation gate (FR-019). Renders the plan and prompts
    y/N at the terminal; only 'y' executes. Anything else cancels."""
    session = agent.session
    plan = session.pending_plan
    if plan is None or plan.state != PlanState.PROPOSED:
        return

    t = Table(title=f"Plan: move {len(plan.moves)} record(s)")
    t.add_column("record")
    t.add_column("to folder")
    target = plan.target_folder.name + (" (new)" if plan.target_folder.create else "")
    for m in plan.moves:
        t.add_row(m.display, target)
    console.print(t)

    if not _ask("¿Confirmás? / Confirm? [y/N] "):
        plan.state = PlanState.CANCELLED
        session.pending_plan = None
        console.print("[dim]cancelled — nothing sent to Discogs[/dim]")
        return

    plan.state = PlanState.CONFIRMED
    try:
        from collection_agent.tools.organize import execute_plan
    except ImportError:
        console.print("[red]write path not available in this build[/red]")
        session.pending_plan = None
        return

    results = execute_plan(plan, settings, store)
    session.pending_plan = None
    rt = Table(title="Result")
    rt.add_column("record")
    rt.add_column("outcome")
    for m in results.moves:
        outcome = "[green]ok[/green]" if m.result == "ok" else f"[red]failed[/red]: {m.error}"
        rt.add_row(m.display, outcome)
    console.print(rt)


def _ask(prompt: str) -> bool:
    try:
        return console.input(prompt).strip().lower() in ("y", "yes", "s", "si", "sí")
    except EOFError:
        return False


if __name__ == "__main__":
    sys.exit(main())
