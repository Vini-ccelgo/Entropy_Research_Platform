"""Resolution of registered source specifications into local adapters."""
from __future__ import annotations

from core.registries import EntropySourceReference, EntropySourceSpecification
from entropy.hardware import OperatingSystemEntropySource
from entropy.prng import PrngEntropySource


class EntropySourceRegistry:
    """Adapter factory.  It does not persist or reinterpret source records."""
    def __init__(self, repository) -> None:
        self._repository = repository
        self._cache = {}

    def resolve(self, reference: EntropySourceReference):
        spec = self._repository.resolve_entropy_source(reference)
        key = (spec.id, spec.revision, spec.content_hash())
        if key not in self._cache:
            if spec.implementation_identity == "entropy.prng.PrngEntropySource":
                self._cache[key] = PrngEntropySource(int(spec.configuration["seed"]))
            elif spec.implementation_identity == "entropy.hardware.OperatingSystemEntropySource":
                self._cache[key] = OperatingSystemEntropySource()
            else:
                raise ValueError(f"unsupported local entropy implementation: {spec.implementation_identity}")
        return spec, self._cache[key]
