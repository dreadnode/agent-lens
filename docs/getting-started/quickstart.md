# Quick Start

## 1. Create a config

Create a file called `my_experiment.yaml`:

```yaml
model: "claude-sonnet-4-20250514"
provider: anthropic
work_dir: "./repos/my_project"
session_mode: isolated

system_prompt: |
  You are exploring a Python codebase. Use MEMORY.md to keep notes.

sessions:
  - session_index: 1
    prompt: "Explore the project structure. Take notes in MEMORY.md."
  - session_index: 2
    prompt: "Read the main module in detail. Update your notes."
```

## 2. Run it

```bash
harness run my_experiment.yaml
```

The harness will:

1. Initialize a shadow git repo to track all file changes
2. Seed `MEMORY.md` in the working directory
3. Run each session sequentially
4. Save ATIF trajectories, diffs, and metadata to `runs/<run-name>/`

## 3. Inspect results

```bash
# CLI summary
harness inspect runs/<run-name>

# Or browse in the web UI
cd ui && npm run dev
# Open http://localhost:5173
```

## 4. Resample for variance

```bash
# Resample a specific API turn
harness resample runs/<run-name> --session 1 --request 5 --count 10

# Or re-run a full session
harness resample-session runs/<run-name> --session 2 --count 5
```

## Example output

```
$ harness run tests/smoke.yaml

[session 1] starting (mode=isolated)...
[session 1] done -- 15 steps, 5 tool calls, $0.0596

Run complete: runs/2026-03-15T10-30-00_claude-sonnet-4-20250514
```

## Next steps

- [Session Modes](../guide/session-modes.md) — isolated, chained, and forked sessions
- [Resampling & Replay](../guide/resampling.md) — study variance from API-level resampling to full turn-level replay
- [Output Structure](../guide/output.md) — where trajectories, diffs, transcripts, and metadata are stored
- [Configuration](../guide/configuration.md) — full config reference with all fields
- [Subagents](../guide/subagents.md) — delegate work to specialized subagents
