"""US4 organize: propose_moves (LLM tool) + execute_plan (runtime-only).

Two-phase, runtime-gated write path (contracts/agent-tools.md §4; FR-017..020):

    LLM  ──► propose_moves  (dry-run: resolve instances, live folder check,
                             WritePlan parked on the session)
    CLI  ──► renders the plan, prompts y/N at the terminal
    CLI  ──► execute_plan   (create folder if planned; per-move LIVE
                             re-validation; per-item results; snapshot patch)

`execute_plan` is deliberately NOT a ToolDef — it is invoked only by the CLI
after an interactive "y". An unconfirmed write is unreachable by
construction. All mutations go through the same rate-limited client.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from collection_agent.agent import AgentSession, ToolDef
from collection_agent.models import (
    PlannedMove,
    PlanState,
    TargetFolder,
    WritePlan,
)
from collection_agent.registry import fold
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore
from collection_agent.tools.common import load_for_serving, with_warnings
from collection_agent.tools.media import _resolve

ClientFactory = Callable[[], Any]


def _default_client_factory(settings: Settings) -> ClientFactory:
    def factory():
        from collection_agent.discogs.client import DiscogsClient

        return DiscogsClient(settings)

    return factory


class ProposeMovesArgs(BaseModel):
    record_refs: list[str] = Field(
        default_factory=list,
        description="Records to move: instance ids and/or name mentions. Empty "
        "with use_last_listing=true to move the previous listing.",
    )
    use_last_listing: bool = Field(
        default=False, description="Move the records from the last listing."
    )
    target_folder_name: str = Field(description="Destination folder name.")
    create_if_missing: bool = Field(
        default=False,
        description="Create the folder if it does not exist (after user confirmation).",
    )


def make_organize_tools(
    settings: Settings,
    store: SnapshotStore,
    client_factory: ClientFactory | None = None,
) -> list[ToolDef]:
    factory = client_factory or _default_client_factory(settings)

    def propose_moves(session: AgentSession, args: ProposeMovesArgs) -> dict[str, Any]:
        ctx = load_for_serving(store)
        if ctx.blocked:
            return ctx.blocked
        snapshot = ctx.snapshot

        records, not_found = _resolve(
            args.record_refs, args.use_last_listing, session, snapshot.records
        )
        if not records:
            return with_warnings(ctx, {
                "error": "no_records_resolved",
                "not_found": not_found,
                "detail": "None of the referenced records could be resolved in "
                "the collection — nothing to move.",
            })

        # live folder-name check (never trust the snapshot for writes)
        client = factory()
        try:
            live_folders = client.get_folders(snapshot.meta.username)
        finally:
            close = getattr(client, "close", None)
            if close:
                close()

        wanted = fold(args.target_folder_name)
        existing = next(
            (f for f in live_folders if fold(str(f["name"])) == wanted), None
        )
        notes: list[str] = []
        if existing is not None and int(existing["id"]) == 0:
            return with_warnings(ctx, {
                "error": "invalid_target_folder",
                "detail": '"All" (folder 0) is virtual and cannot receive records.',
            })
        if existing is not None:
            target = TargetFolder(
                folder_id=int(existing["id"]), name=str(existing["name"]), create=False
            )
            if args.create_if_missing:
                notes.append(
                    f'a folder named "{existing["name"]}" already exists — the plan '
                    "uses the existing folder instead of creating a duplicate"
                )
        else:
            if not args.create_if_missing:
                return with_warnings(ctx, {
                    "error": "folder_not_found",
                    "target_folder_name": args.target_folder_name,
                    "existing_folders": [str(f["name"]) for f in live_folders],
                    "detail": "No folder by that name. Ask the user whether to "
                    "create it (then call propose_moves with create_if_missing=true).",
                })
            target = TargetFolder(folder_id=None, name=args.target_folder_name, create=True)

        plan = WritePlan(
            target_folder=target,
            moves=[
                PlannedMove(
                    instance_id=r.instance_id,
                    release_id=r.release_id,
                    display=f"{', '.join(r.artists) or '?'} – {r.title}",
                    from_folder_id=r.folder_id,
                )
                for r in records
            ],
        )
        session.expire_pending_plan()
        session.pending_plan = plan

        payload: dict[str, Any] = {
            "plan_id": plan.plan_id,
            "target_folder": target.name + (" (will be created)" if target.create else ""),
            "moves": [m.display for m in plan.moves],
            "move_count": len(plan.moves),
            "requires_confirmation": True,
            "detail": "Plan prepared — NOT executed. The terminal will ask the "
            "user to confirm (y/N); tell them to confirm there. Never state "
            "the move already happened.",
        }
        if notes:
            payload["notes"] = notes
        if not_found:
            payload["not_found"] = not_found
        return with_warnings(ctx, payload)

    return [
        ToolDef(
            name="propose_moves",
            description="Prepare a plan to move records to a collection folder "
            "(existing, or created if create_if_missing). DRY-RUN ONLY: execution "
            "happens after the user confirms at the terminal prompt, outside this "
            "conversation.",
            params_model=ProposeMovesArgs,
            fn=propose_moves,
        )
    ]


# --- runtime-only execution (NOT a ToolDef; called by the CLI after "y") -------


def execute_plan(
    plan: WritePlan,
    settings: Settings,
    store: SnapshotStore,
    client_factory: ClientFactory | None = None,
) -> WritePlan:
    """Execute a CONFIRMED plan: create the folder if planned, live-revalidate
    each instance, move it, record per-item results (never aborting the rest —
    FR-020), then patch the snapshot. Returns the plan with results filled."""
    if plan.state != PlanState.CONFIRMED:
        raise ValueError(f"plan is {plan.state.value!r}; only a confirmed plan executes")

    factory = client_factory or _default_client_factory(settings)
    client = factory()
    try:
        snapshot = store.load()
        username = snapshot.meta.username if snapshot else None
        if username is None:
            username = client.get_identity()["username"]

        # target folder: create now if planned (re-checking collisions live)
        target = plan.target_folder
        if target.create:
            live = client.get_folders(username)
            hit = next(
                (f for f in live if fold(str(f["name"])) == fold(target.name)), None
            )
            if hit is not None:
                target.folder_id = int(hit["id"])
                target.create = False
            else:
                created = client.create_folder(username, target.name)
                target.folder_id = int(created["id"])
        assert target.folder_id is not None

        succeeded: list[tuple[int, int]] = []
        for move in plan.moves:
            try:
                live_instances = client.get_release_instances(username, move.release_id)
                live_hit = next(
                    (
                        inst
                        for inst in live_instances
                        if int(inst.get("instance_id", -1)) == move.instance_id
                    ),
                    None,
                )
                if live_hit is None:
                    move.result = "failed"
                    move.error = (
                        "instance no longer found in the collection (moved or "
                        "removed on Discogs since the last sync)"
                    )
                    continue
                current_folder = int(live_hit.get("folder_id", move.from_folder_id))
                if current_folder == target.folder_id:
                    move.result = "ok"
                    move.error = None  # already there — idempotent success
                    succeeded.append((move.instance_id, target.folder_id))
                    continue
                client.move_instance(
                    username,
                    current_folder,
                    move.release_id,
                    move.instance_id,
                    target.folder_id,
                )
                move.result = "ok"
                succeeded.append((move.instance_id, target.folder_id))
            except Exception as exc:  # per-item failure; keep going (FR-020)
                move.result = "failed"
                move.error = str(exc)

        # snapshot: patch successes in place (stays complete); nothing to do
        # for failures — they didn't change anything on Discogs.
        if succeeded:
            store.patch_moved_instances(
                succeeded,
                new_folder=(target.folder_id, target.name),
            )
        plan.state = PlanState.EXECUTED
        return plan
    finally:
        close = getattr(client, "close", None)
        if close:
            close()
