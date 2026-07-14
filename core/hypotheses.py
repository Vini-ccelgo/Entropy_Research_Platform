"""Hypothesis registry implementations."""

from __future__ import annotations

from core.interfaces import HypothesisRegistryPort
from core.types import Hypothesis, HypothesisReference


class InMemoryHypothesisRegistry(HypothesisRegistryPort):
    """Deterministic registry useful for local workflows and tests."""

    def __init__(self) -> None:
        self._hypotheses: dict[tuple[str, int], Hypothesis] = {}

    def register(self, hypothesis: Hypothesis) -> HypothesisReference:
        key = (str(hypothesis.id), hypothesis.revision)
        if key in self._hypotheses:
            raise ValueError("hypothesis revision is already registered")
        self._hypotheses[key] = hypothesis
        return HypothesisReference(
            hypothesis_id=hypothesis.id,
            revision=hypothesis.revision,
            content_hash=hypothesis.content_hash(),
        )

    def resolve(self, reference: HypothesisReference) -> Hypothesis:
        key = (str(reference.hypothesis_id), reference.revision)
        hypothesis = self._hypotheses.get(key)
        if hypothesis is None or hypothesis.content_hash() != reference.content_hash:
            raise KeyError("hypothesis reference cannot be resolved")
        return hypothesis
