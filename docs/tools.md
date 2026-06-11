# Tool Reference

## Tier definitions

**Tier 1 — auto-execute.** The tool runs immediately without a prompt. A labeled info panel is shown in the terminal for transparency.

**Tier 2 — approval required.** Execution halts. A bordered questionary prompt appears with the operation details:
- `write_file`: Allow / Show diff / Deny — give feedback / Skip step
- `run_command`, `fetch_page`, `read_file`: Allow / Deny — give feedback / Skip step

On "Deny — give feedback", the user types a correction note and the worker is re-called (see [Correction loop](#correction-loop)).

## Tier assignment table

| Tool | Block 2 | Block 3 |
|---|---|---|
| `read_file` | Tier 1 | Tier 2 |
| `list_files` | Tier 1 | — (not available) |
| `search_in_files` | Tier 1 | — (not available) |
| `web_search` | Tier 1 | Tier 1 |
| `fetch_page` | Tier 1 | Tier 2 |
| `write_file` | — (not available) | Tier 2 |
| `run_command` | — (not available) | Tier 2 |

`list_files` and `search_in_files` are not available in Block 3. File discovery is the responsibility of Block 1 (host-level call) and Block 2 (Tier 1 tools). An unexpected `read_file` call from Block 3 signals the planning phase missed a file — it surfaces as a Tier 2 pause, not auto-execute.

Note: `list_files` is also called directly by the host before Block 1's Call 2 to generate the project file list. This is a host-level call outside the model tool system. The tier table above governs model-initiated calls only.

## Correction loop

When a Block 3 Tier 2 call is denied with feedback:

1. User selects "Deny — give feedback" and enters a correction note.
2. The host assembles a re-call with:
   - Original step instruction including file contents **frozen from the first Block 3 call** — files are not re-read from disk during correction rounds.
   - `## Already executed in this step` section listing all approved operations so far in this step, so Block 3 does not re-propose them.
   - `## Previous output` containing the prior Block 3 response — natural language and generated code only; tool call JSON and tool results are excluded.
   - `## Correction note` with the user's feedback text.
3. Block 3 is called again. The Tier 2 prompt reappears for the next tool call.
4. Running cost delta for each correction round is displayed inline: `⠹ Regenerating... · round N · ~X tokens · $X.XXX`.
5. Loop continues until "Allow" or "Skip step". There is no cap on correction rounds — the user is aware of the token cost.

"Skip step" exits the loop immediately. The step is recorded as `partial` in the step result object. Execution proceeds to the next step with denied items noted in context via `## Previously denied operations`.

## Tool reference

### `read_file`

```
read_file(path: str) -> str
```

Reads a file at the given path relative to the project root. Returns the file contents as a string.

**Large file truncation.** If the file exceeds `large_file_head_lines + large_file_tail_lines` lines, only the first `large_file_head_lines` lines and last `large_file_tail_lines` lines are returned, with an explicit truncation notice inserted between them. Both limits are configurable in `.agent.json` under `tools`.

Returns an error string if the file does not exist or cannot be decoded as UTF-8 (binary files).

---

### `write_file`

```
write_file(path: str, content: str) -> None
```

Writes content to a file at the given path relative to the project root. Creates parent directories automatically. Overwrites the file if it already exists.

"Show diff" in the Tier 2 prompt shows a unified diff of the existing file against the proposed content using red/green syntax highlighting before the user commits to Allow.

---

### `list_files`

```
list_files() -> list[str]
```

Returns a sorted list of forward-slash relative paths for all non-ignored files in the project. Uses the `pathspec` library with gitignore-style matching against `.agentignore` patterns. Ignored directories are pruned during traversal so descent into them is skipped entirely.

---

### `search_in_files`

```
search_in_files(query: str) -> list[dict]
```

Case-insensitive substring search across all non-ignored project files. Skips binary files and files that cannot be decoded as UTF-8. Returns a list of `{"file": str, "line": int, "content": str}` dicts. Capped at **50 matches** total.

---

### `run_command`

```
run_command(cmd: str) -> dict
```

Executes a shell command in the project root directory. Returns `{"stdout": str, "stderr": str, "exit_code": int}`. stdout and stderr are streamed to the terminal in real time during execution.

**Environment detection (checked in this order):**

1. If any file in `docs/context/` contains the string `uv`, the command is prefixed with `uv run`.
2. Otherwise, if `uv.lock` exists at the project root, the command is prefixed with `uv run`.
3. Otherwise, the command runs in the shell environment as-is — the user is responsible for having the project environment activated.

On Windows, the command is invoked via `shell=True`. On other platforms it is split with `shlex.split` and run directly. All commands execute in the project root directory regardless of where nephew was installed.

---

### `web_search`

```
web_search(query: str) -> list[dict]
```

Searches the web and returns `{"title": str, "url": str, "snippet": str}` dicts. Provider is configured via `web_search.provider` in `.agent.json`. Results are capped at `web_search_max_results`.

Supported providers:
- `"brave"` — uses `BRAVE_SEARCH_API_KEY` from `.env`
- `"tavily"` — uses `TAVILY_API_KEY` from `.env`

Switching providers requires one config change and one `.env` update — no code changes.

---

### `fetch_page`

```
fetch_page(url: str) -> str
```

Fetches a web page and returns its content as plain text. HTML responses are stripped to plain text; other content types are returned as-is. Content is truncated to `fetch_page_max_chars` characters with an explicit truncation notice appended. Timeout: 30 seconds. Uses `httpx` with redirect following enabled.

---

## `.agentignore`

Controls which files `list_files` and `search_in_files` see. Uses gitignore syntax. Located at the project root. Generated by `/init`.

Default patterns (also used as hardcoded fallback when no `.agentignore` is present):

```
# .agentignore
.git
.venv
venv
__pycache__
node_modules
dist
build
.next
*.pyc
*.lock
*.min.js
```

If no `.agentignore` exists, the agent uses this fallback list automatically. nephew works correctly in projects that have not been `/init`'d.
