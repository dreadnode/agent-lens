# Session Modes

The `session_mode` field controls how sessions relate to each other — both in terms of conversation context (SDK session chaining) and file state (shadow git).

## Modes

| Mode | Conversation | File state |
|------|-------------|------------|
| `isolated` | Each session starts fresh | Changes accumulate (no reset) |
| `chained` | Each session resumes from the previous | Changes accumulate (no reset) |
| `forked` | Sessions 2+ fork from session 1 | Reset to session 1's end state |

### Isolated

Each session starts with a fresh conversation — no chat history is carried over. The working directory is **not** reset; file changes from previous sessions persist. Continuity between sessions is through the working directory and the memory file.

```yaml
session_mode: isolated

sessions:
  - session_index: 1
    prompt: "Explore the codebase and take notes in MEMORY.md"
  - session_index: 2
    prompt: "Read MEMORY.md and continue your analysis"
```

### Chained

Each session resumes the previous session's conversation. The agent has full context of what happened before. File changes accumulate.

```yaml
session_mode: chained

sessions:
  - session_index: 1
    prompt: "Explore the codebase"
  - session_index: 2
    prompt: "Now refactor the main module based on what you found"
```

### Forked

Sessions 2+ fork from session 1's conversation. Each sees session 1's context but not sibling sessions. The working directory is reset to session 1's end state before each fork.

```yaml
session_mode: forked

sessions:
  - session_index: 1
    prompt: "Explore the codebase and take notes"
  - session_index: 2
    prompt: "Write a security analysis"
  - session_index: 3
    prompt: "Write a performance analysis"
```

## Flexible forking with `fork_from`

For more control, use `fork_from` on individual sessions to fork from any prior session:

```yaml
session_mode: isolated  # fork_from overrides this per-session

sessions:
  - session_index: 1
    prompt: "Explore the codebase and take notes"
  - session_index: 2
    prompt: "Write a security analysis based on your notes"
    fork_from: 1
  - session_index: 3
    prompt: "Write a performance analysis based on your notes"
    fork_from: 1
```

`fork_from` must reference a session with a lower index. When set, it overrides `session_mode` for that session.

## Shadow git and session modes

The [shadow git](../api/shadow-git.md) system handles file state for each mode:

- **Isolated**: No reset — changes accumulate, only chat history is fresh
- **Chained**: No reset — changes accumulate
- **Forked**: `git reset --hard session_NN` to the fork point

This means the working directory does not need to be a git repo. The shadow git creates its own invisible bare repo in the run output directory.

## Replicates with `count`

To study behavioral variance, run the same session multiple times:

```yaml
sessions:
  - session_index: 1
    prompt: "Explore the codebase"
  - session_index: 2
    prompt: "Write a security analysis"
    fork_from: 1
    count: 5  # run 5 independent replicates
```

Each replicate gets its own directory with a `_rNN` suffix:

```
session_02_r01/
session_02_r02/
session_02_r03/
session_02_r04/
session_02_r05/
```
