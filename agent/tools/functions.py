from __future__ import annotations

import os
import platform
import shlex
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import httpx

from agent.tools.agentignore import is_ignored, parse_agentignore


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

def read_file(path: str, project_root: Path, config: dict) -> str:
    target = project_root / path
    if not target.exists():
        return f"Error: file not found: {path}"
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"Error: cannot read binary file: {path}"
    head = config["tools"]["large_file_head_lines"]
    tail = config["tools"]["large_file_tail_lines"]
    threshold = head + tail
    if len(lines) <= threshold:
        return "\n".join(lines)
    notice = f"[... truncated — file exceeds display limit. Showing first {head} and last {tail} lines ...]"
    return "\n".join(lines[:head]) + "\n" + notice + "\n" + "\n".join(lines[-tail:])


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

def write_file(path: str, content: str, project_root: Path) -> None:
    target = project_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

def list_files(project_root: Path, config: dict) -> list[str]:
    import pathspec

    patterns = parse_agentignore(project_root)
    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    result: list[str] = []

    for dirpath, dirnames, filenames in os.walk(project_root):
        rel_dir = Path(dirpath).relative_to(project_root)
        # Filter out ignored directories in-place so os.walk won't descend into them
        dirnames[:] = [
            d for d in dirnames
            if not is_ignored(str(rel_dir / d), spec)
            and not is_ignored(str(rel_dir / d) + "/", spec)
        ]
        for filename in filenames:
            rel_path = rel_dir / filename
            rel_str = rel_path.as_posix()
            if not is_ignored(rel_str, spec):
                result.append(rel_str)

    result.sort()
    return result


# ---------------------------------------------------------------------------
# search_in_files
# ---------------------------------------------------------------------------

def search_in_files(query: str, project_root: Path, config: dict) -> list[dict]:
    import pathspec

    patterns = parse_agentignore(project_root)
    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    matches: list[dict] = []
    query_lower = query.lower()

    for dirpath, dirnames, filenames in os.walk(project_root):
        rel_dir = Path(dirpath).relative_to(project_root)
        dirnames[:] = [
            d for d in dirnames
            if not is_ignored(str(rel_dir / d), spec)
            and not is_ignored(str(rel_dir / d) + "/", spec)
        ]
        for filename in filenames:
            rel_path = rel_dir / filename
            rel_str = rel_path.as_posix()
            if is_ignored(rel_str, spec):
                continue
            abs_path = project_root / rel_path
            try:
                text = abs_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if query_lower in line.lower():
                    matches.append({"file": rel_str, "line": lineno, "content": line})
                    if len(matches) >= 50:
                        return matches

    return matches


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------

def _should_use_uv_run(project_root: Path) -> bool:
    context_dir = project_root / "docs" / "context"
    if context_dir.exists():
        for f in context_dir.iterdir():
            if f.is_file():
                try:
                    text = f.read_text(encoding="utf-8").lower()
                    if "uv" in text:
                        return True
                except (UnicodeDecodeError, OSError):
                    pass
    if (project_root / "uv.lock").exists():
        return True
    return False


def run_command(cmd: str, project_root: Path, config: dict) -> dict:
    if _should_use_uv_run(project_root):
        full_cmd = f"uv run {cmd}"
    else:
        full_cmd = cmd

    stdout_buf: list[str] = []
    stderr_buf: list[str] = []

    is_windows = platform.system() == "Windows"
    if is_windows:
        popen_args = {"args": full_cmd, "shell": True}
    else:
        popen_args = {"args": shlex.split(full_cmd), "shell": False}

    proc = subprocess.Popen(
        **popen_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(project_root),
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    # Stream stdout
    assert proc.stdout is not None
    assert proc.stderr is not None
    for line in proc.stdout:
        print(line, end="", flush=True)
        stdout_buf.append(line)
    for line in proc.stderr:
        print(line, end="", flush=True)
        stderr_buf.append(line)

    proc.wait()

    return {
        "stdout": "".join(stdout_buf),
        "stderr": "".join(stderr_buf),
        "exit_code": proc.returncode,
    }


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------

def web_search(query: str, config: dict) -> list[dict]:
    provider = config["web_search"]["provider"]
    max_results = config["tools"]["web_search_max_results"]

    if provider == "brave":
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
        if not api_key:
            return [{"error": "web search API key not configured"}]
        try:
            resp = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={"X-Subscription-Token": api_key},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("web", {}).get("results", [])
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
                for r in results[:max_results]
            ]
        except Exception as e:
            return [{"error": str(e)}]

    elif provider == "tavily":
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return [{"error": "web search API key not configured"}]
        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "max_results": max_results},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                for r in results[:max_results]
            ]
        except Exception as e:
            return [{"error": str(e)}]

    return [{"error": f"unsupported web search provider: {provider}"}]


# ---------------------------------------------------------------------------
# fetch_page
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def fetch_page(url: str, config: dict) -> str:
    max_chars = config["tools"]["fetch_page_max_chars"]
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "html" in content_type:
            extractor = _TextExtractor()
            extractor.feed(resp.text)
            text = extractor.get_text()
        else:
            text = resp.text
    except Exception as e:
        return f"Error fetching {url}: {str(e)}"

    if len(text) > max_chars:
        return text[:max_chars] + f"\n[... truncated to {max_chars} characters ...]"
    return text
