# AgentLens

Harness for running multi-session Claude Code experiments and capturing trajectories in ATIF format. Built for AI alignment and interpretability research.

## Project structure

```
src/harness/
  config.py          # Pydantic models: RunConfig, SessionConfig, AgentConfig
  cli.py             # Typer CLI: harness run/list/inspect/resample/replay
  experiment.py      # Multi-session orchestrator
  runner.py          # Single session executor (Claude Agent SDK)
  atif_adapter.py    # SDK messages → ATIF steps
  state.py           # Per-step write tracking via shadow git
  shadow_git.py      # Shadow git: invisible change tracking for working directory
  proxy.py           # Reverse proxy for raw API request capture
  resample.py        # Turn-level resample implementation
  resample_session.py # Session-level resample implementation
  transcript.py      # Transcript parser and truncation for turn-level replay
  uuid_map.py        # UUID map: correlates transcript, ATIF, and raw API dumps
  replay.py          # Turn-level replay orchestrator

ui/                  # SvelteKit web UI for exploring runs
  src/routes/        # Pages: runs list, session viewer, resamples
  src/lib/           # Components, server utils, types

examples/            # Example configs (isolated.yaml, chained.yaml)
tests/               # Test configs (smoke.yaml, subagent.yaml)
experiments/         # Real experiment configs
repos/               # Target repos/working directories for experiments
runs/                # Output directory (gitignored)
```

## Running experiments

```bash
harness run <config.yaml>                    # Run experiment
harness run config.yaml --tag my-tag         # With tag
harness run config.yaml --run-name my-run    # Custom name
harness list                                 # List runs
harness inspect runs/<name>                  # Inspect run
harness replay runs/<name> --session 1 --turn 5 --count 3  # Replay from turn
harness replay runs/<name> --session 1 --list-turns         # List turns
```

## Config format (YAML)

Required fields: `model`, `work_dir`, `sessions`

```yaml
model: "claude-sonnet-4-20250514"      # Anthropic model name
provider: anthropic                     # anthropic | openrouter | bedrock | vertex
work_dir: "./repos/my_repo"            # Working directory (any directory, not just repos)
session_mode: isolated                  # isolated | chained | forked
system_prompt: "..."                    # Shared system prompt
max_turns: 30                           # Per-session turn limit
permission_mode: bypassPermissions      # acceptEdits | bypassPermissions
capture_api_requests: true              # Required for resampling
max_budget_usd: 2.00                    # Spend cap per session
tags: ["tag1"]

memory_file: "MEMORY.md"               # Auto-seeded memory file (default: MEMORY.md)
memory_seed: "# Notes\n"               # Initial content for memory file
revert_work_dir: true                  # Reset working directory after run (default: false)

sessions:
  - session_index: 1
    prompt: "..."
  - session_index: 2
    prompt: "..."

agents:                                 # Subagents (optional)
  - name: "explorer"
    description: "When to use this agent"
    prompt: "System prompt for subagent"
    tools: ["Read", "Glob", "Grep"]     # null = inherit all
    model: "sonnet"                     # sonnet | opus | haiku | inherit
```

### Shadow git (change tracking)

All file changes in the working directory are tracked automatically via a shadow git repo stored in the run output directory (`.shadow_git/`). The agent never sees this repo — it uses `GIT_DIR`/`GIT_WORK_TREE` env vars to stay invisible.

This enables:
- **Full diffs**: every file change is captured, not just declared files
- **Turn-level replay**: git worktrees provide isolated filesystem copies at any turn's state for parallel replay
- **Per-step attribution**: file writes are detected after each tool-using step

### Session modes
- **isolated**: Fresh conversation each session, working directory unchanged
- **chained**: Conversation resumes from previous session, working directory unchanged
- **forked**: Sessions 2+ reset working directory to the state after session 1 (or specified fork point)

### Providers
- `anthropic` (default): needs `ANTHROPIC_API_KEY` or Claude Code subscription
- `openrouter`: needs `OPENROUTER_API_KEY`
- `bedrock`: uses AWS credentials
- `vertex`: uses GCP credentials

## Web UI

```bash
cd ui && npm run dev
```

Browse runs at `http://localhost:5173/runs/`. Features: trajectory viewer, file diffs, resample viewer with edit & resample (intervention testing).

## Dev commands

```bash
uv sync                              # Install Python deps
cd ui && npm install                  # Install UI deps
cd ui && npx svelte-check             # Type check UI
harness run tests/smoke.yaml          # Smoke test
```

## Key conventions

- Session indices start at 1 and must be contiguous
- Config validation is done by Pydantic (see `src/harness/config.py`)
- Configs go in `experiments/` for real experiments, `tests/` for test configs
- Always set `capture_api_requests: true` if you want to resample or inspect raw API calls
- Always set `permission_mode: bypassPermissions` for unattended runs
- MEMORY.md is automatically seeded in the working directory (configurable via `memory_file`/`memory_seed`)
- The UI reads from `runs/` directory; run name becomes the URL slug
