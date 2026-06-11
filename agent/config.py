import json
from pathlib import Path

REQUIRED_KEYS = ["models", "tracing", "diary", "web_search", "tools", "warnings"]


def load_config(project_root: Path) -> dict:
    config_path = project_root / ".agent.json"
    if not config_path.exists():
        print(
            f"✗ No .agent.json found at {config_path}\n"
            "  Create one using the template in the agent repository."
        )
        raise SystemExit(1)

    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    for key in REQUIRED_KEYS:
        if key not in config:
            print(f"✗ Missing required key in .agent.json: '{key}'")
            raise SystemExit(1)

    return config
