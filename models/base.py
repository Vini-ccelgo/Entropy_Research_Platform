"""Language-model provider adapter contract."""

from __future__ import annotations

from core.interfaces import ModelProviderPort


class ModelProvider(ModelProviderPort):
    """Backward-compatible semantic alias for the application model port."""
