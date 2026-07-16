"""LM Studio OpenAI-compatible HTTP adapter."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Mapping

import httpx

from core.types import ModelRequest, ModelResponse
from core.provenance import ModelSnapshot, canonical_hash
from models.base import ModelProvider


class LmStudioProvider(ModelProvider):
    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1", timeout_s: float = 120.0,
                 model_artifact_hashes: Mapping[str, str] | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._model_artifact_hashes = dict(model_artifact_hashes or {})

    def capabilities(self) -> dict[str, object]:
        return {"api": "openai-compatible", "seed": "best-effort", "streaming": False}

    def provenance_snapshot(self, model_identifier: str) -> ModelSnapshot:
        artifact_hash = self._model_artifact_hashes.get(model_identifier)
        if artifact_hash is None:
            raise ValueError("LM Studio execution requires a configured model artifact SHA-256")
        configuration = {"base_url": self._base_url, "timeout_s": self._timeout_s,
                         "endpoint": "/chat/completions"}
        return ModelSnapshot(
            provider="lmstudio", model_identifier=model_identifier,
            model_artifact_hash=artifact_hash, provider_capabilities=self.capabilities(),
            provider_configuration=configuration, provider_configuration_hash=canonical_hash(configuration),
        )

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
