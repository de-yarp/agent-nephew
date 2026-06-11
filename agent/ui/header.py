from pathlib import Path
from pyfiglet import Figlet
from agent.ui.output import console, PRIMARY, METADATA, Rule


def print_startup_header(
    config: dict,
    project_root: Path,
    branch: str,
    agent_branch: str,
) -> None:
    project_name = project_root.name or "agent"

    f = Figlet(font="slant")
    ascii_art = f.renderText(project_name).rstrip()

    router_model = config["models"]["router"]["model"]
    orch_model   = config["models"]["orchestrator"]["model"]
    worker_model = config["models"]["worker"]["model"]

    console.print(f"[bold {PRIMARY}]{ascii_art}[/]")
    console.print(
        f"[{METADATA}]v0.1.0  ·  {router_model} + {orch_model}  ·  {worker_model}  ·  {project_root}[/]"
    )
    if branch != "none":
        console.print(f"[{METADATA}]branch: {branch}  →  {agent_branch}[/]")
    else:
        console.print(f"[{METADATA}]branch: (no git)[/]")
    console.print(Rule(style=METADATA))
