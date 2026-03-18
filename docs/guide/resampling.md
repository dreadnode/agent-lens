# Resampling & Replay

AgentLens provides four ways to re-run agent behavior, each at a different level of fidelity. They form a spectrum from cheap/fast (resample a single API call) to expensive/thorough (replay a full trajectory with tool execution).

For CLI flags and syntax, see the [CLI Reference](../cli.md).

## Overview

### The spectrum

```
Cheapest / fastest                                    Most thorough
─────────────────────────────────────────────────────────────────────

  Turn resample     Intervention     Session resample   Turn replay
  (API only)        (edit + API)     (full session)     (branch mid-session)

  Same request,     Modified input,  Re-run a whole     Resume from any
  new response.     new response.    session N times.   turn with full
  No tools run.     No tools run.    Tools execute.     tool execution.
```

### When to use what

| I want to... | Method | Command |
|--------------|--------|---------|
| Check if the model would say the same thing again | [Turn resample](#turn-level-resampling) | `harness resample` |
| See what happens if the model had different thinking | [Intervention](#intervention-testing) | `harness resample-edit` |
| See what happens if a tool returned something different | [Intervention](#intervention-testing) | `harness resample-edit` |
| Compare N complete trajectories for the same task | [Session resample](#session-level-resampling) | `harness resample-session` |
| Branch from a specific point and let the agent continue | [Turn replay](#turn-level-replay) | `harness replay` |
| Test a prompt injection at a specific turn | [Turn replay](#turn-level-replay) | `harness replay --prompt` |

### Comparison table

| | Turn resample | Intervention | Session resample | Turn replay |
|---|---|---|---|---|
| **Tools execute** | No | No | Yes | Yes |
| **Filesystem reset** | No | No | Yes (fork point) | Yes (git worktree) |
| **Parallel** | Yes | Yes | Yes | Yes |
| **Creates new run** | No | No | No (appends replicates) | Yes |
| **Editable inputs** | No | Yes | No | Prompt only |
| **Requires** | `capture_api_requests` | `capture_api_requests` | `fork_from` session | `transcript.jsonl` |

---

## Turn-level resampling

Send the exact same API request again N times and save each response. This is **stateless** — no tools execute, no files change. Use it to quickly check how much variance exists at a specific decision point.

**What you get:** N alternative responses to the same context. Useful for measuring how deterministic the model is at a given turn — does it always pick the same tool? Always hedge the same way?

**Requires:** `capture_api_requests: true` in the original experiment config.

### Discovering requests

```bash
$ harness resample runs/my-run --session 1 --list-requests

Session 1: 12 captured requests

    1  |  15 messages  |  claude-sonnet-4  |  Explore the project...
    2  |  17 messages  |  claude-sonnet-4  |  [tool_result for toolu_01H...]
   ...
```

### Running

```bash
# Resample request 5 ten times
harness resample runs/my-run --session 1 --request 5 --count 10

# From a replicate session
harness resample runs/my-run --session 2 --replicate 3 --request 5 --count 5
```

### Output

```
session_01/resamples/request_005/
├── sample_01.json
├── sample_02.json
└── ...
```

---

## Intervention testing

Edit the conversation inputs — thinking blocks, text, tool results, or system prompt — then resample. This lets you test counterfactuals: "What would the model do differently if it had seen X instead of Y?"

Like turn-level resampling, this is **stateless** — no tools execute. But the input is modified before sending, so you can study causal effects.

**What you can edit:**

- **Thinking blocks** — change the model's internal reasoning
- **Text responses** — alter what the model said in prior turns
- **Tool results** — change what a tool returned (e.g., different file contents)
- **System prompt** — modify instructions

### From the CLI

Two-step workflow: dump the request, edit it, resample.

```bash
# 1. Dump the request to a file
harness resample-edit runs/my-run --session 1 --request 5 --dump > edit.json

# 2. Edit edit.json (change thinking, text, tool results, system prompt...)

# 3. Resample with the modified request
harness resample-edit runs/my-run --session 1 --request 5 \
  --input edit.json --label "removed hedging" --count 5
```

For scriptable interventions, pipe through `jq`:

```bash
harness resample-edit runs/my-run --session 1 --request 5 --dump \
  | jq '.messages[-1].content[0].thinking = "Be more direct."' \
  | harness resample-edit runs/my-run --session 1 --request 5 \
      --input - --label "direct thinking" --count 10
```

Batch across multiple requests:

```bash
for req in 3 5 7 9; do
  harness resample-edit runs/my-run --session 1 --request $req --dump \
    | jq '.messages[-1].content[0].thinking = "Skip exploration."' \
    | harness resample-edit runs/my-run --session 1 --request $req \
        --input - --label "skip-exploration" --count 5
done
```

### From the web UI

1. Open a session's API captures
2. Click "Edit & Resample" on any request
3. Modify thinking blocks, text, tool results, or system prompts
4. Resample with the modified input

### Output

Both CLI and web UI produce the same structure:

```
session_01/resamples/request_005_v01/
├── variant.json     # label + metadata
├── request.json     # modified request body
├── sample_01.json   # response to modified input
└── ...
```

CLI-created variants appear in the web UI and vice versa.

---

## Session-level resampling

Re-run a full session N times from scratch. Unlike turn-level methods, this **executes tools** — each replicate is a complete agent session with real file reads, writes, and tool calls.

**What you get:** N complete trajectories for the same task, each potentially diverging from the first tool call onward. Useful for studying how much the agent's overall approach varies.

**Requires:** The session must have a `fork_from` target (or be in forked mode).

```bash
harness resample-session runs/my-run --session 2 --count 5
```

Each replicate runs in its own git worktree, so all 5 execute in parallel. New directories are appended with auto-incrementing replicate numbers (`session_02_r01`, `session_02_r02`, ...), and `run_meta.json` is updated. The source working directory is never modified.

---

## Turn-level replay

Branch execution from any API turn with **full tool execution** and filesystem reset. This is the highest-fidelity method — the agent sees the exact same conversation context and filesystem state up to the branch point, then generates a fresh response that may diverge.

**What you get:** A new independent run where the agent resumed from a specific point. The agent can take completely different actions from that point forward, using real tools on a real filesystem.

**Key difference from resampling:** Resampling gives you alternative *responses*. Replay gives you alternative *trajectories* — the agent continues running with full tool execution, potentially for many more turns.

**Requires:** `transcript.jsonl` and `.shadow_git/` in the source run.

### How it works

For replay from turn N:

1. **Transcript truncation** — The original transcript is cut after turn N-1's assistant messages, before the tool results
2. **Filesystem reset via git worktrees** — Each replicate gets its own worktree checked out from the source shadow git at the filesystem state as of turn N. Worktrees share the git object store (space efficient) but are fully isolated
3. **Tool result injection** — The original tool results from turn N-1 are sent to the SDK, so the agent sees the exact same context
4. **Fresh response** — The agent generates a new response (the branch point) and continues with full tool execution
5. **Parallel execution** — When `count > 1`, all replicates run concurrently. Each operates in its own worktree — no contention. The source working directory is never modified

### Discovering turns

```bash
$ harness replay runs/my-run --session 1 --list-turns

Turns in session 1 (12 total):

  Turn 1: Read  (1 results)
  Turn 2: Read, Grep  (2 results)  [_step_1_3]
  Turn 3: Edit, Write  (2 results)  [_step_1_5]
  Turn 4: Bash  (1 results)  [_step_1_7]
  ...
  Turn 12: (no tools)
```

Bracketed tags (e.g. `[_step_1_3]`) indicate shadow git snapshots — turns where file writes were detected. The replay resets the filesystem to the nearest snapshot at or before the target turn.

### Running

```bash
# Replay from turn 5, three times (runs in parallel)
harness replay runs/my-run --session 1 --turn 5 --count 3

# Replay with an additional prompt after tool results
harness replay runs/my-run --session 1 --turn 5 --prompt "Try a different approach"

# Replay from turn 1 (re-run from scratch with same config)
harness replay runs/my-run --session 1 --turn 1 --count 2

# Replay session 1 turn 5, then continue with sessions 2..end
harness replay runs/my-run --session 1 --turn 5 --continue-sessions
```

When `--continue-sessions` is enabled, each replicate runs the replayed session first, then continues with sessions `N+1..end` from the original config.

### Output

Each replay creates a new independent run directory:

```
runs/replay_my-run_s1_t5_r01_2026-03-16T00-00-00/
├── config.yaml                          # frozen config from source
├── run_meta.json                        # standard run metadata + replay fields
├── replay_meta.json                     # full provenance (source run, session, turn, etc.)
├── .shadow_git/                         # fresh shadow git for this replay
└── session_01/
    ├── trajectory.json                  # ATIF trajectory (from turn 5 onward)
    ├── transcript.jsonl                 # Claude Code transcript
    ├── uuid_map.json                    # turn correlation map
    ├── session_diff.patch               # file changes during replay
    └── source_transcript_truncated.jsonl # truncated source for reference
```

---

## Technical notes

### UUID map

Each session generates a `uuid_map.json` that correlates entries across the three data formats (transcript, ATIF trajectory, raw API dumps). The primary join key is `tool_call_id`. The replay system uses this to find shadow git tags for filesystem reset.

### Thinking signatures

When resampling, the harness automatically strips thinking block signatures from the request. Signatures are response-specific and would cause errors if replayed verbatim.
