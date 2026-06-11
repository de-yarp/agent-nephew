# Tracing

nephew records every model call to a Postgres `traces` table. At `/end`, the trace records are used to build a structured session summary, which Flash uses to write the diary entry.

## Start Postgres

```bash
docker compose up -d
```

Run from the agent repo directory. A single Postgres 16 container with a named volume (`postgres_data`) for persistence.

The default credentials match the example `POSTGRES_URL` in `.env`:

```
POSTGRES_URL=postgresql://agent:agent@localhost:5432/agent
```

## `traces` table schema

```sql
CREATE TABLE IF NOT EXISTS traces (
    id            SERIAL PRIMARY KEY,
    session_id    TEXT NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    block         TEXT,
    role          TEXT,
    model         TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    latency_ms    INTEGER,
    cost          REAL,
    input_payload  JSONB,
    output_payload JSONB,
    error         TEXT
);
```

An index on `session_id` is created automatically.

| Column | Type | Description |
|---|---|---|
| `id` | serial | Auto-incrementing primary key. |
| `session_id` | text | UUID v4 shared by all calls in one session. |
| `timestamp` | timestamptz | Wall-clock time when the record was written. Auto-set to `NOW()`. |
| `block` | text | Calling context: `block1`, `block2`, `block3`, or `lifecycle` (diary and commit message calls in `/end`). |
| `role` | text | Model role: `router`, `orchestrator`, or `worker`. |
| `model` | text | Actual model string used, reflecting any session override set via `/model` or `--worker`. |
| `input_tokens` | integer | Input tokens from the API response. |
| `output_tokens` | integer | Output tokens from the API response. |
| `latency_ms` | integer | Wall-clock time for the API call in milliseconds. |
| `cost` | real | Calculated from `cost_per_1k_input` and `cost_per_1k_output` config rates. Never from an API-returned cost field. |
| `input_payload` | jsonb | `{"role": str, "message_count": int, "user_request": str or null, "messages_summary": [{"role": str, "content_len": int}]}`. `user_request` is only populated for Block 1 router Call 1 rows. Content lengths only — not full prompt text. |
| `output_payload` | jsonb | Full `call_llm()` result dict. For worker calls this includes the assembled `step_result_object`. |
| `error` | text | Non-null if the call raised an exception or the session was interrupted. |

## What is and isn't stored

**Stored in `input_payload`:** message count, message roles, content lengths, and the user's request text (Block 1 Call 1 only). Not the full prompt text or injected file contents.

**Stored in `output_payload`:** the complete `call_llm()` return value — model content, token counts, finish reason, tool calls. For worker calls, the assembled step result (files written, commands run, denied items, errors) is included.

This keeps input payload sizes small and manageable regardless of how large the context becomes during a session.

## Structured session summary

`get_session_trace_summary(session_id, conn)` extracts a human-readable summary from the trace records:

- **User requests** — extracted from Block 1 router rows where `user_request` is set.
- **Plan steps** — extracted from orchestrator rows whose output content parses as `{"steps": [...]}`.
- **Step results** — extracted from worker rows whose `output_payload` contains a `status` key.
- **Token metrics** — aggregated token counts and cost by role.
- **Session duration** — derived from the timestamp range of the trace rows.

Full file contents and generated code payloads are excluded from the summary — they are noise for diary purposes. Typical summary size: 2–5k tokens regardless of session length.

## Disable tracing

**CLI flag:**
```bash
nephew --no-trace
```

**Config file** (`.agent.json`):
```json
"tracing": { "enabled": false }
```

When disabled: no Postgres connection is attempted, `/end` skips diary generation, all other functionality is unaffected. `/history` always works from the in-memory token accumulator regardless of tracing state.

## Graceful degradation

On startup, nephew attempts to connect to Postgres 3 times with exponential backoff (1s → 2s → 4s intervals). If all attempts fail:

```
⚠ Postgres unavailable — tracing disabled for this session.
  /end will not generate a diary entry.
  Start Postgres with: docker compose up -d
```

The agent continues normally. `POSTGRES_URL` missing from `.env` triggers the same warning immediately without attempting any connections.
