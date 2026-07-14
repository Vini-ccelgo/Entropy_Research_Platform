"""Application service for append-only scientific-record workflows."""

from __future__ import annotations

from core.interfaces import ScientificRecordRepositoryPort
from core.science import (
    BeliefAssessment, Claim, ExternalReference,
    JournalEntry, ResearchQuestion, ScientificRecordReference, ScientificRelation,
)
from core.types import Hypothesis


class ResearchRecordService:
    """Records scientific reasoning and its audit events as one application workflow."""

    def __init__(self, records: ScientificRecordRepositoryPort) -> None:
        self._records = records

    def register_question(self, question: ResearchQuestion) -> ScientificRecordReference:
        return self._records.register_question(question)

    def register_journal_entry(self, entry: JournalEntry) -> ScientificRecordReference:
        return self._records.register_journal_entry(entry)

    def register_claim(self, claim: Claim) -> ScientificRecordReference:
        return self._records.register_claim(claim)

    def register_external_reference(self, reference: ExternalReference) -> ScientificRecordReference:
        return self._records.register_external_reference(reference)

    def register_hypothesis(
        self, hypothesis: Hypothesis, motivated_by: tuple[ScientificRecordReference, ...] = (),
    ) -> ScientificRecordReference:
        return self._records.register_hypothesis(hypothesis, motivated_by)

    def record_relation(self, relation: ScientificRelation) -> None:
        self._records.record_relation(relation)

    def record_belief_assessment(self, assessment: BeliefAssessment) -> None:
        self._records.record_belief_assessment(assessment)
