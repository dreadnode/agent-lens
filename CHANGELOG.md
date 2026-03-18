# Changelog

All notable changes to AgentLens will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-03-18

### Fixed

- **Replay filesystem reset for chained sessions** — when replaying session N > 1, the filesystem was incorrectly reset to `baseline` (pre-experiment state) instead of the end state of session N-1. This caused the agent to see stale files (e.g. an empty MEMORY.md instead of one populated by prior sessions). The fix falls back to `session_{N-1}` when no file-write tags exist within the current session before the replay turn.

### Changed

- Removed experiment configs from version control (already in `.gitignore`, now untracked)

## [0.1.0] - 2026-03-17

Initial release.

### Added

- **Experiment runner** — YAML-based config for multi-session Claude Code experiments via the Claude Agent SDK
- **ATIF trajectory capture** — every agent step, tool call, observation, and thinking block captured in [ATIF v1.6](https://harborframework.com/docs/agents/trajectory-format) format
- **Shadow git change tracking** — invisible bare git repo tracks all file changes with per-step write attribution and unified diffs
- **Session modes** — `isolated` (fresh conversation, files persist), `chained` (conversation resumes), `forked` (independent branches from a base session)
- **Flexible forking** — `fork_from` on individual sessions to fork from any prior session, not just session 1
- **Session replicates** — `count: N` runs the same session N times as independent replicates with `_rNN` directory suffixes
- **Subagent capture** — separate ATIF trajectories for each subagent invocation, linked to parent via `SubagentTrajectoryRef`
- **API request capture** — local reverse proxy captures raw request/response bodies, system prompts, tool definitions, token usage, and compaction events
- **Turn-level resampling** — replay a specific API request N times to study response variance (stateless, no tool execution)
- **Intervention testing** — edit captured API requests (assistant text, tool results, system prompt) and resample with modified inputs; available from both CLI (`harness resample-edit`) and web UI
- **Session-level resampling** — re-run a forked session N times with full tool execution (`harness resample-session`)
- **Turn-level replay** — branch execution from any API turn with exact-match context, filesystem reset via git worktrees, and full tool execution; replicates run in parallel (`harness replay`)
- **Transcript capture** — Claude Code transcript JSONL copied into session output for replay support
- **UUID map** — per-turn correlation across transcript, ATIF trajectory, and raw API dumps using `tool_call_id` as join key
- **Web UI** — SvelteKit interface for browsing runs, viewing trajectories, memory diffs, API captures, resamples, edit & resample, and file changelogs
- **CLI** — `harness run`, `list`, `inspect`, `resample`, `resample-edit`, `resample-session`, `replay`
- **Provider support** — OpenRouter (default), Anthropic, AWS Bedrock, GCP Vertex AI
- **Memory file** — auto-seeded file in working directory for cross-session note persistence
