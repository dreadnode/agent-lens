"""Re-run a forked session N times to study behavioral variance.

Reads the run's config and metadata, finds the fork point, and runs N new
replicates using the same session config. Each replicate runs in an isolated
git worktree, enabling parallel execution. Results are appended as new
session directories (session_NN_rNN) and run_meta.json is updated.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import typer

from harness.config import load_config, SessionConfig, RunConfig
from harness.runner import SessionResult, run_session
from harness.shadow_git import ShadowGit
from harness.state import StateManager

logger = logging.getLogger(__name__)


def _find_existing_replicates(run_dir: Path, session_index: int) -> list[int]:
    """Find existing replicate numbers for a session index."""
    nums: list[int] = []
    for d in run_dir.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        prefix = f"session_{session_index:02d}_r"
        if name.startswith(prefix):
            try:
                nums.append(int(name[len(prefix):]))
            except ValueError:
                pass
    return sorted(nums)


async def _run_single_replicate(
    rep: int,
    worktree_dir: Path,
    run_dir: Path,
    session_config: SessionConfig,
    config: RunConfig,
    session_index: int,
    resume_id: str | None,
    fork_from: int | None,
    count: int,
) -> tuple[Path, SessionResult]:
    """Run one session replicate in an isolated worktree.

    Returns (session_dir, result).
    """
    session_dir = run_dir / f"session_{session_index:02d}_r{rep:02d}"

    # Each replicate gets its own shadow git + state manager in the worktree
    replay_shadow_git = ShadowGit(
        work_dir=worktree_dir,
        git_dir=session_dir / ".shadow_git_tmp",
    )
    replay_shadow_git.init()
    replay_shadow_git.commit_baseline()

    state = StateManager(work_dir=worktree_dir, shadow_git=replay_shadow_git)

    try:
        result = await run_session(
            session_config=session_config,
            run_config=config,
            session_dir=session_dir,
            state_manager=state,
            resume_session_id=resume_id,
            fork=bool(resume_id),
            cwd_override=str(worktree_dir),
        )
    except Exception as e:
        logger.exception("Replicate %d crashed", rep)
        result = SessionResult(
            session_index=session_index,
            error=f"CRASHED: {e}",
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    # Save session diff
    session_diff = replay_shadow_git.diff_from_ref("baseline")
    (session_dir / "session_diff.patch").write_text(session_diff or "# No changes\n")

    # Save changelog for this replicate
    state.save_changelog(session_dir / "state_changelog.jsonl")

    # Clean up temp shadow git (the run's main shadow git has the canonical history)
    shutil.rmtree(session_dir / ".shadow_git_tmp", ignore_errors=True)

    result.fork_from = fork_from
    result.replicate = rep
    result.replicate_count = count

    return session_dir, result


async def run_resample_session(
    run_dir: Path,
    session_index: int,
    count: int,
) -> list[Path]:
    """Run N new replicates of a session and update run_meta.json.

    Each replicate runs in an isolated git worktree. When count > 1,
    replicates execute in parallel.

    Returns list of new session directories created.
    """
    # Load config
    config_path = run_dir / "config.yaml"
    if not config_path.exists():
        typer.echo(f"Error: No config.yaml in {run_dir}", err=True)
        raise typer.Exit(1)

    config = load_config(config_path)

    # Find the session config
    session_config = None
    for sc in config.sessions:
        if sc.session_index == session_index:
            session_config = sc
            break

    if session_config is None:
        typer.echo(f"Error: No session with index {session_index} in config", err=True)
        raise typer.Exit(1)

    # Load run_meta to find session_ids for fork_from
    meta_path = run_dir / "run_meta.json"
    if not meta_path.exists():
        typer.echo(f"Error: No run_meta.json in {run_dir}", err=True)
        raise typer.Exit(1)

    with open(meta_path) as f:
        meta = json.load(f)

    # Determine fork_from session_id and worktree reset tag
    fork_from = session_config.fork_from
    resume_id: str | None = None

    # Handle session_mode: forked (implicit fork from session 1)
    if fork_from is None and config.session_mode.value == "forked" and session_index > 1:
        fork_from = 1

    if fork_from is not None:
        for s in meta["sessions"]:
            if s["session_index"] == fork_from and s.get("session_id"):
                resume_id = s["session_id"]
                break
        if not resume_id:
            typer.echo(
                f"Error: Cannot find session_id for fork_from session {fork_from}",
                err=True,
            )
            raise typer.Exit(1)
    else:
        typer.echo(
            f"Warning: Session {session_index} has no fork_from. "
            "Running isolated replicates.",
            err=True,
        )

    # Worktree tag: use the fork point's end state, not baseline
    worktree_ref = f"session_{fork_from:02d}" if fork_from is not None else "baseline"

    # Find next replicate number
    existing = _find_existing_replicates(run_dir, session_index)
    plain_dir = run_dir / f"session_{session_index:02d}"
    if plain_dir.exists() and not existing:
        next_num = 2
    elif existing:
        next_num = max(existing) + 1
    else:
        next_num = 1

    # Source shadow git for worktree creation
    shadow_git_dir = run_dir / ".shadow_git"
    if not shadow_git_dir.exists():
        typer.echo(f"Error: No .shadow_git in {run_dir}. Cannot create worktrees.", err=True)
        raise typer.Exit(1)

    work_dir = Path(config.work_dir).resolve()
    source_shadow_git = ShadowGit(work_dir=work_dir, git_dir=shadow_git_dir)

    typer.echo(
        f"Resampling session {session_index} "
        f"({count} new replicates, starting at r{next_num:02d}"
        f"{f', forked from session {fork_from}' if fork_from else ''})..."
    )

    # Create worktrees for all replicates
    worktree_base = run_dir / "_worktrees" / f"resample_s{session_index}"
    worktree_base.mkdir(parents=True, exist_ok=True)
    worktree_paths: list[Path] = []

    try:
        for i in range(count):
            rep = next_num + i
            wt = worktree_base / f"rep_{rep:02d}"
            source_shadow_git.add_worktree(wt, worktree_ref)
            worktree_paths.append(wt)

        # Launch all replicates in parallel
        tasks = [
            _run_single_replicate(
                rep=next_num + i,
                worktree_dir=wt,
                run_dir=run_dir,
                session_config=session_config,
                config=config,
                session_index=session_index,
                resume_id=resume_id,
                fork_from=fork_from,
                count=count,
            )
            for i, wt in enumerate(worktree_paths)
        ]

        gather_results = await asyncio.gather(*tasks, return_exceptions=True)

    finally:
        # Clean up all worktrees
        for wt in worktree_paths:
            try:
                source_shadow_git.remove_worktree(wt)
            except Exception:
                logger.warning("Failed to remove worktree: %s", wt)
        shutil.rmtree(worktree_base, ignore_errors=True)
        # Clean up _worktrees parent if empty
        try:
            worktree_base.parent.rmdir()
        except OSError:
            pass  # not empty or already gone

    # Process results
    new_dirs: list[Path] = []
    new_results: list[SessionResult] = []

    for i, res in enumerate(gather_results):
        rep = next_num + i
        if isinstance(res, Exception):
            logger.error("Replicate %d failed: %s", rep, res)
            typer.echo(f"  Replicate {rep}... FAILED: {res}")
        else:
            session_dir, result = res
            new_dirs.append(session_dir)
            new_results.append(result)

            status = "ERROR" if result.error else "done"
            cost_str = f" ${result.total_cost_usd:.4f}" if result.total_cost_usd is not None else ""
            typer.echo(
                f"  Replicate {rep}... {status} ({result.step_count} steps, "
                f"{result.tool_call_count} tool calls{cost_str})"
            )

    # Update run_meta.json with new session entries
    for r in new_results:
        entry = {
            "session_index": r.session_index,
            "session_id": r.session_id,
            "resumed_from": r.resumed_from,
            "fork_from": r.fork_from,
            "replicate": r.replicate,
            "replicate_count": r.replicate_count,
            "step_count": r.step_count,
            "tool_call_count": r.tool_call_count,
            "num_turns": r.num_turns,
            "total_cost_usd": r.total_cost_usd,
            "compaction_count": r.compaction_count,
            "subagent_count": r.subagent_count,
            "error": r.error,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
        }
        meta["sessions"].append(entry)

    meta["session_count"] = len(meta["sessions"])

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, default=str)

    typer.echo(f"\n{len(new_dirs)} replicates added. Updated {meta_path}")
    return new_dirs
