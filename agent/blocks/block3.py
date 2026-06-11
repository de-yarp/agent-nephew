# agent/blocks/block3.py
# STUB — full implementation provided by Prompt [6].
# This file exists so Block 2 can import and call execute_step() during development.
# Prompt [6] replaces this file entirely.

from pathlib import Path


def execute_step(
    assembled_prompt: str,
    session: "Session",
    config: dict,
    project_root: Path
) -> dict:
    """
    STUB — returns a mock success result for testing Block 2 in isolation.
    Full implementation provided by Prompt [6].
    """
    print("[block3 stub] execute_step called — returning mock success")
    return {
        "status": "success",
        "files_written": [],
        "commands_run": [],
    }
