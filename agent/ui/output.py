import io
import sys
from contextlib import contextmanager
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.rule import Rule


def _make_console() -> Console:
    if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
        return Console(legacy_windows=False)
    return Console()


console = _make_console()

PRIMARY    = "#5B8DEF"
SUCCESS    = "#4EC994"
METADATA   = "#6B7280"
PERMISSION = "#D4934A"
ERROR      = "#D45C5C"


@contextmanager
def spinner(label: str):
    with console.status(f"[{METADATA}]{label}[/]", spinner="arc"):
        yield


def show_tier1_panel(tool_name: str, args: dict) -> None:
    if tool_name == "web_search":
        body = f'"{args.get("query", "")}"'
    elif tool_name == "fetch_page":
        body = f'{args.get("url", "")}\n(truncated to {args.get("max_chars", 6000)} chars)'
    elif tool_name in ("read_file", "write_file"):
        body = args.get("path", "")
    elif tool_name == "list_files":
        body = "(listing project files)"
    elif tool_name == "search_in_files":
        body = f'"{args.get("query", "")}"'
    elif tool_name == "run_command":
        body = f'$ {args.get("cmd", "")}'
    else:
        body = str(args)

    console.print(
        Panel(body, title=f"[{METADATA}]{tool_name}[/]",
              border_style=METADATA, expand=False)
    )


def show_routing_result(decision: str) -> None:
    color = SUCCESS if decision == "SIMPLE" else PRIMARY
    console.print(f"[{color}]→ {decision}[/]")


def show_step_header(step_n: int, total: int) -> None:
    console.print(f"\n[{METADATA}]─── Step {step_n} / {total} ───[/]")


def show_completion_summary(tokens: int, cost: float, steps: int | None = None) -> None:
    parts = ["✓ Done"]
    if steps is not None:
        parts.append(f"{steps} step{'s' if steps != 1 else ''}")
    parts.append(f"~{tokens:,} tokens")
    parts.append(f"${cost:.3f}")
    console.print(f"[bold {SUCCESS}]{' · '.join(parts)}[/]")


def show_truncation_warning() -> None:
    console.print(
        f"[{ERROR}]⚠ Output truncated — worker hit token limit. "
        f"Consider narrowing the task scope or increasing max_tokens in .agent.json.[/]"
    )


def show_large_plan_warning(step_count: int, threshold: int) -> None:
    console.print(
        f"[{PERMISSION}]⚠ Large plan ({step_count} steps, threshold {threshold}) — "
        f"consider narrowing the task scope.[/]"
    )


def show_interrupt_message() -> None:
    console.print(f"\n[{PERMISSION}]⚠ Generation stopped. Partial output saved to context.[/]")


def show_syntax(code: str, language: str) -> None:
    console.print(Syntax(code, language, theme="one-dark"))


def make_stream_handler() -> callable:
    def handler(token: str) -> None:
        console.print(token, end="", highlight=False)
    return handler
