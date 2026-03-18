"""Turn-level replay — branch a session from any API turn.

Truncates the Claude Code transcript at a given turn boundary, resets the
filesystem via git worktrees, and resumes the session through the SDK with the
original tool results injected as an AsyncIterable prompt.

Each replay becomes a new independent run directory with full provenance
back to the source run/session/turn. Multiple replicates run in parallel,
each in its own isolated worktree.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid as uuid_mod
from collections.abc import AsyncIterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
import yaml

from harness.config import RunConfig, SessionConfig, load_config
from harness.runner import SessionResult, run_session
from harness.shadow_git import ShadowGit
from harness.state import StateManager
from harness.transcript import (
    get_project_dir,
    list_turns,
    parse_turns,
    truncate_for_replay,
    write_truncated_transcript,
)

logger = logging.getLogger(__name__)


async def run_replay(
    source_run_dir: Path,
    session_index: int,
    turn_index: int,
    count: int = 1,
    prompt_override: str | None = None,
    continue_sessions: bool = False,
    output_base: Path = Path("runs"),
) -> list[Path]:
    """Run N replays of a session from a specific turn.

    Each replay runs in an isolated git worktree checked out from the source
    shadow git. When count > 1, replicates execute in parallel.

    Args:
        source_run_dir: Path to the original run directory
        session_index: Which session to replay from
        turn_index: Which API turn to replay from (1-based)
        count: Number of replay replicates
        prompt_override: Optional additional prompt after tool results
        continue_sessions: Run remaining sessions from config after replay
        output_base: Base directory for new run directories

    Returns:
        List of new run directory paths created.
    """
    # Load source config and metadata
    config = load_config(source_run_dir / "config.yaml")
    meta_path = source_run_dir / "run_meta.json"
    if not meta_path.exists():
        typer.echo(f"Error: No run_meta.json in {source_run_dir}", err=True)
        raise typer.Exit(1)

    with open(meta_path) as f:
        meta = json.load(f)

    # Find source session
    source_session_dir = _find_session_dir(source_run_dir, session_index)
    if not source_session_dir:
        typer.echo(f"Error: No session {session_index} directory in {source_run_dir}", err=True)
        raise typer.Exit(1)

    # Find source session_id from metadata
    source_session_id = None
    for s in meta.get("sessions", []):
        if s["session_index"] == session_index and s.get("session_id"):
            source_session_id = s["session_id"]
            break

    if not source_session_id:
        typer.echo(f"Error: No session_id found for session {session_index}", err=True)
        raise typer.Exit(1)

    # Validate transcript exists
    transcript_path = source_session_dir / "transcript.jsonl"
    if not transcript_path.exists():
        typer.echo(
            f"Error: No transcript.jsonl in {source_session_dir}. "
            "Re-run the experiment with a newer harness version to capture transcripts.",
            err=True,
        )
        raise typer.Exit(1)

    # Parse and validate turn_index
    preamble, turns = parse_turns(transcript_path)
    if turn_index < 1 or turn_index > len(turns):
        typer.echo(
            f"Error: turn_index {turn_index} out of range (1..{len(turns)})",
            err=True,
        )
        raise typer.Exit(1)

    # Load uuid_map for shadow git tag lookup
    uuid_map = None
    uuid_map_path = source_session_dir / "uuid_map.json"
    if uuid_map_path.exists():
        with open(uuid_map_path) as f:
            uuid_map = json.load(f)

    # Determine filesystem reset tag
    reset_tag = _determine_reset_tag(uuid_map, turn_index, session_index)

    # Find session config
    session_config = None
    for sc in config.sessions:
        if sc.session_index == session_index:
            session_config = sc
            break
    if not session_config:
        typer.echo(f"Error: No session config for index {session_index}", err=True)
        raise typer.Exit(1)

    # Source shadow git for worktree creation
    source_shadow_git_dir = source_run_dir / ".shadow_git"
    if not source_shadow_git_dir.exists():
        typer.echo(
            f"Error: No .shadow_git in {source_run_dir}. Cannot reset filesystem.",
            err=True,
        )
        raise typer.Exit(1)
    source_shadow_git = ShadowGit(
        work_dir=Path(config.work_dir).resolve(),
        git_dir=source_shadow_git_dir,
    )

    # Truncate transcript (same for all replicates)
    truncated_entries, tool_result_entries = truncate_for_replay(
        transcript_path, turn_index
    )

    source_name = source_run_dir.name
    typer.echo(
        f"Replaying session {session_index} from turn {turn_index} "
        f"({count} replicate{'s' if count > 1 else ''}, "
        f"reset to {reset_tag})..."
    )

    # Create worktrees for all replicates
    worktree_base = output_base / "_worktrees" / f"replay_{source_name}_s{session_index}_t{turn_index}"
    worktree_base.mkdir(parents=True, exist_ok=True)
    worktree_paths: list[Path] = []

    try:
        for rep in range(1, count + 1):
            wt = worktree_base / f"rep_{rep:02d}"
            source_shadow_git.add_worktree(wt, reset_tag)
            worktree_paths.append(wt)

        # Launch all replicates (parallel when count > 1)
        tasks = [
            _run_single_replicate(
                rep=rep,
                worktree_dir=wt,
                source_run_dir=source_run_dir,
                source_name=source_name,
                config=config,
                session_config=session_config,
                session_index=session_index,
                turn_index=turn_index,
                count=count,
                truncated_entries=truncated_entries,
                tool_result_entries=tool_result_entries,
                source_session_id=source_session_id,
                prompt_override=prompt_override,
                output_base=output_base,
                reset_tag=reset_tag,
                continue_sessions=continue_sessions,
            )
            for rep, wt in zip(range(1, count + 1), worktree_paths)
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
    for rep, res in enumerate(gather_results, 1):
        if isinstance(res, Exception):
            logger.error("Replicate %d failed: %s", rep, res)
            typer.echo(f"  Replicate r{rep}/{count}... FAILED: {res}")
        else:
            replay_run_dir, result, cleanup_path = res
            new_dirs.append(replay_run_dir)

            # Clean up truncated transcript
            try:
                cleanup_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to clean up: %s", cleanup_path)

            status = "ERROR" if result.error else "done"
            cost_str = f" ${result.total_cost_usd:.4f}" if result.total_cost_usd is not None else ""
            rep_desc = f" r{rep}/{count}" if count > 1 else ""
            typer.echo(
                f"  Replicate{rep_desc}... {status} ({result.step_count} steps, "
                f"{result.tool_call_count} tool calls{cost_str})"
            )

    typer.echo(f"\n{len(new_dirs)} replay run(s) created.")
    for d in new_dirs:
        typer.echo(f"  {d}")

    return new_dirs


async def _run_single_replicate(
    rep: int,
    worktree_dir: Path,
    source_run_dir: Path,
    source_name: str,
    config: RunConfig,
    session_config: SessionConfig,
    session_index: int,
    turn_index: int,
    count: int,
    truncated_entries: list[dict],
    tool_result_entries: list[dict],
    source_session_id: str,
    prompt_override: str | None,
    output_base: Path,
    reset_tag: str,
    continue_sessions: bool,
) -> tuple[Path, SessionResult, Path]:
    """Run one replay replicate in an isolated worktree.

    Returns (replay_run_dir, result, cleanup_path).
    """
    # Generate new session ID
    new_session_id = str(uuid_mod.uuid4())

    # Create run directory
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    run_name = f"replay_{source_name}_s{session_index}_t{turn_index}_r{rep:02d}_{timestamp}"
    replay_run_dir = output_base / run_name
    replay_run_dir.mkdir(parents=True)

    # Write truncated transcript to Claude's project dir for the worktree path
    # (SDK computes project hash from cwd, which is the worktree, not original work_dir)
    worktree_project_dir = get_project_dir(str(worktree_dir.resolve()))
    truncated_path = write_truncated_transcript(
        truncated_entries, new_session_id, worktree_project_dir
    )

    # Save a copy in the replay run for reference
    replay_session_dir = replay_run_dir / f"session_{session_index:02d}"
    replay_session_dir.mkdir(parents=True)
    _save_truncated_copy(truncated_entries, replay_session_dir / "source_transcript_truncated.jsonl")

    # Init fresh shadow git for the replay run, pointed at the worktree
    replay_shadow_git = ShadowGit(
        work_dir=worktree_dir,
        git_dir=replay_run_dir / ".shadow_git",
    )
    replay_shadow_git.init()
    replay_shadow_git.commit_baseline()

    state = StateManager(work_dir=worktree_dir, shadow_git=replay_shadow_git)

    # Build AsyncIterable prompt
    prompt: str | AsyncIterable[dict[str, Any]]
    if turn_index == 1:
        # Replay from scratch — use original prompt, optionally with override appended
        if prompt_override:
            prompt = f"{session_config.prompt}\n\n{prompt_override}"
        else:
            prompt = session_config.prompt
        resume_id = None
    else:
        prompt = _build_replay_prompt(tool_result_entries, prompt_override)
        resume_id = new_session_id

    try:
        result = await run_session(
            session_config=session_config,
            run_config=config,
            session_dir=replay_session_dir,
            state_manager=state,
            resume_session_id=resume_id,
            fork=True,
            prompt_override=prompt,
            cwd_override=str(worktree_dir),
        )
    except Exception as e:
        logger.exception("Replay replicate %d crashed", rep)
        result = SessionResult(
            session_index=session_index,
            error=f"CRASHED: {e}",
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    # Finalize replayed session in shadow git
    replay_shadow_git.end_session(session_index)

    # Save diff for replayed session (relative to replay baseline)
    first_session_diff = replay_shadow_git.diff_from_ref("baseline")
    (replay_session_dir / "session_diff.patch").write_text(first_session_diff or "# No changes\n")

    # Optionally continue with remaining sessions from config
    results: list[SessionResult] = [result]
    session_ids: dict[int, str | None] = {session_index: result.session_id}

    if continue_sessions:
        for sc in sorted(config.sessions, key=lambda s: s.session_index):
            if sc.session_index <= session_index:
                continue

            replicates = sc.count or 1
            for rep_idx in range(1, replicates + 1):
                if replicates == 1:
                    next_session_dir = replay_run_dir / f"session_{sc.session_index:02d}"
                else:
                    next_session_dir = replay_run_dir / f"session_{sc.session_index:02d}_r{rep_idx:02d}"

                # Determine resume behavior (same logic as run_experiment)
                resume_id: str | None = None
                fork = False
                fork_from = sc.fork_from

                if fork_from is not None:
                    resume_id = session_ids.get(fork_from)
                    fork = True
                    if not resume_id:
                        logger.warning(
                            "Cannot fork session %d from %d during replay: no session_id available. Running isolated.",
                            sc.session_index,
                            fork_from,
                        )
                        fork = False
                elif config.session_mode.value == "chained" and results:
                    resume_id = results[-1].session_id
                    if resume_id is None:
                        logger.warning(
                            "Cannot chain session %d during replay: previous session has no session_id. Running isolated.",
                            sc.session_index,
                        )
                elif config.session_mode.value == "forked" and session_ids.get(1):
                    resume_id = session_ids[1]
                    fork = True

                # Determine if working dir reset is needed for this fork.
                # In replay context, we always reset for forked sessions because
                # the replayed session (or prior continuation sessions) will have
                # mutated the worktree since the fork point's clean state.
                effective_fork_from = fork_from
                if effective_fork_from is None and config.session_mode.value == "forked":
                    effective_fork_from = 1
                needs_reset = False
                if fork or config.session_mode.value == "forked":
                    needs_reset = True

                replay_shadow_git.begin_session(
                    sc.session_index,
                    config.session_mode,
                    fork_from=effective_fork_from,
                    needs_reset=needs_reset,
                )

                try:
                    next_result = await run_session(
                        session_config=sc,
                        run_config=config,
                        session_dir=next_session_dir,
                        state_manager=state,
                        resume_session_id=resume_id,
                        fork=fork,
                        cwd_override=str(worktree_dir),
                    )
                except Exception as e:
                    logger.exception("Replay continuation session %d crashed", sc.session_index)
                    next_result = SessionResult(
                        session_index=sc.session_index,
                        error=f"CRASHED: {e}",
                        started_at=datetime.now(timezone.utc).isoformat(),
                        finished_at=datetime.now(timezone.utc).isoformat(),
                    )

                replicate_num = rep_idx if replicates > 1 else None
                replay_shadow_git.end_session(sc.session_index, replicate=replicate_num)

                next_diff = replay_shadow_git.get_session_diff(
                    sc.session_index,
                    config.session_mode,
                    fork_from=fork_from,
                )
                (next_session_dir / "session_diff.patch").write_text(next_diff or "# No changes\n")

                next_result.fork_from = fork_from
                if replicates > 1:
                    next_result.replicate = rep_idx
                    next_result.replicate_count = replicates
                results.append(next_result)

                if rep_idx == 1 and next_result.session_id:
                    session_ids[sc.session_index] = next_result.session_id

    # Save aggregate replay artifacts
    full_diff = replay_shadow_git.diff_from_ref("baseline")
    (replay_run_dir / "full_diff.patch").write_text(full_diff or "# No changes\n")
    state.save_changelog(replay_run_dir / "state_changelog.jsonl")

    # Save replay metadata
    replay_meta = {
        "source_run": source_name,
        "source_run_dir": str(source_run_dir.resolve()),
        "source_session_index": session_index,
        "source_session_id": source_session_id,
        "replay_turn_index": turn_index,
        "replay_count": count,
        "replay_number": rep,
        "prompt_override": prompt_override,
        "new_session_id": new_session_id,
        "shadow_git_reset_tag": reset_tag,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(replay_run_dir / "replay_meta.json", "w") as f:
        json.dump(replay_meta, f, indent=2)

    # Save run_meta.json
    run_meta = {
        "run_name": run_name,
        "model": config.model,
        "provider": config.provider,
        "session_mode": config.session_mode.value,
        "work_dir": config.work_dir,
        "tags": [*config.tags, "replay"],
        "replay_source": source_name,
        "replay_turn": turn_index,
        "session_count": len(results),
        "sessions": [
            {
                "session_index": result.session_index,
                "session_id": result.session_id,
                "resumed_from": result.resumed_from,
                "replay_source": source_name,
                "replay_turn": turn_index,
                "step_count": result.step_count,
                "tool_call_count": result.tool_call_count,
                "num_turns": result.num_turns,
                "total_cost_usd": result.total_cost_usd,
                "compaction_count": result.compaction_count,
                "subagent_count": result.subagent_count,
                "error": result.error,
                "started_at": result.started_at,
                "finished_at": result.finished_at,
            }
            for result in results
        ],
        "started_at": results[0].started_at if results else None,
        "finished_at": results[-1].finished_at if results else None,
        "total_steps": sum(r.step_count for r in results),
        "total_tool_calls": sum(r.tool_call_count for r in results),
        "total_cost_usd": (
            sum(r.total_cost_usd for r in results if r.total_cost_usd is not None)
            if any(r.total_cost_usd is not None for r in results)
            else None
        ),
        "total_file_writes": len(state.write_log),
        "total_compaction_events": sum(r.compaction_count for r in results),
        "total_subagent_invocations": sum(r.subagent_count for r in results),
        "errors": [r.error for r in results if r.error],
    }
    with open(replay_run_dir / "run_meta.json", "w") as f:
        json.dump(run_meta, f, indent=2, default=str)

    # Save frozen config
    with open(replay_run_dir / "config.yaml", "w") as f:
        yaml.dump(
            config.model_dump(mode="json"),
            f,
            default_flow_style=False,
            sort_keys=False,
        )

    return replay_run_dir, result, truncated_path


def _find_session_dir(run_dir: Path, session_index: int) -> Path | None:
    """Find the session directory, handling replicates."""
    # Try plain directory first
    plain = run_dir / f"session_{session_index:02d}"
    if plain.exists():
        return plain
    # Try first replicate
    r01 = run_dir / f"session_{session_index:02d}_r01"
    if r01.exists():
        return r01
    return None


def _determine_reset_tag(
    uuid_map: dict | None,
    turn_index: int,
    session_index: int = 1,
) -> str:
    """Find the shadow git tag to reset to for replaying from a given turn.

    Walks backwards from turn N-1 to find the most recent turn with a
    shadow git tag (i.e., a turn that produced file writes).

    For sessions > 1, falls back to the prior session's end-state tag
    instead of baseline, since prior sessions may have modified files.
    """
    if turn_index <= 1:
        if session_index > 1:
            return f"session_{session_index - 1:02d}"
        return "baseline"

    if not uuid_map:
        if session_index > 1:
            return f"session_{session_index - 1:02d}"
        return "baseline"

    turns = uuid_map.get("turns", [])
    # Look for shadow git tags in turns up to N-1
    for t in reversed(turns[: turn_index - 1]):
        tag = t.get("shadow_git_tag")
        if tag:
            return tag

    # No file writes in this session before the target turn —
    # fall back to prior session's end state or baseline
    if session_index > 1:
        return f"session_{session_index - 1:02d}"
    return "baseline"


async def _replay_prompt_generator(
    tool_result_entries: list[dict],
    prompt_override: str | None = None,
) -> AsyncIterable[dict[str, Any]]:
    """AsyncIterable that yields tool_result messages and optional extra prompt."""
    # Yield original tool results
    for entry in tool_result_entries:
        msg = entry.get("message", {})
        yield {
            "type": "user",
            "session_id": "",
            "message": msg,
            "parent_tool_use_id": None,
        }

    # Yield additional user prompt if provided
    if prompt_override:
        yield {
            "type": "user",
            "session_id": "",
            "message": {"role": "user", "content": prompt_override},
            "parent_tool_use_id": None,
        }


def _build_replay_prompt(
    tool_result_entries: list[dict],
    prompt_override: str | None = None,
) -> AsyncIterable[dict[str, Any]]:
    """Build an AsyncIterable prompt for replay."""
    return _replay_prompt_generator(tool_result_entries, prompt_override)


def _save_truncated_copy(entries: list[dict], dest: Path) -> None:
    """Save a copy of truncated entries for reference."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
