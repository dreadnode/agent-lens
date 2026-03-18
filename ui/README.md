# AgentLens

Local web UI for browsing AgentLens runs. View trajectories as chat conversations, inspect memory diffs, API captures, and state changelogs.

## Setup

Requires Node.js 22+.

```sh
cd ui
npm install
```

Create a `.env` file (or edit the existing one) to point at your runs directory:

```
RUNS_DIR=../runs
```

## Development

```sh
npm run dev
```

Opens at http://localhost:5174.

## Routes

| Route | Description |
|---|---|
| `/` | Runs list with search/filter |
| `/runs/[name]` | Run overview — metrics, session list |
| `/runs/[name]/sessions/[idx]` | Session trajectory as chat view |
| `/runs/[name]/sessions/[idx]/memory` | Session memory diff (before/after) |
| `/runs/[name]/sessions/[idx]/api` | API captures with token usage |
| `/runs/[name]/memory` | Run-level memory (init vs final) |
| `/runs/[name]/changelog` | State changelog timeline |
| `/runs/[name]/config` | Frozen config.yaml |

## Production build

```sh
npm run build
npm run preview
```
