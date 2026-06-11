def assemble_step_result(
    approved_writes: list[str],
    approved_commands: list[str],
    denied: dict[str, list[str]],
    errors: list[str],
) -> dict:
    has_approved = bool(approved_writes) or bool(approved_commands)
    has_errors = bool(errors)
    has_denied = any(bool(v) for v in denied.values()) if denied else False

    if has_errors and not has_approved:
        status = "error"
    elif has_errors or has_denied:
        status = "partial"
    else:
        status = "success"

    result: dict = {"status": status}
    if approved_writes:
        result["files_written"] = approved_writes
    if approved_commands:
        result["commands_run"] = approved_commands
    filtered_denied = {k: v for k, v in denied.items() if v}
    if filtered_denied:
        result["denied"] = filtered_denied
    if errors:
        result["errors"] = errors
    return result
