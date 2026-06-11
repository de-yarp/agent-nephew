from pathlib import Path


def _extract_injected_sections(entry_text: str) -> str:
    sections = {}
    current_section = None
    current_lines = []

    for line in entry_text.split('\n'):
        if line.startswith('## '):
            if current_section:
                sections[current_section] = '\n'.join(current_lines).strip()
            current_section = line[3:].strip()
            current_lines = []
        elif current_section:
            current_lines.append(line)
    if current_section:
        sections[current_section] = '\n'.join(current_lines).strip()

    result_parts = []
    for key in ['Next session', 'Open questions', 'Decisions']:
        if key in sections and sections[key]:
            result_parts.append(f"## {key}\n{sections[key]}")
    return '\n\n'.join(result_parts)


def _read_context_files(project_root: Path) -> str:
    context_dir = project_root / "docs" / "context"
    if not context_dir.exists() or not any(context_dir.glob("*.md")):
        print("⚠ No context files found in docs/context/ — project context limited.")
        print("  Run /init to create a template.")
        return "[NO PROJECT CONTEXT — docs/context/ is empty or absent. All models are operating without project-level guidance.]"

    parts = []
    for md_file in sorted(context_dir.glob("*.md")):
        contents = md_file.read_text(encoding="utf-8")
        parts.append(f"### {md_file.name}\n{contents}")
    return "\n\n".join(parts)


def _read_diary_sections(project_root: Path, config: dict) -> str:
    diary_dir = project_root / "docs" / "diary"
    if not diary_dir.exists():
        return ""

    entries = sorted(diary_dir.glob("*.md"))
    if not entries:
        return ""

    n = config["diary"]["sliding_window"]
    recent = entries[-n:]

    parts = []
    for entry_path in recent:
        text = entry_path.read_text(encoding="utf-8")
        extracted = _extract_injected_sections(text)
        if extracted:
            parts.append(extracted)
    return "\n\n".join(parts)


def start_session(project_root: Path, session, config: dict) -> dict:
    import git

    try:
        repo = git.Repo(project_root, search_parent_directories=False)
    except git.InvalidGitRepositoryError:
        print("⚠ No git repository found — version control features unavailable.")
        print("  File writes will not be tracked. Strongly recommended: run git init.")
        return {
            "branch": "none",
            "agent_branch": "none",
            "context_contents": _read_context_files(project_root),
            "diary_sections": _read_diary_sections(project_root, config),
            "repo": None,
        }

    try:
        current_branch = repo.active_branch.name
    except TypeError:
        print("✗ Repository is in a detached HEAD state.")
        print("  Checkout a named branch before running the agent:")
        print("  git checkout <branch-name>")
        raise SystemExit(1)

    agent_branch_name = f"agent/{current_branch}"
    existing_branch_names = [b.name for b in repo.branches]

    if agent_branch_name not in existing_branch_names:
        agent_branch = repo.create_head(agent_branch_name)
    else:
        agent_branch = repo.heads[agent_branch_name]

    agent_branch.checkout()

    return {
        "branch": current_branch,
        "agent_branch": agent_branch_name,
        "context_contents": _read_context_files(project_root),
        "diary_sections": _read_diary_sections(project_root, config),
        "repo": repo,
    }
