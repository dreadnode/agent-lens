"""CLI entry point for the harness.

Commands:
    harness run <config.yaml> [--model MODEL] [--tag TAG] [--session-mode MODE]
    harness list [--runs-dir DIR]
    harness inspect <run_dir>
    harness resample <run_dir> --session N --request N --count N
    harness resample-edit <run_dir> --session N --request N --dump / --input FILE
    harness resample-session <run_dir> --session N --count N
    harness replay <run_dir> --session N --turn N --count N
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from harness.config import SessionMode, load_config

app = typer.Typer(
    name="harness",
    help="Multi-session agent interpretability harness",
    add_completion=False,
)


@app.command()
def run(
    config_path: Annotated[Path, typer.Argument(help="Path to YAML config file")],
    model: Annotated[Optional[str], typer.Option(help="Override model")] = None,
    tag: Annotated[Optional[list[str]], typer.Option(help="Add tags")] = None,
    session_mode: Annotated[Optional[SessionMode], typer.Option(help="Override session mode")] = None,
    run_name: Annotated[Optional[str], typer.Option(help="Custom run name")] = None,
    runs_dir: Annotated[Path, typer.Option(help="Output directory")] = Path("runs"),
    no_capture: Annotated[bool, typer.Option(help="Disable API request capture (disables resampling)")] = False,
) -> None:
    """Run a multi-session experiment from a config file."""
    config = load_config(config_path)

    if model:
        config.model = model
    if tag:
        config.tags.extend(tag)
    if session_mode:
        config.session_mode = session_mode
    if run_name:
        config.run_name = run_name
    if no_capture:
        config.capture_api_requests = False

    from harness.experiment import run_experiment

    run_dir = asyncio.run(run_experiment(config, output_base=runs_dir))
    typer.echo(f"\nOutputs saved to: {run_dir}")


@app.command(name="list")
def list_runs(
    runs_dir: Annotated[Path, typer.Option(help="Runs directory")] = Path("runs"),
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """List all completed runs."""
    if not runs_dir.exists():
        if output_json:
            typer.echo("[]")
        else:
            typer.echo("No runs directory found.")
        raise typer.Exit()

    run_dirs = sorted(runs_dir.iterdir())
    if not run_dirs:
        if output_json:
            typer.echo("[]")
        else:
            typer.echo("No runs found.")
        raise typer.Exit()

    json_entries = []
    for d in run_dirs:
        if not d.is_dir():
            continue
        meta_path = d / "run_meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)

            if output_json:
                json_entries.append({
                    "run_name": d.name,
                    "model": meta.get("model"),
                    "session_mode": meta.get("session_mode"),
                    "session_count": meta.get("session_count"),
                    "total_steps": meta.get("total_steps"),
                    "total_cost_usd": meta.get("total_cost_usd"),
                    "errors": meta.get("errors", []),
                    "path": str(d),
                })
            else:
                sessions = meta.get("session_count", "?")
                mode = meta.get("session_mode", "?")
                model_name = meta.get("model", "?")
                steps = meta.get("total_steps", "?")
                cost = meta.get("total_cost_usd")
                cost_str = f"${cost:.4f}" if cost is not None else "n/a"
                errors = len(meta.get("errors", []))
                err_str = f" [{errors} errors]" if errors else ""
                typer.echo(
                    f"  {d.name}  |  {model_name}  |  {mode}  |  "
                    f"{sessions} sessions, {steps} steps  |  {cost_str}{err_str}"
                )
        elif not output_json:
            typer.echo(f"  {d.name}  |  (no metadata)")

    if output_json:
        typer.echo(json.dumps(json_entries, indent=2, default=str))


@app.command()
def inspect(
    run_dir: Annotated[Path, typer.Argument(help="Path to run directory")],
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Inspect a completed run: sessions, steps, tool calls, writes, compaction."""
    meta_path = run_dir / "run_meta.json"
    if not meta_path.exists():
        typer.echo(f"No run_meta.json found in {run_dir}")
        raise typer.Exit(1)

    with open(meta_path) as f:
        meta = json.load(f)

    # Add changelog to meta for JSON output
    changelog_events = []
    changelog = run_dir / "state_changelog.jsonl"
    if changelog.exists() and changelog.stat().st_size > 0:
        with open(changelog) as f:
            for line in f:
                event = json.loads(line)
                changelog_events.append({
                    "session_index": event["session_index"],
                    "step_id": event["step_id"],
                    "file_path": event["file_path"],
                    "diff_stats": event.get("diff_stats", {}),
                })

    if output_json:
        meta["file_changes"] = changelog_events
        typer.echo(json.dumps(meta, indent=2, default=str))
        return

    typer.echo(f"Run: {meta['run_name']}")
    typer.echo(f"Model: {meta['model']} ({meta.get('provider', 'unknown')})")
    typer.echo(f"Mode: {meta['session_mode']}")
    typer.echo(f"Tags: {', '.join(meta.get('tags', []))}")
    typer.echo(f"Total: {meta['total_steps']} steps, {meta['total_tool_calls']} tool calls")

    cost = meta.get("total_cost_usd")
    if cost is not None:
        typer.echo(f"Cost: ${cost:.4f}")

    compactions = meta.get("total_compaction_events", 0)
    if compactions:
        typer.echo(f"Compaction events: {compactions}")

    subagents = meta.get("total_subagent_invocations", 0)
    if subagents:
        typer.echo(f"Subagent invocations: {subagents}")

    typer.echo(f"File writes: {meta['total_file_writes']}")
    typer.echo("")

    for s in meta.get("sessions", []):
        idx = s["session_index"]
        steps = s.get("step_count", 0)
        tools = s.get("tool_call_count", 0)
        cost_s = s.get("total_cost_usd")
        cost_str = f"  ${cost_s:.4f}" if cost_s is not None else ""
        resumed = s.get("resumed_from")
        error = s.get("error")

        resume_str = f"  (resumed from {resumed})" if resumed else ""
        err_str = f"  ERROR: {error[:80]}" if error else ""
        sub_count = s.get("subagent_count", 0)
        sub_str = f", {sub_count} subagents" if sub_count else ""

        typer.echo(
            f"  Session {idx}: {steps} steps, {tools} tool calls"
            f"{cost_str}{sub_str}{resume_str}{err_str}"
        )

    if changelog_events:
        typer.echo("")
        typer.echo("File changes:")
        for event in changelog_events:
            stats = event["diff_stats"]
            typer.echo(
                f"  session {event['session_index']}, step {event['step_id']}: "
                f"{event['file_path']} "
                f"(+{stats.get('added', 0)}/-{stats.get('removed', 0)})"
            )


@app.command()
def resample(
    run_dir: Annotated[Path, typer.Argument(help="Path to run directory")],
    session: Annotated[int, typer.Option(help="Session index")] = 1,
    request: Annotated[int, typer.Option(help="Request index to resample")] = 1,
    count: Annotated[int, typer.Option(help="Number of resamples")] = 5,
    model: Annotated[Optional[str], typer.Option(help="Override model (default: use original)")] = None,
    replicate: Annotated[Optional[int], typer.Option(help="Replicate number (for session_NN_rNN dirs)")] = None,
    list_requests: Annotated[bool, typer.Option("--list-requests", help="List available requests and exit")] = False,
) -> None:
    """Resample a specific API turn to get N fresh responses (no tool execution).

    Use --list-requests to discover available request indices before resampling.
    Use --replicate to target replicate sessions (e.g. session_02_r01).
    """
    from harness.resample import list_requests as _list_requests, run_resample

    if list_requests:
        _list_requests(run_dir, session, replicate)
        raise typer.Exit()

    asyncio.run(run_resample(
        run_dir=run_dir,
        session_index=session,
        request_index=request,
        count=count,
        model_override=model,
        replicate=replicate,
    ))


@app.command(name="resample-edit")
def resample_edit(
    run_dir: Annotated[Path, typer.Argument(help="Path to run directory")],
    session: Annotated[int, typer.Option(help="Session index")] = 1,
    request: Annotated[int, typer.Option(help="Request index")] = 1,
    dump: Annotated[bool, typer.Option("--dump", help="Dump the request JSON to stdout for editing")] = False,
    input_file: Annotated[Optional[Path], typer.Option("--input", help="Path to edited request JSON")] = None,
    label: Annotated[str, typer.Option(help="Label for this variant")] = "cli-edit",
    count: Annotated[int, typer.Option(help="Number of resamples")] = 5,
    model: Annotated[Optional[str], typer.Option(help="Override model")] = None,
    replicate: Annotated[Optional[int], typer.Option(help="Replicate number")] = None,
) -> None:
    """Edit & resample: modify a captured request and resample with the edited version.

    Two-step workflow:

      1. Dump the request for editing:
         harness resample-edit runs/my-run --session 1 --request 5 --dump > edit.json

      2. Edit the JSON, then resample with the modified request:
         harness resample-edit runs/my-run --session 1 --request 5 \\
           --input edit.json --label "removed hedging" --count 5

    Or pipe from stdin:
         cat edit.json | harness resample-edit runs/my-run --session 1 --request 5 \\
           --input - --label "piped edit" --count 5

    The variant is saved alongside vanilla resamples and is visible in the web UI.
    """
    from harness.resample import dump_request, run_variant_resample

    if dump:
        request_data = dump_request(run_dir, session, request, replicate)
        json.dump(request_data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        raise typer.Exit()

    if input_file is None:
        typer.echo(
            "Error: Either --dump or --input is required.\n\n"
            "Usage:\n"
            "  Dump:   harness resample-edit <run> --session N --request N --dump > edit.json\n"
            "  Run:    harness resample-edit <run> --session N --request N --input edit.json --label 'my edit'",
            err=True,
        )
        raise typer.Exit(1)

    # Load edited request from file or stdin
    if str(input_file) == "-":
        edited_request = json.load(sys.stdin)
    else:
        if not input_file.exists():
            typer.echo(f"Error: Input file not found: {input_file}", err=True)
            raise typer.Exit(1)
        with open(input_file) as f:
            edited_request = json.load(f)

    asyncio.run(run_variant_resample(
        run_dir=run_dir,
        session_index=session,
        request_index=request,
        edited_request=edited_request,
        label=label,
        count=count,
        model_override=model,
        replicate=replicate,
    ))


@app.command()
def replay(
    run_dir: Annotated[Path, typer.Argument(help="Path to source run directory")],
    session: Annotated[int, typer.Option(help="Session index to replay from")] = 1,
    turn: Annotated[Optional[int], typer.Option(help="Turn index to replay from (1-based)")] = None,
    count: Annotated[int, typer.Option(help="Number of replay replicates")] = 1,
    prompt: Annotated[Optional[str], typer.Option(help="Additional prompt after tool results")] = None,
    list_turns: Annotated[bool, typer.Option("--list-turns", help="List available turns and exit")] = False,
    continue_sessions: Annotated[bool, typer.Option("--continue-sessions", help="Run remaining sessions after replay")] = False,
    runs_dir: Annotated[Path, typer.Option(help="Output directory")] = Path("runs"),
    replicate: Annotated[Optional[int], typer.Option(help="Replicate number (for session_NN_rNN dirs)")] = None,
) -> None:
    """Replay a session from a specific API turn N times.

    Each replay branches execution from the specified turn, resetting the
    filesystem to the state at that point and resuming with full tool execution.
    Each replay becomes a new independent run with full provenance.

    Use --list-turns to discover available turn indices before replaying.

    Examples:

        harness replay runs/my-run --session 1 --list-turns
        harness replay runs/my-run --session 1 --turn 5 --count 3
        harness replay runs/my-run --session 1 --turn 5 --prompt "Try a different approach"
    """
    from harness.replay import run_replay
    from harness.transcript import list_turns as _list_turns

    if list_turns:
        # Load transcript and uuid_map for turn listing
        session_dir = _find_replay_session_dir(run_dir, session, replicate)
        transcript_path = session_dir / "transcript.jsonl"
        if not transcript_path.exists():
            typer.echo(f"Error: No transcript.jsonl in {session_dir}", err=True)
            raise typer.Exit(1)

        uuid_map = None
        uuid_map_path = session_dir / "uuid_map.json"
        if uuid_map_path.exists():
            with open(uuid_map_path) as f:
                uuid_map = json.load(f)

        summaries = _list_turns(transcript_path, uuid_map)
        typer.echo(f"Turns in session {session} ({len(summaries)} total):\n")
        for s in summaries:
            tools = ", ".join(s.tool_names[:5]) if s.tool_names else "(no tools)"
            if len(s.tool_names) > 5:
                tools += f", +{len(s.tool_names) - 5} more"
            tag_str = f"  [{s.shadow_git_tag}]" if s.shadow_git_tag else ""
            results_str = f"  ({s.tool_result_count} results)" if s.tool_result_count else ""
            typer.echo(f"  Turn {s.turn_index}: {tools}{results_str}{tag_str}")
        raise typer.Exit()

    if turn is None:
        typer.echo("Error: --turn is required (use --list-turns to see available turns)", err=True)
        raise typer.Exit(1)

    new_dirs = asyncio.run(run_replay(
        source_run_dir=run_dir,
        session_index=session,
        turn_index=turn,
        count=count,
        prompt_override=prompt,
        continue_sessions=continue_sessions,
        output_base=runs_dir,
    ))


def _find_replay_session_dir(run_dir: Path, session_index: int, replicate: int | None = None) -> Path:
    """Find the session directory for replay listing."""
    if replicate is not None:
        d = run_dir / f"session_{session_index:02d}_r{replicate:02d}"
        if d.exists():
            return d
    d = run_dir / f"session_{session_index:02d}"
    if d.exists():
        return d
    d = run_dir / f"session_{session_index:02d}_r01"
    if d.exists():
        return d
    typer.echo(f"Error: No session {session_index} directory in {run_dir}", err=True)
    raise typer.Exit(1)


@app.command(name="resample-session")
def resample_session(
    run_dir: Annotated[Path, typer.Argument(help="Path to run directory")],
    session: Annotated[int, typer.Option(help="Session index to resample")] = 2,
    count: Annotated[int, typer.Option(help="Number of new replicates")] = 5,
) -> None:
    """Re-run a forked session N times to study behavioral variance.

    Reads config.yaml and run_meta.json from the run, finds the fork_from
    session_id, and runs N new replicates appending to existing ones.
    """
    from harness.resample_session import run_resample_session

    asyncio.run(run_resample_session(
        run_dir=run_dir,
        session_index=session,
        count=count,
    ))


if __name__ == "__main__":
    app()
