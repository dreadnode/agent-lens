# AgentLens

A harness for running multi-session agent trajectories using the Claude Agent SDK, capturing them in [ATIF](https://harborframework.com/docs/agents/trajectory-format) (Agent Trajectory Interchange Format), and tracking file state changes across sessions.

Built for agent interpretability research — studying how LLM agents behave across multi-turn, multi-session, multi-agent interactions.

## What it does

The harness takes a YAML config describing a sequence of sessions (prompts to an agent), runs each session against a working directory via the Claude Agent SDK, and produces structured outputs:

- **ATIF trajectories** — standardized JSON capturing every agent step, tool call, observation, and thinking block
- **Shadow git change tracking** — automatic tracking of all file changes via an invisible git repo, with per-step write attribution and full unified diffs
- **Session chaining** — three modes for controlling how sessions relate to each other (isolated, chained, forked)
- **Resampling & replay** — four methods for studying behavioral variance, from quick API resampling to full trajectory replay with tool execution. Edit assistant text, tool results, or system prompts to test counterfactuals
- **Subagent capture** — separate ATIF trajectories for each subagent invocation, linked to the parent via `SubagentTrajectoryRef`

## Next steps

<div class="grid cards" markdown>

- :material-download: **[Installation](getting-started/install.md)** — get set up
- :material-rocket-launch: **[Quick Start](getting-started/quickstart.md)** — run your first experiment
- :material-layers-triple: **[Session Modes](guide/session-modes.md)** — isolated, chained, and forked behavior
- :material-shuffle-variant: **[Resampling & Replay](guide/resampling.md)** — variance analysis from API-level to full replay

</div>
