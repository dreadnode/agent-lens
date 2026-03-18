"""Tests for harness.transcript — transcript parsing and truncation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.transcript import (
    Turn,
    TurnSummary,
    get_project_dir,
    list_turns,
    parse_turns,
    truncate_for_replay,
    write_truncated_transcript,
)


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _make_assistant_entry(
    msg_id: str,
    content: list[dict] | None = None,
    uuid: str = "",
    timestamp: str | None = None,
) -> dict:
    if content is None:
        content = [{"type": "text", "text": "hello"}]
    entry = {
        "type": "assistant",
        "uuid": uuid,
        "message": {"id": msg_id, "content": content},
    }
    if timestamp:
        entry["timestamp"] = timestamp
    return entry


def _make_tool_use_block(tool_use_id: str, name: str = "Read") -> dict:
    return {"type": "tool_use", "id": tool_use_id, "name": name, "input": {}}


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


def _make_user_prompt(text: str = "do something") -> dict:
    return {
        "type": "user",
        "uuid": "user-prompt-uuid",
        "message": {"role": "user", "content": text},
    }


@pytest.fixture
def simple_transcript(tmp_path: Path) -> Path:
    """Three-turn transcript: user prompt + 3 assistant turns with tool use."""
    entries = [
        # Preamble
        _make_user_prompt("build a thing"),
        # Turn 1: assistant with tool_use + tool_result
        _make_assistant_entry(
            "msg-1",
            [
                {"type": "thinking", "thinking": "let me think"},
                _make_tool_use_block("tc-1", "Read"),
            ],
            uuid="a1",
            timestamp="2026-01-01T00:00:00Z",
        ),
        _make_tool_result_entry("tc-1", uuid="tr1"),
        # Turn 2: assistant with tool_use + tool_result
        _make_assistant_entry(
            "msg-2",
            [
                {"type": "text", "text": "I see the file"},
                _make_tool_use_block("tc-2", "Edit"),
            ],
            uuid="a2",
        ),
        _make_tool_result_entry("tc-2", uuid="tr2"),
        # Turn 3: text-only (no tools)
        _make_assistant_entry("msg-3", [{"type": "text", "text": "done!"}], uuid="a3"),
    ]
    path = tmp_path / "transcript.jsonl"
    _write_jsonl(path, entries)
    return path


class TestParseTurns:
    def test_basic_structure(self, simple_transcript: Path):
        preamble, turns = parse_turns(simple_transcript)
        assert len(preamble) == 1  # user prompt
        assert len(turns) == 3

    def test_turn_indices(self, simple_transcript: Path):
        _, turns = parse_turns(simple_transcript)
        assert [t.turn_index for t in turns] == [1, 2, 3]

    def test_message_ids(self, simple_transcript: Path):
        _, turns = parse_turns(simple_transcript)
        assert [t.message_id for t in turns] == ["msg-1", "msg-2", "msg-3"]

    def test_tool_names(self, simple_transcript: Path):
        _, turns = parse_turns(simple_transcript)
        assert turns[0].tool_names == ["Read"]
        assert turns[1].tool_names == ["Edit"]
        assert turns[2].tool_names == []

    def test_has_tool_use(self, simple_transcript: Path):
        _, turns = parse_turns(simple_transcript)
        assert turns[0].has_tool_use is True
        assert turns[1].has_tool_use is True
        assert turns[2].has_tool_use is False

    def test_tool_result_lines(self, simple_transcript: Path):
        _, turns = parse_turns(simple_transcript)
        assert len(turns[0].tool_result_lines) == 1
        assert len(turns[1].tool_result_lines) == 1
        assert len(turns[2].tool_result_lines) == 0

    def test_timestamp(self, simple_transcript: Path):
        _, turns = parse_turns(simple_transcript)
        assert turns[0].timestamp == "2026-01-01T00:00:00Z"

    def test_preamble_includes_metadata(self, tmp_path: Path):
        entries = [
            {"type": "queue-operation", "data": "init"},
            {"type": "file-history-snapshot", "data": "snap"},
            _make_user_prompt("go"),
            _make_assistant_entry("msg-1", uuid="a1"),
        ]
        path = tmp_path / "transcript.jsonl"
        _write_jsonl(path, entries)
        preamble, turns = parse_turns(path)
        assert len(preamble) == 3  # queue-op + file-snap + user prompt
        assert len(turns) == 1

    def test_empty_transcript(self, tmp_path: Path):
        path = tmp_path / "empty.jsonl"
        _write_jsonl(path, [])
        preamble, turns = parse_turns(path)
        assert preamble == []
        assert turns == []

    def test_multi_entry_turn(self, tmp_path: Path):
        """Multiple assistant entries with same message.id form one turn."""
        entries = [
            _make_user_prompt("go"),
            _make_assistant_entry("msg-1", [{"type": "thinking", "thinking": "hmm"}], uuid="a1a"),
            _make_assistant_entry("msg-1", [_make_tool_use_block("tc-1")], uuid="a1b"),
            _make_tool_result_entry("tc-1", uuid="tr1"),
        ]
        path = tmp_path / "transcript.jsonl"
        _write_jsonl(path, entries)
        _, turns = parse_turns(path)
        assert len(turns) == 1
        assert len(turns[0].assistant_lines) == 2

    def test_mid_conversation_user_prompt_is_not_preamble(self, tmp_path: Path):
        entries = [
            _make_user_prompt("initial"),
            _make_assistant_entry("msg-1", [_make_tool_use_block("tc-1")], uuid="a1"),
            _make_tool_result_entry("tc-1", uuid="tr1"),
            _make_user_prompt("follow-up prompt"),
            _make_assistant_entry("msg-2", [{"type": "text", "text": "second"}], uuid="a2"),
        ]
        path = tmp_path / "transcript.jsonl"
        _write_jsonl(path, entries)
        preamble, turns = parse_turns(path)
        assert len(preamble) == 1  # only initial user prompt
        assert len(turns) == 2
        # Follow-up user prompt is kept inline with turn ordering
        assert turns[0].assistant_lines[-1]["type"] == "user"


class TestTruncateForReplay:
    def test_truncate_turn_1(self, simple_transcript: Path):
        """Replaying from turn 1 returns just preamble, no tool results."""
        truncated, tool_results = truncate_for_replay(simple_transcript, 1)
        assert len(truncated) == 1  # just user prompt
        assert len(tool_results) == 0

    def test_truncate_turn_2(self, simple_transcript: Path):
        """Replaying from turn 2: include turn 1 assistant only, tool results as prompt."""
        truncated, tool_results = truncate_for_replay(simple_transcript, 2)
        # Preamble (1) + turn 1 assistant (1) = 2
        assert len(truncated) == 2
        # Turn 1's tool result becomes the prompt
        assert len(tool_results) == 1
        assert tool_results[0]["type"] == "user"

    def test_truncate_turn_3(self, simple_transcript: Path):
        """Replaying from turn 3: include turns 1-1 fully + turn 2 assistant only."""
        truncated, tool_results = truncate_for_replay(simple_transcript, 3)
        # Preamble (1) + turn 1 full (assistant + tool_result = 2) + turn 2 assistant (1) = 4
        assert len(truncated) == 4
        # Turn 2's tool result becomes the prompt
        assert len(tool_results) == 1

    def test_truncate_out_of_range(self, simple_transcript: Path):
        with pytest.raises(ValueError, match="out of range"):
            truncate_for_replay(simple_transcript, 0)
        with pytest.raises(ValueError, match="out of range"):
            truncate_for_replay(simple_transcript, 4)

    def test_truncated_preserves_content(self, simple_transcript: Path):
        truncated, _ = truncate_for_replay(simple_transcript, 2)
        # First entry should be user prompt
        assert truncated[0]["type"] == "user"
        # Second entry should be turn 1's assistant
        assert truncated[1]["type"] == "assistant"
        assert truncated[1]["message"]["id"] == "msg-1"

    def test_truncate_preserves_mid_conversation_user_prompt_order(self, tmp_path: Path):
        entries = [
            _make_user_prompt("initial"),
            _make_assistant_entry("msg-1", [_make_tool_use_block("tc-1")], uuid="a1"),
            _make_tool_result_entry("tc-1", uuid="tr1"),
            _make_user_prompt("follow-up prompt"),
            _make_assistant_entry("msg-2", [{"type": "text", "text": "second"}], uuid="a2"),
        ]
        path = tmp_path / "transcript.jsonl"
        _write_jsonl(path, entries)

        truncated, _ = truncate_for_replay(path, 2)
        # preamble + turn1 assistant + inline follow-up user prompt
        assert [e["type"] for e in truncated] == ["user", "assistant", "user"]


class TestWriteTruncatedTranscript:
    def test_writes_file(self, tmp_path: Path):
        entries = [_make_user_prompt("hello"), _make_assistant_entry("msg-1")]
        # Add sessionId to entries
        for e in entries:
            e["sessionId"] = "old-id"
        project_dir = tmp_path / "project"
        new_id = "new-session-123"
        result = write_truncated_transcript(entries, new_id, project_dir)
        assert result.exists()
        assert result.name == f"{new_id}.jsonl"

    def test_rewrites_session_id(self, tmp_path: Path):
        entries = [{"type": "user", "sessionId": "old-id", "message": {"role": "user", "content": "hi"}}]
        project_dir = tmp_path / "project"
        new_id = "new-id"
        result = write_truncated_transcript(entries, new_id, project_dir)
        with open(result) as f:
            written = json.loads(f.readline())
        assert written["sessionId"] == "new-id"

    def test_does_not_mutate_input(self, tmp_path: Path):
        entries = [{"type": "user", "sessionId": "old-id", "message": {}}]
        project_dir = tmp_path / "project"
        write_truncated_transcript(entries, "new-id", project_dir)
        assert entries[0]["sessionId"] == "old-id"


class TestGetProjectDir:
    def test_basic(self):
        result = get_project_dir("/Users/v/dev/foo")
        assert str(result).endswith("-Users-v-dev-foo")
        assert ".claude/projects/" in str(result)

    def test_strips_leading_slash(self):
        result = get_project_dir("/a/b/c")
        assert result.name == "-a-b-c"


class TestListTurns:
    def test_basic_listing(self, simple_transcript: Path):
        summaries = list_turns(simple_transcript)
        assert len(summaries) == 3
        assert summaries[0].turn_index == 1
        assert summaries[0].tool_names == ["Read"]
        assert summaries[0].tool_result_count == 1

    def test_has_text_and_thinking(self, simple_transcript: Path):
        summaries = list_turns(simple_transcript)
        # Turn 1 has thinking
        assert summaries[0].has_thinking is True
        assert summaries[0].has_text is False
        # Turn 2 has text
        assert summaries[1].has_text is True
        # Turn 3 has text only
        assert summaries[2].has_text is True
        assert summaries[2].has_thinking is False

    def test_with_uuid_map(self, simple_transcript: Path):
        uuid_map = {
            "turns": [
                {"turn_index": 1, "shadow_git_tag": "_step_1_3"},
                {"turn_index": 2, "shadow_git_tag": None},
            ]
        }
        summaries = list_turns(simple_transcript, uuid_map)
        assert summaries[0].shadow_git_tag == "_step_1_3"
        assert summaries[1].shadow_git_tag is None
