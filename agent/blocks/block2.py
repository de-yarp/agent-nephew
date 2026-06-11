from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

import questionary

from agent.tracing import traced_call_llm
from agent.tools.dispatcher import execute_tool
from agent.tools.functions import read_file
from agent.tools.schemas import BLOCK2_SCHEMAS
from agent.ui.output import spinner, show_step_header, show_large_plan_warning

if TYPE_CHECKING:
    from agent.session import Session

_SYSTEM_TEMPLATE = """\
You are an expert software development orchestrator. You plan and coordinate coding task implementation.

BEHAVIORAL RULES:
- Analyze tasks thoroughly before decomposing
- Each step must be scoped as a single coherent worker call
- Steps affecting the same file MUST be batched — no separate calls per function in a file
- Steps may include run_command where appropriate (migrations, installs, tests)
- Be specific about files, constraints, and expected outputs

PROJECT CONTEXT:
{context_section}

{history_section}\
"""


def _build_system_message(context_contents: str, diary_sections: str) -> str:
    context_section = context_contents if context_contents else "(no project context files found)"
    history_section = f"SESSION HISTORY:\n{diary_sections}" if diary_sections else ""
    return _SYSTEM_TEMPLATE.format(
        context_section=context_section,
        history_section=history_section,
    ).rstrip()


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


def _parse_steps_json(
    content: str,
    messages: list,
    config: dict,
    session: "Session",
    conn=None,
) -> list:
    """
    Parses {"steps": [...]} from content. messages should already contain the
    last assistant response. Single retry via orchestrator on first failure.
    """
    cleaned = _strip_fences(content)
    try:
        parsed = json.loads(cleaned)
        return parsed["steps"]
    except (json.JSONDecodeError, KeyError):
        pass

    retry_messages = list(messages) + [
        {
            "role": "user",
            "content": (
                "Your previous response could not be parsed as valid JSON. "
                "Output the plan as a JSON object only — no markdown fences, no prose:\n"
                '{"steps": [{"title": "...", "description": "..."}]}'
            ),
        }
    ]
    retry_result = traced_call_llm(role="orchestrator", messages=retry_messages, session=session, conn=conn, config=config)
    session.accumulate_tokens("orchestrator", retry_result["input_tokens"], retry_result["output_tokens"])
    cleaned2 = _strip_fences(retry_result["content"])
    try:
        parsed2 = json.loads(cleaned2)
        return parsed2["steps"]
    except (json.JSONDecodeError, KeyError):
        print("✗ Block 2 failed to produce valid steps JSON after 2 attempts. Halting.")
        raise SystemExit(1)


def _parse_instruction_json(
    content: str,
    messages: list,
    config: dict,
    session: "Session",
    conn=None,
) -> dict:
    """
    Parses block2_step_instruction dict from content. messages should NOT include
    the last assistant response. Single retry via orchestrator on first failure.
    """
    cleaned = _strip_fences(content)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    retry_messages = list(messages) + [
        {"role": "assistant", "content": content},
        {
            "role": "user",
            "content": (
                "Your previous response could not be parsed as valid JSON. "
                "Output the step instruction as a JSON object only — no markdown fences, no prose:\n"
                '{"task_description": "...", "files": ["path/to/file.py"], '
                '"constraints": "...", "expected_output": "..."}'
            ),
        },
    ]
    retry_result = traced_call_llm(role="orchestrator", messages=retry_messages, session=session, conn=conn, config=config)
    session.accumulate_tokens("orchestrator", retry_result["input_tokens"], retry_result["output_tokens"])
    cleaned2 = _strip_fences(retry_result["content"])
    try:
        return json.loads(cleaned2)
    except json.JSONDecodeError:
        print("✗ Block 2 failed to produce valid instruction JSON after 2 attempts. Halting.")
        raise SystemExit(1)


def _scan_documentation_manifest(
    context_contents: str,
    project_root: Path,
    config: dict,
) -> str:
    extra_parts: list[str] = []
    in_doc_section = False

    for line in context_contents.splitlines():
        if re.match(r"^##\s+Documentation", line):
            in_doc_section = True
            continue
        if in_doc_section:
            if line.startswith("## "):
                in_doc_section = False
                continue
            if line.startswith("-"):
                # Extract path-like token ending in .md
                match = re.search(r"[\w./-]+\.md", line)
                if match:
                    path_str = match.group(0)
                    full_path = project_root / path_str
                    if full_path.exists():
                        doc_content = read_file(path_str, project_root, config)
                        extra_parts.append(f"### {path_str}\n{doc_content}")

    return "\n\n".join(extra_parts)


def _run_analysis_with_tools(
    messages: list,
    config: dict,
    session: "Session",
    project_root: Path,
    conn=None,
) -> tuple[str, list]:
    while True:
        result = traced_call_llm(
            role="orchestrator",
            messages=messages,
            session=session,
            conn=conn,
            config=config,
            tools=BLOCK2_SCHEMAS,
        )
        session.accumulate_tokens("orchestrator", result["input_tokens"], result["output_tokens"])

        if result["finish_reason"] != "tool_calls" or not result["tool_calls"]:
            return (result["content"], messages)

        messages = list(messages)
        messages.append(result["raw_assistant_message"])

        for tc in result["tool_calls"]:
            tool_result = execute_tool(
                tc["name"],
                tc["arguments"],
                "block2",
                project_root,
                config,
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(tool_result),
            })


def _display_plan(steps: list, config: dict) -> None:
    print(f"\nPlan ({len(steps)} steps):")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step['title']} — {step['description']}")
    if len(steps) > config["warnings"]["large_plan_steps"]:
        show_large_plan_warning(len(steps), config["warnings"]["large_plan_steps"])


def run_planning_phase(
    user_request: str,
    file_list: list,
    context_contents: str,
    diary_sections: str,
    session: "Session",
    config: dict,
    project_root: Path,
    conn=None,
) -> tuple[list, list] | None:
    system_msg = _build_system_message(context_contents, diary_sections)
    planning_messages: list = [{"role": "system", "content": system_msg}]

    # Step 1 — Analysis call (with tools)
    analysis_user_msg = (
        f"User request: {user_request}\n\n"
        f"Available project files:\n{chr(10).join(file_list)}\n\n"
        "Analyze this request. Identify what needs to be done, which files are involved, "
        "and any dependencies or constraints. Use tools to read additional files if needed."
    )
    planning_messages.append({"role": "user", "content": analysis_user_msg})

    with spinner("Analysing..."):
        analysis_content, planning_messages = _run_analysis_with_tools(
            planning_messages, config, session, project_root, conn=conn
        )
    planning_messages.append({"role": "assistant", "content": analysis_content})

    # Step 2 — Decomposition call (no tools)
    decomp_user_msg = (
        "Now decompose this task into discrete implementation steps.\n\n"
        "Rules:\n"
        "- Each step = one focused worker call\n"
        "- Steps affecting the same file MUST be batched\n"
        "- Include run_command steps where appropriate\n"
        "- One concern per step\n\n"
        'Output a JSON object only — no markdown fences, no prose:\n'
        '{"steps": [{"title": "Brief title", "description": "What this step implements"}]}'
    )
    planning_messages.append({"role": "user", "content": decomp_user_msg})

    with spinner("Planning..."):
        decomp_result = traced_call_llm(role="orchestrator", messages=planning_messages, session=session, conn=conn, config=config)
    session.accumulate_tokens("orchestrator", decomp_result["input_tokens"], decomp_result["output_tokens"])
    planning_messages.append({"role": "assistant", "content": decomp_result["content"]})

    steps = _parse_steps_json(decomp_result["content"], planning_messages, config, session, conn=conn)

    # Step 3 — Plan approval loop
    while True:
        _display_plan(steps, config)
        choice = questionary.select(
            "Execute?",
            choices=["Yes, proceed", "Modify plan", "Cancel"],
        ).ask()

        if choice == "Yes, proceed":
            return (steps, planning_messages)

        elif choice == "Cancel":
            return None

        elif choice == "Modify plan":
            modification = questionary.text("❯").ask()
            if not modification or not modification.strip():
                continue

            planning_messages.append({
                "role": "user",
                "content": (
                    f"Modify the plan as follows: {modification}\n\n"
                    "Output the revised plan as a JSON object only — no markdown fences:\n"
                    '{"steps": [{"title": "...", "description": "..."}]}'
                ),
            })

            with spinner("Revising plan..."):
                mod_result = traced_call_llm(role="orchestrator", messages=planning_messages, session=session, conn=conn, config=config)
            session.accumulate_tokens("orchestrator", mod_result["input_tokens"], mod_result["output_tokens"])
            planning_messages.append({"role": "assistant", "content": mod_result["content"]})

            steps = _parse_steps_json(mod_result["content"], planning_messages, config, session, conn=conn)


def _build_step_execution_message(
    step: dict,
    step_n: int,
    total: int,
    previous_result: dict | None,
    denied_ops: list,
) -> str:
    parts = [
        f"Execute step {step_n} of {total}: {step['title']}",
        "",
        step["description"],
        "",
    ]

    if previous_result is not None:
        parts.append(f"Previous step result:\n{json.dumps(previous_result, indent=2)}")
    else:
        parts.append("This is the first step.")

    if denied_ops:
        parts.extend([
            "",
            "## Previously denied operations",
            "The following operations were denied in previous steps — do not re-attempt them:",
            "\n".join(denied_ops),
        ])

    parts.extend([
        "",
        "Output the JSON instruction for this step only — no markdown fences, no prose:",
        '{"task_description": "...", "files": ["path/to/file.py"], "constraints": "...", "expected_output": "..."}',
    ])

    return "\n".join(parts)


def _assemble_block3_prompt(
    instruction: dict,
    project_root: Path,
    config: dict,
    denied_ops: list,
) -> str:
    files = instruction.get("files", [])

    file_contents_sections: list[str] = []
    for path in files:
        contents = read_file(path, project_root, config)
        file_contents_sections.append(f"### {path}\n{contents}\n")

    denied_section = ""
    if denied_ops:
        denied_section = (
            "## Previously denied operations\n"
            + "\n".join(denied_ops)
            + "\n\n"
        )

    return (
        denied_section
        + f"## Task\n{instruction.get('task_description', '')}\n\n"
        f"## Files provided\n" + "\n".join(files) + "\n\n"
        f"## File contents\n" + "".join(file_contents_sections) + "\n"
        f"## Constraints\n{instruction.get('constraints', '') or '(none)'}\n\n"
        f"## Expected output\n{instruction.get('expected_output', '')}"
    )


def _evaluate_step_result(result: dict) -> str:
    status = result.get("status", "error")
    if status == "success":
        return "proceed"
    if status == "partial":
        denied = result.get("denied", {})
        errors = result.get("errors", [])
        if denied and not errors:
            return "proceed_with_denials"
        return "halt_errors"
    return "halt_error"


def run_execution_phase(
    steps: list,
    planning_messages: list,
    session: "Session",
    config: dict,
    project_root: Path,
    conn=None,
    approval_callback=None,
) -> list:
    from agent.blocks.block3 import execute_step

    all_results: list = []
    all_denied: list = []

    for i, step in enumerate(steps, 1):
        show_step_header(i, len(steps))

        previous_result = all_results[-1] if all_results else None
        step_user_msg = _build_step_execution_message(
            step=step,
            step_n=i,
            total=len(steps),
            previous_result=previous_result,
            denied_ops=all_denied,
        )

        step_messages = list(planning_messages) + [{"role": "user", "content": step_user_msg}]

        with spinner("Building step instruction..."):
            result = traced_call_llm(role="orchestrator", messages=step_messages, session=session, conn=conn, config=config)
        session.accumulate_tokens("orchestrator", result["input_tokens"], result["output_tokens"])

        instruction = _parse_instruction_json(result["content"], step_messages, config, session, conn=conn)

        assembled_prompt = _assemble_block3_prompt(instruction, project_root, config, all_denied)

        step_result = execute_step(assembled_prompt, session, config, project_root, conn=conn, approval_callback=approval_callback)
        all_results.append(step_result)

        evaluation = _evaluate_step_result(step_result)

        if evaluation == "proceed":
            continue

        elif evaluation == "proceed_with_denials":
            for tool, items in step_result.get("denied", {}).items():
                for item in items:
                    all_denied.append(f"- {tool}: {item}")
            continue

        elif evaluation == "halt_errors":
            choice = questionary.select(
                f"Step {i} completed with errors. Proceed or abort?",
                choices=["Proceed to next step", "Abort"],
            ).ask()
            if choice == "Abort":
                break
            continue

        elif evaluation == "halt_error":
            print(f"\n✗ Step {i} failed with errors: {step_result.get('errors', [])}")
            print("Halting execution.")
            break

    return all_results


def orchestrate(
    user_request: str,
    file_list: list,
    context_contents: str,
    diary_sections: str,
    session: "Session",
    config: dict,
    project_root: Path,
    conn=None,
    approval_callback=None,
) -> list:
    extra_docs = _scan_documentation_manifest(context_contents, project_root, config)
    if extra_docs:
        context_contents = context_contents + "\n\n" + extra_docs

    planning_result = run_planning_phase(
        user_request=user_request,
        file_list=file_list,
        context_contents=context_contents,
        diary_sections=diary_sections,
        session=session,
        config=config,
        project_root=project_root,
        conn=conn,
    )

    if planning_result is None:
        print("Task cancelled.")
        return []

    steps, planning_messages = planning_result

    return run_execution_phase(
        steps=steps,
        planning_messages=planning_messages,
        session=session,
        config=config,
        project_root=project_root,
        conn=conn,
        approval_callback=approval_callback,
    )
