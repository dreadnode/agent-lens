"""Shared fixtures for harness tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def tmp_work_dir(tmp_path: Path) -> Path:
    """Create a temporary working directory with some files."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "main.py").write_text("print('hello')\n")
    (work / "README.md").write_text("# Test Repo\n")
    return work


@pytest.fixture
def tmp_git_dir(tmp_path: Path) -> Path:
    """Path for shadow git bare repo."""
    return tmp_path / ".shadow_git"


@pytest.fixture
def shadow_git(tmp_work_dir: Path, tmp_git_dir: Path):
    """Initialized ShadowGit instance."""
    from harness.shadow_git import ShadowGit

    sg = ShadowGit(work_dir=tmp_work_dir, git_dir=tmp_git_dir)
    sg.init()
    return sg


@pytest.fixture
def shadow_git_with_baseline(shadow_git):
    """ShadowGit with baseline committed."""
    shadow_git.commit_baseline()
    return shadow_git
