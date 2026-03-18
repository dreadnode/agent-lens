# Roadmap

Feature ideas for AgentLens. Contributions welcome — pick something and open a PR.

## Analysis & Comparison

- [ ] **Replicate diff view** — Given N resamples or replays, automatically find where trajectories diverge (first different tool call, different file write) and surface it in the web UI
- [ ] **Metrics extraction** — Auto-compute per-session stats: thinking token count, hedging frequency, tool call sequence, memory write size. Enable quantitative comparison without reading every trajectory
- [ ] **Model comparison mode** — Run the same config across multiple models (`model: [sonnet, opus]`) and produce side-by-side results in a single run

## Experiment Workflow

- [ ] **Batch runner** — Run multiple config files in sequence or parallel (`harness run experiments/*.yaml`)
- [ ] **Conditional sessions** — `run_if` on a session that checks a condition (file contains X, previous session errored) so experiments can branch based on agent behavior
- [ ] **Config templating** — Parameterize configs with variables (`$MODEL`, `$REPO`) to reuse experiment designs across repos and models

## Agent Support

- [ ] **OpenAI Codex support** — Run experiments against Codex via the OpenAI API as an alternative agent backend
- [ ] **Open Code support** — Run experiments against open-source coding agents (Aider, Continue, etc.)

## Web UI

- [ ] **Step annotations** — Tag steps in the UI ("interesting", "hallucination", "hedge dropped") to build labeled datasets from trajectories
- [ ] **Run comparison view** — Select two runs and view them side by side (trajectory, memory diff, cost)
- [ ] **Search across runs** — Find all runs where the agent used a specific tool, wrote a specific string, or had thinking containing a phrase
