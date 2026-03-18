# AgentLens

Developed at [MATS Exploration Phase](https://www.matsprogram.org/) under [Neel Nanda](https://github.com/neelnanda-io), for a research project with [Greg Kocher](https://github.com/gregkocher).

A harness for running multi-session agent trajectories using the Claude Agent SDK, capturing them in [ATIF](https://harborframework.com/docs/agents/trajectory-format) (Agent Trajectory Interchange Format), and tracking file state changes across sessions.

Built for AI alignment and interpretability research — studying how LLM agents behave across multi-turn, multi-session, multi-agent interactions.

> **Note:** AgentLens currently supports Claude Code via the Claude Agent SDK. Support for additional agents and frameworks is planned — see [Roadmap](#roadmap). Some features (especially turn-level replay) are experimental. We welcome PRs and contributions — [open an issue](https://github.com/dreadnode/agent-lens/issues) if you run into bugs.

## What it does

The harness takes a YAML config describing a sequence of sessions (prompts to an agent), runs each session against a working directory via the Claude Agent SDK, and produces structured outputs:

- **ATIF trajectories** — standardized JSON capturing every agent step, tool call, observation, and thinking block
- **Shadow git change tracking** — automatic tracking of all file changes via an invisible git repo, with per-step write attribution and full unified diffs
- **Session chaining** — three modes for controlling how sessions relate to each other (isolated, chained, forked)
- **Resampling & replay** — study behavioral variance at multiple levels: stateless API resampling, intervention testing (edit assistant text, tool results, or system prompts and resample), session-level resampling, and turn-level replay with full tool execution from any branch point
- **Subagent capture** — separate ATIF trajectories for each subagent invocation, linked to the parent via `SubagentTrajectoryRef`

## Install

Requires Python >= 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone <this-repo>
cd agentlens
uv sync
```

## Quick start

Set your API key (see [Providers](#providers) for all options):

```bash
export OPENROUTER_API_KEY=sk-or-...
```

Run the smoke test:

```bash
harness run tests/smoke.yaml
```

Inspect results:

```bash
harness inspect runs/<run-name>
```

Browse in the web UI:

```bash
cd ui && npm install && npm run dev
# Open http://localhost:5173
```

## Providers

The harness uses the [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/) to run Claude Code sessions programmatically. **Only Claude models are supported** — the SDK speaks the Anthropic Messages API protocol and cannot run non-Claude models. Set the `provider` field in your config to choose how to route API calls.

| Provider | Config value | Env var | Notes |
|----------|-------------|---------|-------|
| [OpenRouter](https://openrouter.ai) | `openrouter` (default) | `OPENROUTER_API_KEY` | Routes through OpenRouter. The harness sets `ANTHROPIC_BASE_URL` automatically. |
| [Anthropic](https://console.anthropic.com) | `anthropic` | `ANTHROPIC_API_KEY` | Direct Anthropic API. The SDK reads the key from the environment. |
| [AWS Bedrock](https://aws.amazon.com/bedrock/) | `bedrock` | Standard AWS credentials (`AWS_ACCESS_KEY_ID`, etc.) | Sets `CLAUDE_CODE_USE_BEDROCK=1`. |
| [GCP Vertex AI](https://cloud.google.com/vertex-ai) | `vertex` | Standard GCP credentials (`GOOGLE_APPLICATION_CREDENTIALS`, etc.) | Sets `CLAUDE_CODE_USE_VERTEX=1`. |

You can also set `base_url` in your config to point at a custom Anthropic-compatible endpoint.

If no API key is set, the SDK will use your Claude Code subscription credentials from `~/.claude/credentials.json` (requires Claude Pro/Max). Usage is covered by your subscription with rate limits rather than per-token billing.

> **Cost reporting caveat:** Cost figures in `run_meta.json` and the web UI come from the SDK and are based on Anthropic's list pricing regardless of provider. They may not match your actual bill (especially on OpenRouter, Bedrock, or Vertex) and are purely informational when using a Claude Code subscription.

Example configs:

```yaml
# OpenRouter (default)
model: "claude-sonnet-4-20250514"
provider: openrouter

# Anthropic direct
model: "claude-sonnet-4-20250514"
provider: anthropic
```

## Configuration

Experiments are defined as YAML config files. Here's a full example:

```yaml
model: "claude-sonnet-4-20250514"
provider: openrouter                    # openrouter | anthropic | bedrock | vertex
hypothesis: "The agent preserves hedging across sessions"  # what this experiment tests
work_dir: "./repos/my_project"          # working directory the agent operates in
session_mode: chained                   # isolated | chained | forked
tags: ["experiment-1"]

system_prompt: |
  You are exploring a Python codebase. Use MEMORY.md to keep notes.

allowed_tools:                          # Claude Code tools the agent can use
  - Read
  - Grep
  - Glob
  - Bash
  - Write
  - Edit

max_turns: 30                           # max agent turns per session
permission_mode: bypassPermissions      # acceptEdits | bypassPermissions
max_budget_usd: 1.00                    # optional spend cap per session
load_project_settings: false            # whether to load the repo's CLAUDE.md

memory_file: "MEMORY.md"               # auto-seeded file in working dir (default: MEMORY.md)
memory_seed: "# Project Notes\n"        # initial content if file doesn't exist
revert_work_dir: true                  # reset working dir after run (default: false)

sessions:
  - session_index: 1
    prompt: "Explore the project structure. Take notes in MEMORY.md."
  - session_index: 2
    prompt: "Read the main module in detail. Update your notes."
  - session_index: 3
    prompt: "Summarize what you know about this project."
    max_turns: 10                       # per-session override
```

### Shadow git (change tracking)

All file changes in the working directory are tracked automatically via a **shadow git** — a bare git repo stored in the run output directory (`.shadow_git/`). The agent never sees this repo; it uses `GIT_DIR`/`GIT_WORK_TREE` env vars to stay invisible.

This enables:
- **Full diffs** — every file change is captured automatically, no need to declare files upfront
- **Turn-level replay** — git worktrees provide isolated filesystem copies at any turn's state for parallel replay execution
- **Per-step attribution** — file writes are detected after each tool-using step and logged to `state_changelog.jsonl`
- **Session diffs** — unified patches showing what each session changed, saved as `session_diff.patch`

The working directory does not need to be a git repo. The shadow git works with any directory.

### Automatic behaviors

- **Memory file is auto-seeded.** The harness creates `MEMORY.md` (or whatever `memory_file` is set to) with the `memory_seed` content if it doesn't already exist.
- **Working directory path is injected into the system prompt.** The harness appends the absolute path and memory file location to the system prompt so the agent knows where to read/write.
- **The agent's cwd is the working directory.** Set to the resolved `work_dir`.

### Session modes

| Mode | Behavior | Shadow git action |
|------|----------|-------------------|
| `isolated` | Each session starts with a fresh conversation. File changes persist. | No reset |
| `chained` | Each session resumes from the previous session's conversation. Full context preserved. | Changes accumulate (no reset) |
| `forked` | Sessions 2+ fork from session 1. Each sees session 1's context but not each other's. | Reset to session 1's end state |

### Flexible forking with `fork_from`

For more control than `session_mode: forked` provides, use `fork_from` on individual sessions to fork from any prior session — not just session 1:

```yaml
session_mode: isolated   # fork_from overrides session_mode per-session

sessions:
  - session_index: 1
    prompt: "Explore the codebase and take notes in MEMORY.md"
  - session_index: 2
    prompt: "Write a security analysis based on your notes"
    fork_from: 1         # forks from session 1's conversation
  - session_index: 3
    prompt: "Write a performance analysis based on your notes"
    fork_from: 1         # also forks from session 1 (independent of session 2)
```

`fork_from` must reference a session with a lower index. It works with any `session_mode` — when set, it overrides the mode for that session.

### Session resampling with `count`

To study behavioral variance, run the same forked session multiple times:

```yaml
sessions:
  - session_index: 1
    prompt: "Explore the codebase and take notes"
  - session_index: 2
    prompt: "Write a security analysis based on your notes"
    fork_from: 1
    count: 5             # run 5 replicates of this session
```

Replicates use a `_rNN` suffix on the session directory:

```
session_01/              # session 1 (count=1, no suffix)
session_02_r01/          # session 2, replicate 1 of 5
session_02_r02/          # session 2, replicate 2 of 5
...
session_02_r05/          # session 2, replicate 5 of 5
```

Sessions with `count: 1` (the default) use the normal `session_NN/` directory name. You can also add replicates to an existing run after the fact using `harness resample-session`.

### Subagents

The harness can define subagents that the main agent delegates work to via the `Agent` tool. When `capture_subagent_trajectories` is enabled (the default), each subagent invocation produces a separate ATIF trajectory file linked to the parent via `SubagentTrajectoryRef`.

```yaml
agents:
  - name: "code-explorer"
    description: "Explores code structure, reads files, and reports findings."
    prompt: "You are a code exploration specialist. Read files and report structure."
    tools: ["Read", "Glob", "Grep"]    # tool restrictions (null = inherit all)
    model: "sonnet"                     # sonnet | opus | haiku | inherit
```

Each agent in `agents` has:

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | yes | — | Agent name (used as key in SDK's agents dict) |
| `description` | yes | — | When to use this agent (shown to the parent) |
| `prompt` | yes | — | System prompt for the subagent |
| `tools` | no | inherit all | Tool restrictions for the subagent |
| `model` | no | inherit | Model override: `sonnet`, `opus`, `haiku`, or `inherit` |

The `Agent` tool is automatically added to `allowed_tools` when `agents` is non-empty.

Subagent messages are filtered from the parent trajectory to keep it clean. The parent's observation result for the `Agent` tool call includes a `subagent_trajectory_ref` pointing to the separate subagent trajectory file.

### Config reference

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `model` | yes | — | Claude model identifier (e.g. `claude-sonnet-4-20250514`). Use Anthropic model names, not OpenRouter-format names. |
| `provider` | no | `openrouter` | API provider: `openrouter`, `anthropic`, `bedrock`, `vertex` |
| `base_url` | no | — | Custom API base URL (overrides provider default) |
| `hypothesis` | no | — | One-sentence hypothesis this experiment tests. Shown in the web UI and saved to `run_meta.json`. |
| `work_dir` | yes | — | Working directory the agent operates in (any directory, not just repos) |
| `repo_name` | no | — | Human-readable name for the working directory |
| `sessions` | yes | — | List of `SessionConfig` objects |
| `session_mode` | no | `isolated` | `isolated`, `chained`, or `forked` |
| `system_prompt` | no | — | System prompt for all sessions |
| `allowed_tools` | no | Read, Grep, Glob, Bash, Write, Edit | Tools the agent can use |
| `max_turns` | no | `50` | Max agent turns per session |
| `permission_mode` | no | `bypassPermissions` | `acceptEdits` or `bypassPermissions` |
| `memory_file` | no | `MEMORY.md` | File to auto-seed in working directory |
| `memory_seed` | no | `# Notes\n` | Initial content for the memory file |
| `max_budget_usd` | no | — | Per-session spend cap |
| `revert_work_dir` | no | `false` | Reset working directory to pre-run state after the run completes |
| `load_project_settings` | no | `false` | Load repo's CLAUDE.md and .claude/settings.json |
| `agents` | no | `[]` | Subagent definitions (see [Subagents](#subagents)) |
| `capture_subagent_trajectories` | no | `true` | Save separate ATIF trajectories for each subagent invocation |
| `capture_api_requests` | no | `true` | Capture raw API requests via proxy (enables resampling and intervention testing) |
| `run_name` | no | auto-generated | Custom name for the run directory |
| `tags` | no | `[]` | Metadata tags |

Each session in `sessions` has:

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `session_index` | yes | — | Sequential index starting at 1 |
| `prompt` | yes | — | The user prompt for this session |
| `system_prompt` | no | — | Per-session system prompt override |
| `max_turns` | no | — | Per-session max turns override |
| `fork_from` | no | — | Session index to fork from (must be lower). Overrides `session_mode` for this session. |
| `count` | no | `1` | Run this session N times as independent replicates. Directories get `_rNN` suffix. |

## CLI

```
harness run <config.yaml>                Run an experiment
harness list [--json]                    List completed runs
harness inspect <run_dir> [--json]       Show run details
harness resample <run_dir> --session N --request N --count N           Resample an API turn
harness resample-edit <run_dir> --session N --request N --dump/--input Edit & resample
harness resample-session <run_dir> --session N --count N               Re-run a session N times
harness replay <run_dir> --session N --turn N --count N                Replay from a turn
```

### `harness run`

```bash
harness run examples/isolated.yaml \
  --model anthropic/claude-sonnet-4 \
  --tag baseline \
  --session-mode chained \
  --run-name my-run-01 \
  --runs-dir ./output \
  --no-capture                          # disable API capture (disables resampling)
```

### `harness inspect`

```
$ harness inspect runs/smoke-test-01

Run: smoke-test-01
Model: anthropic/claude-sonnet-4 (openrouter)
Mode: isolated
Tags: smoke-test
Total: 15 steps, 5 tool calls
Cost: $0.0596
File writes: 1

  Session 1: 15 steps, 5 tool calls  $0.0596

File changes:
  session 1, step 15: MEMORY.md (+9/-0)
```

### `harness resample`

Replay a specific API turn N times to study output variance:

```bash
# Discover available requests
harness resample runs/my-run --session 1 --list-requests

# Resample request 5 ten times
harness resample runs/my-run --session 1 --request 5 --count 10

# Resample from a replicate session
harness resample runs/my-run --session 2 --replicate 3 --request 5 --count 5
```

Resample results are saved to `session_NN/resamples/request_NNN/` and can be viewed in the web UI.

### `harness resample-edit`

Edit a captured API request and resample with the modified version — the CLI equivalent of the web UI's "Edit & Resample". Designed for scriptable intervention testing.

```bash
# Step 1: Dump the request for editing
harness resample-edit runs/my-run --session 1 --request 5 --dump > edit.json

# Step 2: Edit the JSON (assistant text, tool results, system prompt...)
# Step 3: Resample with the modified request
harness resample-edit runs/my-run --session 1 --request 5 \
  --input edit.json --label "removed hedging" --count 5
```

Pipe through `jq` for programmatic edits:

```bash
harness resample-edit runs/my-run --session 1 --request 5 --dump \
  | jq '.system = "You are a cautious engineer. Double-check everything."' \
  | harness resample-edit runs/my-run --session 1 --request 5 \
      --input - --label "cautious prompt" --count 10
```

> **Note:** Thinking blocks cannot be edited — they carry cryptographic signatures validated by the API. See [Thinking blocks](docs/guide/resampling.md#thinking-blocks-not-editable) for details.

Variants are saved alongside vanilla resamples and appear in the web UI.

### `harness resample-session`

Re-run a forked session N times to study behavioral variance across full trajectories:

```bash
harness resample-session runs/my-run --session 2 --count 5
```

This finds session 2's `fork_from` target, resolves the session ID to fork from, and runs 5 new replicates. New session directories are appended (auto-incrementing from existing replicates), and `run_meta.json` is updated.

### `harness replay`

> **Experimental.** Turn-level replay with git worktree filesystem reset is new and likely has bugs. If you run into issues, please [open an issue](https://github.com/dreadnode/agent-lens/issues).

Replay a session from any API turn with full tool execution. Each replicate runs in an isolated git worktree, so multiple replicates execute in parallel. Each replay becomes a new independent run with full provenance back to the source.

```bash
# List available turns
harness replay runs/my-run --session 1 --list-turns

# Replay from turn 5, three times (only session 1 runs)
harness replay runs/my-run --session 1 --turn 5 --count 3

# Replay session 1 turn 5, then continue with sessions 2, 3, etc.
harness replay runs/my-run --session 1 --turn 5 --continue-sessions

# Replay with an additional prompt after tool results
harness replay runs/my-run --session 1 --turn 5 --prompt "Try a different approach"
```

By default, replay only runs the targeted session. Use `--continue-sessions` to also run subsequent sessions from the original config.

Replay creates new run directories (e.g. `replay_my-run_s1_t5_r01_<timestamp>/`) with full artifacts. Each includes a `replay_meta.json` with provenance linking back to the source run, session, and turn. The source working directory is never modified.

## Web UI

A SvelteKit web UI for browsing runs, trajectories, memory diffs, and resamples:

```bash
cd ui
npm install
npm run dev
```

Open `http://localhost:5173`. The UI reads from the `runs/` directory and provides:

- **Run list** — searchable/filterable list of all runs with model, cost, session count
- **Run overview** — metrics, session list with fork relationships, hypothesis display
- **Trajectory viewer** — full chat view with thinking blocks, tool calls, and observations
- **Memory diff** — before/after diffs of the memory file per session
- **API captures** — request/response viewer with token usage, system prompts, tool definitions, compaction events
- **Subagent viewer** — separate trajectory view for each subagent, with task prompt and return value
- **Resamples** — compare N resample outputs for a given API turn
- **Edit & Resample** — interactive message editor for intervention testing: edit assistant text, tool results, or system prompts in the conversation, then resample with the modified input to study how changes affect behavior (thinking blocks are shown read-only — see [why](docs/guide/resampling.md#thinking-blocks-not-editable))
- **Changelog** — per-step file write log across all sessions with expandable diffs
- **Config viewer** — frozen YAML config from the run
- **Analysis** — rendered markdown from `analysis.md`
- **Dark mode** — toggle between light and dark themes

The UI expects `RUNS_DIR=../runs` (configured in `ui/.env`).

## Output structure

Each run produces a directory under `runs/`:

```
runs/<run_name>/
├── config.yaml                 # frozen copy of the run config
├── run_meta.json               # run-level metadata and aggregates
├── full_diff.patch             # unified diff of all changes (baseline → final)
├── state_changelog.jsonl       # per-step write log across all sessions
├── analysis.md                 # experiment analysis (if created)
├── .shadow_git/                # shadow git repo (invisible change tracker)
│
├── session_01/
│   ├── trajectory.json         # ATIF v1.6 trajectory (parent)
│   ├── transcript.jsonl        # Claude Code transcript (for replay)
│   ├── uuid_map.json           # turn correlation map (transcript ↔ ATIF ↔ raw dumps)
│   ├── session_diff.patch      # unified diff of this session's changes
│   ├── subagent_<name>_<id>.json  # subagent ATIF trajectory (if any)
│   ├── api_captures.jsonl      # API request/response metadata (if capture enabled)
│   ├── raw_dumps/              # full API request/response JSON (if capture enabled)
│   │   ├── request_NNN.json
│   │   ├── request_NNN_headers.json
│   │   ├── response_NNN.txt
│   │   └── response_NNN_headers.json
│   └── resamples/              # resample outputs (created by UI or CLI)
│       ├── request_005/        # vanilla resamples for request 5
│       │   ├── sample_01.json
│       │   └── sample_02.json
│       └── request_005_v01/    # intervention variant
│           ├── variant.json    # edit metadata (label, find/replace pairs)
│           ├── request.json    # modified request body
│           └── sample_01.json
│
├── session_02/                 # session 2 (count=1)
│   └── ...
├── session_03_r01/             # session 3, replicate 1 (count=3)
├── session_03_r02/             # session 3, replicate 2
└── session_03_r03/             # session 3, replicate 3
```

### ATIF trajectory

Each session produces a `trajectory.json` in [ATIF v1.6](https://harborframework.com/docs/agents/trajectory-format) format. Key fields:

- `steps[].source` — `"agent"`, `"user"`, or `"system"`
- `steps[].message` — the text content of the step
- `steps[].reasoning_content` — extended thinking / chain-of-thought (when available)
- `steps[].tool_calls[]` — tool invocations with function name and arguments
- `steps[].observation` — tool results, linked back to their tool call by `source_call_id`
- `final_metrics` — token counts, cost, step count

### State changelog

`state_changelog.jsonl` records every detected file write with step-level attribution:

```json
{
  "session_index": 1,
  "step_id": 15,
  "file_path": "MEMORY.md",
  "diff": "--- MEMORY.md\n+++ MEMORY.md\n@@ ...",
  "diff_stats": {"added": 9, "removed": 0}
}
```

### API request capture

When `capture_api_requests: true` is set (or `--no-capture` is not passed), the harness runs a local reverse proxy between the SDK and the API. This captures data not available in the SDK message stream:

- **System prompt** — the SDK's system prompt (a minimal agent prompt plus your `system_prompt` config)
- **Tool definitions** — JSON schemas for each tool (Read, Write, Bash, etc.)
- **Context management** — `applied_edits` from the API response when compaction occurs
- **Per-request token usage** — input/output tokens, cache creation/read breakdown
- **Compaction detection** — when message count drops between requests, captures the post-compaction messages
- **Sampling parameters** — model, temperature, max_tokens
- **Agent context** — classifies each request as `main`, `subagent`, or `sdk_internal`

The proxy logs to `api_captures.jsonl` in each session directory. System prompt and tools are logged in full on the first request and on change; otherwise only a hash is recorded to keep file sizes small.

Raw request/response bodies are saved to `raw_dumps/` for resampling and intervention testing.

## Architecture

```
src/harness/
├── config.py            # Pydantic config models, YAML loading
├── shadow_git.py        # Shadow git: invisible change tracking via GIT_DIR/GIT_WORK_TREE
├── state.py             # Per-step write detection via shadow git index
├── atif_adapter.py      # Claude SDK Message -> ATIF Step mapping
├── runner.py            # Single session execution
├── experiment.py        # Multi-session orchestration (fork_from, replicates, shadow git lifecycle)
├── proxy.py             # Reverse proxy for raw API request/response capture
├── resample.py          # Single-turn API resampling
├── resample_session.py  # Full session resampling (resample-session CLI)
├── transcript.py        # Transcript parser and truncation for turn-level replay
├── uuid_map.py          # UUID map builder — correlates transcript, ATIF, and raw API dumps
├── replay.py            # Turn-level replay orchestrator
└── cli.py               # Typer CLI
```

The core complexity lives in `atif_adapter.py`: the Claude Agent SDK streams messages (AssistantMessage, UserMessage, SystemMessage, ResultMessage) and the adapter maps them into ATIF steps with correct tool call / observation pairing, thinking block capture, and sequential step IDs.

## Roadmap

- **Multi-agent support** — extend beyond Claude Code to support other agent frameworks and LLM providers (Codex, Devin, custom agents, etc.)
- **Comparative analysis** — side-by-side trajectory comparison across agents, models, and prompt variants
- **Richer intervention toolkit** — programmatic intervention pipelines for systematic counterfactual testing
- **Scoring & evaluation** — built-in trajectory scoring and automated evaluation metrics

## Contributing

We welcome PRs and contributions! Whether it's bug fixes, new features, documentation improvements, or support for additional agent frameworks — all contributions are appreciated.

## Dependencies

- [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) — runs Claude Code sessions programmatically
- [harbor](https://pypi.org/project/harbor/) — ATIF Pydantic models for trajectory validation
- [typer](https://typer.tiangolo.com/) — CLI framework
- [pyyaml](https://pyyaml.org/) — config file loading
- [pydantic](https://docs.pydantic.dev/) — config validation
