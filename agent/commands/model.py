_VALID_ROLES = {"router", "orchestrator", "worker"}


def handle_model(session, role: str, model: str) -> None:
    if role not in _VALID_ROLES:
        print(f"✗ Unknown role: {role}. Valid roles: router, orchestrator, worker")
        return
    session.model_overrides[role] = model
    print(f"✓ {role} model set to: {model} (this session only)")
