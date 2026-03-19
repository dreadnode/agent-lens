"""Tests for harness.resample — header building, thinking signatures, request discovery, variants."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.resample import (
    _build_headers,
    _clean_thinking_signatures,
    _is_ollama_target,
    _next_variant_id,
    _prepare_request,
    _resolve_api_key,
    dump_request,
    list_requests,
    resolve_session_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw_dumps(session_dir: Path, requests: list[dict]) -> Path:
    """Create raw_dumps/ with request files."""
    raw = session_dir / "raw_dumps"
    raw.mkdir(parents=True)
    for i, req in enumerate(requests, 1):
        (raw / f"request_{i:03d}.json").write_text(json.dumps(req))
        (raw / f"request_{i:03d}_headers.json").write_text(json.dumps({
            "target": "https://api.anthropic.com/v1/messages",
            "headers": {"content-type": "application/json"},
            "provider": "anthropic",
        }))
    return raw


def _make_session(run_dir: Path, session_index: int, replicate: int | None = None) -> Path:
    """Create a session directory with a sample request."""
    if replicate is not None:
        d = run_dir / f"session_{session_index:02d}_r{replicate:02d}"
    else:
        d = run_dir / f"session_{session_index:02d}"
    d.mkdir(parents=True)
    _make_raw_dumps(d, [
        {"model": "claude-test", "messages": [{"role": "user", "content": "hello"}], "stream": True},
        {"model": "claude-test", "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "hmm", "signature": "sig1"},
                {"type": "text", "text": "response"},
            ]},
            {"role": "user", "content": "follow up"},
        ], "stream": True},
    ])
    return d


# ---------------------------------------------------------------------------
# resolve_session_dir
# ---------------------------------------------------------------------------

class TestResolveSessionDir:
    def test_plain_session(self, tmp_path: Path):
        (tmp_path / "session_01").mkdir()
        d = resolve_session_dir(tmp_path, 1)
        assert d.name == "session_01"

    def test_replicate_session(self, tmp_path: Path):
        (tmp_path / "session_02_r03").mkdir()
        d = resolve_session_dir(tmp_path, 2, replicate=3)
        assert d.name == "session_02_r03"

    def test_missing_session_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            resolve_session_dir(tmp_path, 99)

    def test_missing_replicate_raises(self, tmp_path: Path):
        (tmp_path / "session_01").mkdir()
        with pytest.raises(FileNotFoundError):
            resolve_session_dir(tmp_path, 1, replicate=5)


# ---------------------------------------------------------------------------
# _prepare_request
# ---------------------------------------------------------------------------

class TestPrepareRequest:
    def test_sets_stream_false(self):
        req = {"stream": True, "model": "test"}
        result = _prepare_request(req)
        assert result["stream"] is False

    def test_cleans_thinking_signatures(self):
        req = {
            "model": "test",
            "messages": [
                {"role": "assistant", "content": [
                    {"type": "thinking", "thinking": "x", "signature": "s"},
                ]}
            ],
        }
        result = _prepare_request(req)
        assert "signature" not in result["messages"][0]["content"][0]

    def test_model_override(self):
        req = {"model": "old", "stream": True}
        result = _prepare_request(req, model_override="new-model")
        assert result["model"] == "new-model"

    def test_no_model_override(self):
        req = {"model": "original", "stream": True}
        result = _prepare_request(req)
        assert result["model"] == "original"


# ---------------------------------------------------------------------------
# dump_request
# ---------------------------------------------------------------------------

class TestDumpRequest:
    def test_dump_returns_prepared_request(self, tmp_path: Path):
        _make_session(tmp_path, 1)
        req = dump_request(tmp_path, 1, 1)
        assert req["stream"] is False
        assert req["model"] == "claude-test"

    def test_dump_replicate(self, tmp_path: Path):
        _make_session(tmp_path, 2, replicate=1)
        req = dump_request(tmp_path, 2, 1, replicate=1)
        assert req["model"] == "claude-test"

    def test_dump_cleans_signatures(self, tmp_path: Path):
        _make_session(tmp_path, 1)
        req = dump_request(tmp_path, 1, 2)  # request 2 has thinking blocks
        assistant_msg = req["messages"][1]
        thinking_block = assistant_msg["content"][0]
        assert "signature" not in thinking_block


# ---------------------------------------------------------------------------
# list_requests
# ---------------------------------------------------------------------------

class TestListRequests:
    def test_lists_requests(self, tmp_path: Path, capsys):
        _make_session(tmp_path, 1)
        list_requests(tmp_path, 1)
        captured = capsys.readouterr()
        assert "2 captured requests" in captured.out
        assert "claude-test" in captured.out

    def test_no_raw_dumps_exits(self, tmp_path: Path):
        from click.exceptions import Exit
        (tmp_path / "session_01").mkdir()
        with pytest.raises(Exit):
            list_requests(tmp_path, 1)

    def test_shows_existing_resamples(self, tmp_path: Path, capsys):
        session_dir = _make_session(tmp_path, 1)
        # Create some resamples
        resample_dir = session_dir / "resamples" / "request_001"
        resample_dir.mkdir(parents=True)
        (resample_dir / "sample_01.json").write_text("{}")
        (resample_dir / "sample_02.json").write_text("{}")

        list_requests(tmp_path, 1)
        captured = capsys.readouterr()
        assert "2 samples" in captured.out

    def test_shows_existing_variants(self, tmp_path: Path, capsys):
        session_dir = _make_session(tmp_path, 1)
        variant_dir = session_dir / "resamples" / "request_001_v01"
        variant_dir.mkdir(parents=True)

        list_requests(tmp_path, 1)
        captured = capsys.readouterr()
        assert "1 variants" in captured.out


# ---------------------------------------------------------------------------
# _next_variant_id
# ---------------------------------------------------------------------------

class TestNextVariantId:
    def test_first_variant(self, tmp_path: Path):
        assert _next_variant_id(tmp_path, 1) == "v01"

    def test_increments(self, tmp_path: Path):
        resamples = tmp_path / "resamples"
        (resamples / "request_001_v01").mkdir(parents=True)
        (resamples / "request_001_v02").mkdir(parents=True)
        assert _next_variant_id(tmp_path, 1) == "v03"

    def test_ignores_other_requests(self, tmp_path: Path):
        resamples = tmp_path / "resamples"
        (resamples / "request_002_v01").mkdir(parents=True)
        (resamples / "request_002_v02").mkdir(parents=True)
        # Request 1 should still start at v01
        assert _next_variant_id(tmp_path, 1) == "v01"


# ---------------------------------------------------------------------------
# _clean_thinking_signatures (kept from original)
# ---------------------------------------------------------------------------

class TestCleanThinkingSignatures:
    def test_strips_signatures(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Let me think...",
                        "signature": "abc123",
                    },
                    {"type": "text", "text": "Here's my answer"},
                ],
            }
        ]
        cleaned = _clean_thinking_signatures(messages)
        thinking_block = cleaned[0]["content"][0]

        assert thinking_block["type"] == "thinking"
        assert thinking_block["thinking"] == "Let me think..."
        assert "signature" not in thinking_block

    def test_preserves_non_thinking_blocks(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "tool_use", "id": "tc1", "name": "Read", "input": {}},
                ],
            }
        ]
        cleaned = _clean_thinking_signatures(messages)
        assert cleaned[0]["content"][0] == {"type": "text", "text": "hello"}
        assert cleaned[0]["content"][1]["type"] == "tool_use"

    def test_handles_string_content(self):
        messages = [{"role": "user", "content": "Hello!"}]
        cleaned = _clean_thinking_signatures(messages)
        assert cleaned == messages

    def test_handles_empty_messages(self):
        assert _clean_thinking_signatures([]) == []

    def test_multiple_thinking_blocks(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "thought 1", "signature": "s1"},
                    {"type": "text", "text": "answer"},
                    {"type": "thinking", "thinking": "thought 2", "signature": "s2"},
                ],
            }
        ]
        cleaned = _clean_thinking_signatures(messages)
        assert "signature" not in cleaned[0]["content"][0]
        assert "signature" not in cleaned[0]["content"][2]
        assert cleaned[0]["content"][0]["thinking"] == "thought 1"
        assert cleaned[0]["content"][2]["thinking"] == "thought 2"


# ---------------------------------------------------------------------------
# _build_headers (kept from original)
# ---------------------------------------------------------------------------

class TestBuildHeaders:
    def test_openrouter_headers(self):
        headers = _build_headers(
            captured_headers={"content-type": "application/json", "x-api-key": "old"},
            api_key="new-key",
            target_url="https://openrouter.ai/api/v1/messages",
        )
        assert headers["Authorization"] == "Bearer new-key"
        assert "x-api-key" not in headers

    def test_anthropic_headers(self):
        headers = _build_headers(
            captured_headers={"content-type": "application/json", "Authorization": "old"},
            api_key="new-key",
            target_url="https://api.anthropic.com/v1/messages",
        )
        assert headers["x-api-key"] == "new-key"
        assert "Authorization" not in headers

    def test_removes_stainless_headers(self):
        headers = _build_headers(
            captured_headers={
                "content-type": "application/json",
                "x-stainless-version": "1.0",
                "x-stainless-os": "macos",
            },
            api_key="key",
            target_url="https://api.anthropic.com/v1/messages",
        )
        assert "x-stainless-version" not in headers
        assert "x-stainless-os" not in headers

    def test_removes_connection_headers(self):
        headers = _build_headers(
            captured_headers={
                "Connection": "keep-alive",
                "Accept-Encoding": "gzip",
                "content-type": "application/json",
            },
            api_key="key",
            target_url="https://api.anthropic.com/v1/messages",
        )
        assert "Connection" not in headers
        assert "Accept-Encoding" not in headers

    def test_preserves_other_headers(self):
        headers = _build_headers(
            captured_headers={
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            api_key="key",
            target_url="https://api.anthropic.com/v1/messages",
        )
        assert headers["content-type"] == "application/json"
        assert headers["anthropic-version"] == "2023-06-01"

    def test_ollama_headers_no_api_key(self):
        headers = _build_headers(
            captured_headers={"content-type": "application/json"},
            api_key="",
            target_url="http://localhost:11434/v1/messages",
        )
        assert headers["x-api-key"] == "ollama"
        assert "Authorization" not in headers

    def test_ollama_headers_provider_marker(self):
        headers = _build_headers(
            captured_headers={"content-type": "application/json"},
            api_key="",
            target_url="http://custom:9999/v1/messages",
            provider="ollama",
        )
        assert headers["x-api-key"] == "ollama"


class TestIsOllamaTarget:
    def test_localhost(self):
        assert _is_ollama_target("http://localhost:11434/v1/messages") is True

    def test_loopback(self):
        assert _is_ollama_target("http://127.0.0.1:11434/v1/messages") is True

    def test_default_port(self):
        assert _is_ollama_target("http://gpu-box:11434/v1/messages") is True

    def test_provider_marker(self):
        assert _is_ollama_target("http://custom:9999/v1/messages", "ollama") is True

    def test_anthropic(self):
        assert _is_ollama_target("https://api.anthropic.com/v1/messages") is False

    def test_openrouter(self):
        assert _is_ollama_target("https://openrouter.ai/api/v1/messages") is False


class TestResolveApiKeyOllama:
    def test_ollama_returns_empty(self):
        assert _resolve_api_key("http://localhost:11434/v1/messages") == ""

    def test_ollama_custom_port_returns_empty(self):
        assert _resolve_api_key("http://gpu-box:11434/v1/messages") == ""

    def test_ollama_provider_marker_returns_empty(self):
        assert _resolve_api_key("http://custom:9999/v1/messages", "ollama") == ""
