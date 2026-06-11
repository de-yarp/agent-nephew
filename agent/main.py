import argparse
from pathlib import Path

from agent.config import load_config
from agent.env import load_env
from agent.root import find_project_root


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent — CLI Coding Assistant")
    parser.add_argument("--no-trace", action="store_true", default=False)
    parser.add_argument("--worker", metavar="model_string", default=None)
    parser.parse_args()

    project_root = find_project_root(Path.cwd())
    load_env(project_root)
    load_config(project_root)

    print(
        f"Agent initialised. REPL not yet implemented — coming in [9].\n"
        f"Project root: {project_root}"
    )
