# nephew

A personal CLI coding assistant built on a three-block routing architecture.

## What it is

nephew is a token-efficient coding assistant that routes each request through the cheapest capable model. Simple tasks go directly to the worker; complex tasks flow through a planner that decomposes them into discrete steps. Every file write, command execution, and external fetch requires explicit user approval before execution. Full session diaries are generated automatically via Postgres tracing at the end of each session.

## Prerequisites

- Python 3.12+
- `uv` installed globally
- Docker Desktop (for Postgres tracing)
- A DeepSeek API key
- An OpenRouter API key
- Optional: Brave Search or Tavily API key for web search

## Installation

```bash
git clone <repo>
cd <repo>
uv tool install . --force --no-cache
```

`--force --no-cache` is required to ensure the latest build is used.

## Configuration

**Step 1** — create `.env` at your project root (not the agent repo):

```
DEEPSEEK_API_KEY=your_key
OPENROUTER_API_KEY=your_key
POSTGRES_URL=postgresql://agent:agent@localhost:5432/agent
```

**Step 2** — create `.agent.json` at your project root. See [docs/configuration.md](docs/configuration.md) for the full schema. Minimal working example with cost rates at `0.0`:

```json
{
  "models": {
    "router": {
      "provider": "deepseek",
      "model": "deepseek-v4-flash",
      "temperature": 0,
      "max_tokens_routing": 100,
      "max_tokens_files": 512,
      "cost_per_1k_input": 0.0,
      "cost_per_1k_output": 0.0
    },
    "orchestrator": {
      "provider": "deepseek",
      "model": "deepseek-v4-pro",
      "temperature": 0.6,
      "max_tokens": 8000,
      "cost_per_1k_input": 0.0,
      "cost_per_1k_output": 0.0
    },
    "worker": {
      "provider": "openrouter",
      "model": "qwen/qwen3-coder-next",
      "temperature": 0.2,
      "max_tokens": 16000,
      "max_tokens_ceiling": 32000,
      "cost_per_1k_input": 0.0,
      "cost_per_1k_output": 0.0
    }
  },
  "tracing": { "enabled": true },
  "diary": { "sliding_window": 5 },
  "web_search": { "provider": "brave" },
  "tools": {
    "fetch_page_max_chars": 6000,
    "web_search_max_results": 5,
    "large_file_head_lines": 150,
    "large_file_tail_lines": 50
  },
  "warnings": { "large_plan_steps": 7 }
}
```

## Start Postgres

```bash
docker compose up -d
```

Run from the agent repo directory. Tracing is optional — nephew works without Postgres, but diary generation will be skipped at `/end`.

## Usage

```bash
cd /your/project
nephew
```

Startup output:

```
   ___  ____
  / _ \/ __/
 /  __/\ \
 \___/___/  your-project

v0.1.0  ·  deepseek-v4-flash + deepseek-v4-pro  ·  qwen/qwen3-coder-next  ·  /your/project
branch: main  →  agent/main
────────────────────────────────────────────────────────────────

❯ fix the null check in src/utils.py

  ⠹ Routing...
  → SIMPLE

  ⠹ Selecting files + building instruction...

  [streaming response]

  ╔══ Allow file write? ════════════════╗
  ║  src/utils.py  (+3 lines)           ║
  ║  > Allow                            ║
  ║    Show diff                        ║
  ║    Deny — give feedback             ║
  ║    Skip step                        ║
  ╚═════════════════════════════════════╝

  ✓ Done  ·  ~820 tokens  ·  $0.000
```

## Session commands

- `/history` — token usage and cost breakdown for the current session
- `/model <role> <model>` — override the model for a role for this session only
- `/init` — create `docs/context/CAPITAL.md`, `docs/lowercase/`, `docs/diary/`, `.agentignore` in the current project
- `/end` — generate diary entry, commit the agent branch, close session

## Documentation

Full reference in [docs/](docs/):

- [docs/architecture.md](docs/architecture.md) — system overview and data contracts
- [docs/configuration.md](docs/configuration.md) — `.agent.json` and `.env` reference
- [docs/tools.md](docs/tools.md) — tool reference and tier assignments
- [docs/session-lifecycle.md](docs/session-lifecycle.md) — session flow, commands, diary format
- [docs/tracing.md](docs/tracing.md) — Postgres setup and traces schema
- [docs/development.md](docs/development.md) — build process and developer notes
