import argparse
from pathlib import Path


def main() -> None:
    # === ARGUMENT PARSING ===
    parser = argparse.ArgumentParser(description="nephew — CLI coding assistant")
    parser.add_argument("--no-trace", action="store_true", default=False,
                        help="Disable Postgres tracing for this session")
    parser.add_argument("--worker", type=str, default=None,
                        help="Override worker model for this session")
    args = parser.parse_args()

    # === STARTUP ===
    from agent.root import find_project_root
    from agent.env import load_env
    from agent.config import load_config
    from agent.session import create_session
    from agent.db import connect_postgres
    from agent.tracing import create_traces_table
    from agent.lifecycle import start_session
    from agent.handlers.sigterm import register_interrupted_handler, mark_session_complete
    from agent.ui.header import print_startup_header
    from agent.ui.output import console, spinner, show_routing_result, show_completion_summary, make_stream_handler, PRIMARY, ERROR, METADATA

    project_root = find_project_root(Path.cwd())
    load_env(project_root)
    config = load_config(project_root)

    session = create_session()

    if args.worker:
        session.model_overrides["worker"] = args.worker

    conn = None
    tracing_enabled = (
        not args.no_trace
        and config.get("tracing", {}).get("enabled", True)
    )
    if tracing_enabled:
        conn = connect_postgres(config)
        if conn is not None:
            create_traces_table(conn)

    try:
        session_data = start_session(project_root, session, config)
    except SystemExit:
        raise

    register_interrupted_handler(
        project_root=project_root,
        session=session,
        conn=conn,
        repo=session_data["repo"],
    )

    print_startup_header(
        config=config,
        project_root=project_root,
        branch=session_data["branch"],
        agent_branch=session_data["agent_branch"],
    )

    # === REPL ===
    from agent.blocks.block1 import route_and_dispatch
    from agent.blocks.block2 import orchestrate
    from agent.blocks.block3 import execute_step
    from agent.commands.history import handle_history
    from agent.commands.model import handle_model
    from agent.commands.end import handle_end
    from agent.commands.init import handle_init

    while True:
        try:
            user_input = console.input(f"[bold {PRIMARY}]❯[/] ").strip()
        except KeyboardInterrupt:
            raise SystemExit(0)
        except EOFError:
            raise SystemExit(0)

        if not user_input:
            continue

        if user_input == "/history":
            handle_history(session, config)
            continue

        if user_input.startswith("/model"):
            parts = user_input.split(maxsplit=2)
            if len(parts) == 3:
                handle_model(session, parts[1], parts[2])
            else:
                console.print(f"[{ERROR}]Usage: /model <role> <model>[/]")
            continue

        if user_input == "/end":
            handle_end(
                session=session,
                config=config,
                project_root=project_root,
                conn=conn,
                repo=session_data["repo"],
            )
            mark_session_complete()
            break

        if user_input.startswith("/init"):
            force = "--force" in user_input
            handle_init(project_root, force=force)
            continue

        # --- Routing ---
        tokens_before = _session_total_tokens(session, config)
        cost_before = session.total_cost(config)

        with spinner("Routing..."):
            try:
                routing_result = route_and_dispatch(
                    user_request=user_input,
                    session=session,
                    config=config,
                    project_root=project_root,
                    context_contents=session_data["context_contents"],
                    diary_sections=session_data["diary_sections"],
                    conn=conn,
                )
            except SystemExit:
                raise
            except Exception as e:
                console.print(f"[{ERROR}]✗ Routing error: {e}[/]")
                continue

        show_routing_result(routing_result["routing"])

        approval_cb = _make_approval_callback(project_root, session, config)

        if routing_result["routing"] == "SIMPLE":
            execute_step(
                assembled_prompt=routing_result["assembled_prompt"],
                session=session,
                config=config,
                project_root=project_root,
                conn=conn,
                approval_callback=approval_cb,
                stream_handler=make_stream_handler(),
            )
            steps_completed = None

        else:
            step_results = orchestrate(
                user_request=routing_result["user_request"],
                file_list=routing_result["file_list"],
                context_contents=routing_result["context_contents"],
                diary_sections=routing_result["diary_sections"],
                session=session,
                config=config,
                project_root=project_root,
                conn=conn,
                approval_callback=approval_cb,
            )
            steps_completed = len(step_results)

        tokens_used = _session_total_tokens(session, config) - tokens_before
        cost_used = session.total_cost(config) - cost_before
        show_completion_summary(
            tokens=tokens_used,
            cost=cost_used,
            steps=steps_completed,
        )


def _session_total_tokens(session, config: dict) -> int:
    s = session.get_summary(config)
    return s.get("total_input_tokens", 0) + s.get("total_output_tokens", 0)


def _make_approval_callback(project_root, session, config):
    from agent.ui import output as _ui_output
    from agent.ui import prompts as _ui_prompts

    def callback(tier: str, tool_name: str, args: dict):
        if tier == "tier1":
            _ui_output.show_tier1_panel(tool_name, args)
            return "approved"

        if tool_name == "write_file":
            choice = _ui_prompts.prompt_write_file(
                args.get("path", ""),
                args.get("content", ""),
                project_root,
            )
        elif tool_name == "run_command":
            choice = _ui_prompts.prompt_run_command(args.get("cmd", ""))
        elif tool_name == "fetch_page":
            choice = _ui_prompts.prompt_fetch_page(args.get("url", ""))
        elif tool_name == "read_file":
            choice = _ui_prompts.prompt_read_file(args.get("path", ""))
        else:
            choice = "Allow"

        if choice == "Allow":
            return "approved"
        elif choice == "Skip step":
            return "skip"
        elif choice == "Deny — give feedback":
            feedback = _ui_prompts.prompt_correction_feedback()
            if feedback and feedback.strip():
                return {"result": "denied", "feedback": feedback.strip()}
            return "denied"
        else:
            return "denied"

    return callback
