"""Multi-session experiment orchestrator.

Runs sessions sequentially, passing session IDs forward based on session_mode:
- isolated: fresh conversation each session, working directory unchanged
- chained: conversation resumes from previous session
- forked: reset working directory to fork point before each session
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path

import yaml

from harness.config import RunConfig, SessionMode
from harness.runner import SessionResult, run_session
from harness.shadow_git import ShadowGit
from harness.state import StateManager

logger = logging.getLogger(__name__)


async def run_experiment(config: RunConfig, output_base: Path | None = None) -> Path:
    """Run a complete multi-session experiment.

    Returns:
        Path to the run directory.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    model_slug = config.model.replace("/", "_").replace(":", "_")
    run_name = config.run_name or f"{timestamp}_{model_slug}"

    base = output_base or Path("runs")
    run_dir = base / run_name
    if run_dir.exists():
        raise FileExistsError(
            f"Run directory already exists: {run_dir}. "
            "Use a different --run-name or remove the existing directory."
        )
    run_dir.mkdir(parents=True)

    # Save frozen config
    with open(run_dir / "config.yaml", "w") as f:
        yaml.dump(config.model_dump(mode="json"), f, default_flow_style=False, sort_keys=False)

    # Initialize shadow git
    work_dir = Path(config.work_dir).resolve()
    shadow_git = ShadowGit(work_dir=work_dir, git_dir=run_dir / ".shadow_git")
    shadow_git.init()

    # Initialize state manager and seed memory file
    state = StateManager(work_dir=work_dir, shadow_git=shadow_git)
    state.seed_memory(config.memory_file, config.memory_seed)

    # Commit baseline (captures full working directory state)
    shadow_git.commit_baseline()

    # Run sessions
    results: list[SessionResult] = []
    # Track session_id by index for fork_from lookups
    session_ids: dict[int, str | None] = {}
    # Track how many sessions have forked from each fork point (for reset logic)
    fork_counts: dict[int | None, int] = {}

    for sc in sorted(config.sessions, key=lambda s: s.session_index):
        replicates = sc.count or 1

        for rep in range(1, replicates + 1):
            # Directory naming: _rNN suffix only when count > 1
            if replicates == 1:
                session_dir = run_dir / f"session_{sc.session_index:02d}"
            else:
                session_dir = run_dir / f"session_{sc.session_index:02d}_r{rep:02d}"

            # Determine resume behavior
            resume_id: str | None = None
            fork = False
            fork_from = sc.fork_from

            if fork_from is not None:
                # Explicit fork_from overrides session_mode
                resume_id = session_ids.get(fork_from)
                fork = True
                if not resume_id:
                    logger.warning(
                        "Cannot fork session %d from %d: no session_id available. "
                        "Running isolated.",
                        sc.session_index,
                        fork_from,
                    )
                    fork = False
            elif config.session_mode == SessionMode.CHAINED and results:
                resume_id = results[-1].session_id
                if resume_id is None:
                    logger.warning(
                        "Cannot chain session %d: previous session returned no session_id. "
                        "Falling back to isolated.",
                        sc.session_index,
                    )
            elif config.session_mode == SessionMode.FORKED and session_ids.get(1):
                resume_id = session_ids[1]
                fork = True

            # Determine if we need to reset the working directory.
            # Only needed for forked sessions when a sibling has already run
            # and modified the working directory since the fork point.
            effective_fork_from = fork_from
            if effective_fork_from is None and config.session_mode == SessionMode.FORKED:
                effective_fork_from = 1  # default fork point
            needs_reset = False
            if fork or config.session_mode == SessionMode.FORKED:
                fork_key = effective_fork_from
                fork_counts[fork_key] = fork_counts.get(fork_key, 0) + 1
                if fork_counts[fork_key] > 1 or rep > 1:
                    needs_reset = True

            shadow_git.begin_session(
                sc.session_index,
                config.session_mode,
                fork_from=effective_fork_from,
                needs_reset=needs_reset,
            )

            # Log
            mode_desc = config.session_mode.value
            resume_desc = f", resume={resume_id}" if resume_id else ""
            fork_desc = ", fork=True" if fork else ""
            rep_desc = f" r{rep}/{replicates}" if replicates > 1 else ""
            fork_from_desc = f", fork_from={fork_from}" if fork_from is not None else ""
            print(
                f"[session {sc.session_index}{rep_desc}] starting "
                f"(mode={mode_desc}{fork_from_desc}{resume_desc}{fork_desc})..."
            )

            try:
                result = await run_session(
                    session_config=sc,
                    run_config=config,
                    session_dir=session_dir,
                    state_manager=state,
                    resume_session_id=resume_id,
                    fork=fork,
                )
            except Exception as e:
                logger.exception("Session %d crashed", sc.session_index)
                result = SessionResult(
                    session_index=sc.session_index,
                    error=f"CRASHED: {e}",
                    started_at=datetime.now(timezone.utc).isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )

            # Finalize session in shadow git (commit + tag)
            replicate_num = rep if replicates > 1 else None
            shadow_git.end_session(sc.session_index, replicate=replicate_num)

            # Save session diff as artifact
            session_diff = shadow_git.get_session_diff(
                sc.session_index, config.session_mode, fork_from=fork_from
            )
            (session_dir / "session_diff.patch").write_text(session_diff or "# No changes\n")

            # Attach fork/replicate metadata
            result.fork_from = fork_from
            if replicates > 1:
                result.replicate = rep
                result.replicate_count = replicates

            results.append(result)

            # Store session_id from first replicate for downstream fork_from references
            if rep == 1 and result.session_id:
                session_ids[sc.session_index] = result.session_id

            status = "ERROR" if result.error else "done"
            cost_str = f", ${result.total_cost_usd:.4f}" if result.total_cost_usd is not None else ""
            compact_str = (
                f", {result.compaction_count} compactions" if result.compaction_count else ""
            )
            subagent_str = (
                f", {result.subagent_count} subagents" if result.subagent_count else ""
            )
            print(
                f"[session {sc.session_index}{rep_desc}] {status} -- "
                f"{result.step_count} steps, {result.tool_call_count} tool calls"
                f"{cost_str}{compact_str}{subagent_str}"
            )
            if result.error:
                print(f"  error: {result.error[:200]}")

    # Save full diff (baseline → final state)
    full_diff = shadow_git.diff_from_ref("baseline")
    (run_dir / "full_diff.patch").write_text(full_diff or "# No changes\n")

    # Save changelog
    state.save_changelog(run_dir / "state_changelog.jsonl")

    # Build run metadata
    meta = _build_run_meta(config, run_name, results, state)
    with open(run_dir / "run_meta.json", "w") as f:
        json.dump(meta, f, indent=2, default=str)

    # Revert working directory if requested
    if config.revert_work_dir:
        shadow_git.hard_reset_to("baseline")
        print("Reverted working directory to pre-run state.")

    print(f"\nRun complete: {run_dir}")
    return run_dir


def _build_run_meta(
    config: RunConfig,
    run_name: str,
    results: list[SessionResult],
    state: StateManager,
) -> dict:
    def _get_version(pkg: str) -> str | None:
        try:
            return pkg_version(pkg)
        except Exception:
            return None

    return {
        "run_name": run_name,
        "hypothesis": config.hypothesis,
        "model": config.model,
        "provider": config.provider,
        "sdk_version": _get_version("claude-agent-sdk"),
        "harness_version": _get_version("agentlens"),
        "session_mode": config.session_mode.value,
        "work_dir": config.work_dir,
        "repo_name": config.repo_name,
        "tags": config.tags,
        "session_count": len(results),
        "sessions": [
            {
                "session_index": r.session_index,
                "session_id": r.session_id,
                "resumed_from": r.resumed_from,
                "fork_from": r.fork_from,
                **({"replicate": r.replicate} if r.replicate is not None else {}),
                **({"replicate_count": r.replicate_count} if r.replicate_count is not None else {}),
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
            for r in results
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
