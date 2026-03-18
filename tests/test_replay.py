"""Tests for replay — _determine_reset_tag and worktree filesystem reset."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.replay import _determine_reset_tag
from harness.shadow_git import ShadowGit


# ---------------------------------------------------------------------------
# _determine_reset_tag
# ---------------------------------------------------------------------------


class TestDetermineResetTag:
    def test_turn_1_returns_baseline(self):
        assert _determine_reset_tag(None, 1) == "baseline"

    def test_no_uuid_map_returns_baseline(self):
        assert _determine_reset_tag(None, 5) == "baseline"

    def test_empty_uuid_map_returns_baseline(self):
        assert _determine_reset_tag({"turns": []}, 3) == "baseline"

    def test_finds_tag_at_previous_turn(self):
        uuid_map = {
            "turns": [
                {"turn_index": 1, "shadow_git_tag": "_step_1_1"},
                {"turn_index": 2, "shadow_git_tag": "_step_1_3"},
                {"turn_index": 3},  # no tag
                {"turn_index": 4, "shadow_git_tag": "_step_1_7"},
            ]
        }
        # Replaying from turn 3 → should find _step_1_3 (turn 2)
        assert _determine_reset_tag(uuid_map, 3) == "_step_1_3"

    def test_walks_back_past_tagless_turns(self):
        uuid_map = {
            "turns": [
                {"turn_index": 1, "shadow_git_tag": "_step_1_1"},
                {"turn_index": 2},  # no tag
                {"turn_index": 3},  # no tag
                {"turn_index": 4},  # no tag
            ]
        }
        # Replaying from turn 4 → walks back to turn 1
        assert _determine_reset_tag(uuid_map, 4) == "_step_1_1"

    def test_no_tags_before_turn_returns_baseline(self):
        uuid_map = {
            "turns": [
                {"turn_index": 1},  # no tag
                {"turn_index": 2},  # no tag
                {"turn_index": 3, "shadow_git_tag": "_step_1_5"},
            ]
        }
        # Replaying from turn 2 → only turn 1 is before, and it has no tag
        assert _determine_reset_tag(uuid_map, 2) == "baseline"

    def test_uses_most_recent_tag(self):
        uuid_map = {
            "turns": [
                {"turn_index": 1, "shadow_git_tag": "_step_1_1"},
                {"turn_index": 2, "shadow_git_tag": "_step_1_3"},
                {"turn_index": 3, "shadow_git_tag": "_step_1_5"},
                {"turn_index": 4},
            ]
        }
        # Replaying from turn 4 → should get _step_1_5 (most recent)
        assert _determine_reset_tag(uuid_map, 4) == "_step_1_5"

    def test_session_gt_1_no_tags_falls_back_to_prior_session(self):
        uuid_map = {
            "turns": [
                {"turn_index": 1},
                {"turn_index": 2},
            ]
        }
        # Session 3, no tags in this session → fall back to session_02
        assert _determine_reset_tag(uuid_map, 2, session_index=3) == "session_02"

    def test_session_gt_1_turn_1_falls_back_to_prior_session(self):
        # Session 2, turn 1 → fall back to session_01
        assert _determine_reset_tag(None, 1, session_index=2) == "session_01"

    def test_session_gt_1_with_tag_uses_tag(self):
        uuid_map = {
            "turns": [
                {"turn_index": 1, "shadow_git_tag": "_step_3_1"},
                {"turn_index": 2},
            ]
        }
        # Session 3 has a tag at turn 1 → use it, not the session fallback
        assert _determine_reset_tag(uuid_map, 2, session_index=3) == "_step_3_1"

    def test_session_1_no_tags_falls_back_to_baseline(self):
        uuid_map = {
            "turns": [
                {"turn_index": 1},
                {"turn_index": 2},
            ]
        }
        # Session 1, no tags → baseline (original behavior)
        assert _determine_reset_tag(uuid_map, 2, session_index=1) == "baseline"


# ---------------------------------------------------------------------------
# Worktree filesystem reset to correct turn state
# ---------------------------------------------------------------------------


class TestReplayFilesystemReset:
    """Test that worktrees checked out at step tags have the correct file state."""

    def test_worktree_at_baseline_has_original_files(
        self, shadow_git_with_baseline: ShadowGit, tmp_work_dir: Path, tmp_path: Path
    ):
        sg = shadow_git_with_baseline
        wt = tmp_path / "wt_baseline"
        sg.add_worktree(wt, "baseline")

        assert (wt / "main.py").read_text() == "print('hello')\n"
        assert (wt / "README.md").read_text() == "# Test Repo\n"

        sg.remove_worktree(wt)

    def test_worktree_at_step_tag_has_modified_files(
        self, shadow_git_with_baseline: ShadowGit, tmp_work_dir: Path, tmp_path: Path
    ):
        sg = shadow_git_with_baseline

        # Simulate step 3 writing to a file
        (tmp_work_dir / "main.py").write_text("print('step 3')\n")
        sg.commit_snapshot("_step_1_3", message="step 3")

        # Simulate step 5 writing more
        (tmp_work_dir / "main.py").write_text("print('step 5')\n")
        (tmp_work_dir / "notes.md").write_text("# Notes\nSome findings\n")
        sg.commit_snapshot("_step_1_5", message="step 5")

        # Worktree at step 3 should see step 3's state
        wt3 = tmp_path / "wt_step3"
        sg.add_worktree(wt3, "_step_1_3")
        assert (wt3 / "main.py").read_text() == "print('step 3')\n"
        assert not (wt3 / "notes.md").exists()  # not created until step 5

        # Worktree at step 5 should see step 5's state
        wt5 = tmp_path / "wt_step5"
        sg.add_worktree(wt5, "_step_1_5")
        assert (wt5 / "main.py").read_text() == "print('step 5')\n"
        assert (wt5 / "notes.md").read_text() == "# Notes\nSome findings\n"

        sg.remove_worktree(wt3)
        sg.remove_worktree(wt5)

    def test_worktree_at_earlier_step_does_not_have_later_changes(
        self, shadow_git_with_baseline: ShadowGit, tmp_work_dir: Path, tmp_path: Path
    ):
        sg = shadow_git_with_baseline

        # Step 1: create MEMORY.md
        (tmp_work_dir / "MEMORY.md").write_text("# Notes\n")
        sg.commit_snapshot("_step_1_1", message="step 1")

        # Step 3: update MEMORY.md with findings
        (tmp_work_dir / "MEMORY.md").write_text("# Notes\n## Findings\n- Found a bug\n")
        sg.commit_snapshot("_step_1_3", message="step 3")

        # Step 5: further updates
        (tmp_work_dir / "MEMORY.md").write_text("# Notes\n## Findings\n- Found a bug\n- Fixed it\n## Summary\nDone.\n")
        sg.commit_snapshot("_step_1_5", message="step 5")

        # Replaying from turn 2: reset_tag would be _step_1_1
        wt = tmp_path / "wt_replay"
        sg.add_worktree(wt, "_step_1_1")

        # Should only have step 1's content
        assert (wt / "MEMORY.md").read_text() == "# Notes\n"
        # Original files still present
        assert (wt / "main.py").read_text() == "print('hello')\n"

        sg.remove_worktree(wt)

    def test_parallel_worktrees_at_same_tag_are_independent(
        self, shadow_git_with_baseline: ShadowGit, tmp_work_dir: Path, tmp_path: Path
    ):
        sg = shadow_git_with_baseline

        (tmp_work_dir / "MEMORY.md").write_text("# Notes\n")
        sg.commit_snapshot("_step_1_1", message="step 1")

        # Create 3 worktrees at the same tag (simulating count=3 replay)
        worktrees = []
        for i in range(1, 4):
            wt = tmp_path / f"rep_{i:02d}"
            sg.add_worktree(wt, "_step_1_1")
            worktrees.append(wt)

        # Each starts with the same state
        for wt in worktrees:
            assert (wt / "MEMORY.md").read_text() == "# Notes\n"

        # Simulate each replicate diverging
        (worktrees[0] / "MEMORY.md").write_text("# Notes\nReplicate 1 findings\n")
        (worktrees[1] / "MEMORY.md").write_text("# Notes\nReplicate 2 findings\n")
        (worktrees[2] / "MEMORY.md").write_text("# Notes\nReplicate 3 findings\n")

        # Each worktree has its own state
        assert "Replicate 1" in (worktrees[0] / "MEMORY.md").read_text()
        assert "Replicate 2" in (worktrees[1] / "MEMORY.md").read_text()
        assert "Replicate 3" in (worktrees[2] / "MEMORY.md").read_text()

        # Original work_dir is untouched
        assert (tmp_work_dir / "MEMORY.md").read_text() == "# Notes\n"

        for wt in worktrees:
            sg.remove_worktree(wt)

    def test_determine_reset_tag_integrated_with_worktree(
        self, shadow_git_with_baseline: ShadowGit, tmp_work_dir: Path, tmp_path: Path
    ):
        """End-to-end: build a uuid_map-like structure, determine the tag, checkout worktree."""
        sg = shadow_git_with_baseline

        # Simulate a 4-turn session
        # Turn 1: Read only (no file writes)
        # Turn 2: Writes to MEMORY.md
        (tmp_work_dir / "MEMORY.md").write_text("# Notes\nTurn 2 notes\n")
        sg.commit_snapshot("_step_1_3", message="turn 2 writes")

        # Turn 3: Read only (no file writes)
        # Turn 4: Writes more
        (tmp_work_dir / "MEMORY.md").write_text("# Notes\nTurn 2 notes\nTurn 4 notes\n")
        sg.commit_snapshot("_step_1_7", message="turn 4 writes")

        uuid_map = {
            "turns": [
                {"turn_index": 1},  # no tag (read only)
                {"turn_index": 2, "shadow_git_tag": "_step_1_3"},
                {"turn_index": 3},  # no tag (read only)
                {"turn_index": 4, "shadow_git_tag": "_step_1_7"},
            ]
        }

        # Replay from turn 3: should reset to _step_1_3 (after turn 2's writes)
        tag = _determine_reset_tag(uuid_map, 3)
        assert tag == "_step_1_3"

        wt = tmp_path / "wt_replay_t3"
        sg.add_worktree(wt, tag)
        assert (wt / "MEMORY.md").read_text() == "# Notes\nTurn 2 notes\n"

        sg.remove_worktree(wt)

        # Replay from turn 1: should reset to baseline
        tag1 = _determine_reset_tag(uuid_map, 1)
        assert tag1 == "baseline"

        wt1 = tmp_path / "wt_replay_t1"
        sg.add_worktree(wt1, tag1)
        assert not (wt1 / "MEMORY.md").exists()  # didn't exist at baseline

        sg.remove_worktree(wt1)
