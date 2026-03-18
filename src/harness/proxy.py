"""Lightweight reverse proxy for capturing API requests and responses.

Sits between the Claude Agent SDK and the real API to capture:
- System prompt (Claude Code's built-in + user's appended)
- Tool definitions (JSON schemas for Read, Write, Bash, etc.)
- Context management events (applied_edits from response)
- Per-request token usage with cache breakdown
- Compaction events (when message count drops, captures summarized messages)
- Sampling parameters (model, temperature, max_tokens)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import ClientSession, web

logger = logging.getLogger(__name__)


def _hash(obj: object) -> str:
    """Stable SHA-256 hash of a JSON-serializable object."""
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _parse_sse_response(body: bytes) -> dict:
    """Parse SSE events from a streaming response to extract metadata.

    Extracts from message_start: usage, model
    Extracts from message_delta: context_management, final usage
    """
    result: dict = {}
    text = body.decode("utf-8", errors="replace")

    for block in text.split("\n\n"):
        lines = block.strip().split("\n")
        event_type = None
        data_str = None
        for line in lines:
            if line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data_str = line[6:]

        if not data_str:
            continue

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        if event_type == "message_start":
            msg = data.get("message", {})
            usage = msg.get("usage")
            if usage:
                result["usage_start"] = usage
            if msg.get("model"):
                result["response_model"] = msg["model"]

        elif event_type == "message_delta":
            delta = data.get("delta", {})
            usage = data.get("usage")
            if usage:
                result["usage_delta"] = usage
            ctx = data.get("context_management")
            if ctx:
                result["context_management"] = ctx

    return result


class CaptureProxy:
    """Reverse proxy that logs API request/response metadata to JSONL."""

    def __init__(self, raw_dump_count: int = 0) -> None:
        self._target_url: str = ""
        self._log_path: Path | None = None
        self._site: web.TCPSite | None = None
        self._runner: web.AppRunner | None = None
        self._request_index = 0
        self._raw_dump_count = raw_dump_count  # dump full req/resp for first N requests
        # Per-agent-context tracking (keyed by system_prompt_hash)
        self._main_system_hash: str | None = None
        self._per_agent_prev_count: dict[str | None, int] = {}
        self._seen_system_hashes: set[str | None] = set()
        self._seen_tools_hashes: set[str | None] = set()

    async def start(self, target_url: str, log_path: Path) -> int:
        """Start the proxy server. Returns the assigned port."""
        self._target_url = target_url.rstrip("/")
        self._log_path = log_path
        self._request_index = 0
        self._main_system_hash = None
        self._per_agent_prev_count = {}
        self._seen_system_hashes = set()
        self._seen_tools_hashes = set()

        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self._handle)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await self._site.start()

        # Get the actual assigned port
        assert self._site._server is not None
        port = self._site._server.sockets[0].getsockname()[1]
        logger.info("Capture proxy started on port %d -> %s", port, self._target_url)
        return port

    async def stop(self) -> None:
        """Stop the proxy server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            logger.info("Capture proxy stopped")

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        """Forward request to target, log Messages API calls."""
        target = f"{self._target_url}/{request.match_info['path']}"
        body = await request.read()

        # Detect Messages API requests
        is_messages = request.method == "POST" and "/messages" in request.path

        # Parse request body (but don't log yet — wait for response)
        request_data: dict | None = None
        if is_messages and body:
            try:
                request_data = json.loads(body)
                self._request_index += 1
            except Exception:
                logger.exception("Failed to parse API request body")

        # Forward headers (drop host, it'll be set by aiohttp)
        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length", "transfer-encoding")
        }

        # Raw dump for first N requests
        should_dump_raw = (
            is_messages
            and self._raw_dump_count > 0
            and self._request_index <= self._raw_dump_count
            and self._log_path
        )

        async with ClientSession() as session:
            async with session.request(
                request.method, target, headers=headers, data=body
            ) as resp:
                # Build response, preserving status and safe headers
                response = web.StreamResponse(status=resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in (
                        "content-length", "transfer-encoding", "content-encoding",
                    ):
                        response.headers[k] = v
                await response.prepare(request)

                # Stream response body; collect for Messages API requests
                response_chunks: list[bytes] = []
                async for chunk in resp.content.iter_any():
                    await response.write(chunk)
                    if is_messages:
                        response_chunks.append(chunk)

                await response.write_eof()

                # Log combined request + response metadata
                if request_data is not None:
                    try:
                        resp_body = b"".join(response_chunks)
                        response_meta = _parse_sse_response(resp_body)
                        self._log_exchange(request_data, response_meta)
                    except Exception:
                        logger.exception("Failed to log API exchange")

                # Save raw dump
                if should_dump_raw and self._log_path:
                    raw_dir = self._log_path.parent / "raw_dumps"
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    idx = self._request_index
                    # Request
                    req_path = raw_dir / f"request_{idx:03d}.json"
                    with open(req_path, "wb") as f:
                        f.write(body)
                    # Request headers (strip auth)
                    safe_headers = {
                        k: v for k, v in headers.items()
                        if k.lower() not in ("x-api-key", "authorization")
                    }
                    hdr_path = raw_dir / f"request_{idx:03d}_headers.json"
                    with open(hdr_path, "w") as f:
                        json.dump(
                            {"method": request.method, "path": request.path,
                             "target": target, "headers": safe_headers},
                            f, indent=2,
                        )
                    # Response
                    resp_dump = b"".join(response_chunks)
                    resp_path = raw_dir / f"response_{idx:03d}.txt"
                    with open(resp_path, "wb") as f:
                        f.write(resp_dump)
                    # Response headers
                    resp_hdr_path = raw_dir / f"response_{idx:03d}_headers.json"
                    with open(resp_hdr_path, "w") as f:
                        json.dump(
                            {"status": resp.status,
                             "headers": dict(resp.headers)},
                            f, indent=2,
                        )
                    logger.info("Raw dump saved: request/response %d", idx)

                return response

    def _log_exchange(self, request_data: dict, response_meta: dict) -> None:
        """Log combined request + response metadata to JSONL."""
        if not self._log_path:
            return

        system = request_data.get("system")
        tools = request_data.get("tools")
        messages = request_data.get("messages", [])
        message_count = len(messages)

        system_hash = _hash(system) if system else None
        tools_hash = _hash(tools) if tools else None

        # Classify agent context
        if system is None and (not tools or len(tools) == 0):
            agent_context = "sdk_internal"
        elif self._main_system_hash is None:
            # First request with a system prompt establishes the main agent
            self._main_system_hash = system_hash
            agent_context = "main"
        elif system_hash == self._main_system_hash:
            agent_context = "main"
        else:
            agent_context = "subagent"

        # Per-context compaction detection
        context_key = system_hash
        prev_count = self._per_agent_prev_count.get(context_key, 0)
        is_compaction = (
            message_count < prev_count
            and prev_count > 0
            and agent_context != "sdk_internal"
        )
        self._per_agent_prev_count[context_key] = message_count

        # Build log entry
        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_index": self._request_index,
            "agent_context": agent_context,
            "model": request_data.get("model"),
            "sampling_params": {
                k: request_data.get(k)
                for k in ("temperature", "max_tokens", "top_p", "top_k")
                if request_data.get(k) is not None
            },
            "message_count": message_count,
        }

        # System prompt: full on first appearance, hash-only on repeat
        if system_hash not in self._seen_system_hashes:
            entry["system_prompt"] = system
            entry["system_prompt_hash"] = system_hash
            self._seen_system_hashes.add(system_hash)
        else:
            entry["system_prompt_hash"] = system_hash

        # Tools: full on first appearance, hash-only on repeat
        if tools_hash not in self._seen_tools_hashes:
            entry["tools"] = tools
            entry["tools_hash"] = tools_hash
            self._seen_tools_hashes.add(tools_hash)
        else:
            entry["tools_hash"] = tools_hash

        # Compaction: capture the summarized messages
        entry["is_compaction"] = is_compaction
        if is_compaction:
            entry["compacted_messages"] = messages
            logger.info(
                "Compaction detected (context=%s): message count %d -> %d",
                agent_context, prev_count, message_count,
            )

        # Response metadata
        if response_meta.get("context_management"):
            entry["context_management"] = response_meta["context_management"]
            applied = response_meta["context_management"].get("applied_edits", [])
            if applied:
                logger.info(
                    "Context management: %d applied edits", len(applied),
                )

        # Per-request token usage from response
        usage_start = response_meta.get("usage_start", {})
        usage_delta = response_meta.get("usage_delta", {})
        if usage_start or usage_delta:
            entry["usage"] = {
                "input_tokens": usage_start.get("input_tokens"),
                "output_tokens": usage_delta.get("output_tokens"),
                "cache_creation_input_tokens": usage_start.get("cache_creation_input_tokens"),
                "cache_read_input_tokens": usage_start.get("cache_read_input_tokens"),
                "cache_creation": usage_start.get("cache_creation"),
                "service_tier": usage_start.get("service_tier"),
            }

        # Append to JSONL
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")


def get_target_url(provider: str, base_url: str | None) -> str:
    """Resolve the real API URL for a given provider."""
    if base_url:
        return base_url
    if provider == "openrouter":
        return "https://openrouter.ai/api"
    # Default to Anthropic API for all other providers.
    # For bedrock/vertex, Claude Code may or may not route through
    # ANTHROPIC_BASE_URL — if it doesn't, the proxy will simply
    # receive no requests and api_captures.jsonl will be empty.
    return "https://api.anthropic.com"
