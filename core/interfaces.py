"""Ports owned by the core application, implemented by adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable
from uuid import UUID

from core.types import (
    EntropyRequest, EntropySample, ExperimentPlan, Hypothesis,
    HypothesisReference, ModelRequest, ModelResponse, Observation,
    PromptTemplate, RenderedPrompt, TrialResult,
)
from core.science import (
    AuditEvent, BeliefAssessment, Claim, ExternalReference, JournalEntry,
    ResearchQuestion, ScientificRecordReference, ScientificRelation,
)


class EntropyPort(ABC):
    @abstractmethod
    def sample(self, request: EntropyRequest) -> EntropySample: ...


class PromptRendererPort(ABC):
    @abstractmethod
    def render(self, template: PromptTemplate, variables: dict[str, str]) -> RenderedPrompt: ...


class ModelProviderPort(ABC):
    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse: ...

    @abstractmethod
    def capabilities(self) -> dict[str, object]: ...


class ExperimentRepositoryPort(ABC):
    @abstractmethod
    def create_experiment(self, plan: ExperimentPlan) -> None: ...

    @abstractmethod
    def record_trial(self, result: TrialResult) -> None: ...

    @abstractmethod
    def record_observation(self, observation: Observation) -> None: ...

    @abstractmethod
    def trials_for_experiment(self, experiment_id: UUID) -> Iterable[TrialResult]: ...


class HypothesisRegistryPort(ABC):
    @abstractmethod
    def register(self, hypothesis: Hypothesis) -> HypothesisReference: ...

    @abstractmethod
    def resolve(self, reference: HypothesisReference) -> Hypothesis: ...


class ScientificRecordRepositoryPort(ABC):
    """Persistence port for revisioned reasoning records and their audit trail."""

    @abstractmethod
    def register_question(self, question: ResearchQuestion) -> ScientificRecordReference: ...

    @abstractmethod
    def register_journal_entry(self, entry: JournalEntry) -> ScientificRecordReference: ...

    @abstractmethod
    def register_claim(self, claim: Claim) -> ScientificRecordReference: ...

    @abstractmethod
    def register_external_reference(self, reference: ExternalReference) -> ScientificRecordReference: ...

    @abstractmethod
    def register_hypothesis(
        self, hypothesis: Hypothesis, motivated_by: tuple[ScientificRecordReference, ...] = (),
    ) -> ScientificRecordReference: ...

    @abstractmethod
    def resolve_scientific_record(self, reference: ScientificRecordReference) -> object: ...

    @abstractmethod
    def record_relation(self, relation: ScientificRelation) -> None: ...

    @abstractmethod
    def record_belief_assessment(self, assessment: BeliefAssessment) -> None: ...

    @abstractmethod
    def append_audit_event(self, event: AuditEvent) -> None: ...
