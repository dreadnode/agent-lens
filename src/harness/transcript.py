"""Transcript parser and truncation for turn-level replay.

Parses Claude Code transcript JSONL files, detects API turn boundaries,
and truncates transcripts for exact-match replay from any turn.
"""

from __future__ import annotations

import json
import logging
import uuid as uuid_mod
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    """A single API turn in the transcript."""

    turn_index: int
    message_id: str  # API message.id grouping assistant entries
    assistant_lines: list[dict] = field(default_factory=list)
    tool_result_lines: list[dict] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    has_tool_use: bool = False
    timestamp: str | None = None


@dataclass
class TurnSummary:
    """Summary of a turn for --list-turns display."""

    turn_index: int
    tool_names: list[str]
    tool_result_count: int
    has_text: bool
    has_thinking: bool
    shadow_git_tag: str | None
    timestamp: str | None


def parse_turns(transcript_path: Path) -> tuple[list[dict], list[Turn]]:
    """Parse transcript JSONL into preamble entries and a list of Turns.

    Returns:
        (preamble, turns) where preamble contains non-conversation entries
        (queue-operation, file-history-snapshot) and the initial user message.
    """
    entries: list[dict] = []
    with open(transcript_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    preamble: list[dict] = []
    turns: list[Turn] = []
    current_turn: Turn | None = None
    seen_first_assistant = False

    # Collect tool_use IDs in current turn for matching tool_results
    current_tool_use_ids: set[str] = set()

    def _flush_turn() -> None:
        nonlocal current_turn
        if current_turn is not None:
            turns.append(current_turn)
            current_turn = None

    for entry in entries:
        entry_type = entry.get("type")

        if entry_type == "assistant":
            msg = entry.get("message", {})
            msg_id = msg.get("id")
            if not msg_id:
                # Synthetic or error messages — include in preamble if before first turn
                if not seen_first_assistant:
                    preamble.append(entry)
                elif current_turn:
                    current_turn.assistant_lines.append(entry)
                continue

            seen_first_assistant = True

            # New turn if message.id changes
            if current_turn is None or msg_id != current_turn.message_id:
                _flush_turn()
                current_turn = Turn(
                    turn_index=len(turns) + 1,
                    message_id=msg_id,
                    timestamp=entry.get("timestamp"),
                )
                current_tool_use_ids = set()

            current_turn.assistant_lines.append(entry)

            # Detect content block types
            for block in msg.get("content", []):
                block_type = block.get("type")
                if block_type == "tool_use":
                    current_turn.has_tool_use = True
                    current_tool_use_ids.add(block.get("id", ""))
                    tool_name = block.get("name", "")
                    if tool_name:
                        current_turn.tool_names.append(tool_name)

        elif entry_type == "user":
            if not seen_first_assistant:
                # Part of preamble (initial user prompt, meta messages)
                preamble.append(entry)
                continue

            # Check if this is a tool_result for the current turn
            msg = entry.get("message", {})
            content = msg.get("content", "")
            is_tool_result = False

            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id", "")
                        if tool_use_id in current_tool_use_ids:
                            is_tool_result = True
                            break

            if is_tool_result and current_turn is not None:
                current_turn.tool_result_lines.append(entry)
            else:
                # Non-tool-result user message mid-conversation
                # (e.g. additional prompts in multi-prompt sessions).
                # Keep it inline with turn ordering so replay truncation
                # includes it only when it appears before the branch point.
                if current_turn is None:
                    # If there is no active turn, preserve ordering by creating
                    # an empty synthetic turn bucket for this entry.
                    current_turn = Turn(
                        turn_index=len(turns) + 1,
                        message_id=f"_user_{len(turns) + 1}",
                        timestamp=entry.get("timestamp"),
                    )
                current_turn.assistant_lines.append(entry)

        elif entry_type in ("file-history-snapshot", "queue-operation", "last-prompt"):
            # Metadata entries — include in preamble or inline
            if not seen_first_assistant:
                preamble.append(entry)
            elif current_turn:
                # file-history-snapshots can appear mid-conversation
                # Attach to current turn's assistant lines to preserve ordering
                current_turn.assistant_lines.append(entry)

        else:
            # Unknown entry type — preserve in preamble
            if not seen_first_assistant:
                preamble.append(entry)

    # Flush final turn
    _flush_turn()

    return preamble, turns


def truncate_for_replay(
    transcript_path: Path,
    turn_index: int,
) -> tuple[list[dict], list[dict]]:
    """Truncate a transcript for replay at a specific turn.

    For replaying turn N, we include:
    - All preamble entries (queue ops, file snapshots, initial user message)
    - All complete turns 1..N-2 (assistant + tool_result pairs)
    - Turn N-1's assistant entries ONLY (no tool_results)

    The tool_result entries from turn N-1 are returned separately — they
    become the AsyncIterable prompt sent via SDK stdin.

    Args:
        transcript_path: Path to the original transcript.jsonl
        turn_index: The turn to replay (1-based). Must be >= 1.

    Returns:
        (truncated_entries, tool_result_entries):
        - truncated_entries: lines to write as the new transcript JSONL
        - tool_result_entries: user messages with tool_results to yield as prompt
    """
    preamble, turns = parse_turns(transcript_path)

    if turn_index < 1 or turn_index > len(turns):
        raise ValueError(
            f"turn_index {turn_index} out of range (1..{len(turns)})"
        )

    truncated: list[dict] = list(preamble)
    tool_results: list[dict] = []

    if turn_index == 1:
        # Replay from the very first turn — just the preamble, no prior turns
        # No tool results to inject (the initial user message IS the prompt)
        return truncated, []

    # Include complete turns 1..N-2 (assistant + tool_results)
    for turn in turns[: turn_index - 2]:
        truncated.extend(turn.assistant_lines)
        truncated.extend(turn.tool_result_lines)

    # Turn N-1: include assistant entries only, tool_results become the prompt
    turn_n_minus_1 = turns[turn_index - 2]
    truncated.extend(turn_n_minus_1.assistant_lines)
    tool_results = list(turn_n_minus_1.tool_result_lines)

    return truncated, tool_results


def write_truncated_transcript(
    entries: list[dict],
    new_session_id: str,
    project_dir: Path,
) -> Path:
    """Write truncated transcript entries with a new session_id.

    Rewrites the sessionId field on all entries so the CLI can find it
    via --resume <new_session_id>.

    Args:
        entries: The truncated JSONL entries to write
        new_session_id: UUID string for the new session
        project_dir: The ~/.claude/projects/<hash>/ directory

    Returns:
        Path to the written JSONL file
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    dest = project_dir / f"{new_session_id}.jsonl"

    with open(dest, "w") as f:
        for entry in entries:
            # Rewrite sessionId — make a shallow copy to avoid mutating input
            entry_copy = dict(entry)
            if "sessionId" in entry_copy:
                entry_copy["sessionId"] = new_session_id
            f.write(json.dumps(entry_copy) + "\n")

    logger.info("Wrote truncated transcript (%d entries) to %s", len(entries), dest)
    return dest


def get_project_dir(cwd: str) -> Path:
    """Get the Claude Code project directory for a given working directory."""
    project_hash = "-" + cwd.lstrip("/").replace("/", "-").replace("_", "-")
    return Path.home() / ".claude" / "projects" / project_hash


def list_turns(
    transcript_path: Path,
    uuid_map: dict | None = None,
) -> list[TurnSummary]:
    """List available replay points in a transcript.

    Args:
        transcript_path: Path to transcript.jsonl
        uuid_map: Optional uuid_map.json contents for shadow git tag info
    """
    _, turns = parse_turns(transcript_path)

    # Build shadow git tag lookup from uuid_map
    tag_by_turn: dict[int, str | None] = {}
    if uuid_map:
        for tm in uuid_map.get("turns", []):
            tag_by_turn[tm["turn_index"]] = tm.get("shadow_git_tag")

    summaries: list[TurnSummary] = []
    for turn in turns:
        has_text = False
        has_thinking = False
        for entry in turn.assistant_lines:
            msg = entry.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "text":
                    has_text = True
                elif block.get("type") == "thinking":
                    has_thinking = True

        summaries.append(TurnSummary(
            turn_index=turn.turn_index,
            tool_names=turn.tool_names,
            tool_result_count=len(turn.tool_result_lines),
            has_text=has_text,
            has_thinking=has_thinking,
            shadow_git_tag=tag_by_turn.get(turn.turn_index),
            timestamp=turn.timestamp,
        ))

    return summaries
