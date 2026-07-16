# Architecture

The platform separates immutable scientific meaning from operational execution.

```mermaid
flowchart LR
    K[Knowledge Plane
Questions · Hypotheses · Journal · Claims] --> E[Evidence Plane
ExperimentRevision · TrialExecution · Provenance]
    C[Control Plane
ExperimentRun · TrialAttempt · ControlEvent] -->|governs, never mutates| E
    C --> O[Trial Orchestrator]
    O --> EN[Entropy port]
    O --> PR[Prompt renderer port]
    O --> MP[Model provider port]
    E --> DB[(SQLite adapter)]
    C --> DB
```

`ExperimentPlan` is a construction DTO. Registration creates an immutable,
revisioned `ExperimentRevision`, which pins the hypothesis and trial protocol.
An `ExperimentRun` references that revision and owns operational state. Each
`TrialAttempt` records scheduling and retry lineage. Terminal attempts produce
one immutable `TrialExecution` in the same transaction as their final state
transition.

```mermaid
sequenceDiagram
    participant S as ExperimentService
    participant C as Control repository
    participant O as Orchestrator
    participant E as Evidence repository
    S->>C: create run and RunCreated event
    S->>C: create/schedule/running attempt events
    S->>O: execute pinned revision and attempt
    O-->>S: terminal TrialExecution
    S->>C: atomic finalize(attempt, execution, event)
    C->>E: persist execution and terminal attempt state
```

Scientific records and their audit events are revision-pinned. Control events
are a separate append-only operational history. The analysis, API, dashboard,
reporting, and provider-expansion packages are deferred placeholders and are
not active architecture.
