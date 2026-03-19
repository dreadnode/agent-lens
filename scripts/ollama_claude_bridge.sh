#!/bin/bash
set -euo pipefail

model=""
args=()

while (($#)); do
  case "$1" in
    --model)
      model="$2"
      shift 2
      ;;
    --model=*)
      model="${1#--model=}"
      shift
      ;;
    *)
      args+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$model" ]]; then
  echo "missing --model for ollama bridge" >&2
  exit 2
fi

real_claude="$(command -v claude)"
if [[ -z "$real_claude" ]]; then
  echo "real claude binary not found in PATH" >&2
  exit 3
fi

# AgentLens sets ANTHROPIC_BASE_URL to its capture proxy before invoking the
# CLI. `ollama launch claude` overwrites that variable with Ollama's local
# endpoint, which disables request capture/resampling. Preserve the proxy URL
# and restore it inside the actual Claude process while still allowing Ollama
# to provide its auth token and model defaults.
capture_base="${ANTHROPIC_BASE_URL:-}"
tmpdir="$(mktemp -d)"

cat > "$tmpdir/claude" <<'INNER'
#!/bin/bash
set -euo pipefail

if [[ -n "${AGENTLENS_CAPTURE_BASE_URL:-}" ]]; then
  export ANTHROPIC_BASE_URL="$AGENTLENS_CAPTURE_BASE_URL"
fi

exec "$AGENTLENS_REAL_CLAUDE" "$@"
INNER

chmod +x "$tmpdir/claude"

export AGENTLENS_REAL_CLAUDE="$real_claude"
export AGENTLENS_CAPTURE_BASE_URL="$capture_base"
export PATH="$tmpdir:$PATH"

exec ollama launch claude --model "$model" -- "${args[@]}"
