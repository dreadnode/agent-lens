# Subagents

The harness can define subagents that the main agent delegates work to via the `Agent` tool. Each subagent invocation produces a separate ATIF trajectory linked to the parent.

## Defining subagents

```yaml
agents:
  - name: "code-explorer"
    description: "Explores code structure, reads files, and reports findings."
    prompt: "You are a code exploration specialist. Read files and report structure."
    tools: ["Read", "Glob", "Grep"]
    model: "sonnet"
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | yes | — | Agent name (used as key in SDK's agents dict) |
| `description` | yes | — | When to use this agent (shown to the parent) |
| `prompt` | yes | — | System prompt for the subagent |
| `tools` | no | inherit all | Tool restrictions for the subagent |
| `model` | no | inherit | Model override: `sonnet`, `opus`, `haiku`, or `inherit` |

## How it works

1. The `Agent` tool is automatically added to `allowed_tools` when `agents` is non-empty
2. The main agent decides when to invoke a subagent based on the `description`
3. Subagent messages are filtered from the parent trajectory
4. Each subagent's work is captured in a separate ATIF trajectory file
5. The parent's observation result includes a `subagent_trajectory_ref` pointing to the subagent trajectory

## Trajectory capture

When `capture_subagent_trajectories: true` (the default), each subagent invocation produces a file like:

```
session_01/
├── trajectory.json                          # parent trajectory
└── subagent_code-explorer_abc123def456.json  # subagent trajectory
```

The subagent trajectory is a full ATIF trajectory with its own steps, tool calls, and observations. The parent trajectory's observation result for the `Agent` tool call includes a reference to this file.

## Example config

```yaml
model: "claude-sonnet-4-20250514"
provider: openrouter
work_dir: "./repos/test_repo"
session_mode: isolated
capture_subagent_trajectories: true

system_prompt: |
  You are exploring a project. Delegate file reading to your code-explorer.

agents:
  - name: "code-explorer"
    description: "Explores code structure, reads files, and reports findings."
    prompt: "You are a code exploration specialist. Be concise."
    tools: ["Read", "Glob", "Grep"]
    model: "sonnet"

sessions:
  - session_index: 1
    prompt: "Use the code-explorer to read main.py, then summarize what you learned."
```
