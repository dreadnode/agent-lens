"""File state tracking via shadow git.

Uses the shadow git index as the "cache" for detecting per-step writes.
After each write check, changes are staged so the next check only sees
new modifications.

Two levels of granularity:
1. Session diffs: full unified diff via shadow git (replaces snapshots)
2. Per-step write log: fine-grained attribution of changes to step_ids
"""

from __future__ import annotations

import difflib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from harness.shadow_git import ShadowGit

__all__ = ["WriteEvent", "StateManager"]

logger = logging.getLogger(__name__)


def _safe_read_text(path: Path) -> str:
    """Read a file as UTF-8, returning a placeholder for binary/undecodable files."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        logger.warning("Cannot read %s as UTF-8 text; treating as binary.", path)
        return f"[binary file: {path.name}]"


@dataclass
class WriteEvent:
    """A single file write detected between steps."""

    timestamp: str
    session_index: int
    step_id: int
    file_path: str
    diff: str
    content_before: str
    content_after: str
    diff_stats: dict[str, int]


class StateManager:
    """Manages file state tracking via shadow git."""

    def __init__(self, work_dir: Path, shadow_git: ShadowGit):
        self.work_dir = work_dir
        self.shadow_git = shadow_git
        self.write_log: list[WriteEvent] = []

    def seed_memory(self, memory_file: str, memory_seed: str) -> None:
        """Write seed content to the memory file if it doesn't exist."""
        target = self.work_dir / memory_file
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(memory_seed)

    def check_for_writes(self, session_index: int, step_id: int) -> list[WriteEvent]:
        """Detect file changes since last check using shadow git.

        Uses the git index as the reference point.  After detecting changes,
        stages them so the next call only sees new modifications.
        """
        changed_files = self.shadow_git.diff_working_names()
        if not changed_files:
            return []

        new_events: list[WriteEvent] = []
        for file_path in changed_files:
            full_path = self.work_dir / file_path

            # Get content before (from git index / HEAD)
            before = self.shadow_git.show_file("HEAD", file_path)
            if before is None:
                before = ""

            # Get content after (current disk state)
            if full_path.exists():
                after = _safe_read_text(full_path)
            else:
                after = ""  # file was deleted

            event = self._create_write_event(
                session_index, step_id, file_path, before, after
            )
            new_events.append(event)

        # Stage changes — the git index becomes the new baseline for next check.
        # diff_working_names() already called git add -A, so index is current.
        self.shadow_git.commit_snapshot(
            tag=f"_step_{session_index}_{step_id}",
            message=f"step {step_id} (session {session_index})",
        )

        self.write_log.extend(new_events)
        return new_events

    def _create_write_event(
        self,
        session_index: int,
        step_id: int,
        file_path: str,
        before: str,
        after: str,
    ) -> WriteEvent:
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=file_path,
                tofile=file_path,
            )
        )
        lines = diff.splitlines()
        added = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))

        return WriteEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_index=session_index,
            step_id=step_id,
            file_path=file_path,
            diff=diff,
            content_before=before,
            content_after=after,
            diff_stats={"added": added, "removed": removed},
        )

    def save_changelog(self, dest: Path) -> None:
        """Write all write events to a JSONL file."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w") as f:
            for event in self.write_log:
                f.write(json.dumps(asdict(event), default=str) + "\n")
