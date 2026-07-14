from pathlib import Path
from uuid import uuid4

from core.research_service import ResearchRecordService
from core.science import (
    BeliefAssessment, Claim, ClaimKind, JournalEntry, JournalEntryType,
    RelationType, ResearchQuestion, ScientificRelation,
)
from core.types import (
    AlternativeExplanation, CriterionKind, EvaluationCriterion, Hypothesis,
    HypothesisReference, HypothesisSpecification, ObserverKind, Prediction,
)
from database.sqlite_repository import SqliteRepository


def test_scientific_reasoning_records_are_revision_pinned_and_audited(tmp_path: Path) -> None:
    repository = SqliteRepository(tmp_path / "scientific-record.db")
    researcher = uuid4()
    service = ResearchRecordService(repository)
    question = ResearchQuestion(created_by=researcher, question="Does source matter?", rationale="Control sampling.")
    question_ref = service.register_question(question)
    hypothesis = Hypothesis(
        title="Source produces a measurable difference", statement="Entropy source changes output metrics.",
        success_criteria="A preregistered analysis separates conditions.", registered_by=researcher,
        specification=HypothesisSpecification(
            predictions=(Prediction(statement="Condition metrics differ.", measurement="effect size"),),
            criteria=(EvaluationCriterion(kind=CriterionKind.SUCCESS, statement="interval excludes zero"),),
            alternatives=(AlternativeExplanation(statement="Provider drift", discrimination_plan="block by runtime"),),
        ),
    )
    hypothesis_ref = service.register_hypothesis(hypothesis, motivated_by=(question_ref,))
    entry = JournalEntry(created_by=researcher, entry_type=JournalEntryType.RATIONALE,
                         title="Why this comparison", body="Establish a controlled baseline.")
    entry_ref = service.register_journal_entry(entry)
    relation = ScientificRelation(source=entry_ref, relation_type=RelationType.MOTIVATES,
                                  target=hypothesis_ref, rationale="Records the design rationale.",
                                  asserted_by=researcher)
    service.record_relation(relation)
    claim = Claim(created_by=researcher, kind=ClaimKind.INTERPRETIVE,
                  statement="The initial result warrants follow-up.")
    claim_ref = service.register_claim(claim)
    revised_hypothesis = Hypothesis(
        id=hypothesis.id, revision=2,
        predecessor=HypothesisReference(hypothesis_id=hypothesis_ref.record_id,
                                        revision=hypothesis_ref.revision,
                                        content_hash=hypothesis_ref.content_hash),
        title=hypothesis.title, statement="The effect is expected only under a fixed runtime.",
        success_criteria=hypothesis.success_criteria, registered_by=researcher,
        specification=hypothesis.specification,
    )
    revised_ref = service.register_hypothesis(revised_hypothesis)
    assessment = BeliefAssessment(hypothesis=revised_ref, observer_id=researcher,
                                  observer_kind=ObserverKind.HUMAN, confidence=0.55,
                                  method="structured expert judgment", basis=(claim_ref,))
    service.record_belief_assessment(assessment)

    assert repository.resolve_scientific_record(question_ref) == question
    audit_count = repository._connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    assert audit_count == 9
    relation_row = repository._connection.execute("SELECT payload_json FROM scientific_relations").fetchone()
    assert str(hypothesis.id) in relation_row[0]
    assert repository.resolve_scientific_record(revised_ref) == revised_hypothesis
    repository.close()
