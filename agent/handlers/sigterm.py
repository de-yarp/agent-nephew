import signal
import atexit
from pathlib import Path

_state: dict = {}
_session_completed_cleanly: bool = False


def mark_session_complete() -> None:
    """Call this from /end before returning — prevents interrupted handler from firing."""
    global _session_completed_cleanly
    _session_completed_cleanly = True


def register_interrupted_handler(
    project_root: Path,
    session,
    conn,
    repo,
) -> None:
    """
    Register SIGTERM and atexit handlers for interrupted session recovery.
    Must be called once at agent startup after git branch is set up.
    Distinct from KeyboardInterrupt in streaming loop — does not overlap.
    """
    _state.update({
        "project_root": project_root,
        "session": session,
        "conn": conn,
        "repo": repo,
    })

    atexit.register(_handle_exit)

    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, _handle_sigterm)


def _handle_sigterm(signum, frame) -> None:
    _run_interrupted_handler()
    raise SystemExit(0)


def _handle_exit() -> None:
    if not _session_completed_cleanly:
        _run_interrupted_handler()


def _run_interrupted_handler() -> None:
    if _session_completed_cleanly:
        return

    repo = _state.get("repo")
    conn = _state.get("conn")

    if repo is not None:
        try:
            if repo.is_dirty(untracked_files=True):
                repo.git.add(A=True)
                repo.index.commit("[interrupted] session ended unexpectedly")
                print("\n[interrupted] Uncommitted writes saved to agent branch.")
        except Exception as e:
            print(f"\n[interrupted] Failed to commit agent branch: {e}")
            print("  Recover manually with: git add . && git commit -m '[interrupted]'")

    if conn is not None:
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE traces SET error = %s WHERE session_id = %s AND error IS NULL",
                ("[interrupted]", _state["session"].session_id),
            )
            conn.commit()
        except Exception:
            pass

    print("[interrupted] Diary generation skipped.")
