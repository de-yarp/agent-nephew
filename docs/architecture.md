# Architecture

## Overview

nephew is a personal CLI coding assistant installed globally via `uv tool install .` and invoked from any project directory. The host Python process is the sole orchestrating entity — models are called for specific scoped tasks and never given open-ended autonomy. All file operations, git commands, and shell commands execute relative to the project root (the nearest `.git/` ancestor of the invocation directory). A three-block architecture routes each request through the minimum number of model calls required.

## Three-block diagram

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────┐
│  BLOCK 1 — Router                               │
│  Two sequential DeepSeek V4 Flash calls         │
│  Call 1: binary decision SIMPLE / COMPLEX       │
│  Call 2: file selection (+ instruction on SIMPLE│
└────────────────┬────────────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
     SIMPLE            COMPLEX
        │                 │
        │         ┌───────▼──────────────────┐
        │         │  BLOCK 2                 │
        │         │  Orchestration System    │
        │         │  DeepSeek V4 Pro         │
        │         └───────┬──────────────────┘
        │                 │
        └────────┬────────┘
                 │
    ┌────────────▼──────────────────────┐
    │  BLOCK 3 — Worker                 │
    │  Qwen3 Coder Next                 │
    │  Executes structured tasks        │
    └───────────────────────────────────┘
```

## Block 1 — Router

Block 1 makes two independent, stateless Flash calls.

**Call 1 — routing decision.** Input: user request. Output: `SIMPLE` or `COMPLEX` (single word, bounded by `max_tokens_routing`). Unexpected output defaults to COMPLEX.

**Call 2 — file selection.** The host calls `list_files()` directly (host-level call, not a model tool call) to generate a fresh project file list, then passes it to Flash along with project context files. On COMPLEX: output is a bare JSON array of file paths. On SIMPLE: output is a JSON object with `files` and an `instruction` containing `task_description`, `constraints`, and `expected_output`.

Both calls strip Markdown fences before `json.loads()`. A single retry is attempted on parse failure; second failure halts with an error message.

On the SIMPLE path, Block 1 reads the listed files from disk and assembles the five-section Block 3 prompt directly. Block 2 is not invoked.

## Block 2 — Orchestrator

Block 2 has two phases.

**Planning phase.** A stateful DeepSeek Pro conversation: analysis call (with Tier 1 tool access to read additional context) → decomposition call (produces `{"steps": [...]}` JSON) → plan displayed to user via questionary. A soft warning appears if step count exceeds `warnings.large_plan_steps`. Plan modification loops until the user selects "Yes, proceed" or "Cancel" — each modification re-calls Pro with the full planning history. Before the analysis call, Block 2 scans all `docs/context/` files for `## Documentation` sections and loads any listed lowercase docs via `read_file`.

**Execution phase.** For each approved step, Pro is called with the full planning history plus the previous step's result object. Pro returns a 4-field JSON instruction (`task_description`, `files`, `constraints`, `expected_output`). The host reads the listed files from disk, assembles the Block 3 prompt, and calls Block 3. Step results feed a 4-branch evaluation: `success` → proceed; `partial` (denials only) → proceed with denied ops injected into next step context via `## Previously denied operations`; `partial` (with errors) → halt and ask user; `error` → halt.

## Block 3 — Worker

Qwen3 Coder Next streams its response token by token. Every Tier 2 tool call (write, command, fetch, read) halts execution and shows an approval prompt. On denial with feedback, a correction loop assembles a re-call with: frozen original file contents from the first call (files are not re-read from disk during correction rounds), `## Already executed in this step`, stripped prior output (text and generated code only — tool call JSON excluded), and the user's correction note. The loop continues until "Allow" or "Skip step". `KeyboardInterrupt` during streaming flushes partial output, saves it to context as a complete assistant message, and returns to the input prompt without closing the session or triggering the SIGTERM handler.

## Shared data contracts

| Contract | Produced by | Consumed by |
|---|---|---|
| `call_llm()` return value | `agent/llm.py` | All blocks, lifecycle commands, tracing wrapper |
| `Session` object | `agent/session.py` | All blocks, lifecycle commands, tracing |
| `step_result_object` | `agent/result.py` (`assemble_step_result`) | Block 2 execution phase, `agent/tracing.py`, diary generation |
| `block2_step_instruction` | Block 2 per-step Pro call | Block 3 prompt assembly in `agent/blocks/block2.py` |
| `block1_complex_routing_output` | Block 1 Call 2 (`agent/blocks/block1.py`) | Block 2 entry point in `orchestrate()` |
| `get_session_trace_summary()` | `agent/tracing.py` | `/end` handler diary generation (`agent/commands/end.py`) |

## Documentation system

Three tiers: `docs/context/*.md` files are always read at session start and injected into every model's system prompt. `docs/lowercase/` files are on-demand — Block 2 scans context files for `## Documentation` sections to discover available docs, then loads them via `read_file` before the analysis call. `docs/diary/` holds auto-generated session records; the last N entries (controlled by `diary.sliding_window`) are parsed at startup and three sections extracted from each — `## Next session`, `## Open questions`, `## Decisions` — are injected into the system prompt.

## Files as shared memory

No conversation history accumulates between Block 3 calls within a multi-step task. Block 2 sees only the step result object (files written, commands run, denied ops, errors) and can read current disk state via tools if needed. Block 3 always works from the real filesystem state, not from a prior model output. This prevents unbounded context growth and ensures the agent's view of the project stays accurate across steps.
