# CLI Reference

The harness provides a `harness` command with several subcommands.

## `harness run`

Run a multi-session experiment from a config file.

```bash
harness run <config.yaml> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--model TEXT` | Override the model from config |
| `--tag TEXT` | Add tags (can be repeated) |
| `--session-mode MODE` | Override session mode (`isolated`, `chained`, `forked`) |
| `--run-name TEXT` | Custom name for the run directory |
| `--runs-dir PATH` | Output directory (default: `runs`) |
| `--no-capture` | Disable API request capture (disables resampling) |

**Examples:**

```bash
# Basic run
harness run examples/isolated.yaml

# With overrides
harness run examples/isolated.yaml \
  --model claude-sonnet-4-20250514 \
  --tag baseline \
  --session-mode chained \
  --run-name my-experiment-01

# Custom output directory
harness run config.yaml --runs-dir ./output
```

## `harness list`

List all completed runs.

```bash
harness list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--runs-dir PATH` | Runs directory (default: `runs`) |
| `--json` | Output as JSON |

**Example output:**

```
  my-run-01  |  claude-sonnet-4  |  isolated  |  2 sessions, 30 steps  |  $0.1234
  my-run-02  |  claude-sonnet-4  |  chained   |  3 sessions, 45 steps  |  $0.2345
```

## `harness inspect`

Show details of a completed run.

```bash
harness inspect <run_dir> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--json` | Output as JSON (includes file changes) |

**Example output:**

```
Run: smoke-test-01
Model: claude-sonnet-4 (openrouter)
Mode: isolated
Tags: smoke-test
Total: 15 steps, 5 tool calls
Cost: $0.0596
File writes: 1

  Session 1: 15 steps, 5 tool calls  $0.0596

File changes:
  session 1, step 15: MEMORY.md (+9/-0)
```

## `harness resample`

Resample a specific API turn N times (no tool execution).

For concepts and method comparison, see [Resampling & Replay](guide/resampling.md).

```bash
harness resample <run_dir> [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--session INT` | `1` | Session index |
| `--request INT` | `1` | Request index to resample |
| `--count INT` | `5` | Number of resamples |
| `--model TEXT` | original | Override model |
| `--replicate INT` | — | Replicate number (for `session_NN_rNN` dirs) |
| `--list-requests` | — | List available requests and exit |

### Discovering requests

```bash
harness resample runs/my-run --session 1 --list-requests
```

### Resampling

```bash
# Resample request 5 ten times
harness resample runs/my-run --session 1 --request 5 --count 10

# Resample from a replicate session
harness resample runs/my-run --session 2 --replicate 3 --request 5 --count 5
```

Results are saved to `session_NN/resamples/request_NNN/` (and `request_NNN_vNN/` for edited variants).

## `harness resample-edit`

Edit a captured API request and resample with the modified version.

For intervention strategy and output details, see [Resampling & Replay](guide/resampling.md#intervention-testing).

```bash
harness resample-edit <run_dir> [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--session INT` | `1` | Session index |
| `--request INT` | `1` | Request index |
| `--dump` | — | Dump the request JSON to stdout for editing |
| `--input PATH` | — | Path to edited request JSON (use `-` for stdin) |
| `--label TEXT` | `cli-edit` | Human-readable label for this variant |
| `--count INT` | `5` | Number of resamples |
| `--model TEXT` | original | Override model |
| `--replicate INT` | — | Replicate number |

### Two-step workflow

**Step 1** — Dump the original request:

```bash
harness resample-edit runs/my-run --session 1 --request 5 --dump > edit.json
```

**Step 2** — Edit the JSON file (change assistant text, tool results, system prompt, etc.), then resample.

> **Do not edit thinking blocks.** They carry cryptographic signatures validated by the API — any modification will cause a 400 error. See [Thinking blocks](guide/resampling.md#thinking-blocks-not-editable) for details.

```bash
harness resample-edit runs/my-run --session 1 --request 5 \
  --input edit.json --label "removed hedging" --count 5
```

### Piping from stdin

```bash
harness resample-edit runs/my-run --session 1 --request 5 --dump \
  | jq '.system = "You are a cautious engineer. Always check for edge cases."' \
  | harness resample-edit runs/my-run --session 1 --request 5 \
      --input - --label "cautious prompt" --count 10
```

### Batch interventions

```bash
for req in 3 5 7 9; do
  harness resample-edit runs/my-run --session 1 --request $req --dump \
    | jq '(.messages[] | select(.role == "user") | .content[] | select(.type == "tool_result")).content = "Error: file not found"' \
    | harness resample-edit runs/my-run --session 1 --request $req \
        --input - --label "tool-error" --count 5
done
```

## `harness resample-session`

Re-run a forked session N times to study behavioral variance.

For behavioral semantics and output expectations, see [Resampling & Replay](guide/resampling.md#session-level-resampling).

```bash
harness resample-session <run_dir> [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--session INT` | `2` | Session index to resample |
| `--count INT` | `5` | Number of new replicates |

**Example:**

```bash
harness resample-session runs/my-run --session 2 --count 5
```

This finds the session's `fork_from` target, resolves the session ID, and runs N new replicates. New directories are appended with auto-incrementing replicate numbers, and `run_meta.json` is updated.

## `harness replay`

Replay a session from any API turn with full tool execution. Each replicate runs in an isolated git worktree, so multiple replicates execute in parallel. Each replay becomes a new independent run with complete provenance.

For replay internals and data model details, see [Resampling & Replay](guide/resampling.md#turn-level-replay).

```bash
harness replay <run_dir> [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--session INT` | `1` | Session index to replay from |
| `--turn INT` | — | Turn index to replay from (1-based, required unless `--list-turns`) |
| `--count INT` | `1` | Number of replay replicates |
| `--prompt TEXT` | — | Additional prompt after tool results |
| `--list-turns` | — | List available turns and exit |
| `--continue-sessions` | — | After replaying the selected session, run sessions `N+1..end` using the source config |
| `--runs-dir PATH` | `runs` | Output directory |
| `--replicate INT` | — | Replicate number (for `session_NN_rNN` dirs) |

### Listing turns

```bash
$ harness replay runs/my-run --session 1 --list-turns

Turns in session 1 (12 total):

  Turn 1: Read  (1 results)
  Turn 2: Read, Grep  (2 results)  [_step_1_3]
  Turn 3: Edit, Write  (2 results)  [_step_1_5]
  ...
```

### Replaying

By default, only the targeted session is replayed. Use `--continue-sessions` to also run sessions after it.

```bash
# Replay from turn 5, three times (only session 1 runs)
harness replay runs/my-run --session 1 --turn 5 --count 3

# Replay session 1 turn 5, then continue with sessions 2, 3, etc.
harness replay runs/my-run --session 1 --turn 5 --continue-sessions

# Replay with an additional prompt
harness replay runs/my-run --session 1 --turn 5 --prompt "Try a different approach"

# Replay from turn 1 (re-run from scratch)
harness replay runs/my-run --session 1 --turn 1 --count 2
```

Each replay creates a new run directory (e.g. `replay_my-run_s1_t5_r01_2026-03-16T00-00-00/`) with full artifacts including `replay_meta.json` for provenance tracking. The source working directory is never modified — each replicate operates in its own git worktree.
