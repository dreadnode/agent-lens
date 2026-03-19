# Installation

## Requirements

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) package manager
- Git (for shadow git change tracking)

## Install

```bash
git clone <this-repo>
cd agentlens
uv sync
```

## API keys

If you have a Claude Code subscription (Pro/Max), no API key is needed — the SDK uses your subscription credentials automatically with `provider: anthropic` (the default).

If `ANTHROPIC_API_KEY` is set in your environment, the SDK will use that instead of your subscription (per-token billing). To use your subscription when a key is present, unset it: `unset ANTHROPIC_API_KEY`.

Otherwise, set an API key for your chosen provider:

| Provider | Environment variable |
|----------|---------------------|
| Anthropic (default) | `ANTHROPIC_API_KEY` (or Claude Code subscription) |
| OpenRouter | `OPENROUTER_API_KEY` |
| AWS Bedrock | Standard AWS credentials |
| GCP Vertex AI | Standard GCP credentials |

```bash
# Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...

# Or OpenRouter (set provider: openrouter in config)
export OPENROUTER_API_KEY=sk-or-...
```

## Web UI (optional)

The web UI requires Node.js:

```bash
cd ui
npm install
npm run dev
# Open http://localhost:5173
```
