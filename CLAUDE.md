# Agent — CLI Coding Assistant

## Source of truth
All architectural decisions are in these two files. Read them before writing any code:
- `docs/PROJECT_BRIEF_v2_4.md` — full specification (Sections 0–12)
- `docs/BLUEPRINT_Stage1.md` — 9-prompt implementation plan with contracts and deliverables

If anything in this file conflicts with the brief, **the brief wins**.

---

## Implementation status

Update this section after each completed prompt.

| Prompt | Part | Description | Status |
|--------|------|-------------|--------|
| [1] | 1.1 | Package scaffolding, config, .env, root discovery | ✅ complete |
| [2] | 1.2 | call_llm(), Session, cost tracking, Postgres connect | ✅ complete |
| [3] | 2   | Tool system: 7 functions, schemas, dispatcher, .agentignore | ✅ complete |
| [4] | 3   | Block 1 Router: two Flash calls, SIMPLE/COMPLEX dispatch | ✅ complete |
| [5] | 4   | Block 2 Orchestrator: planning + execution loop | ✅ complete |
| [6] | 5   | Block 3 Worker: Qwen3 handler, correction loop | ⬜ not started |
| [7] | 6   | Session lifecycle: /init, /end, /model, git branch, diary | ⬜ not started |
| [8] | 7   | Observability: traces table, logging wrapper, docker-compose.yml | ⬜ not started |
| [9] | 8   | Rich CLI & UX + full main loop assembly | ⬜ not started |

**Current prompt:** [6]
**Last completed:** [5]
**Last updated by:** Claude

---

## Hard rules — never violate these

- **No hardcoded model names anywhere.** All model names, temperatures, and token limits come from `.agent.json`. Zero exceptions.
- **`pathlib.Path` throughout.** No `os.path`, no string path concatenation.
- **All file operations relative to project root.** Project root = nearest `.git/` ancestor directory, discovered by walking up from `cwd()`.
- **Mac ↔ Windows compatible at all times.** Every file you write must work on both. Flag anything platform-specific.
- **Host orchestrates, models execute scoped tasks.** Models are never given open-ended autonomy. The host Python process is always in control.
- **Do not modify files outside the current prompt's scope.** Each prompt has a defined file list — touch nothing else.

---

## Architecture overview

```
User Input
    │
    ▼
BLOCK 1 — Router (DeepSeek V4 Flash, 2 sequential calls)
  Call 1: SIMPLE or COMPLEX  (max_tokens: 10)
  Call 2: file selection + instruction  (max_tokens: 512)
    │
    ├── SIMPLE ──────────────────────────────────────┐
    │                                                 │
    └── COMPLEX → BLOCK 2 — Orchestrator             │
                  (DeepSeek V4 Pro)                  │
                  Phase 1: planning + approval        │
                  Phase 2: per-step JSON instructions │
                    │                                 │
                    └──────── BLOCK 3 ←──────────────┘
                              Worker (Qwen3 Coder)
                              Tier 2 tools + correction loop
```

Block 2 is an isolated experimental zone — its internals can change without touching Block 1 or Block 3.

---

## Package structure

```
agent/
  __init__.py
  main.py           ← entry point, main() + REPL (completed in [9])
  config.py         ← load_config(project_root) → dict
  env.py            ← load_env(project_root) → None
  root.py           ← find_project_root(start) → Path
  llm.py            ← call_llm(role, messages, **kwargs) → dict
  session.py        ← Session dataclass
  db.py             ← connect_postgres(config) → conn | None
  tracing.py        ← traced_call_llm(), create_traces_table(), get_session_trace_summary()
  blocks/
    block1.py       ← route_and_dispatch(...)
    block2.py       ← orchestrate(...)
    block3.py       ← execute_step(...)
  tools/
    functions.py    ← 7 tool functions
    schemas.py      ← OpenAI-compatible schemas
    agentignore.py  ← parse_agentignore(project_root) → list[str]
    dispatcher.py   ← execute_tool(tool_name, args, block, approval_callback)
  ui/
    header.py       ← print_startup_header(...)
    output.py       ← stream_block3(), spinner(), show_tier1_panel(), ...
    prompts.py      ← prompt_write_file(), prompt_run_command(), show_diff(), ...
pyproject.toml      ← [project.scripts] nephew = "agent.main:main"
.agent.json         ← all config (project root)
.env                ← API keys (project root, gitignored)
.agentignore        ← file exclusion rules (project root)
docker-compose.yml  ← single Postgres service (created in [8])
docs/
  PROJECT_BRIEF_v2_4.md
  BLUEPRINT_Stage1.md
  context/          ← always injected at session start
  lowercase/        ← on-demand detailed docs
  diary/            ← auto-generated session records
```

---

## Key data contracts

These interfaces are defined once and must never be redefined. Refer to `docs/BLUEPRINT_Stage1.md` Section 2 for full details.

**`call_llm(role: str, messages: list, **kwargs) -> dict`**
Always returns: `{"content": str, "input_tokens": int, "output_tokens": int, "finish_reason": str}`
Produced by [2]. Consumed by [4], [5], [6], [7], [8].

**`Session` dataclass**
Fields: `session_id: str` (UUID v4, generated once at startup), `model_overrides: dict`
Methods: `accumulate_tokens(role, input_tokens, output_tokens)`, `total_cost() -> float`, `get_summary() -> dict`
Produced by [2]. Consumed by all subsequent prompts.

**`step_result_object`**
Assembled by host after each Block 3 step via `assemble_step_result()`.
Produced by [6]. Consumed by [5] (per-step Pro call), [7] (diary), [8] (stored in traces JSONB).

**`block2_step_instruction`** — 4-field JSON from Pro per step:
`{"task_description": str, "files": list, "constraints": str, "expected_output": str}`
Produced by [5]. Consumed by [6].

**`block1_complex_routing_output`** — bare JSON array of file paths.
Produced by [4]. Consumed by [5].

**`get_session_trace_summary(session_id: str, conn) -> dict`**
Produced by [8]. Consumed by [7] (`/end` handler — stub until [8] provides full implementation).

---

## `.agent.json` schema

Exact schema from Brief Section 3. Do not add or rename fields.

```json
{
  "models": {
    "router": {
      "provider": "deepseek",
      "model": "deepseek-v4-flash",
      "temperature": 0,
      "max_tokens_routing": 10,
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
  "tracing": {
    "enabled": true
  },
  "diary": {
    "sliding_window": 5
  },
  "web_search": {
    "provider": "brave"
  },
  "tools": {
    "fetch_page_max_chars": 6000,
    "web_search_max_results": 5,
    "large_file_head_lines": 150,
    "large_file_tail_lines": 50
  },
  "warnings": {
    "large_plan_steps": 7
  }
}
```

Notes: there are only 3 model roles (`router`, `orchestrator`, `worker`). Diary generation uses the `router` role (Flash) — no separate `diary` role exists. `postgres_url` is in `.env`, not in `.agent.json`. Cost rates default to `0.0` — fill in from provider pricing page. No rates hardcoded in source.

---

## Tool tier assignments

| Tool | Block 2 | Block 3 |
|------|---------|---------|
| `read_file` | Tier 1 | Tier 2 |
| `list_files` | Tier 1 | — |
| `search_in_files` | Tier 1 | — |
| `web_search` | Tier 1 | Tier 1 |
| `fetch_page` | Tier 1 | Tier 2 |
| `write_file` | — | Tier 2 |
| `run_command` | — | Tier 2 |

Tier 1 = auto-execute, shown in info panel. Tier 2 = requires user approval before execution.

**Block 3 has no access to `list_files` or `search_in_files`.** File discovery is the sole responsibility of Block 1 (host call) and Block 2. An unexpected `read_file` from Block 3 signals the planning phase missed something — it fires as Tier 2 pause, not auto-execute.

Note: `list_files()` is also called directly by the host before Block 1's Call 2 — this is a host-level call outside the model tool system entirely. The tier table above governs model-initiated calls only.

---

## Git workflow — two developers

> **Note:** The brief specifies fully independent instances per developer with no shared state. The workflow below describes the team's working agreement for the build phase — not an architectural requirement.

```
main
  └─ feature/...              ← developer's working branch
       └─ agent/feature/...   ← agent writes here during sessions
```

Shared repository workflow during build:

1. `git pull` before starting any session
2. Work on your feature branch
3. Agent creates `agent/<your-branch>` automatically at startup
4. After each completed prompt: `git add . && git commit -m "feat: part X — description" && git push`
5. Update `CLAUDE.md` implementation status and commit it with the prompt

If you pull and see changes from the other developer, read the updated `CLAUDE.md` before continuing — it is the source of truth about current implementation state.

---

## Environment

- **OS:** Windows with WSL2 + Docker Desktop
- **Python manager:** `uv` — install agent with `uv tool install .` (run from agent repo root). To add dependencies to the agent, use `uv add` **only inside the agent repository** — never inside a user project directory.
- **Invoke command:** `nephew` (from any project directory after install)
- **Postgres:** Docker container via `docker compose up -d` (docker-compose.yml created in [8])
- **API keys in `.env`:** `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`

---

## Verification — Prompt [2]
- [x] Check 1: install — `uv tool install . --force` succeeded
- [x] Check 2: imports — `call_llm`, `Session`, `create_session`, `connect_postgres` all import cleanly
- [x] Check 3: session creation — UUID v4 generated, `model_overrides == {}`
- [x] Check 4: token accumulation and cost — totals and `calls_by_role` correct
- [!] Check 5: call_llm() router call — skipped; no `.env` present at verification time (API keys required)
- [x] Check 6: Postgres unavailable graceful degradation — returns `None`, prints correct warning

---

## Color palette (UX)

| Role | Hex |
|------|-----|
| Primary accent | `#5B8DEF` |
| Success | `#4EC994` |
| Metadata | `#6B7280` |
| Permission prompt | `#D4934A` |
| Error | `#D45C5C` |

Spinner style: `arc`. Syntax theme: `one-dark`.

---

## Verification pattern

After each prompt, verify by running the specific checks listed in that prompt's deliverable section in `docs/BLUEPRINT_Stage1.md`. At minimum for every prompt:

```bash
uv tool install .        # must succeed without errors
python -c "import agent" # package must import cleanly
```

---

## Verification — Prompt [3]
- [x] Check 1: install — `uv tool install . --force` succeeded
- [x] Check 2: imports — all 4 modules import cleanly
- [x] Check 3: agentignore fallback — 11 patterns returned including .git, __pycache__, node_modules
- [x] Check 4: list_files respects agentignore — .git/ directory entries absent (27 files found); note: prompt check uses `f.startswith('.git')` which also matches `.gitignore` — this is a check bug, not a code bug. `.gitignore` is correctly included.
- [x] Check 5: read_file truncation — head/tail with notice inserted correctly
- [x] Check 6: write_file creates dirs — nested path created and content verified
- [x] Check 7: dispatcher tier enforcement — block3 restriction, tier2 no callback, tier1 auto-execute all correct
- [x] Check 8: schemas structure — 7 schemas, BLOCK2/BLOCK3 subsets correct

---

## Verification — Prompt [4]
- [x] Check 1: install — `uv tool install . --force` succeeded
- [x] Check 2: imports — `route_and_dispatch` imports cleanly
- [x] Check 3: max_tokens_routing config fix — value is 100
- [x] Check 4: call1 routing — SIMPLE decision — returned SIMPLE for "fix the typo in the README"
- [x] Check 5: call1 routing — COMPLEX decision — returned COMPLEX for auth system request
- [x] Check 6: call2 SIMPLE path end-to-end — all 5 sections present in assembled_prompt
- [x] Check 7: call2 COMPLEX path end-to-end — file_list (5 files), context_contents, diary_sections, user_request all present
- [x] Check 8: token accumulation active — 2 router calls recorded, input_tokens > 0

---

## Verification — Prompt [5]
- [x] Check 1: install — `uv tool install . --force` succeeded
- [x] Check 2: imports — `orchestrate`, `run_planning_phase`, `run_execution_phase`, `execute_step` all import cleanly
- [x] Check 3: llm.py tool_calls extension — `tool_calls=None`, `raw_assistant_message` field present for non-tool response
- [x] Check 4: block3 stub — returns `{'status': 'success', 'files_written': [], 'commands_run': []}`
- [x] Check 5: step result evaluation — all 4 branches correct (proceed, proceed_with_denials, halt_errors, halt_error)
- [x] Check 6: assembled block3 prompt — all 5 sections present (## Task, ## Files provided, ## File contents, ## Constraints, ## Expected output)
- [x] Check 7: planning phase live call — 1 step produced, 8 messages in planning_messages, questionary auto-approved
- [x] Check 8: token accumulation — orchestrator recorded 6 calls, input_tokens > 0 after planning phase
