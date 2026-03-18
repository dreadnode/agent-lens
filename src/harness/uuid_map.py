"""UUID map builder — correlates transcript, ATIF trajectory, and raw API dumps.

Produces a uuid_map.json that maps each API turn to its entries across all three
formats, using tool_call_id as the primary join key.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TurnMapping:
    """Mapping for a single API turn across all formats."""

    turn_index: int
    message_id: str  # API message.id from transcript (groups assistant entries)
    request_file: str | None = None  # e.g. "request_001.json"
    atif_step_ids: list[int] = field(default_factory=list)
    transcript_assistant_uuids: list[str] = field(default_factory=list)
    transcript_tool_result_uuids: list[str] = field(default_factory=list)
    tool_call_ids: list[str] = field(default_factory=list)
    shadow_git_tag: str | None = None
    timestamp: str | None = None


def build_uuid_map(
    session_dir: Path,
    session_index: int,
) -> dict | None:
    """Build a UUID map correlating transcript, ATIF, and raw dumps.

    Returns the map dict, or None if transcript is missing.
    """
    transcript_path = session_dir / "transcript.jsonl"
    trajectory_path = session_dir / "trajectory.json"

    if not transcript_path.exists():
        logger.warning("No transcript found at %s, skipping uuid_map", transcript_path)
        return None

    # Parse transcript into turns
    turns = _parse_transcript_turns(transcript_path)
    if not turns:
        return None

    # Load ATIF trajectory for step correlation
    atif_tool_map: dict[str, int] = {}  # tool_call_id -> step_id
    if trajectory_path.exists():
        try:
            with open(trajectory_path) as f:
                traj = json.load(f)
            for step in traj.get("steps", []):
                for tc in step.get("tool_calls") or []:
                    tc_id = tc.get("tool_call_id")
                    if tc_id:
                        atif_tool_map[tc_id] = step["step_id"]
        except Exception as e:
            logger.warning("Failed to parse trajectory: %s", e)

    # Find available raw dump files
    raw_dir = session_dir / "raw_dumps"
    raw_files: set[str] = set()
    if raw_dir.exists():
        raw_files = {f.name for f in raw_dir.glob("request_*.json") if not f.name.endswith("_headers.json")}

    # Find shadow git step tags
    shadow_tags = _find_shadow_git_tags(session_dir.parent, session_index)

    # Build turn mappings
    mappings: list[TurnMapping] = []
    for turn in turns:
        turn_idx = turn["turn_index"]

        # Map request file (1-indexed)
        request_file: str | None = f"request_{turn_idx:03d}.json"
        if request_file not in raw_files:
            request_file = None

        # Correlate ATIF steps via tool_call_ids
        step_ids: set[int] = set()
        for tc_id in turn["tool_call_ids"]:
            if tc_id in atif_tool_map:
                step_ids.add(atif_tool_map[tc_id])

        # Also find steps for thinking/text blocks (no tool_call_id)
        # These are ATIF steps that precede the tool-calling step
        # We approximate by including step_ids adjacent to known ones

        # Find shadow git tag — use the highest step_id that has a tag
        shadow_tag = None
        for sid in sorted(step_ids, reverse=True):
            tag = f"_step_{session_index}_{sid}"
            if tag in shadow_tags:
                shadow_tag = tag
                break

        mapping = TurnMapping(
            turn_index=turn_idx,
            message_id=turn["message_id"],
            request_file=request_file,
            atif_step_ids=sorted(step_ids),
            transcript_assistant_uuids=turn["assistant_uuids"],
            transcript_tool_result_uuids=turn["tool_result_uuids"],
            tool_call_ids=turn["tool_call_ids"],
            shadow_git_tag=shadow_tag,
            timestamp=turn.get("timestamp"),
        )
        mappings.append(mapping)

    result = {"turns": [asdict(m) for m in mappings]}

    # Write to session dir
    out_path = session_dir / "uuid_map.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info("Built uuid_map with %d turns: %s", len(mappings), out_path)

    return result


def _parse_transcript_turns(transcript_path: Path) -> list[dict]:
    """Parse transcript JSONL into turn groups based on message.id.

    Returns a list of turn dicts with:
      turn_index, message_id, assistant_uuids, tool_result_uuids,
      tool_call_ids, timestamp
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

    turns: list[dict] = []
    current_msg_id: str | None = None
    current_assistant_uuids: list[str] = []
    current_tool_call_ids: list[str] = []
    current_timestamp: str | None = None

    # Pending tool results for the current turn
    pending_tool_use_ids: set[str] = set()
    current_tool_result_uuids: list[str] = []
    turn_index = 0

    def _flush_turn() -> None:
        nonlocal turn_index
        if current_msg_id is None:
            return
        turn_index += 1
        turns.append({
            "turn_index": turn_index,
            "message_id": current_msg_id,
            "assistant_uuids": list(current_assistant_uuids),
            "tool_result_uuids": list(current_tool_result_uuids),
            "tool_call_ids": list(current_tool_call_ids),
            "timestamp": current_timestamp,
        })

    for entry in entries:
        entry_type = entry.get("type")

        if entry_type == "assistant":
            msg = entry.get("message", {})
            msg_id = msg.get("id")
            if not msg_id:
                continue

            # New turn if message.id changes
            if msg_id != current_msg_id:
                _flush_turn()
                current_msg_id = msg_id
                current_assistant_uuids = []
                current_tool_call_ids = []
                current_tool_result_uuids = []
                pending_tool_use_ids = set()
                current_timestamp = entry.get("timestamp")

            current_assistant_uuids.append(entry.get("uuid", ""))

            # Collect tool_use IDs from content blocks
            for block in msg.get("content", []):
                if block.get("type") == "tool_use" and block.get("id"):
                    current_tool_call_ids.append(block["id"])
                    pending_tool_use_ids.add(block["id"])

        elif entry_type == "user":
            msg = entry.get("message", {})
            content = msg.get("content", "")

            # Check if this is a tool_result
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id", "")
                        if tool_use_id in pending_tool_use_ids:
                            current_tool_result_uuids.append(entry.get("uuid", ""))
                            pending_tool_use_ids.discard(tool_use_id)
                            break

    # Flush final turn
    _flush_turn()
    return turns


def _find_shadow_git_tags(run_dir: Path, session_index: int) -> set[str]:
    """Find all shadow git step tags for a session."""
    import os
    import subprocess

    git_dir = run_dir / ".shadow_git"
    if not git_dir.exists():
        return set()

    try:
        result = subprocess.run(
            ["git", "tag", "-l", f"_step_{session_index}_*"],
            env={**os.environ, "GIT_DIR": str(git_dir)},
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return set()
        return {t.strip() for t in result.stdout.splitlines() if t.strip()}
    except Exception:
        return set()
