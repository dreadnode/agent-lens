"""Tests for harness.uuid_map — turn correlation across formats."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.uuid_map import TurnMapping, build_uuid_map


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _make_assistant_entry(
    msg_id: str,
    tool_use_blocks: list[dict] | None = None,
    uuid: str = "",
    timestamp: str | None = None,
) -> dict:
    content = []
    if tool_use_blocks:
        content.extend(tool_use_blocks)
    else:
        content.append({"type": "text", "text": "hello"})
    entry = {
        "type": "assistant",
        "uuid": uuid,
        "message": {"id": msg_id, "content": content},
    }
    if timestamp:
        entry["timestamp"] = timestamp
    return entry


def _make_tool_result_entry(tool_use_id: str, uuid: str = "") -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok"}
            ],
        },
    }


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    """Session directory with transcript and trajectory."""
    sdir = tmp_path / "run" / "session_01"
    sdir.mkdir(parents=True)

    # Write transcript
    entries = [
        {"type": "user", "uuid": "u0", "message": {"role": "user", "content": "go"}},
        _make_assistant_entry(
            "msg-1",
            [{"type": "tool_use", "id": "tc-1", "name": "Read", "input": {}}],
            uuid="a1",
            timestamp="2026-01-01T00:00:00Z",
        ),
        _make_tool_result_entry("tc-1", uuid="tr1"),
        _make_assistant_entry(
            "msg-2",
            [{"type": "tool_use", "id": "tc-2", "name": "Edit", "input": {}}],
            uuid="a2",
        ),
        _make_tool_result_entry("tc-2", uuid="tr2"),
    ]
    _write_jsonl(sdir / "transcript.jsonl", entries)

    # Write ATIF trajectory
    trajectory = {
        "steps": [
            {"step_id": 1, "tool_calls": [{"tool_call_id": "tc-1"}]},
            {"step_id": 2, "tool_calls": [{"tool_call_id": "tc-2"}]},
        ]
    }
    with open(sdir / "trajectory.json", "w") as f:
        json.dump(trajectory, f)

    return sdir


class TestBuildUuidMap:
    def test_basic_structure(self, session_dir: Path):
        result = build_uuid_map(session_dir, session_index=1)
        assert result is not None
        assert "turns" in result
        assert len(result["turns"]) == 2

    def test_turn_indices(self, session_dir: Path):
        result = build_uuid_map(session_dir, session_index=1)
        indices = [t["turn_index"] for t in result["turns"]]
        assert indices == [1, 2]

    def test_message_ids(self, session_dir: Path):
        result = build_uuid_map(session_dir, session_index=1)
        assert result["turns"][0]["message_id"] == "msg-1"
        assert result["turns"][1]["message_id"] == "msg-2"

    def test_tool_call_ids(self, session_dir: Path):
        result = build_uuid_map(session_dir, session_index=1)
        assert result["turns"][0]["tool_call_ids"] == ["tc-1"]
        assert result["turns"][1]["tool_call_ids"] == ["tc-2"]

    def test_atif_step_correlation(self, session_dir: Path):
        result = build_uuid_map(session_dir, session_index=1)
        assert result["turns"][0]["atif_step_ids"] == [1]
        assert result["turns"][1]["atif_step_ids"] == [2]

    def test_transcript_uuids(self, session_dir: Path):
        result = build_uuid_map(session_dir, session_index=1)
        assert result["turns"][0]["transcript_assistant_uuids"] == ["a1"]
        assert result["turns"][0]["transcript_tool_result_uuids"] == ["tr1"]

    def test_timestamp(self, session_dir: Path):
        result = build_uuid_map(session_dir, session_index=1)
        assert result["turns"][0]["timestamp"] == "2026-01-01T00:00:00Z"

    def test_writes_file(self, session_dir: Path):
        build_uuid_map(session_dir, session_index=1)
        assert (session_dir / "uuid_map.json").exists()

    def test_no_transcript(self, tmp_path: Path):
        sdir = tmp_path / "empty_session"
        sdir.mkdir()
        result = build_uuid_map(sdir, session_index=1)
        assert result is None

    def test_no_trajectory(self, session_dir: Path):
        """Should still work without ATIF trajectory, just no step correlation."""
        (session_dir / "trajectory.json").unlink()
        result = build_uuid_map(session_dir, session_index=1)
        assert result is not None
        assert result["turns"][0]["atif_step_ids"] == []
