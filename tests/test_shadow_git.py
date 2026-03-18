"""Tests for harness.shadow_git — invisible change tracking."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.config import SessionMode
from harness.shadow_git import ShadowGit


class TestShadowGitInit:
    def test_init_creates_bare_repo(self, tmp_work_dir: Path, tmp_git_dir: Path):
        sg = ShadowGit(work_dir=tmp_work_dir, git_dir=tmp_git_dir)
        sg.init()
        assert tmp_git_dir.exists()
        # Bare repo has HEAD file directly in git_dir
        assert (tmp_git_dir / "HEAD").exists()

    def test_init_writes_exclude_file(self, shadow_git: ShadowGit):
        exclude = shadow_git.git_dir / "info" / "exclude"
        assert exclude.exists()
        content = exclude.read_text()
        assert ".git" in content
        assert "node_modules" in content
        assert "__pycache__" in content

    def test_init_idempotent(self, tmp_work_dir: Path, tmp_git_dir: Path):
        sg = ShadowGit(work_dir=tmp_work_dir, git_dir=tmp_git_dir)
        sg.init()
        sg.init()  # should not raise


class TestBaseline:
    def test_commit_baseline_tags(self, shadow_git: ShadowGit):
        shadow_git.commit_baseline()
        # Should be able to reference the baseline tag
        result = shadow_git._git("rev-parse", "baseline", check=False)
        assert result.returncode == 0

    def test_baseline_captures_all_files(self, shadow_git: ShadowGit, tmp_work_dir: Path):
        shadow_git.commit_baseline()
        # Check that main.py is tracked
        content = shadow_git.show_file("baseline", "main.py")
        assert content == "print('hello')\n"

    def test_baseline_captures_readme(self, shadow_git: ShadowGit, tmp_work_dir: Path):
        shadow_git.commit_baseline()
        content = shadow_git.show_file("baseline", "README.md")
        assert content == "# Test Repo\n"


class TestSnapshots:
    def test_commit_snapshot_with_changes(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline
        # Modify a file
        (tmp_work_dir / "main.py").write_text("print('modified')\n")
        sg.commit_snapshot("snap1", message="first snapshot")

        # Verify tag exists
        result = sg._git("rev-parse", "snap1", check=False)
        assert result.returncode == 0

    def test_commit_snapshot_no_changes(self, shadow_git_with_baseline):
        """Snapshot with no changes should still tag HEAD."""
        sg = shadow_git_with_baseline
        sg.commit_snapshot("empty_snap")
        result = sg._git("rev-parse", "empty_snap", check=False)
        assert result.returncode == 0

    def test_multiple_snapshots(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline

        (tmp_work_dir / "file1.txt").write_text("one\n")
        sg.commit_snapshot("snap1")

        (tmp_work_dir / "file2.txt").write_text("two\n")
        sg.commit_snapshot("snap2")

        # snap1 should have file1 but not file2
        assert sg.show_file("snap1", "file1.txt") == "one\n"
        assert sg.show_file("snap1", "file2.txt") is None

        # snap2 should have both
        assert sg.show_file("snap2", "file1.txt") == "one\n"
        assert sg.show_file("snap2", "file2.txt") == "two\n"


class TestDiff:
    def test_diff_from_baseline(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline
        (tmp_work_dir / "main.py").write_text("print('changed')\n")
        sg.commit_snapshot("after")

        diff = sg.diff_from_ref("baseline")
        assert "hello" in diff
        assert "changed" in diff

    def test_diff_no_changes(self, shadow_git_with_baseline):
        diff = shadow_git_with_baseline.diff_from_ref("baseline")
        assert diff == ""

    def test_diff_working(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline
        (tmp_work_dir / "new_file.txt").write_text("new content\n")
        diff = sg.diff_working()
        assert "new_file.txt" in diff
        assert "new content" in diff

    def test_diff_working_names(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline
        (tmp_work_dir / "a.txt").write_text("aaa\n")
        (tmp_work_dir / "b.txt").write_text("bbb\n")
        names = sg.diff_working_names()
        assert "a.txt" in names
        assert "b.txt" in names

    def test_diff_working_names_no_changes(self, shadow_git_with_baseline):
        names = shadow_git_with_baseline.diff_working_names()
        assert names == []

    def test_diff_deleted_file(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline
        (tmp_work_dir / "main.py").unlink()
        names = sg.diff_working_names()
        assert "main.py" in names


class TestShowFile:
    def test_show_existing_file(self, shadow_git_with_baseline):
        content = shadow_git_with_baseline.show_file("baseline", "main.py")
        assert content is not None
        assert "hello" in content

    def test_show_nonexistent_file(self, shadow_git_with_baseline):
        content = shadow_git_with_baseline.show_file("baseline", "nonexistent.txt")
        assert content is None


class TestStatus:
    def test_status_clean(self, shadow_git_with_baseline):
        status = shadow_git_with_baseline.status()
        assert status.strip() == ""

    def test_status_with_changes(self, shadow_git_with_baseline, tmp_work_dir: Path):
        (tmp_work_dir / "untracked.txt").write_text("hi\n")
        status = shadow_git_with_baseline.status()
        assert "untracked.txt" in status


class TestHardReset:
    def test_reset_to_baseline(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline

        # Modify and add files
        (tmp_work_dir / "main.py").write_text("MODIFIED\n")
        (tmp_work_dir / "extra.txt").write_text("extra\n")

        sg.hard_reset_to("baseline")

        # Original content restored
        assert (tmp_work_dir / "main.py").read_text() == "print('hello')\n"
        # Extra file removed
        assert not (tmp_work_dir / "extra.txt").exists()

    def test_reset_to_snapshot(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline

        (tmp_work_dir / "added.txt").write_text("added in snap\n")
        sg.commit_snapshot("snap1")

        # Add more changes
        (tmp_work_dir / "later.txt").write_text("later\n")

        # Reset to snap1 — should have added.txt but not later.txt
        sg.hard_reset_to("snap1")
        assert (tmp_work_dir / "added.txt").exists()
        assert not (tmp_work_dir / "later.txt").exists()


class TestSessionLifecycle:
    def test_isolated_sessions_preserve_working_dir(self, shadow_git_with_baseline, tmp_work_dir: Path):
        """Isolated mode only resets chat history, not the working directory."""
        sg = shadow_git_with_baseline

        # Session 1: modify a file
        sg.begin_session(1, SessionMode.ISOLATED)
        (tmp_work_dir / "main.py").write_text("session 1 change\n")
        sg.end_session(1)

        # Session 2 (isolated): working directory should keep session 1's changes
        sg.begin_session(2, SessionMode.ISOLATED)
        assert (tmp_work_dir / "main.py").read_text() == "session 1 change\n"

    def test_chained_sessions(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline

        # Session 1: modify a file
        sg.begin_session(1, SessionMode.CHAINED)
        (tmp_work_dir / "main.py").write_text("session 1 change\n")
        sg.end_session(1)

        # Session 2 (chained): should see session 1's changes
        sg.begin_session(2, SessionMode.CHAINED)
        assert (tmp_work_dir / "main.py").read_text() == "session 1 change\n"

    def test_forked_sessions_with_reset(self, shadow_git_with_baseline, tmp_work_dir: Path):
        """Forked session resets to fork point when needs_reset=True."""
        sg = shadow_git_with_baseline

        # Session 1
        sg.begin_session(1, SessionMode.CHAINED)
        (tmp_work_dir / "main.py").write_text("session 1\n")
        sg.end_session(1)

        # Session 2 (first fork from 1) — no reset needed
        sg.begin_session(2, SessionMode.FORKED, fork_from=1, needs_reset=False)
        (tmp_work_dir / "extra.txt").write_text("session 2\n")
        sg.end_session(2)

        # Session 3 (second fork from 1) — needs reset since session 2 modified things
        sg.begin_session(3, SessionMode.FORKED, fork_from=1, needs_reset=True)
        assert (tmp_work_dir / "main.py").read_text() == "session 1\n"
        assert not (tmp_work_dir / "extra.txt").exists()

    def test_forked_sessions_no_reset_when_single(self, shadow_git_with_baseline, tmp_work_dir: Path):
        """Single fork from a point doesn't need a reset."""
        sg = shadow_git_with_baseline

        # Session 1
        sg.begin_session(1, SessionMode.CHAINED)
        (tmp_work_dir / "main.py").write_text("session 1\n")
        sg.end_session(1)

        # Session 2 (only fork from 1) — no reset, working dir already at session 1's state
        sg.begin_session(2, SessionMode.FORKED, fork_from=1, needs_reset=False)
        assert (tmp_work_dir / "main.py").read_text() == "session 1\n"

    def test_end_session_with_replicate(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline
        sg.begin_session(1, SessionMode.ISOLATED)
        (tmp_work_dir / "f.txt").write_text("rep1\n")
        sg.end_session(1, replicate=1)

        # Should have tagged as session_01_r01
        result = sg._git("rev-parse", "session_01_r01", check=False)
        assert result.returncode == 0

    def test_get_session_diff_isolated(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline

        sg.begin_session(1, SessionMode.ISOLATED)
        (tmp_work_dir / "new.txt").write_text("new content\n")
        sg.end_session(1)

        diff = sg.get_session_diff(1, SessionMode.ISOLATED)
        assert "new.txt" in diff
        assert "new content" in diff

    def test_get_session_diff_chained(self, shadow_git_with_baseline, tmp_work_dir: Path):
        sg = shadow_git_with_baseline

        sg.begin_session(1, SessionMode.CHAINED)
        (tmp_work_dir / "a.txt").write_text("a\n")
        sg.end_session(1)

        sg.begin_session(2, SessionMode.CHAINED)
        (tmp_work_dir / "b.txt").write_text("b\n")
        sg.end_session(2)

        # Session 2 diff should only show b.txt, not a.txt
        diff = sg.get_session_diff(2, SessionMode.CHAINED)
        assert "b.txt" in diff
        assert "a.txt" not in diff
