"""Tests for harness.config — validation, loading, provider env."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness.config import (
    AgentConfig,
    RunConfig,
    SessionConfig,
    SessionMode,
    build_provider_env,
    load_config,
)


# ---------------------------------------------------------------------------
# SessionConfig
# ---------------------------------------------------------------------------

class TestSessionConfig:
    def test_valid_session(self):
        sc = SessionConfig(session_index=1, prompt="Do something")
        assert sc.session_index == 1
        assert sc.count == 1

    def test_session_index_must_be_positive(self):
        with pytest.raises(ValidationError):
            SessionConfig(session_index=0, prompt="nope")

    def test_session_with_replicates(self):
        sc = SessionConfig(session_index=2, prompt="x", count=5)
        assert sc.count == 5

    def test_count_must_be_positive(self):
        with pytest.raises(ValidationError):
            SessionConfig(session_index=1, prompt="x", count=0)


# ---------------------------------------------------------------------------
# AgentConfig
# ---------------------------------------------------------------------------

class TestAgentConfig:
    def test_valid_agent(self):
        ac = AgentConfig(
            name="explorer",
            description="Explores code",
            prompt="You explore code.",
            tools=["Read", "Glob"],
            model="sonnet",
        )
        assert ac.name == "explorer"
        assert ac.tools == ["Read", "Glob"]

    def test_agent_no_tools(self):
        ac = AgentConfig(name="a", description="d", prompt="p")
        assert ac.tools is None
        assert ac.model is None


# ---------------------------------------------------------------------------
# RunConfig validation
# ---------------------------------------------------------------------------

def _minimal(**overrides) -> dict:
    """Build a minimal valid RunConfig dict."""
    base = {
        "model": "claude-sonnet-4-20250514",
        "work_dir": "./repos/test",
        "sessions": [{"session_index": 1, "prompt": "hello"}],
    }
    base.update(overrides)
    return base


class TestRunConfigValidation:
    def test_minimal_config(self):
        rc = RunConfig.model_validate(_minimal())
        assert rc.model == "claude-sonnet-4-20250514"
        assert rc.session_mode == SessionMode.ISOLATED
        assert rc.memory_file == "MEMORY.md"
        assert rc.memory_seed == "# Notes\n"

    def test_defaults(self):
        rc = RunConfig.model_validate(_minimal())
        assert rc.provider == "openrouter"
        assert rc.tags == []
        assert rc.max_turns == 50
        assert rc.permission_mode == "bypassPermissions"
        assert rc.capture_api_requests is True

    def test_duplicate_session_indices(self):
        with pytest.raises(ValidationError, match="unique"):
            RunConfig.model_validate(
                _minimal(
                    sessions=[
                        {"session_index": 1, "prompt": "a"},
                        {"session_index": 1, "prompt": "b"},
                    ]
                )
            )

    def test_non_contiguous_indices(self):
        with pytest.raises(ValidationError, match="contiguous"):
            RunConfig.model_validate(
                _minimal(
                    sessions=[
                        {"session_index": 1, "prompt": "a"},
                        {"session_index": 3, "prompt": "b"},
                    ]
                )
            )

    def test_valid_multi_session(self):
        rc = RunConfig.model_validate(
            _minimal(
                sessions=[
                    {"session_index": 1, "prompt": "a"},
                    {"session_index": 2, "prompt": "b"},
                    {"session_index": 3, "prompt": "c"},
                ]
            )
        )
        assert len(rc.sessions) == 3

    def test_fork_from_nonexistent_session(self):
        with pytest.raises(ValidationError, match="fork_from=5"):
            RunConfig.model_validate(
                _minimal(
                    sessions=[
                        {"session_index": 1, "prompt": "a"},
                        {"session_index": 2, "prompt": "b", "fork_from": 5},
                    ]
                )
            )

    def test_fork_from_later_session(self):
        with pytest.raises(ValidationError, match="earlier session"):
            RunConfig.model_validate(
                _minimal(
                    sessions=[
                        {"session_index": 1, "prompt": "a"},
                        {"session_index": 2, "prompt": "b", "fork_from": 2},
                    ]
                )
            )

    def test_valid_fork_from(self):
        rc = RunConfig.model_validate(
            _minimal(
                sessions=[
                    {"session_index": 1, "prompt": "a"},
                    {"session_index": 2, "prompt": "b", "fork_from": 1},
                ]
            )
        )
        assert rc.sessions[1].fork_from == 1

    def test_session_modes(self):
        for mode in ["isolated", "chained", "forked"]:
            rc = RunConfig.model_validate(_minimal(session_mode=mode))
            assert rc.session_mode.value == mode

    def test_with_agents(self):
        rc = RunConfig.model_validate(
            _minimal(
                agents=[
                    {
                        "name": "explorer",
                        "description": "Explores code",
                        "prompt": "You explore.",
                        "tools": ["Read"],
                    }
                ]
            )
        )
        assert len(rc.agents) == 1
        assert rc.agents[0].name == "explorer"


# ---------------------------------------------------------------------------
# load_config from YAML
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_load_from_yaml(self, tmp_path: Path):
        config_yaml = tmp_path / "test.yaml"
        config_yaml.write_text(
            textwrap.dedent("""\
            model: "claude-sonnet-4-20250514"
            work_dir: "./repos/test"
            session_mode: forked
            tags: ["test"]
            sessions:
              - session_index: 1
                prompt: "do task 1"
              - session_index: 2
                prompt: "do task 2"
                fork_from: 1
            """)
        )
        rc = load_config(config_yaml)
        assert rc.session_mode == SessionMode.FORKED
        assert rc.sessions[1].fork_from == 1

    def test_load_with_memory_seed(self, tmp_path: Path):
        config_yaml = tmp_path / "test.yaml"
        config_yaml.write_text(
            textwrap.dedent("""\
            model: "claude-sonnet-4-20250514"
            work_dir: "./repos/test"
            memory_seed: "# Custom Seed\\n"
            memory_file: "notes.md"
            sessions:
              - session_index: 1
                prompt: "hello"
            """)
        )
        rc = load_config(config_yaml)
        assert rc.memory_file == "notes.md"
        assert "Custom" in rc.memory_seed


# ---------------------------------------------------------------------------
# build_provider_env
# ---------------------------------------------------------------------------

class TestBuildProviderEnv:
    def test_openrouter_default(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key")
        rc = RunConfig.model_validate(_minimal(provider="openrouter"))
        env = build_provider_env(rc)
        assert env["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"
        assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-test-key"

    def test_openrouter_custom_base_url(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        rc = RunConfig.model_validate(
            _minimal(provider="openrouter", base_url="https://custom.api/v1")
        )
        env = build_provider_env(rc)
        assert env["ANTHROPIC_BASE_URL"] == "https://custom.api/v1"

    def test_anthropic_provider(self):
        rc = RunConfig.model_validate(_minimal(provider="anthropic"))
        env = build_provider_env(rc)
        assert "ANTHROPIC_BASE_URL" not in env

    def test_bedrock_provider(self):
        rc = RunConfig.model_validate(_minimal(provider="bedrock"))
        env = build_provider_env(rc)
        assert env["CLAUDE_CODE_USE_BEDROCK"] == "1"

    def test_vertex_provider(self):
        rc = RunConfig.model_validate(_minimal(provider="vertex"))
        env = build_provider_env(rc)
        assert env["CLAUDE_CODE_USE_VERTEX"] == "1"

    def test_claudecode_unset(self):
        """All providers should unset CLAUDECODE to allow nested launches."""
        for provider in ["openrouter", "anthropic", "bedrock", "vertex"]:
            rc = RunConfig.model_validate(_minimal(provider=provider))
            env = build_provider_env(rc)
            assert env["CLAUDECODE"] == ""
