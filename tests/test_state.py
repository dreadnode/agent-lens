"""Tests for harness.state — StateManager with shadow git."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.shadow_git import ShadowGit
from harness.state import StateManager, WriteEvent, _safe_read_text


class TestSafeReadText:
    def test_reads_utf8(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        assert _safe_read_text(f) == "hello world"

    def test_binary_file_returns_placeholder(self, tmp_path: Path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x80\x81\x82\x83")
        result = _safe_read_text(f)
        assert "[binary file:" in result


class TestSeedMemory:
    def test_seeds_new_file(self, tmp_work_dir: Path, shadow_git_with_baseline):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)
        sm.seed_memory("MEMORY.md", "# Notes\n")
        assert (tmp_work_dir / "MEMORY.md").read_text() == "# Notes\n"

    def test_does_not_overwrite_existing(self, tmp_work_dir: Path, shadow_git_with_baseline):
        (tmp_work_dir / "MEMORY.md").write_text("existing content\n")
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)
        sm.seed_memory("MEMORY.md", "# Notes\n")
        assert (tmp_work_dir / "MEMORY.md").read_text() == "existing content\n"

    def test_seeds_nested_path(self, tmp_work_dir: Path, shadow_git_with_baseline):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)
        sm.seed_memory("docs/notes.md", "# Docs\n")
        assert (tmp_work_dir / "docs" / "notes.md").read_text() == "# Docs\n"


class TestCheckForWrites:
    def test_detects_new_file(self, tmp_work_dir: Path, shadow_git_with_baseline):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)

        (tmp_work_dir / "new_file.txt").write_text("new content\n")
        events = sm.check_for_writes(session_index=1, step_id=1)

        assert len(events) == 1
        assert events[0].file_path == "new_file.txt"
        assert events[0].content_before == ""
        assert events[0].content_after == "new content\n"
        assert events[0].session_index == 1
        assert events[0].step_id == 1

    def test_detects_modified_file(self, tmp_work_dir: Path, shadow_git_with_baseline):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)

        (tmp_work_dir / "main.py").write_text("print('modified')\n")
        events = sm.check_for_writes(session_index=1, step_id=2)

        assert len(events) == 1
        assert events[0].file_path == "main.py"
        assert "hello" in events[0].content_before
        assert "modified" in events[0].content_after

    def test_detects_deleted_file(self, tmp_work_dir: Path, shadow_git_with_baseline):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)

        (tmp_work_dir / "main.py").unlink()
        events = sm.check_for_writes(session_index=1, step_id=3)

        assert len(events) == 1
        assert events[0].file_path == "main.py"
        assert events[0].content_after == ""

    def test_no_changes_returns_empty(self, tmp_work_dir: Path, shadow_git_with_baseline):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)
        events = sm.check_for_writes(session_index=1, step_id=1)
        assert events == []

    def test_sequential_writes_only_show_new_changes(
        self, tmp_work_dir: Path, shadow_git_with_baseline
    ):
        """After check_for_writes, the next check should only see NEW changes."""
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)

        # Step 1: create file
        (tmp_work_dir / "a.txt").write_text("step1\n")
        events1 = sm.check_for_writes(session_index=1, step_id=1)
        assert len(events1) == 1

        # Step 2: create another file
        (tmp_work_dir / "b.txt").write_text("step2\n")
        events2 = sm.check_for_writes(session_index=1, step_id=2)
        assert len(events2) == 1
        assert events2[0].file_path == "b.txt"

    def test_write_log_accumulates(self, tmp_work_dir: Path, shadow_git_with_baseline):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)

        (tmp_work_dir / "a.txt").write_text("a\n")
        sm.check_for_writes(1, 1)

        (tmp_work_dir / "b.txt").write_text("b\n")
        sm.check_for_writes(1, 2)

        assert len(sm.write_log) == 2

    def test_diff_stats(self, tmp_work_dir: Path, shadow_git_with_baseline):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)

        (tmp_work_dir / "main.py").write_text("line1\nline2\nline3\n")
        events = sm.check_for_writes(1, 1)

        assert events[0].diff_stats["added"] > 0


class TestSaveChangelog:
    def test_saves_jsonl(self, tmp_work_dir: Path, shadow_git_with_baseline, tmp_path: Path):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)

        (tmp_work_dir / "a.txt").write_text("a\n")
        sm.check_for_writes(1, 1)

        (tmp_work_dir / "b.txt").write_text("b\n")
        sm.check_for_writes(1, 2)

        out = tmp_path / "changelog.jsonl"
        sm.save_changelog(out)

        lines = out.read_text().strip().split("\n")
        assert len(lines) == 2

        event1 = json.loads(lines[0])
        assert event1["file_path"] == "a.txt"
        assert event1["step_id"] == 1

        event2 = json.loads(lines[1])
        assert event2["file_path"] == "b.txt"
        assert event2["step_id"] == 2

    def test_saves_empty_changelog(self, tmp_work_dir: Path, shadow_git_with_baseline, tmp_path: Path):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)
        out = tmp_path / "empty.jsonl"
        sm.save_changelog(out)
        assert out.read_text() == ""

    def test_creates_parent_dirs(self, tmp_work_dir: Path, shadow_git_with_baseline, tmp_path: Path):
        sm = StateManager(work_dir=tmp_work_dir, shadow_git=shadow_git_with_baseline)
        out = tmp_path / "deep" / "nested" / "changelog.jsonl"
        sm.save_changelog(out)
        assert out.exists()
