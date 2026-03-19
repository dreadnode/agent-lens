"""Pydantic models for run configuration."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


__all__ = [
    "SessionMode",
    "SessionConfig",
    "AgentConfig",
    "RunConfig",
    "load_config",
    "build_provider_env",
]


class SessionMode(str, Enum):
    ISOLATED = "isolated"
    CHAINED = "chained"
    FORKED = "forked"


class SessionConfig(BaseModel):
    """Configuration for a single session within a run."""

    session_index: int = Field(ge=1)
    prompt: str
    system_prompt: str | None = None
    max_turns: int | None = None
    fork_from: int | None = None  # session index to fork from
    count: int = Field(default=1, ge=1)  # run this session N times (replicates)


class AgentConfig(BaseModel):
    """Definition of a subagent available to the main agent."""

    name: str
    description: str
    prompt: str
    tools: list[str] | None = None
    model: Literal["sonnet", "opus", "haiku", "inherit"] | None = None


class RunConfig(BaseModel):
    """Top-level run configuration."""

    # identity
    run_name: str | None = None
    hypothesis: str | None = None
    tags: list[str] = []

    # model
    model: str
    provider: str = "anthropic"
    base_url: str | None = None
    cli_path: str | None = None

    # working directory
    work_dir: str
    repo_name: str | None = None

    # sessions
    sessions: list[SessionConfig]
    session_mode: SessionMode = SessionMode.ISOLATED
    system_prompt: str | None = None

    # agent options
    allowed_tools: list[str] = Field(
        default=["Read", "Grep", "Glob", "Bash", "Write", "Edit"]
    )
    max_turns: int = 50
    permission_mode: str = "bypassPermissions"

    # memory file (auto-seeded in working directory)
    memory_file: str = "MEMORY.md"
    memory_seed: str = "# Notes\n"

    # subagents
    agents: list[AgentConfig] = []
    capture_subagent_trajectories: bool = True

    # capture (required for resampling turns)
    capture_api_requests: bool = True

    # budget
    max_budget_usd: float | None = None

    # settings
    load_project_settings: bool = False
    revert_work_dir: bool = False

    @model_validator(mode="after")
    def _validate_sessions(self) -> "RunConfig":
        indices = [s.session_index for s in self.sessions]
        if len(indices) != len(set(indices)):
            raise ValueError("Session indices must be unique.")
        if sorted(indices) != list(range(1, len(indices) + 1)):
            raise ValueError(
                "Session indices must be contiguous starting at 1. "
                f"Got: {sorted(indices)}"
            )
        # Validate fork_from references
        index_set = set(indices)
        for s in self.sessions:
            if s.fork_from is not None:
                if s.fork_from not in index_set:
                    raise ValueError(
                        f"Session {s.session_index} has fork_from={s.fork_from}, "
                        f"but no session with that index exists."
                    )
                if s.fork_from >= s.session_index:
                    raise ValueError(
                        f"Session {s.session_index} has fork_from={s.fork_from}, "
                        f"but fork_from must reference an earlier session."
                    )
        return self


def load_config(path: str | Path) -> RunConfig:
    """Load a RunConfig from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return RunConfig.model_validate(data)


def build_provider_env(config: RunConfig) -> dict[str, str]:
    """Build environment variable dict for ClaudeAgentOptions.env.

    Returns a dict — does NOT mutate os.environ.
    """
    env: dict[str, str] = {
        # Unset CLAUDECODE to allow launching from within a Claude Code session
        "CLAUDECODE": "",
    }

    if config.provider == "openrouter":
        env["ANTHROPIC_BASE_URL"] = config.base_url or "https://openrouter.ai/api"
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
    elif config.provider == "anthropic":
        pass  # SDK reads ANTHROPIC_API_KEY from process env
    elif config.provider == "bedrock":
        env["CLAUDE_CODE_USE_BEDROCK"] = "1"
    elif config.provider == "vertex":
        env["CLAUDE_CODE_USE_VERTEX"] = "1"

    return env
