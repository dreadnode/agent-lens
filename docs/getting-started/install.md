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

Set the API key for your chosen provider:

| Provider | Environment variable |
|----------|---------------------|
| OpenRouter (default) | `OPENROUTER_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| AWS Bedrock | Standard AWS credentials |
| GCP Vertex AI | Standard GCP credentials |

```bash
# OpenRouter (default)
export OPENROUTER_API_KEY=sk-or-...

# Or Anthropic direct
export ANTHROPIC_API_KEY=sk-ant-...
```

## Web UI (optional)

The web UI requires Node.js:

```bash
cd ui
npm install
npm run dev
# Open http://localhost:5173
```
