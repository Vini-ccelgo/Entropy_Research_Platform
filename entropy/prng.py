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
