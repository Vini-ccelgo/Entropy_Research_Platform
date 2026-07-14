"""Port for deterministic, versioned analysis adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from core.types import TrialResult


class BaseAnalyzer(ABC):
    """Analysis must declare its version and operate on persisted trial data."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def analyze(self, trials: Iterable[TrialResult]) -> dict[str, Any]: ...
