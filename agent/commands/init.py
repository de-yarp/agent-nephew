from pathlib import Path

_CAPITAL_TEMPLATE = """\
# [Project Name]

## Purpose
What this project does and why it exists.

## Architecture
High-level structure and key design decisions.

## Tech stack
Languages, frameworks, key libraries, versions.

## Conventions
Naming conventions, code style, patterns to follow.

## Constraints
Hard limits, non-negotiable requirements, things to avoid.

## Documentation
List of available lowercase docs for this project:
- docs/lowercase/example.md — description
"""

_AGENTIGNORE_TEMPLATE = """\
# .agentignore
.git
.venv
venv
__pycache__
node_modules
dist
build
.next
*.pyc
*.lock
*.min.js
"""


def handle_init(project_root: Path, force: bool = False) -> None:
    capital_path = project_root / "docs" / "context" / "CAPITAL.md"
    agentignore_path = project_root / ".agentignore"
    lowercase_dir = project_root / "docs" / "lowercase"
    diary_dir = project_root / "docs" / "diary"

    capital_path.parent.mkdir(parents=True, exist_ok=True)
    if capital_path.exists() and not force:
        print("⚠ CAPITAL.md already exists — skipping. Use --force to overwrite.")
    else:
        capital_path.write_text(_CAPITAL_TEMPLATE, encoding="utf-8")

    lowercase_dir.mkdir(parents=True, exist_ok=True)
    diary_dir.mkdir(parents=True, exist_ok=True)

    if agentignore_path.exists() and not force:
        print("⚠ .agentignore already exists — skipping. Use --force to overwrite.")
    else:
        agentignore_path.write_text(_AGENTIGNORE_TEMPLATE, encoding="utf-8")

    print("✓ Project initialised.")
    print("  docs/context/CAPITAL.md — edit this to describe your project")
    print("  docs/lowercase/       — add detailed docs here")
    print("  docs/diary/           — populated automatically by /end")
    print("  .agentignore          — edit to exclude files from agent view")
