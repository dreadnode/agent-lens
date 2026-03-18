# Roadmap

AgentLens currently supports Claude Code via the Claude Agent SDK. Here's where we're headed.

## Planned

### Multi-agent support

Extend beyond Claude Code to support other agent frameworks and LLM providers — Codex, Devin, custom agents, and any tool-using LLM system. The core trajectory format (ATIF) and analysis tooling are already agent-agnostic; the main work is adding new adapters and runner integrations.

### Comparative analysis

Side-by-side trajectory comparison across agents, models, and prompt variants. Run the same experiment config against different agents and compare behavior, tool usage patterns, and outcomes.

### Richer intervention toolkit

Programmatic intervention pipelines for systematic counterfactual testing. Build on the existing edit & resample workflow with scriptable intervention sequences, batch processing, and automated hypothesis testing.

### Scoring & evaluation

Built-in trajectory scoring and automated evaluation metrics. Define custom scorers that run against captured trajectories to measure agent behavior quantitatively.

## Contributing

We welcome PRs and contributions! Whether it's bug fixes, new features, documentation improvements, or support for additional agent frameworks — all contributions are appreciated.

If you're interested in adding support for a new agent framework, the key integration points are:

- **Runner** (`src/harness/runner.py`) — session execution loop
- **Adapter** (`src/harness/atif_adapter.py`) — message-to-ATIF step mapping
- **Proxy** (`src/harness/proxy.py`) — API request capture (optional)
