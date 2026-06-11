from __future__ import annotations

import json as _json
import time
from typing import TYPE_CHECKING

from agent.llm import call_llm

if TYPE_CHECKING:
    from agent.session import Session

_ROLE_TO_BLOCK = {
    "router": "block1",
    "orchestrator": "block2",
    "worker": "block3",
}


def create_traces_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS traces (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            block TEXT,
            role TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            latency_ms INTEGER,
            cost REAL,
            input_payload JSONB,
            output_payload JSONB,
            error TEXT
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS traces_session_id_idx ON traces(session_id)"
    )
    conn.commit()


def traced_call_llm(
    role: str,
    messages: list,
    session: "Session",
    conn,
    config: dict,
    **kwargs,
) -> dict:
    block = kwargs.pop("block", _ROLE_TO_BLOCK.get(role, "unknown"))
    user_request = kwargs.pop("user_request", None)

    if conn is None:
        return call_llm(role, messages, config, **kwargs)
    model = config["models"][role]["model"]

    if role in session.model_overrides:
        model = session.model_overrides[role]

    t_start = time.monotonic()
    error = None
    result = None

    try:
        result = call_llm(role, messages, config, **kwargs)
    except Exception as e:
        error = str(e)
        raise
    finally:
        latency_ms = int((time.monotonic() - t_start) * 1000)

        input_tokens = result["input_tokens"] if result else 0
        output_tokens = result["output_tokens"] if result else 0

        cost_per_k_in = config["models"][role].get("cost_per_1k_input", 0.0)
        cost_per_k_out = config["models"][role].get("cost_per_1k_output", 0.0)
        cost = (input_tokens / 1000 * cost_per_k_in) + (output_tokens / 1000 * cost_per_k_out)

        input_payload = {
            "role": role,
            "message_count": len(messages),
            "user_request": user_request,
            "messages_summary": [
                {"role": m.get("role", ""), "content_len": len(str(m.get("content", "")))}
                for m in messages
            ],
        }
        output_payload = result if result else {"error": error}

        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO traces
                    (session_id, block, role, model, input_tokens, output_tokens,
                     latency_ms, cost, input_payload, output_payload, error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session.session_id,
                    block,
                    role,
                    model,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    cost,
                    _json.dumps(input_payload),
                    _json.dumps(output_payload),
                    error,
                ),
            )
            conn.commit()
        except Exception:
            pass

    return result


def _parse_json_col(val):
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    try:
        return _json.loads(val)
    except Exception:
        return {}


def get_session_trace_summary(session_id: str, conn) -> dict:
    if conn is None:
        return {}

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT block, role, model, input_tokens, output_tokens, latency_ms,
                   cost, output_payload, input_payload, timestamp, error
            FROM traces
            WHERE session_id = %s
            ORDER BY timestamp ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()
    except Exception:
        return {}

    if not rows:
        return {}

    user_requests: list = []
    plan_steps: list = []
    step_results: list = []
    errors: list = []

    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    total_calls = 0
    calls_by_role: dict = {}
    timestamps = []

    for row in rows:
        (block, role, model, input_tokens, output_tokens,
         latency_ms, cost, output_payload_raw, input_payload_raw,
         timestamp, error) = row

        input_tokens = input_tokens or 0
        output_tokens = output_tokens or 0
        cost = cost or 0.0

        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        total_cost += cost
        total_calls += 1

        role_key = role or "unknown"
        if role_key not in calls_by_role:
            calls_by_role[role_key] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
        calls_by_role[role_key]["calls"] += 1
        calls_by_role[role_key]["input_tokens"] += input_tokens
        calls_by_role[role_key]["output_tokens"] += output_tokens

        if timestamp:
            timestamps.append(timestamp)

        if error:
            errors.append(error)

        output_payload = _parse_json_col(output_payload_raw)
        input_payload = _parse_json_col(input_payload_raw)

        # user_requests — block1 router Call 1 rows with stored user_request
        if block == "block1" and role == "router":
            user_req = input_payload.get("user_request")
            if user_req:
                user_requests.append(user_req)

        # plan_steps — orchestrator rows with {"steps": [...]} content
        if role == "orchestrator":
            content = output_payload.get("content", "")
            if content:
                try:
                    parsed = _json.loads(content)
                    if isinstance(parsed, dict) and "steps" in parsed:
                        plan_steps.extend(parsed["steps"])
                except Exception:
                    pass

        # step_results — worker rows with a "status" key in output_payload
        if role == "worker" and "status" in output_payload:
            step_results.append(output_payload)

    session_duration_ms = 0
    if len(timestamps) >= 2:
        try:
            delta = timestamps[-1] - timestamps[0]
            session_duration_ms = int(delta.total_seconds() * 1000)
        except Exception:
            session_duration_ms = 0

    for key in ("router", "orchestrator", "worker"):
        if key not in calls_by_role:
            calls_by_role[key] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    return {
        "session_id": session_id,
        "user_requests": user_requests,
        "plan_steps": plan_steps,
        "step_results": step_results,
        "errors": errors,
        "token_metrics": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost": total_cost,
            "total_calls": total_calls,
            "calls_by_role": calls_by_role,
        },
        "session_duration_ms": session_duration_ms,
    }
