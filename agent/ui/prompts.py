import questionary
from pathlib import Path
from agent.ui.output import console, PRIMARY, SUCCESS, METADATA, PERMISSION, ERROR
from rich.panel import Panel
from rich.syntax import Syntax

_PERMISSION_STYLE = questionary.Style([
    ("qmark",       f"{PERMISSION} bold"),
    ("question",    f"{PERMISSION} bold"),
    ("answer",      f"{PRIMARY} bold"),
    ("pointer",     f"{PRIMARY} bold"),
    ("highlighted", f"{PRIMARY} bold"),
    ("selected",    f"{SUCCESS}"),
])


def prompt_write_file(path: str, content: str, project_root: Path) -> str:
    new_lines = len(content.splitlines())
    file_path = project_root / path
    if file_path.exists():
        try:
            old_lines = len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
        except Exception:
            old_lines = 0
        delta = new_lines - old_lines
        delta_str = f"+{delta}" if delta >= 0 else str(delta)
    else:
        delta_str = f"+{new_lines}"

    while True:
        console.print(
            Panel(
                f"[bold]{path}[/]  ({delta_str} lines)",
                title="Allow file write?",
                border_style=PERMISSION,
                expand=False,
            )
        )
        choice = questionary.select(
            "",
            choices=["Allow", "Show diff", "Deny — give feedback", "Skip step"],
            style=_PERMISSION_STYLE,
        ).ask()

        if choice is None:
            return "Skip step"

        if choice == "Show diff":
            show_diff(path, content, project_root)
            continue

        return choice


def prompt_run_command(cmd: str) -> str:
    console.print(
        Panel(
            f"[bold]$ {cmd}[/]",
            title="Allow command?",
            border_style=PERMISSION,
            expand=False,
        )
    )
    choice = questionary.select(
        "",
        choices=["Allow", "Deny — give feedback", "Skip step"],
        style=_PERMISSION_STYLE,
    ).ask()
    return choice if choice is not None else "Skip step"


def prompt_fetch_page(url: str) -> str:
    console.print(
        Panel(
            url,
            title="Allow fetch?",
            border_style=PERMISSION,
            expand=False,
        )
    )
    choice = questionary.select(
        "",
        choices=["Allow", "Deny — give feedback", "Skip step"],
        style=_PERMISSION_STYLE,
    ).ask()
    return choice if choice is not None else "Skip step"


def prompt_read_file(path: str) -> str:
    console.print(
        Panel(
            path,
            title="Allow file read?",
            border_style=PERMISSION,
            expand=False,
        )
    )
    choice = questionary.select(
        "",
        choices=["Allow", "Deny — give feedback", "Skip step"],
        style=_PERMISSION_STYLE,
    ).ask()
    return choice if choice is not None else "Skip step"


def prompt_correction_feedback() -> str:
    return questionary.text(
        "Feedback:",
        style=_PERMISSION_STYLE,
    ).ask() or ""


def show_diff(path: str, new_content: str, project_root: Path) -> None:
    import difflib
    file_path = project_root / path
    if file_path.exists():
        try:
            old_content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            old_content = ""
    else:
        old_content = ""

    diff_lines = list(difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    ))

    if diff_lines:
        console.print(Syntax("\n".join(diff_lines), "diff", theme="one-dark"))
    else:
        console.print(f"[{METADATA}](no changes)[/]")


def show_correction_cost(round_n: int, tokens: int, cost_delta: float) -> None:
    console.print(
        f"[{METADATA}]  ⠹ Regenerating...  ·  round {round_n}  ·  "
        f"~{tokens:,} tokens  ·  ${cost_delta:.3f}[/]"
    )
