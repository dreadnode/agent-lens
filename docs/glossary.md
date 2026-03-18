# Glossary

Key terms used throughout AgentLens and how they relate to each other.

## Hierarchy

```
Run
├── Session 1
│   ├── Turn 1 (API call → response with tool_use blocks)
│   │   ├── Step 1 (ATIF: thinking block)
│   │   ├── Step 2 (ATIF: tool call + observation)
│   │   └── Step 3 (ATIF: tool call + observation)
│   ├── Turn 2
│   │   └── ...
│   └── Turn N
├── Session 2
│   └── ...
└── Session 2 replicate 2
    └── ...
```

## Terms

### Run

A single execution of an experiment config. Produces a directory under `runs/` containing all sessions, trajectories, diffs, and metadata. One config file → one run.

### Session

One `query()` call to the Claude Agent SDK — a single prompt sent to the agent, which then runs autonomously for multiple turns. Each session produces a trajectory, transcript, and session diff.

In **chained** mode, session 2 resumes session 1's conversation (they share a Claude Code session ID). In **isolated** mode, each session starts a fresh conversation. In **forked** mode, sessions 2+ fork from session 1's conversation.

Not to be confused with Claude Code's internal session ID, which is a lower-level concept. Our sessions map to `query()` calls; Claude Code sessions map to conversation state files.

### Turn

A single API round-trip: one request to Claude, one response. A turn corresponds to one `message.id` in the Claude Code transcript and one `request_NNN.json` in the raw API dumps.

A turn typically contains:

- Assistant response (thinking blocks, text, tool_use blocks)
- Tool result messages (user messages containing `tool_result` blocks)

Turns are numbered 1-based within a session. Turn-level replay branches execution from a specific turn.

### Step

An ATIF trajectory unit. One turn may produce multiple steps — for example, a turn with a thinking block, a text block, and two tool calls produces four steps (thinking, text, tool call 1, tool call 2), each with its own step ID.

Steps are the primary unit in ATIF trajectories. They have a `source` field (`agent`, `user`, or `system`) and may contain `tool_calls` and `observation` results.

### Trajectory

An [ATIF](https://harborframework.com/docs/agents/trajectory-format) (Agent Trajectory Interchange Format) JSON file capturing the full sequence of steps in a session. Agent-agnostic format — not specific to Claude Code. Saved as `trajectory.json` in each session directory.

### Transcript

A Claude Code-specific JSONL file recording every message in a conversation. Stored by Claude Code at `~/.claude/projects/<hash>/<session_id>.jsonl` and copied into the session directory as `transcript.jsonl`. Used for turn-level replay via the SDK's `--resume` mechanism.

### Replicate

A repeated execution of the same session config. Created via `count: N` in the config or `harness resample-session`. Each replicate gets its own directory with a `_rNN` suffix (e.g. `session_02_r01`, `session_02_r02`). All replicates share the same prompt and fork point but execute independently.

### Resample

A stateless replay of a single API request. The exact same request body is sent to Claude and the response is saved — no tools are executed, no files change. Used to study response variance at a single decision point. See also: [intervention](#intervention-variant).

### Replay

A full-fidelity re-execution from a specific turn. Each replicate runs in an isolated git [worktree](#worktree) checked out at the target turn's state, the transcript is truncated, and Claude resumes with real tool execution. When `count > 1`, replicates execute in parallel. Each replay becomes a new independent [run](#run). See [Resampling & Replay](guide/resampling.md#turn-level-replay).

### Intervention (variant)

A modified resample — the API request is edited before being sent (e.g. changing assistant text, tool results, or system prompt) to test counterfactuals. Thinking blocks cannot be edited due to cryptographic signature requirements. Variants are saved alongside vanilla resamples with a `_vNN` suffix and include the edited request for reproducibility.

### Shadow git

An invisible bare git repository stored in the run directory (`.shadow_git/`) that tracks all file changes in the working directory. Uses `GIT_DIR`/`GIT_WORK_TREE` environment variables to stay invisible to the agent. Provides baselines, per-step snapshots, diffs, worktrees for parallel replay, and filesystem reset for forking.

### Worktree

A git worktree — an isolated checkout of the shadow git at a specific ref (tag). Used by the replay system to give each replicate its own filesystem copy without modifying the source working directory. All worktrees share the shadow git's object store (space efficient). Created via `ShadowGit.add_worktree()` and cleaned up automatically after replay completes.

### Baseline

The shadow git snapshot of the working directory before any sessions run. Tagged as `baseline`. All diffs and resets reference this as the starting point.

### Fork

A session that branches from a prior session's conversation state. The agent sees the prior session's full context but starts a fresh response. The filesystem is reset to the fork point's state when there are multiple forks from the same point. Configured via `fork_from` or `session_mode: forked`.

### Compaction

When Claude Code's conversation context grows too large, it compacts (summarizes) the history. The harness detects compaction events by monitoring message count drops between API requests. Compaction events are logged in the ATIF trajectory's `extra` field.

### UUID map

A correlation file (`uuid_map.json`) that maps each API turn to its entries across all three data formats: Claude Code transcript (message IDs, UUIDs), ATIF trajectory (step IDs), and raw API dumps (request files). The primary join key is `tool_call_id` (e.g. `toolu_01Xp...`). Used by the replay system to find shadow git tags for filesystem reset.

### Working directory

The directory the agent operates in, set via `work_dir` in the config. Can be any directory — does not need to be a git repo. The agent's `cwd` is set to this directory, and all file changes are tracked by the shadow git.

### Memory file

A file automatically seeded in the working directory (default: `MEMORY.md`) that the agent can use to persist notes across sessions. Configured via `memory_file` and `memory_seed` in the config.

### Subagent

An agent delegated to by the main agent via the `Agent` tool. Each subagent invocation produces a separate ATIF trajectory linked to the parent via `SubagentTrajectoryRef`. Configured via the `agents` list in the config.

### Provider

The API backend used to route Claude requests. Options: `openrouter` (default), `anthropic`, `bedrock`, `vertex`. Each requires different credentials and environment variables.
