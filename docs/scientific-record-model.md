# Scientific Record Model

Milestone 0 establishes the auditable intellectual record of research. It does
not add experiment execution, analysis, dashboard, artifact storage, or model
providers.

## Admission criterion

A new domain concept is admitted only when omitting it would make a future
scientific question impossible or significantly harder to answer. Each proposed
concept must state the question it enables, the loss if omitted, and why an
existing record or typed relation cannot represent it.

## Immutable revisions

Research questions, journal entries, claims, and external references are
revisioned scientific records. A revision after the first pins an exact
predecessor reference: record type, UUID, revision, and content hash. The store
validates that the predecessor is the immediately previous revision and writes
an attributed `revises` relation.

Hypotheses follow the same rule using `HypothesisReference`. Their active
specification can contain predictions, success/failure/exclusion/stopping
criteria, and alternative explanations. Confidence is intentionally absent from
the hypothesis; it belongs to an attributed `BeliefAssessment`.

## Atomic commands

The repository exposes scientific mutations as atomic operations:

- register a research question, journal entry, claim, external reference, or
  hypothesis;
- register a hypothesis with its motivating record references;
- assert a typed, revision-pinned relation;
- record a belief assessment with its evidence basis.

Each operation writes its domain record and a corresponding append-only audit
event in one transaction. Ordinary callers cannot create a persisted scientific
record through the repository without its registration audit event.

## Relations and evidence

Relations are directed, typed, attributable, time-stamped, and point to exact
revisions. Supported relation types are `motivates`, `tests`, `supports`,
`contradicts`, `revises`, `supersedes`, `derived_from`, `uses`, and
`interprets`.

Relations are source-of-truth records with validation, not an untyped graph
database. A dashboard graph will later be a projection of these records.

## Audit boundary

The audit ledger records registration, relation assertion, and belief-assessment
events. It is append-only by interface and SQLite schema usage. Database-level
permissions/trigger hardening is deferred until the PostgreSQL deployment
adapter is introduced; local SQLite is an integrity-preserving development
adapter, not a tamper-proof archival system.
