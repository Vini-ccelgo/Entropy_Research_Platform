"""Entropy-source adapter contracts and common helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from hashlib import sha256

from core.interfaces import EntropyPort
from core.types import EntropyRequest, EntropySample


class EntropySource(EntropyPort, ABC):
    """Adapter base for sources of entropy; never decides how it is applied."""

    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    def read_bytes(self, count: int) -> bytes: ...

    def sample(self, request: EntropyRequest) -> EntropySample:
        raw = self.read_bytes(request.bytes_required)
        if len(raw) != request.bytes_required:
            raise RuntimeError("entropy source returned an unexpected number of bytes")
        return EntropySample(
            source=self.source_name,
            raw_bytes=raw,
            value_hash=sha256(raw).hexdigest(),
            provenance={"purpose": request.purpose, "application_policy": request.application_policy},
        )
