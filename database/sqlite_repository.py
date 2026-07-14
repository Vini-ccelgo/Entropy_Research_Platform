"""SQLite persistence adapter for plans, trial results, and observations."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from core.interfaces import ExperimentRepositoryPort, HypothesisRegistryPort, ScientificRecordRepositoryPort
from core.science import (
    AuditAction, AuditEvent, BeliefAssessment, Claim, ExternalReference, JournalEntry,
    ResearchQuestion, ScientificRecordReference, ScientificRecordType, ScientificRelation,
)
from core.types import ExperimentPlan, Hypothesis, HypothesisReference, Observation, TrialResult


class SqliteRepository(ExperimentRepositoryPort, HypothesisRegistryPort, ScientificRecordRepositoryPort):
    """Transactional local adapter; PostgreSQL can replace it without domain changes."""
    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    def close(self) -> None:
        self._connection.close()

    def register(self, hypothesis: Hypothesis) -> HypothesisReference:
        reference = self.register_hypothesis(hypothesis)
        return HypothesisReference(
            hypothesis_id=reference.record_id, revision=reference.revision,
            content_hash=reference.content_hash,
        )

    def resolve(self, reference: HypothesisReference) -> Hypothesis:
        row = self._connection.execute(
            "SELECT payload_json, content_hash FROM hypotheses WHERE id = ? AND revision = ?",
            (str(reference.hypothesis_id), reference.revision)).fetchone()
        if row is None or row["content_hash"] != reference.content_hash:
            raise KeyError("hypothesis reference cannot be resolved")
        return Hypothesis.model_validate_json(row["payload_json"])

    def create_experiment(self, plan: ExperimentPlan) -> None:
        self.resolve(plan.hypothesis)
        with self._connection:
            self._connection.execute("INSERT INTO experiments VALUES (?, ?, ?, ?, ?, ?)",
                (str(plan.id), plan.config_hash(), str(plan.hypothesis.hypothesis_id), plan.hypothesis.revision,
                 plan.model_dump_json(), plan.created_at.isoformat()))

    def record_trial(self, result: TrialResult) -> None:
        with self._connection:
            self._connection.execute("INSERT OR REPLACE INTO trials VALUES (?, ?, ?, ?, ?, ?)",
                (str(result.trial_id), str(result.experiment_id), result.status.value, result.model_dump_json(),
                 result.started_at.isoformat(), result.finished_at.isoformat() if result.finished_at else None))

    def record_observation(self, observation: Observation) -> None:
        with self._connection:
            self._connection.execute("INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
                (str(observation.id), str(observation.trial_id), str(observation.observer_id),
                 observation.model_dump_json(), observation.recorded_at.isoformat()))

    def trials_for_experiment(self, experiment_id: UUID) -> Iterable[TrialResult]:
        rows = self._connection.execute("SELECT result_json FROM trials WHERE experiment_id = ? ORDER BY started_at",
                                        (str(experiment_id),))
        return [TrialResult.model_validate_json(row["result_json"]) for row in rows]

    def _validate_hypothesis_lineage(self, hypothesis: Hypothesis) -> None:
        predecessor = hypothesis.predecessor
        if hypothesis.revision == 1:
            if predecessor is not None:
                raise ValueError("the first hypothesis revision cannot have a predecessor")
            return
        if predecessor is None or predecessor.hypothesis_id != hypothesis.id or predecessor.revision != hypothesis.revision - 1:
            raise ValueError("a hypothesis revision must pin its immediately preceding revision")
        self.resolve(predecessor)

    def _write_audit(self, event: AuditEvent) -> None:
        subject = event.subject
        self._connection.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(event.id), event.action.value, subject.record_type.value if subject else None,
             str(subject.record_id) if subject else None, subject.revision if subject else None,
             str(event.actor_id), event.occurred_at.isoformat(), event.model_dump_json()),
        )

    def _write_relation(self, relation: ScientificRelation) -> None:
        self._connection.execute(
            "INSERT INTO scientific_relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(relation.id), relation.source.record_type.value, str(relation.source.record_id),
             relation.source.revision, relation.relation_type.value, relation.target.record_type.value,
             str(relation.target.record_id), relation.target.revision, relation.model_dump_json()),
        )

    def _register_scientific_record(self, table: str, record: object) -> ScientificRecordReference:
        reference = record.reference()
        predecessor = record.predecessor
        if record.revision == 1:
            if predecessor is not None:
                raise ValueError("the first record revision cannot have a predecessor")
        else:
            if (predecessor is None or predecessor.record_type != reference.record_type
                    or predecessor.record_id != reference.record_id
                    or predecessor.revision != reference.revision - 1):
                raise ValueError("a revision must pin its immediately preceding record revision")
            self.resolve_scientific_record(predecessor)
        with self._connection:
            self._connection.execute(
                f"INSERT INTO {table} VALUES (?, ?, ?, ?)",
                (str(reference.record_id), reference.revision, reference.content_hash,
                 record.model_dump_json()),
            )
            if predecessor is not None:
                relation = ScientificRelation(
                    source=reference, relation_type="revises", target=predecessor,
                    rationale="Immutable revision lineage.", asserted_by=record.created_by,
                )
                self._write_relation(relation)
                self._write_audit(AuditEvent(
                    action=AuditAction.RELATION_RECORDED, subject=reference,
                    actor_id=record.created_by, details={"relation_id": str(relation.id)},
                ))
            self._write_audit(AuditEvent(
                action=AuditAction.REGISTERED, subject=reference, actor_id=record.created_by,
            ))
        return reference

    def register_question(self, question: ResearchQuestion) -> ScientificRecordReference:
        return self._register_scientific_record("research_questions", question)

    def register_journal_entry(self, entry: JournalEntry) -> ScientificRecordReference:
        return self._register_scientific_record("journal_entries", entry)

    def register_claim(self, claim: Claim) -> ScientificRecordReference:
        return self._register_scientific_record("claims", claim)

    def register_external_reference(self, reference: ExternalReference) -> ScientificRecordReference:
        return self._register_scientific_record("external_references", reference)

    def register_hypothesis(
        self, hypothesis: Hypothesis, motivated_by: tuple[ScientificRecordReference, ...] = (),
    ) -> ScientificRecordReference:
        self._validate_hypothesis_lineage(hypothesis)
        pinned = HypothesisReference(hypothesis_id=hypothesis.id, revision=hypothesis.revision,
                                     content_hash=hypothesis.content_hash())
        reference = ScientificRecordReference(record_type="hypothesis", record_id=pinned.hypothesis_id,
                                               revision=pinned.revision, content_hash=pinned.content_hash)
        for source in motivated_by:
            self.resolve_scientific_record(source)
        with self._connection:
            self._connection.execute("INSERT INTO hypotheses VALUES (?, ?, ?, ?)",
                (str(hypothesis.id), hypothesis.revision, pinned.content_hash, hypothesis.model_dump_json()))
            if hypothesis.predecessor is not None:
                prior = ScientificRecordReference(
                    record_type="hypothesis", record_id=hypothesis.predecessor.hypothesis_id,
                    revision=hypothesis.predecessor.revision, content_hash=hypothesis.predecessor.content_hash,
                )
                relation = ScientificRelation(
                    source=reference, relation_type="revises", target=prior,
                    rationale="Immutable revision lineage.", asserted_by=hypothesis.registered_by,
                )
                self._write_relation(relation)
                self._write_audit(AuditEvent(
                    action=AuditAction.RELATION_RECORDED, subject=reference,
                    actor_id=hypothesis.registered_by, details={"relation_id": str(relation.id)},
                ))
            for source in motivated_by:
                relation = ScientificRelation(
                    source=source, relation_type="motivates", target=reference,
                    rationale="Recorded as a design motivation at registration.",
                    asserted_by=hypothesis.registered_by,
                )
                self._write_relation(relation)
                self._write_audit(AuditEvent(
                    action=AuditAction.RELATION_RECORDED, subject=source,
                    actor_id=hypothesis.registered_by, details={"relation_id": str(relation.id)},
                ))
            self._write_audit(AuditEvent(
                action=AuditAction.REGISTERED, subject=reference, actor_id=hypothesis.registered_by,
            ))
        return reference

    def resolve_scientific_record(self, reference: ScientificRecordReference) -> object:
        if reference.record_type is ScientificRecordType.HYPOTHESIS:
            hypothesis = self.resolve(HypothesisReference(
                hypothesis_id=reference.record_id, revision=reference.revision,
                content_hash=reference.content_hash,
            ))
            return hypothesis
        table_and_model = {
            ScientificRecordType.RESEARCH_QUESTION: ("research_questions", ResearchQuestion),
            ScientificRecordType.JOURNAL_ENTRY: ("journal_entries", JournalEntry),
            ScientificRecordType.CLAIM: ("claims", Claim),
            ScientificRecordType.EXTERNAL_REFERENCE: ("external_references", ExternalReference),
        }
        pair = table_and_model.get(reference.record_type)
        if pair is None:
            raise KeyError(f"record type is not persisted by this repository: {reference.record_type}")
        table, model = pair
        row = self._connection.execute(
            f"SELECT payload_json, content_hash FROM {table} WHERE id = ? AND revision = ?",
            (str(reference.record_id), reference.revision),
        ).fetchone()
        if row is None or row["content_hash"] != reference.content_hash:
            raise KeyError("scientific record reference cannot be resolved")
        return model.model_validate_json(row["payload_json"])

    def record_relation(self, relation: ScientificRelation) -> None:
        self.resolve_scientific_record(relation.source)
        self.resolve_scientific_record(relation.target)
        with self._connection:
            self._write_relation(relation)
            self._write_audit(AuditEvent(
                action=AuditAction.RELATION_RECORDED, subject=relation.source,
                actor_id=relation.asserted_by, details={"relation_id": str(relation.id)},
            ))

    def record_belief_assessment(self, assessment: BeliefAssessment) -> None:
        self.resolve_scientific_record(assessment.hypothesis)
        for reference in assessment.basis:
            self.resolve_scientific_record(reference)
        with self._connection:
            self._connection.execute(
                "INSERT INTO belief_assessments VALUES (?, ?, ?, ?, ?, ?)",
                (str(assessment.id), str(assessment.hypothesis.record_id), assessment.hypothesis.revision,
                 str(assessment.observer_id), assessment.assessed_at.isoformat(), assessment.model_dump_json()),
            )
            self._write_audit(AuditEvent(
                action=AuditAction.BELIEF_ASSESSED, subject=assessment.hypothesis,
                actor_id=assessment.observer_id, details={"assessment_id": str(assessment.id)},
            ))

    def append_audit_event(self, event: AuditEvent) -> None:
        with self._connection:
            self._write_audit(event)
