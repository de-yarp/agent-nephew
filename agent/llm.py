import os

from openai import OpenAI


def call_llm(role: str, messages: list, config: dict, **kwargs) -> dict:
    model_cfg = config["models"][role]
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

    response = client.chat.completions.create(
        model=model_cfg["model"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )

    choice = response.choices[0]
    usage = response.usage

    return {
        "content": choice.message.content or "",
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
        "finish_reason": choice.finish_reason or "stop",
    }
