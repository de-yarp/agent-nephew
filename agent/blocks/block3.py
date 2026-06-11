from __future__ import annotations

from pathlib import Path

from agent.tracing import traced_call_llm
from agent.result import assemble_step_result
from agent.session import Session
from agent.tools.dispatcher import execute_tool
from agent.tools.schemas import BLOCK3_SCHEMAS

SYSTEM_MESSAGE = (
    "You are an expert coding assistant executing a specific implementation task.\n"
    "\n"
    "BEHAVIORAL RULES:\n"
    "1. Explain your approach in natural language before calling any tools.\n"
    "2. Before any write_file call, describe exactly what you are writing and why.\n"
    "3. If you notice issues outside the assigned task scope, explain them in text before proposing any out-of-scope changes — never silently modify unrelated files.\n"
    "4. Be precise and minimal — change only what the task requires.\n"
    "5. Use run_command to verify your work where appropriate (e.g. running tests, checking syntax).\n"
    "6. If you receive correction feedback, acknowledge it explicitly and adjust your approach."
)


def _format_denied_item(tool_name: str, args: dict) -> str:
    if tool_name == "write_file":
        return args.get("path", "(unknown path)")
    if tool_name == "run_command":
        return args.get("cmd", "(unknown command)")
    if tool_name == "read_file":
        return args.get("path", "(unknown path)")
    if tool_name == "fetch_page":
        return args.get("url", "(unknown url)")
    return str(args)


def _format_executed_item(tool_name: str, args: dict) -> str:
    return f"{tool_name}: {_format_denied_item(tool_name, args)}"


def _build_worker_message(
    frozen_assembled_prompt: str,
    already_executed: list[str],
    last_text_output: str,
    correction_note: str | None,
) -> str:
    if not already_executed and correction_note is None:
        return frozen_assembled_prompt

    parts = [frozen_assembled_prompt]

    executed_text = "\n".join(already_executed) if already_executed else "(none)"
    parts.append(f"## Already executed in this step\n{executed_text}")

    output_text = last_text_output if last_text_output else "(none)"
    parts.append(f"## Previous output\n{output_text}")

    if correction_note is not None:
        parts.append(f"## Correction note\n{correction_note}")

    return "\n\n".join(parts)


def execute_step(
    assembled_prompt: str,
    session: Session,
    config: dict,
    project_root: Path,
    approval_callback: callable = None,
    conn=None,
) -> dict:
    if approval_callback is None:
        def approval_callback(tier, tool_name, args):
            if tier == "tier2":
                print(f"[dev-mode auto-approve] {tool_name}: {list(args.keys())}")
            return "approved"

    approved_writes: list[str] = []
    approved_commands: list[str] = []
    denied: dict[str, list[str]] = {}
    errors: list[str] = []
    already_executed: list[str] = []
    frozen_assembled_prompt: str = assembled_prompt
    last_text_output: str = ""
    pending_correction_note: str | None = None
    correction_round: int = 0

    while True:
        user_message = _build_worker_message(
            frozen_assembled_prompt=frozen_assembled_prompt,
            already_executed=already_executed,
            last_text_output=last_text_output,
            correction_note=pending_correction_note,
        )

        messages = [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": user_message},
        ]

        if correction_round > 0:
            print(f"\n[Regenerating... round {correction_round}]")

        def token_printer(token: str):
            print(token, end="", flush=True)

        result = traced_call_llm(
            role="worker",
            messages=messages,
            session=session,
            conn=conn,
            config=config,
            stream_handler=token_printer,
            tools=BLOCK3_SCHEMAS,
        )
        session.accumulate_tokens("worker", result["input_tokens"], result["output_tokens"])
        print()

        last_text_output = result["content"]
        pending_correction_note = None

        if result["finish_reason"] == "interrupted":
            print("\n⚠ Generation stopped. Partial output saved to context.")
            return assemble_step_result(approved_writes, approved_commands, denied, errors)

        if result["finish_reason"] == "length":
            print("\n⚠ Output truncated — worker hit token limit. Consider narrowing the task scope.")

        if not result["tool_calls"]:
            break

        denial_triggered_correction = False

        for tc in result["tool_calls"]:
            tool_name = tc["name"]
            tool_args = tc["arguments"]

            feedback_capture = {"value": None}

            def _callback_wrapper(tier, tname, targs,
                                  _capture=feedback_capture,
                                  _cb=approval_callback):
                raw = _cb(tier, tname, targs)
                if isinstance(raw, dict):
                    _capture["value"] = raw.get("feedback")
                    return raw.get("result", "denied")
                return raw

            try:
                tool_result = execute_tool(
                    tool_name, tool_args, "block3",
                    project_root, config, _callback_wrapper,
                )
            except Exception as e:
                errors.append(f"{tool_name}: {e}")
                continue

            if isinstance(tool_result, dict) and tool_result.get("skip"):
                return assemble_step_result(approved_writes, approved_commands, denied, errors)

            elif isinstance(tool_result, dict) and tool_result.get("denied"):
                denied.setdefault(tool_name, []).append(
                    _format_denied_item(tool_name, tool_args)
                )
                feedback = feedback_capture["value"]
                if feedback:
                    pending_correction_note = feedback
                    correction_round += 1
                    denial_triggered_correction = True
                break

            else:
                already_executed.append(_format_executed_item(tool_name, tool_args))
                if tool_name == "write_file":
                    approved_writes.append(tool_args.get("path", ""))
                elif tool_name == "run_command":
                    approved_commands.append(tool_args.get("cmd", ""))

        if not denial_triggered_correction:
            break

    return assemble_step_result(approved_writes, approved_commands, denied, errors)
