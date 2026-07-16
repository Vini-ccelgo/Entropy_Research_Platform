"""Entropy-source adapter contracts and common helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from hashlib import sha256

from core.interfaces import EntropyPort
from core.provenance import EntropySourceSnapshot, canonical_hash
from core.types import EntropyRequest, EntropySample


class EntropySource(EntropyPort, ABC):
    """Adapter base for sources of entropy; never decides how it is applied."""

    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    def read_bytes(self, count: int) -> bytes: ...

    def provenance_configuration(self) -> dict[str, object]:
        """Return all source settings required to interpret a sample."""
        return {}

    def capabilities(self) -> dict[str, int | bool | str]:
        return {"max_bytes_per_request": 1_048_576, "replayable": False}

    def provenance_snapshot(self) -> EntropySourceSnapshot:
        configuration = self.provenance_configuration()
        return EntropySourceSnapshot(
            source_type=f"{type(self).__module__}.{type(self).__qualname__}",
            source_name=self.source_name, configuration=configuration,
            configuration_hash=canonical_hash(configuration),
        )

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
