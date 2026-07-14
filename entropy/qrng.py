"""QRNG adapter boundary.

A provider-specific implementation must validate TLS, preserve provider metadata,
and declare any provider-side conditioning. It is intentionally not simulated.
"""

from __future__ import annotations

from typing import Callable

from entropy.base import EntropySource


class QrngEntropySource(EntropySource):
    def __init__(self, fetch_bytes: Callable[[int], bytes], provider: str) -> None:
        self._fetch_bytes = fetch_bytes
        self._provider = provider

    @property
    def source_name(self) -> str:
        return f"qrng:{self._provider}"

    def read_bytes(self, count: int) -> bytes:
        return self._fetch_bytes(count)
