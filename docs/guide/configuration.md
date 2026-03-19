# Configuration

Experiments are defined as YAML config files. The harness validates configs with Pydantic — errors are caught before any sessions run.

## Full example

```yaml
model: "claude-sonnet-4-20250514"
provider: anthropic
hypothesis: "The agent preserves hedging across sessions"
work_dir: "./repos/my_project"
session_mode: chained
tags: ["experiment-1"]

system_prompt: |
  You are exploring a Python codebase. Use MEMORY.md to keep notes.

allowed_tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Write
  - Edit

max_turns: 30
permission_mode: bypassPermissions
max_budget_usd: 1.00

memory_file: "MEMORY.md"
memory_seed: "# Project Notes\n"

capture_api_requests: true

sessions:
  - session_index: 1
    prompt: "Explore the project structure. Take notes in MEMORY.md."
  - session_index: 2
    prompt: "Read the main module in detail. Update your notes."
  - session_index: 3
    prompt: "Summarize what you know about this project."
    max_turns: 10
```

## Config reference

### Top-level fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `model` | yes | — | Claude model identifier (e.g. `claude-sonnet-4-20250514`) |
| `provider` | no | `anthropic` | API provider: `anthropic`, `openrouter`, `bedrock`, `vertex` |
| `base_url` | no | — | Custom API base URL (overrides provider default) |
| `cli_path` | no | — | Override the `claude` executable path used by the Claude Agent SDK. Useful for wrappers such as `ollama launch claude`. |
| `hypothesis` | no | — | What this experiment tests. Shown in the web UI. |
| `work_dir` | yes | — | Working directory the agent operates in (any directory) |
| `repo_name` | no | — | Human-readable name for the working directory |
| `sessions` | yes | — | List of session configs |
| `session_mode` | no | `isolated` | `isolated`, `chained`, or `forked` |
| `system_prompt` | no | — | System prompt for all sessions |
| `allowed_tools` | no | Read, Grep, Glob, Bash, Write, Edit | Tools the agent can use |
| `max_turns` | no | `50` | Max agent turns per session |
| `permission_mode` | no | `bypassPermissions` | `acceptEdits` or `bypassPermissions` |
| `memory_file` | no | `MEMORY.md` | File to auto-seed in working directory |
| `memory_seed` | no | `# Notes\n` | Initial content for the memory file |
| `max_budget_usd` | no | — | Per-session spend cap |
| `agents` | no | `[]` | Subagent definitions (see [Subagents](subagents.md)) |
| `capture_subagent_trajectories` | no | `true` | Save separate ATIF trajectories per subagent |
| `capture_api_requests` | no | `true` | Capture raw API requests (enables resampling) |
| `run_name` | no | auto | Custom name for the run directory |
| `tags` | no | `[]` | Metadata tags |
| `revert_work_dir` | no | `false` | Reset working directory to pre-run state after the run completes |
| `load_project_settings` | no | `false` | Load the repo's CLAUDE.md and .claude/settings.json |

### Session fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `session_index` | yes | — | Sequential index starting at 1 |
| `prompt` | yes | — | The user prompt for this session |
| `system_prompt` | no | — | Per-session system prompt override |
| `max_turns` | no | — | Per-session max turns override |
| `fork_from` | no | — | Session index to fork from (must be lower) |
| `count` | no | `1` | Run N independent replicates of this session |

### Providers

| Provider | Config value | Env var | Notes |
|----------|-------------|---------|-------|
| Anthropic | `anthropic` (default) | `ANTHROPIC_API_KEY` | Direct Anthropic API. Falls back to Claude Code subscription if no key set. |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | Routes through OpenRouter |
| AWS Bedrock | `bedrock` | AWS credentials | Sets `CLAUDE_CODE_USE_BEDROCK=1` |
| GCP Vertex AI | `vertex` | GCP credentials | Sets `CLAUDE_CODE_USE_VERTEX=1` |
| Claude Code subscription | `anthropic` | *(none needed)* | If no `ANTHROPIC_API_KEY` is set, the SDK uses your Claude Code subscription credentials from `~/.claude/credentials.json`. Usage is covered by your subscription (Pro/Max) with rate limits rather than per-token billing. |

### Custom CLI wrappers

The Claude Agent SDK launches the `claude` CLI under the hood. If you want
to route AgentLens through an alternate launcher that still exposes the Claude
Code CLI interface, set `cli_path` to a wrapper executable.

One practical example is `ollama launch claude`. The wrapper needs to bridge
AgentLens' `--model ...` flag to the launcher layer, because Ollama expects
the model on `ollama launch claude --model <name>` rather than forwarding it
to the inner `claude` process.

Example bridge script:

```bash
#!/bin/bash
set -euo pipefail

model=""
args=()
while (($#)); do
  case "$1" in
    --model)
      model="$2"
      shift 2
      ;;
    --model=*)
      model="${1#--model=}"
      shift
      ;;
    *)
      args+=("$1")
      shift
      ;;
  esac
done

exec ollama launch claude --model "$model" -- "${args[@]}"
```

AgentLens includes this bridge at:

```yaml
cli_path: "/absolute/path/to/agent-lens/scripts/ollama_claude_bridge.sh"
```

For full feature parity with capture/resampling, set the Ollama local endpoint
as `base_url` so AgentLens' proxy forwards captured requests to Ollama:

```yaml
model: "kimi-k2.5:cloud"
provider: anthropic
base_url: "http://127.0.0.1:11434"
cli_path: "/absolute/path/to/agent-lens/scripts/ollama_claude_bridge.sh"
work_dir: "./repos/my_project"
sessions:
  - session_index: 1
    prompt: "Explore the repo briefly."
```

Then point your config at it:

```yaml
model: "kimi-k2.5:cloud"
base_url: "http://127.0.0.1:11434"
cli_path: "/absolute/path/to/agent-lens/scripts/ollama_claude_bridge.sh"
provider: anthropic
work_dir: "./repos/my_project"
sessions:
  - session_index: 1
    prompt: "Explore the repo briefly."
```

### Cost reporting

Cost figures shown in `run_meta.json`, `harness inspect`, and the web UI come from the Claude Agent SDK's `total_cost_usd` field, which is calculated using Anthropic's list pricing regardless of which provider you use. This means:

- **OpenRouter** — reported cost reflects Anthropic list prices, not your actual OpenRouter bill (which may differ)
- **Bedrock / Vertex** — reported cost may not match AWS or GCP billing
- **Claude Code subscription** — cost is reported but you're not actually billed per-token

Treat cost figures as rough estimates, not authoritative billing data.

## Automatic behaviors

- **Memory file is auto-seeded.** The harness creates the memory file with seed content if it doesn't already exist.
- **Working directory path is injected into the system prompt.** The agent knows where to read/write.
- **The agent's cwd is set to the working directory.**

## Validation rules

- Session indices must be unique and contiguous starting at 1
- `fork_from` must reference a session with a lower index
- `count` must be >= 1
- `session_index` must be >= 1
