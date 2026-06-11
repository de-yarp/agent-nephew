from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agent.tools.functions import (
    fetch_page,
    list_files,
    read_file,
    run_command,
    search_in_files,
    web_search,
    write_file,
)

# tier: 1 = auto-execute, 2 = approval required, None = not available
_TIER_MAP: dict[str, dict[str, int | None]] = {
    "read_file":       {"block2": 1, "block3": 2},
    "list_files":      {"block2": 1, "block3": None},
    "search_in_files": {"block2": 1, "block3": None},
    "web_search":      {"block2": 1, "block3": 1},
    "fetch_page":      {"block2": 1, "block3": 2},
    "write_file":      {"block2": None, "block3": 2},
    "run_command":     {"block2": None, "block3": 2},
}


def _invoke(tool_name: str, args: dict, project_root: Path, config: dict) -> Any:
    if tool_name == "read_file":
        return read_file(args["path"], project_root, config)
    if tool_name == "write_file":
        return write_file(args["path"], args["content"], project_root)
    if tool_name == "list_files":
        return list_files(project_root, config)
    if tool_name == "search_in_files":
        return search_in_files(args["query"], project_root, config)
    if tool_name == "run_command":
        return run_command(args["cmd"], project_root, config)
    if tool_name == "web_search":
        return web_search(args["query"], config)
    if tool_name == "fetch_page":
        return fetch_page(args["url"], config)
    raise RuntimeError(f"Unknown tool: {tool_name}")


def execute_tool(
    tool_name: str,
    args: dict,
    block: str,
    project_root: Path,
    config: dict,
    approval_callback: Callable | None = None,
) -> Any:
    tier_entry = _TIER_MAP.get(tool_name)
    if tier_entry is None:
        raise RuntimeError(f"Unknown tool: {tool_name}")

    tier = tier_entry.get(block)
    if tier is None:
        raise RuntimeError(f"Tool {tool_name} is not available in {block}")

    if tier == 1:
        if approval_callback is not None:
            approval_callback("tier1", tool_name, args)
        return _invoke(tool_name, args, project_root, config)

    # tier == 2
    if approval_callback is None:
        raise RuntimeError(f"No approval callback provided for Tier 2 tool: {tool_name}")

    decision = approval_callback("tier2", tool_name, args)
    if decision == "approved":
        return _invoke(tool_name, args, project_root, config)
    if decision == "denied":
        return {"denied": True, "tool": tool_name}
    if decision == "skip":
        return {"skip": True}
    raise RuntimeError(f"Unexpected approval_callback response: {decision!r}")
