import json
import os

from openai import OpenAI


def call_llm(role: str, messages: list, config: dict, stream_handler=None, **kwargs) -> dict:
    model_cfg = config["models"][role]
    model = kwargs.pop("model", model_cfg["model"])  # allow override via kwargs
    provider = model_cfg["provider"]

    if provider == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set in the environment")
        client = OpenAI(base_url="https://api.deepseek.com", api_key=api_key)
    elif provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set in the environment")
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    else:
        raise RuntimeError(f"Unknown provider: {provider!r}")

    temperature = kwargs.pop("temperature", model_cfg.get("temperature", 0))

    if "max_tokens" not in kwargs:
        if role == "router":
            max_tokens = model_cfg.get("max_tokens_routing", 10)
        else:
            max_tokens = model_cfg.get("max_tokens", 4096)
    else:
        max_tokens = kwargs.pop("max_tokens")

    if stream_handler is not None:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )

        content_parts: list[str] = []
        finish_reason: str = "stop"
        input_tokens: int = 0
        output_tokens: int = 0
        tool_calls_raw: dict = {}  # index -> {id, name, arguments_parts}

        try:
            for chunk in stream:
                if chunk.usage:
                    input_tokens = chunk.usage.prompt_tokens or 0
                    output_tokens = chunk.usage.completion_tokens or 0

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                if delta.content:
                    content_parts.append(delta.content)
                    stream_handler(delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_raw:
                            tool_calls_raw[idx] = {
                                "id": tc_delta.id or "",
                                "name": (tc_delta.function.name or "") if tc_delta.function else "",
                                "arguments_parts": [],
                            }
                        else:
                            if tc_delta.id:
                                tool_calls_raw[idx]["id"] = tc_delta.id
                            if tc_delta.function and tc_delta.function.name:
                                tool_calls_raw[idx]["name"] = tc_delta.function.name

                        if tc_delta.function and tc_delta.function.arguments:
                            tool_calls_raw[idx]["arguments_parts"].append(tc_delta.function.arguments)

        except KeyboardInterrupt:
            finish_reason = "interrupted"

        content = "".join(content_parts)

        result: dict = {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "finish_reason": finish_reason,
            "tool_calls": None,
            "raw_assistant_message": None,
        }

        if finish_reason == "tool_calls" and tool_calls_raw:
            parsed_tool_calls = []
            raw_tool_calls_list = []
            for idx in sorted(tool_calls_raw.keys()):
                tc = tool_calls_raw[idx]
                arguments_str = "".join(tc["arguments_parts"])
                parsed_tool_calls.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "arguments": json.loads(arguments_str) if arguments_str else {},
                })
                raw_tool_calls_list.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": arguments_str,
                    },
                })
            result["tool_calls"] = parsed_tool_calls
            result["raw_assistant_message"] = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": raw_tool_calls_list,
            }

        return result

    # Non-streaming path — unchanged
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )

    choice = response.choices[0]
    usage = response.usage

    result = {
        "content": choice.message.content or "",
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
        "finish_reason": choice.finish_reason or "stop",
        "tool_calls": None,
        "raw_assistant_message": None,
    }

    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": json.loads(tc.function.arguments),
            }
            for tc in choice.message.tool_calls
        ]
        result["raw_assistant_message"] = {
            "role": "assistant",
            "content": choice.message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ],
        }

    return result
