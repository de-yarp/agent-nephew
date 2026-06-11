# STUB — full implementation provided by Prompt [8].
# Prompt [8] replaces this entire file. Do not add logic here.


def create_traces_table(conn) -> None:
    """STUB — no-op. Full implementation in Prompt [8]."""
    pass


def traced_call_llm(role: str, messages: list, session, conn, **kwargs) -> dict:
    """
    STUB — pass-through to call_llm(). Full implementation in Prompt [8].
    Prompt [8] replaces this with a transparent logging wrapper.
    """
    from agent.llm import call_llm
    return call_llm(role, messages, kwargs.pop("config"), **kwargs)


def get_session_trace_summary(session_id: str, conn) -> dict:
    """
    STUB — returns empty dict. Full implementation in Prompt [8].
    Prompt [8] replaces this with a real Postgres query.
    """
    return {}
