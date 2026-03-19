"""Single session runner.

Executes one session via query(), maps messages through ATIFAdapter,
tracks file state, and saves outputs to the session directory.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

from harbor.models.trajectories import SubagentTrajectoryRef

from harness.atif_adapter import ATIFAdapter
from harness.config import RunConfig, SessionConfig, build_provider_env
from harness.proxy import CaptureProxy, get_target_url
from harness.state import StateManager
from harness.uuid_map import build_uuid_map

logger = logging.getLogger(__name__)

# Tool names that may modify files
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "Bash"}


@dataclass
class SessionResult:
    """Result metadata for a completed session."""

    session_index: int
    session_id: str | None = None
    step_count: int = 0
    tool_call_count: int = 0
    trajectory_path: Path | None = None
    resumed_from: str | None = None
    fork_from: int | None = None
    replicate: int | None = None
    replicate_count: int | None = None
    error: str | None = None
    started_at: str = ""
    finished_at: str = ""
    total_cost_usd: float | None = None
    num_turns: int = 0
    compaction_count: int = 0
    subagent_count: int = 0


def _copy_transcript(session_id: str, cwd: str, session_dir: Path) -> Path | None:
    """Copy the Claude Code transcript JSONL to the session output directory."""
    project_hash = "-" + cwd.lstrip("/").replace("/", "-").replace("_", "-")
    source = Path.home() / ".claude" / "projects" / project_hash / f"{session_id}.jsonl"
    if not source.exists():
        logger.warning("Transcript not found: %s", source)
        return None
    dest = session_dir / "transcript.jsonl"
    shutil.copy2(source, dest)
    logger.info("Copied transcript: %s", dest)
    return dest


async def run_session(
    session_config: SessionConfig,
    run_config: RunConfig,
    session_dir: Path,
    state_manager: StateManager,
    resume_session_id: str | None = None,
    fork: bool = False,
    prompt_override: str | AsyncIterable[dict[str, Any]] | None = None,
    cwd_override: str | None = None,
) -> SessionResult:
    """Run a single agent session and save outputs."""
    started_at = datetime.now(timezone.utc).isoformat()
    session_dir.mkdir(parents=True, exist_ok=True)

    # Resolve per-session overrides
    system_prompt = session_config.system_prompt or run_config.system_prompt
    max_turns = session_config.max_turns or run_config.max_turns

    # Inject working directory and memory file hint
    cwd = str(Path(cwd_override).resolve()) if cwd_override else str(Path(run_config.work_dir).resolve())
    memory_path = Path(cwd) / run_config.memory_file
    file_hint = (
        f"\n\nYour working directory is {cwd}\n"
        f"Use {memory_path} to keep notes across sessions.\n"
        f"IMPORTANT: Always use absolute paths when reading or writing files."
    )
    if system_prompt:
        system_prompt = system_prompt.rstrip() + file_hint
    else:
        system_prompt = file_hint.lstrip()

    # Build adapter
    capture_subagents = bool(run_config.agents) and run_config.capture_subagent_trajectories
    adapter = ATIFAdapter(
        agent_name="agentlens",
        agent_version="0.1.0",
        model_name=run_config.model,
        session_id=f"session_{session_config.session_index:02d}",
        capture_subagents=capture_subagents,
    )

    # Build ClaudeAgentOptions
    provider_env = build_provider_env(run_config)

    setting_sources = None
    if run_config.load_project_settings:
        setting_sources = ["user", "project"]

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=run_config.allowed_tools,
        max_turns=max_turns,
        permission_mode=run_config.permission_mode,
        cwd=cwd,
        model=run_config.model,
        cli_path=run_config.cli_path,
        env=provider_env,
        max_budget_usd=run_config.max_budget_usd,
        setting_sources=setting_sources,
    )

    # Build agents dict if configured
    if run_config.agents:
        agents_dict = {
            ac.name: AgentDefinition(
                description=ac.description,
                prompt=ac.prompt,
                tools=ac.tools,
                model=ac.model,
            )
            for ac in run_config.agents
        }
        options.agents = agents_dict
        # Ensure Agent tool is allowed
        if "Agent" not in run_config.allowed_tools:
            options.allowed_tools = [*run_config.allowed_tools, "Agent"]

    # Session mode handling
    if resume_session_id:
        options.resume = resume_session_id
        if fork:
            options.fork_session = True

    # Start capture proxy if configured
    proxy: CaptureProxy | None = None
    if run_config.capture_api_requests:
        target_url = get_target_url(run_config.provider, run_config.base_url)
        proxy = CaptureProxy(raw_dump_count=9999)
        port = await proxy.start(
            target_url, session_dir / "api_captures.jsonl"
        )
        provider_env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{port}"
        options.env = provider_env

    # Run the session
    session_id: str | None = None
    tool_call_count = 0
    error: str | None = None
    total_cost: float | None = None
    num_turns = 0

    try:
        prompt: str | AsyncIterable[dict[str, Any]] = (
            prompt_override if prompt_override is not None else session_config.prompt
        )
        async for message in query(prompt=prompt, options=options):
            step = adapter.process_message(
                message,
                extra={"session_index": session_config.session_index},
            )

            # Check for file writes after tool-using steps
            if step and step.tool_calls:
                if any(tc.function_name in WRITE_TOOLS for tc in step.tool_calls):
                    state_manager.check_for_writes(
                        session_config.session_index, step.step_id
                    )
                tool_call_count += len(step.tool_calls)

            # Extract session metadata from ResultMessage
            if isinstance(message, ResultMessage):
                session_id = message.session_id
                total_cost = message.total_cost_usd
                num_turns = message.num_turns
                if message.is_error:
                    error = message.result

    except Exception as e:
        logger.exception("Session %d failed", session_config.session_index)
        error = str(e)
    finally:
        if proxy:
            await proxy.stop()

    # Post-processing: trajectory, etc.
    # Wrapped so failures here don't kill the entire experiment.
    traj_path: Path | None = None
    step_count = 0
    subagent_count = 0

    try:
        # Final write check — catch writes from the last step
        state_manager.check_for_writes(
            session_config.session_index,
            adapter._step_counter or 1,
        )

        # Save subagent trajectories (before parent, so we can attach refs)
        if capture_subagents:
            sub_trajectories = adapter.build_subagent_trajectories()
            ref_map: dict[str, SubagentTrajectoryRef] = {}
            for tool_id, sub_traj in sub_trajectories.items():
                agent_name = adapter._subagent_names.get(tool_id, "unknown")
                safe_name = agent_name.replace("/", "_").replace(" ", "_")[:40]
                sub_filename = f"subagent_{safe_name}_{tool_id[:12]}.json"
                sub_path = session_dir / sub_filename
                with open(sub_path, "w") as f:
                    json.dump(sub_traj.to_json_dict(), f, indent=2)
                ref_map[tool_id] = SubagentTrajectoryRef(
                    session_id=sub_traj.session_id,
                    trajectory_path=sub_filename,
                    extra={"subagent_name": agent_name},
                )
                subagent_count += 1
                logger.info("Saved subagent trajectory: %s", sub_filename)
            # Attach refs to parent observation results
            if ref_map:
                adapter.attach_subagent_refs(ref_map)

        # Build and save trajectory
        trajectory = adapter.build_trajectory()
        step_count = len(trajectory.steps)
        traj_path = session_dir / "trajectory.json"
        with open(traj_path, "w") as f:
            json.dump(trajectory.to_json_dict(), f, indent=2)

        # Copy Claude Code transcript and build UUID map for replay support
        if session_id:
            _copy_transcript(session_id, cwd, session_dir)
            build_uuid_map(session_dir, session_config.session_index)

    except Exception as e:
        logger.exception(
            "Session %d post-processing failed", session_config.session_index
        )
        if error:
            error = f"{error}; post-processing: {e}"
        else:
            error = f"Post-processing failed: {e}"

    return SessionResult(
        session_index=session_config.session_index,
        session_id=session_id,
        step_count=step_count,
        tool_call_count=tool_call_count,
        trajectory_path=traj_path,
        resumed_from=resume_session_id,
        error=error,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        total_cost_usd=total_cost,
        num_turns=num_turns,
        compaction_count=len(adapter.compaction_events),
        subagent_count=subagent_count,
    )
