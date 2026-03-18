"""Tests for harness.atif_adapter — SDK message → ATIF step conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness.atif_adapter import ATIFAdapter


# ---------------------------------------------------------------------------
# Minimal SDK message stubs (avoid importing real SDK types in unit tests)
# ---------------------------------------------------------------------------

def _make_text_block(text: str):
    block = MagicMock()
    block.text = text
    # Make isinstance checks work via __class__
    block.__class__ = _get_class("TextBlock")
    return block


def _make_thinking_block(thinking: str, signature: str = "sig"):
    block = MagicMock()
    block.thinking = thinking
    block.signature = signature
    block.__class__ = _get_class("ThinkingBlock")
    return block


def _make_tool_use_block(id: str, name: str, input: dict):
    block = MagicMock()
    block.id = id
    block.name = name
    block.input = input
    block.__class__ = _get_class("ToolUseBlock")
    return block


def _make_tool_result_block(tool_use_id: str, content: str):
    block = MagicMock()
    block.tool_use_id = tool_use_id
    block.content = content
    block.__class__ = _get_class("ToolResultBlock")
    return block


def _make_assistant_msg(content: list, model: str = "claude-test", error: str | None = None, parent_tool_use_id: str | None = None):
    from claude_agent_sdk import AssistantMessage
    msg = MagicMock(spec=AssistantMessage)
    msg.content = content
    msg.model = model
    msg.error = error
    msg.parent_tool_use_id = parent_tool_use_id
    # Make isinstance checks work
    msg.__class__ = AssistantMessage
    return msg


def _make_user_msg(content: Any, tool_use_result=None, parent_tool_use_id: str | None = None, uuid: str | None = None):
    from claude_agent_sdk import UserMessage
    msg = MagicMock(spec=UserMessage)
    msg.content = content
    msg.tool_use_result = tool_use_result
    msg.parent_tool_use_id = parent_tool_use_id
    msg.uuid = uuid
    msg.__class__ = UserMessage
    return msg


def _make_system_msg(subtype: str = "", data: dict | None = None):
    from claude_agent_sdk import SystemMessage
    msg = MagicMock(spec=SystemMessage)
    msg.subtype = subtype
    msg.data = data or {}
    msg.__class__ = SystemMessage
    return msg


def _make_result_msg(session_id: str = "sess1", total_cost_usd: float = 0.01,
                     num_turns: int = 5, is_error: bool = False, result: str = "",
                     usage: dict | None = None):
    from claude_agent_sdk import ResultMessage
    msg = MagicMock(spec=ResultMessage)
    msg.session_id = session_id
    msg.total_cost_usd = total_cost_usd
    msg.num_turns = num_turns
    msg.is_error = is_error
    msg.result = result
    msg.usage = usage
    msg.__class__ = ResultMessage
    return msg


def _get_class(name: str):
    """Get the actual SDK class for isinstance checks."""
    import claude_agent_sdk as sdk
    return getattr(sdk, name)


def _make_adapter(**kwargs):
    defaults = {
        "agent_name": "test-harness",
        "agent_version": "0.1.0",
        "model_name": "claude-test",
        "session_id": "test_session",
    }
    defaults.update(kwargs)
    return ATIFAdapter(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAssistantMessage:
    def test_text_only(self):
        adapter = _make_adapter()
        msg = _make_assistant_msg([_make_text_block("Hello world")])
        step = adapter.process_message(msg)

        assert step is not None
        assert step.step_id == 1
        assert step.source == "agent"
        assert step.message == "Hello world"
        assert step.tool_calls is None

    def test_with_thinking(self):
        adapter = _make_adapter()
        msg = _make_assistant_msg([
            _make_thinking_block("Let me think..."),
            _make_text_block("Here's my answer"),
        ])
        step = adapter.process_message(msg)

        assert step.reasoning_content == "Let me think..."
        assert step.message == "Here's my answer"

    def test_with_tool_calls(self):
        adapter = _make_adapter()
        msg = _make_assistant_msg([
            _make_text_block("Let me read that file."),
            _make_tool_use_block("tc1", "Read", {"file_path": "/tmp/x.py"}),
        ])
        step = adapter.process_message(msg)

        assert step.tool_calls is not None
        assert len(step.tool_calls) == 1
        assert step.tool_calls[0].function_name == "Read"
        assert step.tool_calls[0].tool_call_id == "tc1"
        assert step.tool_calls[0].arguments == {"file_path": "/tmp/x.py"}

    def test_multiple_tool_calls(self):
        adapter = _make_adapter()
        msg = _make_assistant_msg([
            _make_tool_use_block("tc1", "Read", {"path": "a.py"}),
            _make_tool_use_block("tc2", "Glob", {"pattern": "*.py"}),
        ])
        step = adapter.process_message(msg)

        assert len(step.tool_calls) == 2

    def test_step_ids_sequential(self):
        adapter = _make_adapter()
        s1 = adapter.process_message(_make_assistant_msg([_make_text_block("one")]))
        s2 = adapter.process_message(_make_assistant_msg([_make_text_block("two")]))
        assert s1.step_id == 1
        assert s2.step_id == 2

    def test_model_in_extra(self):
        adapter = _make_adapter()
        step = adapter.process_message(
            _make_assistant_msg([_make_text_block("x")], model="claude-sonnet-4-20250514")
        )
        assert step.extra.get("sdk_model") == "claude-sonnet-4-20250514"


class TestUserMessage:
    def test_regular_user_message(self):
        adapter = _make_adapter()
        msg = _make_user_msg("What is this code?")
        step = adapter.process_message(msg)

        assert step is not None
        assert step.source == "user"
        assert step.message == "What is this code?"

    def test_tool_result_attaches_to_agent_step(self):
        adapter = _make_adapter()

        # Agent step with tool call
        agent_msg = _make_assistant_msg([
            _make_tool_use_block("tc1", "Read", {"file_path": "/tmp/x.py"}),
        ])
        agent_step = adapter.process_message(agent_msg)

        # Tool result message
        result_msg = _make_user_msg(
            content=[_make_tool_result_block("tc1", "file contents here")],
            tool_use_result={"content": "file contents here"},
            parent_tool_use_id="tc1",
        )
        returned = adapter.process_message(result_msg)

        # Should NOT create a new step
        assert returned is None
        # Should attach observation to the agent step
        assert agent_step.observation is not None
        assert len(agent_step.observation.results) == 1
        assert agent_step.observation.results[0].source_call_id == "tc1"
        assert "file contents" in agent_step.observation.results[0].content


class TestSystemMessage:
    def test_system_message_returns_none(self):
        adapter = _make_adapter()
        msg = _make_system_msg(subtype="init")
        step = adapter.process_message(msg)
        assert step is None

    def test_compaction_event_detected(self):
        adapter = _make_adapter()
        msg = _make_system_msg(subtype="compaction", data={"reason": "context limit"})
        adapter.process_message(msg)

        assert len(adapter.compaction_events) == 1
        assert adapter.compaction_events[0]["subtype"] == "compaction"


class TestResultMessage:
    def test_result_message_stores_metadata(self):
        adapter = _make_adapter()
        msg = _make_result_msg(
            session_id="sess1",
            total_cost_usd=0.05,
            usage={"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 200},
        )
        adapter.process_message(msg)

        traj = adapter.build_trajectory()
        assert traj.final_metrics.total_cost_usd == 0.05
        assert traj.final_metrics.total_prompt_tokens == 1000
        assert traj.final_metrics.total_completion_tokens == 500
        assert traj.final_metrics.total_cached_tokens == 200


class TestBuildTrajectory:
    def test_empty_trajectory_gets_placeholder(self):
        adapter = _make_adapter()
        traj = adapter.build_trajectory()
        assert len(traj.steps) == 1
        assert traj.steps[0].source == "system"

    def test_trajectory_has_agent_info(self):
        adapter = _make_adapter()
        adapter.process_message(_make_assistant_msg([_make_text_block("hi")]))
        traj = adapter.build_trajectory()

        assert traj.agent.name == "test-harness"
        assert traj.agent.version == "0.1.0"
        assert traj.schema_version == "ATIF-v1.6"
        assert traj.session_id == "test_session"

    def test_compaction_events_in_extra(self):
        adapter = _make_adapter()
        adapter.process_message(_make_assistant_msg([_make_text_block("hi")]))
        adapter.record_compaction_event("manual", "keep key info")

        traj = adapter.build_trajectory()
        assert traj.extra is not None
        assert "compaction_events" in traj.extra
        assert len(traj.extra["compaction_events"]) == 1


class TestSubagentTracking:
    def test_agent_tool_call_registers_subagent(self):
        adapter = _make_adapter(capture_subagents=True)

        msg = _make_assistant_msg([
            _make_tool_use_block("agent_tc1", "Agent", {"description": "explore code"}),
        ])
        adapter.process_message(msg)

        assert "agent_tc1" in adapter._subagent_tool_ids

    def test_subagent_messages_routed_to_child(self):
        adapter = _make_adapter(capture_subagents=True)

        # Parent creates Agent tool call
        agent_msg = _make_assistant_msg([
            _make_tool_use_block("agent_tc1", "Agent", {"description": "explore"}),
        ])
        adapter.process_message(agent_msg)

        # Subagent message (has parent_tool_use_id matching the Agent call)
        sub_msg = _make_assistant_msg(
            [_make_text_block("subagent working")],
            parent_tool_use_id="agent_tc1",
        )
        step = adapter.process_message(sub_msg)

        # Should NOT appear in parent
        assert step is None
        # Should appear in child adapter
        child = adapter._subagent_adapters["agent_tc1"]
        assert len(child.steps) == 1

    def test_build_subagent_trajectories(self):
        adapter = _make_adapter(capture_subagents=True)

        # Register subagent
        agent_msg = _make_assistant_msg([
            _make_tool_use_block("agent_tc1", "Agent", {"description": "explore"}),
        ])
        adapter.process_message(agent_msg)

        # Subagent does work
        sub_msg = _make_assistant_msg(
            [_make_text_block("found the file")],
            parent_tool_use_id="agent_tc1",
        )
        adapter.process_message(sub_msg)

        trajectories = adapter.build_subagent_trajectories()
        assert "agent_tc1" in trajectories
        traj = trajectories["agent_tc1"]
        assert len(traj.steps) == 1
        assert traj.extra["parent_session_id"] == "test_session"
