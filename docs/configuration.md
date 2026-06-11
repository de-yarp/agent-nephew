# Configuration Reference

nephew reads `.agent.json` and `.env` from the project root — the nearest `.git/` ancestor of the directory where `nephew` is invoked. If no `.git/` is found, it falls back to the current working directory with a warning. This matches the behavior of standard developer tools like `ruff` and `pyright`.

## `.agent.json` full schema

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

### `models`

There are exactly three model roles: `router`, `orchestrator`, and `worker`. Diary generation also uses the `router` role — there is no separate diary role.

#### `models.router`

| Field | Type | Description |
|---|---|---|
| `provider` | string | API provider. `"deepseek"` uses `DEEPSEEK_API_KEY`. |
| `model` | string | Model identifier passed to the API. |
| `temperature` | float | Sampling temperature. Use `0` for deterministic routing. |
| `max_tokens_routing` | int | Token limit for Call 1 (routing decision). **Must be at least `100`.** DeepSeek V4 Flash is a reasoning model that consumes thinking tokens before producing visible output — setting this too low causes truncation before the answer appears. |
| `max_tokens_files` | int | Token limit for Call 2 (file selection and instruction) and JSON retry calls. Default `512`. |
| `cost_per_1k_input` | float | Cost per 1,000 input tokens in USD. Fill from the provider pricing page. Default `0.0`. |
| `cost_per_1k_output` | float | Cost per 1,000 output tokens in USD. Fill from the provider pricing page. Default `0.0`. |

#### `models.orchestrator`

| Field | Type | Description |
|---|---|---|
| `provider` | string | API provider. `"deepseek"` uses `DEEPSEEK_API_KEY`. |
| `model` | string | Model identifier. |
| `temperature` | float | Sampling temperature. |
| `max_tokens` | int | Maximum output tokens per orchestrator call. Default `8000`. |
| `cost_per_1k_input` | float | Cost per 1,000 input tokens in USD. Default `0.0`. |
| `cost_per_1k_output` | float | Cost per 1,000 output tokens in USD. Default `0.0`. |

#### `models.worker`

| Field | Type | Description |
|---|---|---|
| `provider` | string | API provider. `"openrouter"` uses `OPENROUTER_API_KEY`. |
| `model` | string | Model identifier. |
| `temperature` | float | Sampling temperature. |
| `max_tokens` | int | Default output token limit per worker call. Default `16000`. |
| `max_tokens_ceiling` | int | Maximum allowed value for `max_tokens`. Configurable up to `32000`. |
| `cost_per_1k_input` | float | Cost per 1,000 input tokens in USD. Default `0.0`. |
| `cost_per_1k_output` | float | Cost per 1,000 output tokens in USD. Default `0.0`. |

Cost rates default to `0.0`. Fill them in from the provider's pricing page. Costs are always calculated from these config values — never from any API-returned cost field — ensuring consistent cross-provider cost accounting.

### `tracing`

| Field | Type | Description |
|---|---|---|
| `enabled` | bool | Whether to connect to Postgres and record traces. When `false`, no connection is attempted and `/end` skips diary generation. Default `true`. |

### `diary`

| Field | Type | Description |
|---|---|---|
| `sliding_window` | int | Number of most-recent diary entries to parse and inject at session start. Default `5`. |

### `web_search`

| Field | Type | Description |
|---|---|---|
| `provider` | string | Web search provider. `"brave"` uses `BRAVE_SEARCH_API_KEY`. `"tavily"` uses `TAVILY_API_KEY`. |

### `tools`

| Field | Type | Description |
|---|---|---|
| `fetch_page_max_chars` | int | Maximum characters returned by `fetch_page`. Content is truncated at this limit with an explicit notice. Default `6000`. |
| `web_search_max_results` | int | Maximum results returned by `web_search`. Default `5`. |
| `large_file_head_lines` | int | Lines shown from the start of a large file. Default `150`. |
| `large_file_tail_lines` | int | Lines shown from the end of a large file. Default `50`. |

Files exceeding `large_file_head_lines + large_file_tail_lines` lines are truncated with an explicit notice inserted between the head and tail sections.

### `warnings`

| Field | Type | Description |
|---|---|---|
| `large_plan_steps` | int | Step count threshold that triggers a soft warning at plan approval. No hard cap — the user decides whether to proceed. Default `7`. |

---

## `.env` reference

| Key | Required | Description |
|---|---|---|
| `DEEPSEEK_API_KEY` | Yes | Covers router (Flash) and orchestrator (Pro) calls via the DeepSeek API. |
| `OPENROUTER_API_KEY` | Yes | Covers worker (Qwen3 Coder) calls via OpenRouter. |
| `POSTGRES_URL` | No | Full connection string for tracing. Example: `postgresql://agent:agent@localhost:5432/agent`. If absent, tracing is silently disabled. |
| `BRAVE_SEARCH_API_KEY` | Conditional | Required when `web_search.provider` is `"brave"`. |
| `TAVILY_API_KEY` | Conditional | Required when `web_search.provider` is `"tavily"`. |

---

## Model override

Override the active model for any role for the current session only. The override is stored in-memory and does not modify `.agent.json`.

**CLI flag (worker only):**
```bash
nephew --worker qwen/some-other-model
```

**In-session command (any role):**
```
/model router deepseek-v4-flash
/model orchestrator deepseek-v4-pro
/model worker qwen/qwen3-coder-next
```

Valid roles: `router`, `orchestrator`, `worker`. The override applies until the session ends.

---

## Config and `.env` discovery

On startup, nephew walks parent directories from the invocation directory until it finds `.git/`, then looks for `.agent.json` and `.env` in that directory. If no `.git/` ancestor is found within the directory tree, it falls back to the current working directory with a printed warning. Invoke nephew from inside your project and it finds the right config automatically.
