"""SDK message -> ATIF Step mapping.

Core responsibility: convert a stream of claude_agent_sdk Message objects
into a list of harbor ATIF Steps, maintaining correct step_id sequencing,
tool_call/observation pairing, and agent-only field constraints.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from harbor.models.trajectories import (
    Agent,
    FinalMetrics,
    Observation,
    ObservationResult,
    Step,
    SubagentTrajectoryRef,
    ToolCall,
    Trajectory,
)

logger = logging.getLogger(__name__)


class ATIFAdapter:
    """Converts a stream of SDK messages into an ATIF Trajectory.

    Usage:
        adapter = ATIFAdapter(...)
        async for msg in query(prompt=..., options=...):
            adapter.process_message(msg)
        trajectory = adapter.build_trajectory()

    Key invariants:
    - step_ids are sequential from 1
    - Tool result UserMessages attach as Observation on the previous agent
      step, NOT as new steps
    - agent-only fields never appear on source="user" steps
    - message field is always a non-None string
    """

    def __init__(
        self,
        agent_name: str,
        agent_version: str,
        model_name: str,
        session_id: str,
        capture_subagents: bool = False,
    ):
        self.steps: list[Step] = []
        self._step_counter = 0
        self._agent_info = Agent(
            name=agent_name,
            version=agent_version,
            model_name=model_name,
        )
        self._session_id = session_id

        # Map tool_call_id -> step index for correct observation attachment
        self._tool_call_to_step: dict[str, int] = {}

        # Accumulated data from ResultMessage
        self._result_message: ResultMessage | None = None

        # Compaction events
        self.compaction_events: list[dict[str, Any]] = []

        # Subagent tracking
        self._capture_subagents = capture_subagents
        self._subagent_tool_ids: set[str] = set()  # Agent tool_use_ids
        self._subagent_adapters: dict[str, "ATIFAdapter"] = {}  # tool_use_id -> child adapter
        self._subagent_names: dict[str, str] = {}  # tool_use_id -> agent name

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def process_message(self, msg: Any, extra: dict[str, Any] | None = None) -> Step | None:
        """Process a single SDK message. Returns the ATIF Step if one was created.

        Tool-result UserMessages do NOT create new steps; they attach to the
        previous agent step. Returns None in that case.

        Messages with parent_tool_use_id matching a known subagent are routed
        to the child adapter (if capturing) and excluded from the parent trajectory.
        """
        # Route subagent-internal messages away from parent trajectory.
        # Exception: UserMessages with tool_use_result set are the subagent's
        # RETURN value — these should be processed by the parent as observations.
        parent_id = getattr(msg, "parent_tool_use_id", None)
        if parent_id and parent_id in self._subagent_tool_ids:
            is_subagent_return = (
                isinstance(msg, UserMessage) and msg.tool_use_result is not None
            )
            if not is_subagent_return:
                if self._capture_subagents and parent_id in self._subagent_adapters:
                    self._subagent_adapters[parent_id].process_message(msg, extra)
                return None

        if isinstance(msg, AssistantMessage):
            return self._process_assistant(msg, extra)
        elif isinstance(msg, UserMessage):
            return self._process_user(msg, extra)
        elif isinstance(msg, SystemMessage):
            return self._process_system(msg)
        elif isinstance(msg, ResultMessage):
            self._result_message = msg
            return None
        else:
            # StreamEvent or unknown — skip
            return None

    def _process_assistant(self, msg: AssistantMessage, extra: dict[str, Any] | None) -> Step:
        """Map AssistantMessage -> Step(source="agent")."""
        self._step_counter += 1

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        thinking_signatures: list[str] = []
        tool_calls: list[ToolCall] = []
        observation_results: list[ObservationResult] = []

        for block in msg.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ThinkingBlock):
                thinking_parts.append(block.thinking)
                thinking_signatures.append(block.signature)
            elif isinstance(block, ToolUseBlock):
                tool_calls.append(
                    ToolCall(
                        tool_call_id=block.id,
                        function_name=block.name,
                        arguments=block.input,
                    )
                )
            elif isinstance(block, ToolResultBlock):
                # Inline tool results within AssistantMessage
                content_str = str(block.content) if block.content is not None else ""
                observation_results.append(
                    ObservationResult(
                        source_call_id=block.tool_use_id,
                        content=content_str,
                    )
                )

        message = "\n".join(text_parts) if text_parts else ""

        step_extra: dict[str, Any] = {}
        if extra:
            step_extra.update(extra)
        if thinking_signatures:
            step_extra["thinking_signatures"] = thinking_signatures
        if msg.model:
            step_extra["sdk_model"] = msg.model
        if msg.error:
            step_extra["sdk_error"] = msg.error
        if msg.parent_tool_use_id:
            step_extra["parent_tool_use_id"] = msg.parent_tool_use_id

        step = Step(
            step_id=self._step_counter,
            timestamp=self._now_iso(),
            source="agent",
            model_name=msg.model or None,
            message=message,
            reasoning_content="\n".join(thinking_parts) if thinking_parts else None,
            tool_calls=tool_calls if tool_calls else None,
            observation=(
                Observation(results=observation_results) if observation_results else None
            ),
            extra=step_extra if step_extra else None,
        )

        self.steps.append(step)
        step_index = len(self.steps) - 1
        # Register tool_call_ids for observation attachment lookup
        for tc in tool_calls:
            self._tool_call_to_step[tc.tool_call_id] = step_index
            # Detect Agent tool calls and register subagent
            if tc.function_name == "Agent":
                self._register_subagent(tc)
        return step

    def _process_user(self, msg: UserMessage, extra: dict[str, Any] | None) -> Step | None:
        """Map UserMessage to either an Observation attachment or a new user Step."""
        if msg.tool_use_result is not None:
            self._attach_tool_result(msg)
            return None

        # Regular user message -> new step
        self._step_counter += 1

        if isinstance(msg.content, str):
            message_text = msg.content
        elif isinstance(msg.content, list):
            parts = []
            for block in msg.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
                else:
                    parts.append(str(block))
            message_text = "\n".join(parts) if parts else ""
        else:
            message_text = str(msg.content)

        step_extra: dict[str, Any] = {}
        if extra:
            step_extra.update(extra)
        if msg.uuid:
            step_extra["uuid"] = msg.uuid

        step = Step(
            step_id=self._step_counter,
            timestamp=self._now_iso(),
            source="user",
            message=message_text,
            extra=step_extra if step_extra else None,
        )

        self.steps.append(step)
        return step

    def _attach_tool_result(self, msg: UserMessage) -> None:
        """Attach a tool result as ObservationResult on the correct agent step.

        The SDK sends tool results as UserMessage with tool_use_result set.
        The actual content and tool_use_id are in ToolResultBlock objects
        within msg.content. We look up the step that made the tool call
        by tool_use_id to satisfy ATIF's same-step reference constraint.
        """
        # Extract all ToolResultBlocks from msg.content
        found = False
        if isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    self._attach_observation(
                        tool_use_id=block.tool_use_id,
                        content=str(block.content) if block.content is not None else "",
                    )
                    found = True

        if found:
            return

        # Fallback: use parent_tool_use_id
        tool_use_id = msg.parent_tool_use_id
        result_data = msg.tool_use_result
        if isinstance(result_data, dict):
            content = str(result_data.get("content", ""))
        else:
            content = str(result_data) if result_data else ""
        self._attach_observation(tool_use_id=tool_use_id, content=content)

    def _attach_observation(self, tool_use_id: str | None, content: str) -> None:
        """Attach an ObservationResult to the step that issued the tool call."""
        # Look up the step by tool_call_id
        step_index = self._tool_call_to_step.get(tool_use_id) if tool_use_id else None

        if step_index is None:
            logger.warning(
                "Tool result for %s has no matching tool_call_id. Dropping to avoid misattribution.",
                tool_use_id,
            )
            return

        step = self.steps[step_index]
        obs_result = ObservationResult(
            source_call_id=tool_use_id,
            content=content,
        )
        if step.observation is not None:
            step.observation.results.append(obs_result)
        else:
            step.observation = Observation(results=[obs_result])

    def _process_system(self, msg: SystemMessage) -> Step | None:
        """Process SystemMessage — no ATIF step, just log for compaction detection."""
        logger.debug(
            "SystemMessage subtype=%s data_keys=%s",
            msg.subtype,
            list(msg.data.keys()) if msg.data else [],
        )

        subtype_lower = msg.subtype.lower() if msg.subtype else ""
        if "compact" in subtype_lower or "summary" in subtype_lower:
            self.compaction_events.append(
                {
                    "timestamp": self._now_iso(),
                    "after_step_id": self._step_counter,
                    "subtype": msg.subtype,
                    "data": msg.data,
                }
            )

        return None

    def record_compaction_event(
        self,
        trigger: str,
        custom_instructions: str | None = None,
    ) -> None:
        """Record a compaction event (called externally by hook callbacks)."""
        self.compaction_events.append(
            {
                "timestamp": self._now_iso(),
                "after_step_id": self._step_counter,
                "trigger": trigger,
                "custom_instructions": custom_instructions,
            }
        )

    def _register_subagent(self, tc: ToolCall) -> None:
        """Register an Agent tool call for subagent message routing."""
        tool_id = tc.tool_call_id
        self._subagent_tool_ids.add(tool_id)

        # Extract agent name from arguments
        args = tc.arguments or {}
        agent_name = args.get("description", args.get("subagent_type", "unknown"))
        self._subagent_names[tool_id] = agent_name

        if self._capture_subagents:
            self._subagent_adapters[tool_id] = ATIFAdapter(
                agent_name=f"subagent:{agent_name}",
                agent_version="0.1.0",
                model_name=self._agent_info.model_name or "",
                session_id=f"subagent_{tool_id}",
                capture_subagents=False,  # no nested capture
            )

    def build_subagent_trajectories(self) -> dict[str, Trajectory]:
        """Build ATIF trajectories for each captured subagent.

        Returns:
            dict mapping tool_use_id -> Trajectory for subagents that produced steps.
        """
        result = {}
        for tool_id, adapter in self._subagent_adapters.items():
            if not adapter.steps:
                continue
            traj = adapter.build_trajectory()
            traj.extra = {
                **(traj.extra or {}),
                "parent_session_id": self._session_id,
                "parent_tool_use_id": tool_id,
                "subagent_name": self._subagent_names.get(tool_id, "unknown"),
            }
            result[tool_id] = traj
        return result

    def attach_subagent_refs(self, ref_map: dict[str, SubagentTrajectoryRef]) -> None:
        """Attach SubagentTrajectoryRef to observation results for Agent tool calls.

        Args:
            ref_map: dict mapping tool_use_id -> SubagentTrajectoryRef to attach.
        """
        for step in self.steps:
            if not step.observation:
                continue
            for obs_result in step.observation.results:
                if obs_result.source_call_id and obs_result.source_call_id in ref_map:
                    obs_result.subagent_trajectory_ref = [ref_map[obs_result.source_call_id]]

    def build_trajectory(self) -> Trajectory:
        """Build the final ATIF Trajectory from accumulated steps."""
        if not self.steps:
            # ATIF requires at least 1 step
            self.steps.append(
                Step(
                    step_id=1,
                    timestamp=self._now_iso(),
                    source="system",
                    message="[No messages captured — session may have errored]",
                )
            )

        traj_extra: dict[str, Any] | None = None
        if self.compaction_events:
            traj_extra = {"compaction_events": self.compaction_events}

        return Trajectory(
            schema_version="ATIF-v1.6",
            session_id=self._session_id,
            agent=self._agent_info,
            steps=self.steps,
            final_metrics=self._compute_final_metrics(),
            extra=traj_extra,
        )

    def _compute_final_metrics(self) -> FinalMetrics:
        total_cost: float | None = None
        total_prompt: int | None = None
        total_completion: int | None = None
        total_cached: int | None = None

        if self._result_message:
            total_cost = self._result_message.total_cost_usd
            usage = self._result_message.usage
            if usage:
                total_prompt = usage.get("input_tokens")
                total_completion = usage.get("output_tokens")
                total_cached = usage.get("cache_read_input_tokens")

        return FinalMetrics(
            total_steps=len(self.steps),
            total_cost_usd=total_cost,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_cached_tokens=total_cached,
        )
