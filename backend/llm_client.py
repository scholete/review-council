"""Multi-provider LLM client for the Review Council.

Sends requests to different providers (NeuralWatt, DeepSeek, etc.)
based on the model config. Each provider uses an OpenAI-compatible
chat completions endpoint.
"""

import httpx
from typing import Dict, Any, Optional, List
from .config import PROVIDER_CONFIGS


def _pick_provider(model_cfg: dict) -> tuple:
    """Return (api_key, base_url) for a model config dict like
    {"provider": "neuralwatt", "model": "glm-5.2-short-fast"}."""
    provider_name = model_cfg["provider"]
    cfg = PROVIDER_CONFIGS.get(provider_name)
    if cfg is None:
        raise ValueError(f"Unknown provider: {provider_name}")
    if not cfg["api_key"]:
        raise ValueError(
            f"API key for provider '{provider_name}' is not set. "
            f"Set the {provider_name.upper()}_API_KEY env var."
        )
    return cfg["api_key"], cfg["base_url"]


async def query_model(
    model_cfg: dict,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
) -> Optional[Dict[str, Any]]:
    """Query a single model via its provider.

    Args:
        model_cfg: ``{"provider": ..., "model": ...}``
        messages:  OpenAI-format message list.
        timeout:   Request timeout in seconds.

    Returns:
        ``{"content": ..., "reasoning_details": ...}`` or ``None`` on failure.
    """
    api_key, base_url = _pick_provider(model_cfg)
    model_name = model_cfg["model"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model_name,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            message = data["choices"][0]["message"]

            return {
                "content": message.get("content"),
                "reasoning_details": message.get("reasoning_details"),
            }

    except Exception as e:
        err_msg = str(e) or f"{type(e).__name__} (no message)"
        print(f"[llm_client] Error querying {model_name} @ {base_url}: {err_msg}")
        return None


async def query_models_parallel(
    model_cfgs: List[dict],
    messages: List[Dict[str, str]],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Query multiple models *from different providers* in parallel.

    Args:
        model_cfgs: List of ``{"provider": ..., "model": ...}`` dicts.
        messages:   Message list sent to every model.

    Returns:
        ``{model_name: response_or_None, ...}``
    """
    import asyncio

    # Each model gets a separate HTTP client session so they're
    # truly parallel even when pointing at different base URLs.
    async def _task_with_name(cfg: dict):
        resp = await query_model(cfg, messages)
        return cfg["model"], resp

    results = await asyncio.gather(
        *[_task_with_name(cfg) for cfg in model_cfgs]
    )
    return dict(results)
