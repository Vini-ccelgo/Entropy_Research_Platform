"""Seeded pseudo-random entropy adapter for reproducible controls."""

from __future__ import annotations

import random

from entropy.base import EntropySource


class PrngEntropySource(EntropySource):
    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._random = random.Random(seed)

    @property
    def source_name(self) -> str:
        return "prng"

    def read_bytes(self, count: int) -> bytes:
        return self._random.randbytes(count)

    def provenance_configuration(self) -> dict[str, object]:
        return {"algorithm": "python.random.Random", "seed": self._seed}

    def capabilities(self) -> dict[str, int | bool | str]:
        return {"max_bytes_per_request": 1_048_576, "replayable": True}
