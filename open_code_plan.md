Uplift Assessment: OpenCode Support
What OpenCode Is
OpenCode is an open-source coding agent with a client/server architecture — a Bun/JS backend exposing an HTTP REST API + SSE streaming, with Go TUI client. It supports multiple LLM providers (Anthropic, OpenAI, Gemini, any OpenAI-compatible endpoint) and has TypeScript, Go, and Python SDKs.

Key Architectural Differences
Claude Agent SDK	OpenCode
Interface	Python async generator (async for msg in query(...))	HTTP REST + SSE event stream
Message model	AssistantMessage, UserMessage, SystemMessage, ResultMessage with TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock	MessageV2 with parts: TextPart, ReasoningPart, ToolPart, FilePart, SnapshotPart
Session management	SDK-managed, resume/fork via session_id	Server-managed, CRUD via REST API
Tool calls	ToolUseBlock with .id, .name, .input → ToolResultBlock	ToolPart with state machine (pending→running→completed→failed)
Streaming	Python async iterator yielding typed messages	SSE events (text-delta, tool-call, tool-result)
Models	Claude only	Any (Anthropic, OpenAI, Gemini, etc.)
Language	Python SDK	TypeScript SDK primary (Python/Go also available)
Current Coupling (Why It's Not Trivial)
The harness is tightly coupled to Claude's SDK — 8 message/block types used in isinstance() dispatch across ~400 lines in atif_adapter.py, plus query(), ClaudeAgentOptions, AgentDefinition in runner.py, plus Claude-specific env vars in config.py.

What Would Need to Change
1. New abstraction layer — AgentDriver protocol (~150 lines, new file)


AgentDriver.execute(prompt, options) → AsyncIterator[AgentMessage]
Where AgentMessage is a harness-internal type that both Claude and OpenCode drivers map into.

2. OpenCode driver (~300 lines, new file)

Start/connect to OpenCode server (opencode serve or connect to existing)
Create session via REST API
Send prompt, consume SSE stream
Map OpenCode's MessageV2 parts → harness AgentMessage types
Handle tool state machine (pending→running→completed)
Extract cost/token metadata
3. OpenCode ATIF adapter (~200 lines, new file or extend existing)

Map TextPart → ATIF text step
Map ReasoningPart → ATIF step with reasoning_content
Map ToolPart → ATIF tool_call + observation pair
Handle OpenCode's tool state machine vs Claude's request/response pattern
4. Refactor existing code (~200 lines changed)

runner.py: Extract ClaudeDriver implementing AgentDriver, move query() call behind the interface
atif_adapter.py: Either make generic or keep as ClaudeAtifAdapter alongside OpenCodeAtifAdapter
config.py: Add agent: "claude" | "opencode" field, OpenCode-specific config (server URL, port)
experiment.py: Abstract session_id/resume/fork (OpenCode has its own session model)
5. Proxy capture — different approach needed

Claude: intercept ANTHROPIC_BASE_URL with reverse proxy
OpenCode: would need to either intercept OpenCode's outbound API calls (harder, server is a separate process) or use OpenCode's own event stream which already exposes token counts
6. Dependencies — add OpenCode Python SDK or just use aiohttp to hit the REST API directly

Rough Sizing
Component	Effort	Lines
AgentDriver protocol + internal message types	Small	~150 new
ClaudeDriver (extract from runner.py)	Medium	~200 refactored
OpenCodeDriver (new)	Medium-Large	~300 new
OpenCodeAtifAdapter (new)	Medium	~200 new
Config changes	Small	~50 changed
Experiment/session management abstraction	Medium	~100 changed
Proxy/capture story for OpenCode	Unclear	TBD
Total		~1000 lines
The Big Win
OpenCode supports non-Claude models (GPT-4o, Gemini, Llama, etc.). This would let you run the same memory laundering experiments with different model families — which the Claude Agent SDK fundamentally cannot do. That's the main reason to do this.

The Big Risk
OpenCode's SDK is TypeScript-primary. The Python SDK exists but may be less mature. You'd be going against the grain. An alternative would be to shell out to opencode CLI or talk to the HTTP server directly with aiohttp, which avoids the SDK dependency entirely.

Recommendation
Medium effort, ~1-2 days of focused work. The hardest part is the ATIF adapter for OpenCode's message format (the part→step mapping is different enough to need real thought). The abstraction layer itself is straightforward. I'd suggest talking to the HTTP server directly rather than depending on an external Python SDK — it's just REST + SSE, and aiohttp already handles both.

Sources:

OpenCode SDK docs
OpenCode Server docs
OpenCode GitHub
OpenCode internals deep dive
OpenCode message/session architecture (DeepWiki)