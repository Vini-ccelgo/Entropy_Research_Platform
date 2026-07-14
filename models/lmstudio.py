"""LM Studio OpenAI-compatible HTTP adapter."""

from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx

from core.types import ModelRequest, ModelResponse
from models.base import ModelProvider


class LmStudioProvider(ModelProvider):
    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1", timeout_s: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def capabilities(self) -> dict[str, object]:
        return {"api": "openai-compatible", "seed": "best-effort", "streaming": False}

    def generate(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": request.model_identifier,
            "messages": [{"role": "user", "content": request.prompt.text}],
            "temperature": request.temperature,
            "top_p": request.top_p,
        }
        for key in ("top_k", "repeat_penalty", "max_tokens", "seed"):
            value = getattr(request, key)
            if value is not None:
                payload[key] = value
        started = perf_counter()
        response = httpx.post(f"{self._base_url}/chat/completions", json=payload, timeout=self._timeout_s)
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ModelResponse(
            text=choice["message"]["content"], provider="lmstudio",
            model_identifier=data.get("model", request.model_identifier),
            latency_ms=(perf_counter() - started) * 1000,
            prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
            stop_reason=choice.get("finish_reason"), backend_metadata={"capabilities": self.capabilities()},
        )
