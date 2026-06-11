from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agent.llm import call_llm
from agent.tools.functions import list_files, read_file

if TYPE_CHECKING:
    from agent.session import Session

_CALL1_SYSTEM = """\
You are a routing classifier for a coding assistant. Classify the user request as SIMPLE or COMPLEX.

SIMPLE: a task completable in a single focused step — fixing a bug in one file, adding a function, updating a config value, writing a single test, answering a question about the codebase.

COMPLEX: a task requiring multiple coordinated steps, multiple file changes planned together, architectural work, or anything that benefits from decomposition before execution — implementing a full feature, refactoring a module, setting up a new component.

Reply with exactly one word: SIMPLE or COMPLEX. No explanation, no punctuation.\
"""

_CALL2_SYSTEM_COMPLEX = """\
You are a file selector for a coding assistant. Given the user request and the full project file list, select the files most relevant to completing this task.

Reply with a bare JSON array of relative file paths only. No markdown fences, no explanation, no prose.
Example: ["src/auth/register.py", "src/auth/validators.py"]

If no files are clearly relevant, return an empty array: []\
"""

_CALL2_SYSTEM_SIMPLE = """\
You are a task planner for a coding assistant. Given the user request, the full project file list, and the project context, produce a structured task instruction.

Reply with a JSON object only — no markdown fences, no explanation, no prose:
{
  "files": ["relative/path/to/relevant/file.py"],
  "instruction": {
    "task_description": "Clear description of what needs to be done.",
    "constraints": "Technical constraints, patterns to follow, things to avoid. Empty string if none.",
    "expected_output": "What the completed result should look like."
  }
}\
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        else:
            text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _parse_json_with_retry(
    call2_messages: list,
    config: dict,
    session: "Session",
    raw: str,
) -> object:
    cleaned = _strip_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    retry_messages = call2_messages + [
        {"role": "assistant", "content": raw},
        {
            "role": "user",
            "content": (
                call2_messages[-1]["content"]
                + "\nYour previous response could not be parsed as JSON. "
                "Reply with valid JSON only — no markdown fences, no prose."
            ),
        },
    ]
    router_cfg = config["models"]["router"]
    retry_result = call_llm(
        "router",
        retry_messages,
        config,
        max_tokens=router_cfg["max_tokens_files"],
        temperature=router_cfg["temperature"],
    )
    session.accumulate_tokens("router", retry_result["input_tokens"], retry_result["output_tokens"])
    cleaned2 = _strip_fences(retry_result["content"])
    try:
        return json.loads(cleaned2)
    except json.JSONDecodeError:
        print("✗ Block 1 Call 2 failed to produce valid JSON after 2 attempts. Halting.")
        raise SystemExit(1)


def route_and_dispatch(
    user_request: str,
    session: "Session",
    config: dict,
    project_root: Path,
    context_contents: str = "",
    diary_sections: str = "",
) -> dict:
    router_cfg = config["models"]["router"]

    # Call 1 — routing decision
    call1_messages = [
        {"role": "system", "content": _CALL1_SYSTEM},
        {"role": "user", "content": user_request},
    ]
    result1 = call_llm(
        "router",
        call1_messages,
        config,
        max_tokens=router_cfg["max_tokens_routing"],
        temperature=router_cfg["temperature"],
    )
    session.accumulate_tokens("router", result1["input_tokens"], result1["output_tokens"])

    routing = result1["content"].strip().upper()
    if routing not in ("SIMPLE", "COMPLEX"):
        print(f"⚠ Block 1 Call 1 returned unexpected value {result1['content']!r} — defaulting to COMPLEX")
        routing = "COMPLEX"

    # Host list_files call before Call 2
    file_list = list_files(project_root, config)
    file_list_str = "\n".join(file_list)

    context_str = context_contents if context_contents else "(no context files found)"
    user_msg = (
        f"User request: {user_request}\n\n"
        f"Project files:\n{file_list_str}\n\n"
        f"Project context:\n{context_str}"
    )

    if routing == "COMPLEX":
        system2 = _CALL2_SYSTEM_COMPLEX
    else:
        system2 = _CALL2_SYSTEM_SIMPLE

    call2_messages = [
        {"role": "system", "content": system2},
        {"role": "user", "content": user_msg},
    ]

    result2 = call_llm(
        "router",
        call2_messages,
        config,
        max_tokens=router_cfg["max_tokens_files"],
        temperature=router_cfg["temperature"],
    )
    session.accumulate_tokens("router", result2["input_tokens"], result2["output_tokens"])

    parsed = _parse_json_with_retry(call2_messages, config, session, result2["content"])

    if routing == "COMPLEX":
        return {
            "routing": "COMPLEX",
            "file_list": parsed,
            "context_contents": context_contents,
            "diary_sections": diary_sections,
            "user_request": user_request,
        }

    # SIMPLE path — read files and assemble prompt
    files = parsed.get("files", [])
    instruction = parsed.get("instruction", {})

    file_contents_sections = []
    for path in files:
        contents = read_file(path, project_root, config)
        file_contents_sections.append(f"### {path}\n{contents}\n")

    assembled = (
        f"## Task\n{instruction.get('task_description', '')}\n\n"
        f"## Files provided\n" + "\n".join(files) + "\n\n"
        f"## File contents\n" + "".join(file_contents_sections) + "\n"
        f"## Constraints\n{instruction.get('constraints', '') or '(none)'}\n\n"
        f"## Expected output\n{instruction.get('expected_output', '')}"
    )

    if diary_sections:
        assembled += f"\n\n## Session context\n{diary_sections}"

    return {"routing": "SIMPLE", "assembled_prompt": assembled}
