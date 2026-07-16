"""Operating-system entropy adapter (not a claim of specialised hardware RNG)."""

from __future__ import annotations

import os

from entropy.base import EntropySource


class OperatingSystemEntropySource(EntropySource):
    @property
    def source_name(self) -> str:
        return "os_entropy"

    def read_bytes(self, count: int) -> bytes:
        return os.urandom(count)

    def provenance_configuration(self) -> dict[str, object]:
        return {"api": "os.urandom", "replayable": False}
