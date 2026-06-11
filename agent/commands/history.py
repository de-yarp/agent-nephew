_ROLE_LABELS = {
    "router": "Router",
    "orchestrator": "Orchestrator",
    "worker": "Worker",
}

_SEP = "─" * 33


def handle_history(session, config: dict) -> None:
    summary = session.get_summary(config)
    calls_by_role = summary["calls_by_role"]

    print(f"Session: {summary['session_id']}")
    print(_SEP)

    if not calls_by_role:
        print("No model calls this session.")
        return

    for role in ("router", "orchestrator", "worker"):
        if role not in calls_by_role:
            continue
        data = calls_by_role[role]
        label = _ROLE_LABELS.get(role, role.capitalize())
        print(
            f"{label + ':':<14} {data['calls']} calls  ·  "
            f"{data['input_tokens']} in  ·  {data['output_tokens']} out"
        )

    print(_SEP)
    print(
        f"Total:  {summary['total_input_tokens']} in  ·  "
        f"{summary['total_output_tokens']} out  ·  "
        f"${summary['total_cost']:.4f}"
    )
