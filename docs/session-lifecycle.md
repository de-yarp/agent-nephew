# Session Lifecycle

## Session start sequence

Before the first prompt, nephew performs these steps in order:

1. **Project root discovered** — walks parent directories from the invocation directory until `.git/` is found. Falls back to `cwd()` with a printed warning if not found.
2. **`.env` and `.agent.json` loaded** — from the project root.
3. **Session created** — `Session` object with a UUID v4 session ID generated at startup. All subsequent model calls are tagged with this ID.
4. **Postgres connection attempted** — 3 attempts at 1s → 2s → 4s intervals. On all failures, a warning is printed and tracing is disabled for the session. Skipped entirely if `--no-trace` flag is set or `tracing.enabled` is `false`.
5. **Git branch detected** — `agent/<branch>` created if it does not exist, or resumed if it does. nephew checks out to the agent branch before any model calls.
6. **`docs/context/*.md` files injected** — all markdown files in `docs/context/` are read and injected into the system prompt. A non-blocking warning is shown if the directory is empty or absent.
7. **Last N diary entries parsed** — three sections extracted from each entry within the `diary.sliding_window` and injected into the system prompt: `## Next session`, `## Open questions`, `## Decisions`.
8. **Startup header printed** — ASCII art of the project name (pyfiglet slant font), active model names, project directory, and branch info.
9. **REPL starts** — user prompt ready.

## Detached HEAD

If the repository is in a detached HEAD state, nephew refuses to start:

```
✗ Repository is in a detached HEAD state.
  Checkout a named branch before running the agent:
  git checkout <branch-name>
```

## No git fallback

If the project has no git repository, nephew warns at startup and continues without version control features. File writes accumulate in the working tree but cannot be committed to an agent branch. The user is strongly encouraged to run `git init` before meaningful work.

## Session commands

### `/init`

Creates the project documentation structure in the current directory:

```
docs/
  context/
    CAPITAL.md    ← template with 6 sections including ## Documentation manifest
  lowercase/      ← empty, for detailed on-demand docs
  diary/          ← empty, auto-populated by /end
.agentignore      ← default exclusion patterns
```

Each artifact is handled independently. If a file already exists: it is skipped with a per-artifact warning. `--force` overwrites all existing artifacts.

The generated `CAPITAL.md` template:

```markdown
# [Project Name]

## Purpose
What this project does and why it exists.

## Architecture
High-level structure and key design decisions.

## Tech stack
Languages, frameworks, key libraries, versions.

## Conventions
Naming conventions, code style, patterns to follow.

## Constraints
Hard limits, non-negotiable requirements, things to avoid.

## Documentation
List of available lowercase docs for this project:
- docs/lowercase/example.md — description
```

The `## Documentation` section is the manifest Block 2 uses to discover available lowercase docs.

### `/end`

Full session close flow:

1. Queries Postgres for all trace records belonging to the current session.
2. If tracing is unavailable (`conn` is None), prints a warning and skips diary generation.
3. Extracts a structured session summary from the trace records.
4. Sends the summary to Flash (router role) with a system prompt that enforces exact section headers.
5. Validates that all required section headers are present. Re-prompts Flash once if validation fails. If the second attempt also fails, the entry is saved with a `[malformed]` prefix and a warning is shown — the agent never crashes on a bad diary entry.
6. Determines entry number N by scanning `docs/diary/` for existing `YYYY-MM-DD-*.md` files and incrementing the highest N found. Handles gaps from manual deletions correctly.
7. Creates `docs/diary/` if it does not exist.
8. Writes the diary entry to `docs/diary/YYYY-MM-DD-N.md`.
9. If the session had file writes: Flash generates a conventional commit message and the agent branch is committed. If no writes occurred, the commit is skipped.

### `/history`

Displays token usage and estimated cost for the current session, broken down by role. Reads from the in-memory token accumulator — always available regardless of tracing state.

```
Session: 3f2a1c...
─────────────────────────────────
Router:       12 calls  ·  4,200 in  ·  380 out
Orchestrator:  8 calls  ·  18,400 in  ·  2,100 out
Worker:        4 calls  ·  22,000 in  ·  8,400 out
─────────────────────────────────
Total:  44,600 in  ·  10,880 out  ·  $0.0000
```

### `/model <role> <model>`

Overrides the model for a specific role for the current session only. Stored in `session.model_overrides` and applied to all subsequent calls for that role.

Valid roles: `router`, `orchestrator`, `worker`.

```
/model worker qwen/some-other-model
✓ worker model set to: qwen/some-other-model (this session only)
```

## Diary entry format

Every diary entry has exactly these 12 elements in this order — 1 title and 11 sections:

```markdown
# YYYY-MM-DD — Session N

## State going in
What was working, what was broken, starting point for this session.

## Task
The specific task addressed in this session.

## Decisions
- Decision made — rationale.

## Alternatives rejected
- Option considered — why it was rejected.

## Files changed
- modified: path/to/file.py
- created: path/to/new_file.py

## What worked
Concrete wins from this session.

## What didn't / Mistakes
What failed, wrong assumptions, time lost.

## Open questions
Unresolved issues, uncertainties, risks identified.

## Next session
Where to pick up next time.

## Metrics
Token counts, cost, number of model calls, session duration.

## Notes
Free-form thoughts, context, observations.
```

At the next session start, three of these sections are extracted from each diary entry in the sliding window and injected into the system prompt: `## Decisions`, `## Open questions`, and `## Next session`. All other sections are for human retrospective use only and are never injected.

Section header validation is machine-strict — Flash is required to produce every header exactly as shown. On malformed output, one retry is attempted. If the retry also fails, the entry is saved with a `[malformed]` marker — the session is never aborted over a bad diary entry.

## Git branch workflow

```
main
  └─ your-feature-branch             ← user merges here when ready
       └─ agent/your-feature-branch  ← nephew works here
```

At startup, nephew creates `agent/<current-branch>` if it does not exist, or resumes it if it does, and checks out to that branch. All file writes land on the agent branch. **No intermediate commits.** A single batch commit is made at `/end`. The user reviews the diff, squashes if desired, and merges into their branch manually.

Branch commits accumulate across sessions on the same line of work — running nephew again on the same branch resumes the existing agent branch where the last session left off.

## Interrupted session

Both a `SIGTERM` handler and an `atexit` handler are registered at startup. On unexpected exit (terminal close, SIGTERM, or `Ctrl+C` at the main input prompt):

1. If there are uncommitted writes, the agent branch is committed with `[interrupted] session ended unexpectedly`.
2. A best-effort error log entry is written to Postgres if the connection is still alive.
3. Diary generation is skipped.

This handler is distinct from `Ctrl+C` during active generation (which stops the stream, saves partial output as a complete assistant message, and returns to the input prompt without closing the session).

## Diary unavailable

When Postgres is unreachable or `--no-trace` is active, `/end` skips diary generation and notifies the user. If the session had file writes, the agent branch is still committed — a Flash call generates the commit message from whatever summary is available.
