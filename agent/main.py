import argparse
from pathlib import Path

from agent.config import load_config
from agent.env import load_env
from agent.root import find_project_root


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent — CLI Coding Assistant")
    parser.add_argument("--no-trace", action="store_true", default=False)
    parser.add_argument("--worker", metavar="model_string", default=None)
    args = parser.parse_args()

    project_root = find_project_root(Path.cwd())
    load_env(project_root)
    config = load_config(project_root)

    from agent.session import create_session
    session = create_session()

    conn = None
    if not args.no_trace and config.get("tracing", {}).get("enabled", True):
        from agent.db import connect_postgres
        conn = connect_postgres(config)

    print(f"Agent initialised. Session: {session.session_id}")
    print(f"Project root: {project_root}")
    print(f"Tracing: {'enabled' if conn else 'disabled'}")
    print("REPL not yet implemented — coming in [9].")

    # Temporary test call — removed in [9]
    from agent.blocks.block1 import route_and_dispatch
    result = route_and_dispatch(
        user_request="test request",
        session=session,
        config=config,
        project_root=project_root
    )
    print(f"Routing test: {result['routing']}")
