"""Resample a specific API turn to get N fresh responses.

Reads the raw request dump + captured headers, replays the exact same request
to the same target URL, and saves each response alongside the original run.

Supports:
- Vanilla resampling (same request, multiple responses)
- Variant resampling (edited request via --input JSON file)
- Request discovery (--list-requests)
- Replicate sessions (--replicate)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import typer

logger = logging.getLogger(__name__)


def resolve_session_dir(run_dir: Path, session_index: int, replicate: int | None = None) -> Path:
    """Resolve the session directory, supporting replicate sessions."""
    if replicate is not None:
        d = run_dir / f"session_{session_index:02d}_r{replicate:02d}"
    else:
        d = run_dir / f"session_{session_index:02d}"
    if not d.exists():
        raise FileNotFoundError(f"Session directory not found: {d}")
    return d


def _load_request(raw_dumps_dir: Path, request_index: int) -> dict:
    """Load a raw request JSON from the dumps directory."""
    req_path = raw_dumps_dir / f"request_{request_index:03d}.json"
    if not req_path.exists():
        raise FileNotFoundError(
            f"No raw dump found at {req_path}. "
            "Ensure the run was captured with API request dumping enabled."
        )
    with open(req_path) as f:
        return json.load(f)


def _load_headers(raw_dumps_dir: Path, request_index: int) -> dict:
    """Load captured request headers. Returns {target, headers} or defaults."""
    hdr_path = raw_dumps_dir / f"request_{request_index:03d}_headers.json"
    if hdr_path.exists():
        with open(hdr_path) as f:
            return json.load(f)
    return {}


def _clean_thinking_signatures(messages: list) -> list:
    """Strip thinking block signatures — they're response-specific."""
    cleaned = []
    for msg in messages:
        if isinstance(msg.get("content"), list):
            cleaned_content = []
            for block in msg["content"]:
                if block.get("type") == "thinking":
                    cleaned_content.append({
                        "type": "thinking",
                        "thinking": block.get("thinking", ""),
                    })
                else:
                    cleaned_content.append(block)
            cleaned.append({**msg, "content": cleaned_content})
        else:
            cleaned.append(msg)
    return cleaned


def _build_headers(
    captured_headers: dict[str, str], api_key: str, target_url: str
) -> dict[str, str]:
    """Build replay headers from captured headers, replacing auth."""
    headers = {**captured_headers}
    # Use the right auth header for the target
    if "openrouter.ai" in target_url:
        headers["Authorization"] = f"Bearer {api_key}"
        headers.pop("x-api-key", None)
    else:
        headers["x-api-key"] = api_key
        headers.pop("Authorization", None)
    # Remove stale/unnecessary headers
    for key in list(headers):
        if key.lower().startswith("x-stainless"):
            del headers[key]
    headers.pop("Connection", None)
    headers.pop("Accept-Encoding", None)
    return headers


def _resolve_api_config(raw_dumps_dir: Path, request_index: int) -> tuple[str, dict[str, str]]:
    """Resolve target URL and captured headers for a request.

    Returns (target_url, captured_headers).
    """
    import os

    hdr_data = _load_headers(raw_dumps_dir, request_index)
    target_url = hdr_data.get("target")
    captured_headers = hdr_data.get("headers", {})

    if not target_url:
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        target_url = f"{base_url.rstrip('/')}/v1/messages"
        captured_headers = {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    return target_url, captured_headers


def _resolve_api_key(target_url: str) -> str:
    """Resolve the API key based on the target URL."""
    import os

    if "openrouter.ai" in target_url:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            typer.echo("Error: OPENROUTER_API_KEY not set", err=True)
            raise typer.Exit(1)
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            typer.echo("Error: ANTHROPIC_API_KEY not set", err=True)
            raise typer.Exit(1)
    return api_key


async def _call_api(url: str, headers: dict[str, str], request_data: dict) -> dict:
    """Call the API once (non-streaming) with the exact captured request."""
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(url, json=request_data, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _prepare_request(
    request_data: dict, model_override: str | None = None
) -> dict:
    """Apply standard modifications to a request before resampling."""
    request_data["stream"] = False
    if isinstance(request_data.get("messages"), list):
        request_data["messages"] = _clean_thinking_signatures(request_data["messages"])
    if model_override:
        request_data["model"] = model_override
    return request_data


# ---------------------------------------------------------------------------
# List requests
# ---------------------------------------------------------------------------

def list_requests(
    run_dir: Path,
    session_index: int,
    replicate: int | None = None,
) -> None:
    """List available raw request dumps for a session."""
    session_dir = resolve_session_dir(run_dir, session_index, replicate)
    raw_dumps_dir = session_dir / "raw_dumps"

    if not raw_dumps_dir.exists():
        typer.echo(
            f"No raw_dumps/ directory in {session_dir}. "
            "Run with capture_api_requests: true to enable.",
            err=True,
        )
        raise typer.Exit(1)

    request_files = sorted(raw_dumps_dir.glob("request_[0-9][0-9][0-9].json"))
    if not request_files:
        typer.echo("No request dumps found.", err=True)
        raise typer.Exit(1)

    rep_str = f" (replicate {replicate})" if replicate else ""
    typer.echo(f"Session {session_index}{rep_str}: {len(request_files)} captured requests\n")

    for req_path in request_files:
        idx = int(req_path.stem.split("_")[1])
        try:
            with open(req_path) as f:
                data = json.load(f)
            model = data.get("model", "?")
            messages = data.get("messages", [])
            msg_count = len(messages)

            # Summarize the last user message
            last_user = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        last_user = content[:80]
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict):
                                if block.get("type") == "text":
                                    last_user = block["text"][:80]
                                    break
                                elif block.get("type") == "tool_result":
                                    last_user = f"[tool_result for {block.get('tool_use_id', '?')[:12]}]"
                                    break
                    break

            # Check for existing resamples
            resample_dir = session_dir / "resamples" / f"request_{idx:03d}"
            sample_count = len(list(resample_dir.glob("sample_*.json"))) if resample_dir.exists() else 0
            variant_count = len(list(
                d for d in (session_dir / "resamples").glob(f"request_{idx:03d}_v*")
                if d.is_dir()
            )) if (session_dir / "resamples").exists() else 0

            resample_str = ""
            if sample_count or variant_count:
                parts = []
                if sample_count:
                    parts.append(f"{sample_count} samples")
                if variant_count:
                    parts.append(f"{variant_count} variants")
                resample_str = f"  [{', '.join(parts)}]"

            typer.echo(
                f"  {idx:3d}  |  {msg_count:2d} messages  |  {model}"
                f"  |  {last_user}{resample_str}"
            )
        except Exception as e:
            typer.echo(f"  {idx:3d}  |  error reading: {e}")


# ---------------------------------------------------------------------------
# Dump request for editing
# ---------------------------------------------------------------------------

def dump_request(
    run_dir: Path,
    session_index: int,
    request_index: int,
    replicate: int | None = None,
) -> dict:
    """Load and prepare a request for editing. Returns the request data."""
    session_dir = resolve_session_dir(run_dir, session_index, replicate)
    raw_dumps_dir = session_dir / "raw_dumps"
    request_data = _load_request(raw_dumps_dir, request_index)
    return _prepare_request(request_data)


# ---------------------------------------------------------------------------
# Vanilla resample
# ---------------------------------------------------------------------------

async def run_resample(
    run_dir: Path,
    session_index: int,
    request_index: int,
    count: int,
    model_override: str | None = None,
    replicate: int | None = None,
) -> Path:
    """Resample a specific request N times and save results.

    Returns the directory containing the resample results.
    """
    session_dir = resolve_session_dir(run_dir, session_index, replicate)
    raw_dumps_dir = session_dir / "raw_dumps"

    request_data = _load_request(raw_dumps_dir, request_index)
    target_url, captured_headers = _resolve_api_config(raw_dumps_dir, request_index)

    _prepare_request(request_data, model_override)

    api_key = _resolve_api_key(target_url)
    headers = _build_headers(captured_headers, api_key, target_url)

    # Output directory
    resample_dir = session_dir / "resamples" / f"request_{request_index:03d}"
    resample_dir.mkdir(parents=True, exist_ok=True)

    # Find next sample number (allow appending to existing resamples)
    existing = list(resample_dir.glob("sample_*.json"))
    next_num = len(existing) + 1

    typer.echo(
        f"Resampling request {request_index} from session {session_index} "
        f"({count} samples, model={request_data.get('model')}, target={target_url})..."
    )

    async def _do_sample(sample_num: int) -> None:
        try:
            response = await _call_api(target_url, headers, request_data)
            sample_path = resample_dir / f"sample_{sample_num:02d}.json"
            with open(sample_path, "w") as f:
                json.dump(response, f, indent=2)

            content = response.get("content", [])
            block_types = [b.get("type", "?") for b in content]
            usage = response.get("usage", {})
            out_tokens = usage.get("output_tokens", "?")
            typer.echo(f"  Sample {sample_num}... done ({out_tokens} tokens, blocks: {block_types})")

        except httpx.HTTPStatusError as e:
            typer.echo(f"  Sample {sample_num}... error: {e.response.status_code} {e.response.text[:200]}")
            error_path = resample_dir / f"sample_{sample_num:02d}_error.json"
            with open(error_path, "w") as f:
                json.dump({"error": str(e), "status": e.response.status_code, "body": e.response.text}, f, indent=2)

        except Exception as e:
            typer.echo(f"  Sample {sample_num}... error: {e}")

    tasks = [_do_sample(next_num + i) for i in range(count)]
    await asyncio.gather(*tasks)

    typer.echo(f"\nResults saved to: {resample_dir}")
    return resample_dir


# ---------------------------------------------------------------------------
# Variant resample (edit & resample)
# ---------------------------------------------------------------------------

def _next_variant_id(session_dir: Path, request_index: int) -> str:
    """Find the next variant ID (v01, v02, ...) for a request."""
    resamples_dir = session_dir / "resamples"
    if not resamples_dir.exists():
        return "v01"
    prefix = f"request_{request_index:03d}_v"
    existing = sorted(
        int(d.name[len(prefix):])
        for d in resamples_dir.iterdir()
        if d.is_dir() and d.name.startswith(prefix) and d.name[len(prefix):].isdigit()
    )
    next_num = (existing[-1] + 1) if existing else 1
    return f"v{next_num:02d}"


async def run_variant_resample(
    run_dir: Path,
    session_index: int,
    request_index: int,
    edited_request: dict,
    label: str,
    count: int,
    model_override: str | None = None,
    replicate: int | None = None,
) -> Path:
    """Resample with an edited request body and save as a variant.

    Args:
        run_dir: Path to the run directory.
        session_index: Session index.
        request_index: Original request index this variant is based on.
        edited_request: The modified request body (already prepared).
        label: Human-readable label for this variant.
        count: Number of samples to generate.
        model_override: Optional model override.
        replicate: Optional replicate number for replicate sessions.

    Returns the variant directory.
    """
    session_dir = resolve_session_dir(run_dir, session_index, replicate)
    raw_dumps_dir = session_dir / "raw_dumps"

    # Resolve API config from the original request headers
    target_url, captured_headers = _resolve_api_config(raw_dumps_dir, request_index)

    # Apply model override to the edited request
    if model_override:
        edited_request["model"] = model_override
    edited_request["stream"] = False

    api_key = _resolve_api_key(target_url)
    headers = _build_headers(captured_headers, api_key, target_url)

    # Create variant directory
    variant_id = _next_variant_id(session_dir, request_index)
    variant_dir = session_dir / "resamples" / f"request_{request_index:03d}_{variant_id}"
    variant_dir.mkdir(parents=True, exist_ok=True)

    # Save variant metadata
    variant_meta = {
        "label": label,
        "base_request_index": request_index,
        "edits": [],  # CLI edits are opaque — the full edited request is in request.json
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "cli",
    }
    with open(variant_dir / "variant.json", "w") as f:
        json.dump(variant_meta, f, indent=2)

    # Save the edited request
    with open(variant_dir / "request.json", "w") as f:
        json.dump(edited_request, f, indent=2)

    typer.echo(
        f"Variant {variant_id} ({label!r}) for request {request_index} "
        f"({count} samples, model={edited_request.get('model')}, target={target_url})..."
    )

    async def _do_sample(sample_num: int) -> None:
        try:
            response = await _call_api(target_url, headers, edited_request)
            sample_path = variant_dir / f"sample_{sample_num:02d}.json"
            with open(sample_path, "w") as f:
                json.dump(response, f, indent=2)

            content = response.get("content", [])
            block_types = [b.get("type", "?") for b in content]
            usage = response.get("usage", {})
            out_tokens = usage.get("output_tokens", "?")
            typer.echo(f"  Sample {sample_num}... done ({out_tokens} tokens, blocks: {block_types})")

        except httpx.HTTPStatusError as e:
            typer.echo(f"  Sample {sample_num}... error: {e.response.status_code} {e.response.text[:200]}")
            error_path = variant_dir / f"sample_{sample_num:02d}_error.json"
            with open(error_path, "w") as f:
                json.dump({"error": str(e), "status": e.response.status_code, "body": e.response.text}, f, indent=2)

        except Exception as e:
            typer.echo(f"  Sample {sample_num}... error: {e}")

    tasks = [_do_sample(i + 1) for i in range(count)]
    await asyncio.gather(*tasks)

    typer.echo(f"\nVariant saved to: {variant_dir}")
    return variant_dir
