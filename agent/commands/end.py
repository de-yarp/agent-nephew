import json
import re
from datetime import date
from pathlib import Path

from agent.tracing import get_session_trace_summary
from agent.llm import call_llm

REQUIRED_HEADERS = [
    "## State going in",
    "## Task",
    "## Decisions",
    "## Alternatives rejected",
    "## Files changed",
    "## What worked",
    "## What didn't / Mistakes",
    "## Open questions",
    "## Next session",
    "## Metrics",
    "## Notes",
]


def _validate_diary_headers(entry: str) -> bool:
    return all(header in entry for header in REQUIRED_HEADERS)


def handle_end(session, config: dict, project_root: Path, conn, repo) -> None:
    from agent.handlers.sigterm import mark_session_complete

    # Step 1 — attempt trace summary
    summary = {}
    if conn is not None:
        summary = get_session_trace_summary(session.session_id, conn)

    # Step 2 — diary generation
    if conn is None:
        print("⚠ Tracing unavailable — diary generation skipped.")
        print("  Start Postgres with: docker compose up -d")
    elif not summary:
        print("ℹ No session trace data available — diary generation skipped.")
    else:
        today = date.today().strftime("%Y-%m-%d")
        diary_dir = project_root / "docs" / "diary"
        diary_dir.mkdir(parents=True, exist_ok=True)

        existing = list(diary_dir.glob(f"{today}-*.md"))
        max_n = 0
        for f in existing:
            m = re.match(rf"{re.escape(today)}-(\d+)\.md", f.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
        n = max_n + 1

        system_msg = (
            f"You are generating a session diary entry for a coding assistant session log.\n\n"
            f"Generate a diary entry with EXACTLY these section headers in this exact order. "
            f"Do not skip any section, do not rename any header, do not add extra headers.\n\n"
            f"# {today} — Session {n}\n"
            "## State going in\n"
            "## Task\n"
            "## Decisions\n"
            "## Alternatives rejected\n"
            "## Files changed\n"
            "## What worked\n"
            "## What didn't / Mistakes\n"
            "## Open questions\n"
            "## Next session\n"
            "## Metrics\n"
            "## Notes\n\n"
            "Rules:\n"
            "- Every section must be present with the exact header text shown above\n"
            "- Base content on the session summary provided\n"
            "- Be concise and factual\n"
            "- ## Metrics: include token counts, cost, number of model calls from the summary\n"
            "- ## Files changed: list files written during the session\n"
            "- Do not include markdown code fences around the entry"
        )
        user_msg = f"Session summary:\n{json.dumps(summary, indent=2)}"
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        result = call_llm(role="router", messages=messages, config=config, max_tokens=2000)
        session.accumulate_tokens("router", result["input_tokens"], result["output_tokens"])
        diary_entry = result["content"]

        # Step 3 — section header validation
        if not _validate_diary_headers(diary_entry):
            retry_messages = messages + [
                {"role": "assistant", "content": diary_entry},
                {
                    "role": "user",
                    "content": (
                        "Your response was missing required section headers. "
                        "Reply with the complete diary entry including ALL required section headers exactly as specified."
                    ),
                },
            ]
            retry_result = call_llm(role="router", messages=retry_messages, config=config, max_tokens=2000)
            session.accumulate_tokens("router", retry_result["input_tokens"], retry_result["output_tokens"])
            diary_entry = retry_result["content"]

            if not _validate_diary_headers(diary_entry):
                diary_entry = "[malformed — missing required sections]\n\n" + diary_entry
                print("⚠ Diary entry saved with [malformed] marker — section headers missing after 2 attempts.")

        # Step 5 — write diary entry
        entry_path = diary_dir / f"{today}-{n}.md"
        entry_path.write_text(diary_entry, encoding="utf-8")
        print(f"✓ Diary entry written: docs/diary/{today}-{n}.md")

    # Step 6 — git commit if writes occurred
    if repo is not None and repo.is_dirty(untracked_files=True):
        commit_msg_result = call_llm(
            role="router",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate a conventional commit message for the following session's changes. "
                        "Format: <type>(<scope>): <description>. "
                        "Types: feat, fix, refactor, docs, test, chore. "
                        "Maximum 72 characters total. No mention of AI authorship. "
                        "Reply with the commit message only — no explanation, no punctuation at end."
                    ),
                },
                {"role": "user", "content": f"Session summary:\n{json.dumps(summary, indent=2)}"},
            ],
            config=config,
            max_tokens=100,
        )
        session.accumulate_tokens("router", commit_msg_result["input_tokens"], commit_msg_result["output_tokens"])
        commit_message = commit_msg_result["content"].strip()

        repo.git.add(A=True)
        repo.index.commit(commit_message)
        print(f"✓ Agent branch committed: {commit_message}")

    elif repo is not None:
        print("ℹ No file writes this session — commit skipped.")
    else:
        print("ℹ No git repository — commit skipped.")

    mark_session_complete()
