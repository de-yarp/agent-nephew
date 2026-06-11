from pathlib import Path


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    for directory in [current, *current.parents]:
        if (directory / ".git").exists():
            return directory
    print(
        "⚠ No git repository found — using current directory as project root.\n"
        f"  File operations will be relative to: {Path.cwd()}\n"
        "  Version control features will be unavailable."
    )
    return Path.cwd()
