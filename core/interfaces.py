"""Ports owned by the core application, implemented by adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable
from uuid import UUID

from core.types import (
    EntropyRequest, EntropySample, Hypothesis,
    HypothesisReference, ModelRequest, ModelResponse, Observation,
    PromptTemplate, RenderedPrompt, TrialResult,
)
from core.science import (
    AuditEvent, BeliefAssessment, Claim, ExperimentRevision, ExternalReference, JournalEntry,
    ResearchQuestion, ScientificRecordReference, ScientificRelation,
)
from core.provenance import EntropySourceSnapshot, ModelSnapshot, TrialExecution
from core.control import ControlEvent, ExperimentRun, ExperimentRunState, TrialAttempt, TrialAttemptState


class EntropyPort(ABC):
    @abstractmethod
    def sample(self, request: EntropyRequest) -> EntropySample: ...

    @abstractmethod
    def provenance_snapshot(self) -> EntropySourceSnapshot: ...


class PromptRendererPort(ABC):
    @abstractmethod
    def render(self, template: PromptTemplate, variables: dict[str, str]) -> RenderedPrompt: ...


class ModelProviderPort(ABC):
    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse: ...

    @abstractmethod
    def capabilities(self) -> dict[str, object]: ...

    @abstractmethod
    def provenance_snapshot(self, model_identifier: str) -> ModelSnapshot: ...


class ExperimentRepositoryPort(ABC):
    @abstractmethod
    def record_observation(self, observation: Observation) -> None: ...

    @abstractmethod
    def trials_for_experiment(self, experiment: ScientificRecordReference) -> Iterable[TrialExecution]: ...


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
    def register_experiment_revision(self, experiment: ExperimentRevision) -> ScientificRecordReference: ...

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

class ControlRepositoryPort(ABC):
    @abstractmethod
    def create_run(self, run: ExperimentRun, event: ControlEvent) -> ExperimentRun: ...
    @abstractmethod
    def find_run_by_key(self, key: str) -> ExperimentRun | None: ...
    @abstractmethod
    def get_run(self, run_id: UUID) -> ExperimentRun: ...
    @abstractmethod
    def transition_run(self, run_id: UUID, state: ExperimentRunState, event: ControlEvent) -> ExperimentRun: ...
    @abstractmethod
    def create_attempt(self, attempt: TrialAttempt, event: ControlEvent) -> TrialAttempt: ...
    @abstractmethod
    def transition_attempt(self, attempt_id: UUID, state: TrialAttemptState, event: ControlEvent,
                           error_category=None, error_message: str | None=None) -> TrialAttempt: ...
    @abstractmethod
    def attempts_for_run(self, run_id: UUID) -> Iterable[TrialAttempt]: ...
    @abstractmethod
    def append_control_event(self, event: ControlEvent) -> None: ...
    @abstractmethod
    def finalize_attempt(self, execution: TrialExecution, state: TrialAttemptState,
                         event: ControlEvent, error_category=None, error_message: str | None = None) -> TrialAttempt: ...
