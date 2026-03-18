"""Tests for ShadowGit worktree support."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.shadow_git import ShadowGit


class TestAddWorktree:
    def test_creates_directory(self, shadow_git_with_baseline: ShadowGit, tmp_path: Path):
        sg = shadow_git_with_baseline
        wt = tmp_path / "worktree1"
        result = sg.add_worktree(wt, "baseline")
        assert result == wt.resolve()
        assert wt.exists()

    def test_has_correct_files(self, shadow_git_with_baseline: ShadowGit, tmp_work_dir: Path, tmp_path: Path):
        sg = shadow_git_with_baseline
        wt = tmp_path / "worktree1"
        sg.add_worktree(wt, "baseline")
        # Should have the same files as baseline
        assert (wt / "main.py").read_text() == "print('hello')\n"
        assert (wt / "README.md").read_text() == "# Test Repo\n"

    def test_worktree_from_snapshot(self, shadow_git_with_baseline: ShadowGit, tmp_work_dir: Path, tmp_path: Path):
        sg = shadow_git_with_baseline
        # Modify files and snapshot
        (tmp_work_dir / "main.py").write_text("print('modified')\n")
        (tmp_work_dir / "new_file.txt").write_text("new content\n")
        sg.commit_snapshot("snap1")

        # Worktree from snapshot should have modified content
        wt = tmp_path / "worktree_snap"
        sg.add_worktree(wt, "snap1")
        assert (wt / "main.py").read_text() == "print('modified')\n"
        assert (wt / "new_file.txt").read_text() == "new content\n"

    def test_worktree_from_baseline_after_changes(self, shadow_git_with_baseline: ShadowGit, tmp_work_dir: Path, tmp_path: Path):
        sg = shadow_git_with_baseline
        # Modify files and snapshot
        (tmp_work_dir / "main.py").write_text("print('changed')\n")
        sg.commit_snapshot("later")

        # Worktree from baseline should have original content
        wt = tmp_path / "worktree_baseline"
        sg.add_worktree(wt, "baseline")
        assert (wt / "main.py").read_text() == "print('hello')\n"


class TestRemoveWorktree:
    def test_removes_directory(self, shadow_git_with_baseline: ShadowGit, tmp_path: Path):
        sg = shadow_git_with_baseline
        wt = tmp_path / "worktree_rm"
        sg.add_worktree(wt, "baseline")
        assert wt.exists()
        sg.remove_worktree(wt)
        assert not wt.exists()

    def test_removes_dirty_worktree(self, shadow_git_with_baseline: ShadowGit, tmp_path: Path):
        sg = shadow_git_with_baseline
        wt = tmp_path / "worktree_dirty"
        sg.add_worktree(wt, "baseline")
        # Dirty the worktree
        (wt / "untracked.txt").write_text("dirty\n")
        (wt / "main.py").write_text("modified\n")
        # Should still remove with --force
        sg.remove_worktree(wt)
        assert not wt.exists()


class TestWorktreeIsolation:
    def test_multiple_worktrees_independent(self, shadow_git_with_baseline: ShadowGit, tmp_path: Path):
        sg = shadow_git_with_baseline
        wt1 = tmp_path / "wt1"
        wt2 = tmp_path / "wt2"
        sg.add_worktree(wt1, "baseline")
        sg.add_worktree(wt2, "baseline")

        # Modify one worktree
        (wt1 / "main.py").write_text("changed in wt1\n")

        # Other worktree should be unaffected
        assert (wt2 / "main.py").read_text() == "print('hello')\n"

        sg.remove_worktree(wt1)
        sg.remove_worktree(wt2)

    def test_worktree_does_not_affect_work_dir(self, shadow_git_with_baseline: ShadowGit, tmp_work_dir: Path, tmp_path: Path):
        sg = shadow_git_with_baseline
        wt = tmp_path / "wt_isolated"
        sg.add_worktree(wt, "baseline")

        # Modify worktree
        (wt / "main.py").write_text("worktree change\n")

        # Original work_dir should be unaffected
        assert (tmp_work_dir / "main.py").read_text() == "print('hello')\n"

        sg.remove_worktree(wt)

    def test_worktrees_from_different_refs(self, shadow_git_with_baseline: ShadowGit, tmp_work_dir: Path, tmp_path: Path):
        sg = shadow_git_with_baseline

        # Create a snapshot with modifications
        (tmp_work_dir / "main.py").write_text("snapshot version\n")
        sg.commit_snapshot("v2")

        wt_baseline = tmp_path / "wt_base"
        wt_v2 = tmp_path / "wt_v2"
        sg.add_worktree(wt_baseline, "baseline")
        sg.add_worktree(wt_v2, "v2")

        assert (wt_baseline / "main.py").read_text() == "print('hello')\n"
        assert (wt_v2 / "main.py").read_text() == "snapshot version\n"

        sg.remove_worktree(wt_baseline)
        sg.remove_worktree(wt_v2)
