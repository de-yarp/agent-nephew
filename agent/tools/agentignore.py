from pathlib import Path

import pathspec

_FALLBACK_PATTERNS = [
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    "dist", "build", ".next", "*.pyc", "*.lock", "*.min.js",
]


def parse_agentignore(project_root: Path) -> list[str]:
    ignore_file = project_root / ".agentignore"
    if ignore_file.exists():
        lines = ignore_file.read_text(encoding="utf-8").splitlines()
        patterns = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        return patterns
    return list(_FALLBACK_PATTERNS)


def is_ignored(path: str, spec: pathspec.PathSpec) -> bool:
    return spec.match_file(path)
