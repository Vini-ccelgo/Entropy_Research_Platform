# Architecture

## Conceptual pipeline

The research workflow remains intentionally simple: **Experiment → Prompt →
Entropy → Model → Logger → Analysis → Dashboard**. It is a conceptual view,
not a dependency graph. The internal design keeps its components independently
testable and allows logging and analysis to operate across the workflow.

```mermaid
flowchart LR
    E[Experiment] --> P[Prompt] --> N[Entropy] --> M[Model]
    M --> L[Logger] --> A[Analysis] --> D[Dashboard]
```

## Ports-and-adapters implementation

```mermaid
flowchart LR
    C[CLI / scheduler / API] --> ES[Experiment service]
    ES --> TO[Trial orchestrator]
    TO --> HP[Hypothesis registry port]
    TO --> EP[Entropy port]
    TO --> PP[Prompt renderer port]
    TO --> MP[Model provider port]
    TO --> RP[Experiment repository port]
    EP --> EA[PRNG / OS entropy / QRNG adapters]
    MP --> MA[LM Studio / OpenAI / Ollama adapters]
    HP --> DB[(SQLite / PostgreSQL)]
    RP --> DB
    DB --> AN[Versioned analyzers]
    DB --> UI[Dashboard read model]
```

## Scientific record model

Before an experiment can be executed, its intellectual context is represented
by immutable, revision-pinned records. Each registration, relation, and belief
assessment produces an append-only audit event in the same transaction.

```mermaid
flowchart LR
    Q[Research Question revision] -->|motivates| H[Hypothesis revision]
    J[Journal Entry revision] -->|interprets| C[Claim revision]
    X[Experiment revision] -->|tests| H
    A[Analysis revision] -->|supports / contradicts| C
    C --> B[Belief Assessment]
    H --> B
    Q -. registration and lineage events .-> L[Audit Ledger]
    H -. registration and lineage events .-> L
    C -. registration and lineage events .-> L
    B -. assessment event .-> L
```

See [the scientific record model](scientific-record-model.md) for its scope and
admission criterion.

## Core class relationships

```mermaid
classDiagram
    class ExperimentPlan { +config_hash() str }
    class Hypothesis { +id UUID +revision int +content_hash() str }
    class HypothesisReference { +hypothesis_id UUID +revision int +content_hash str }
    class Observer { +id UUID +kind ObserverKind }
    class TrialSpec { +ordinal int +entropy EntropyRequest }
    class TrialOrchestrator { +execute(plan, trial) TrialResult }
    class EntropyPort { <<interface>> +sample(request) EntropySample }
    class PromptRendererPort { <<interface>> +render(template, variables) RenderedPrompt }
    class ModelProviderPort { <<interface>> +generate(request) ModelResponse }
    class ExperimentRepositoryPort { <<interface>> +record_trial(result) }
    class HypothesisRegistryPort { <<interface>> +register(hypothesis) HypothesisReference }
    ExperimentPlan --> HypothesisReference
    ExperimentPlan --> Observer
    ExperimentPlan --> TrialSpec
    TrialOrchestrator --> EntropyPort
    TrialOrchestrator --> PromptRendererPort
    TrialOrchestrator --> ModelProviderPort
    TrialOrchestrator --> ExperimentRepositoryPort
    HypothesisRegistryPort --> Hypothesis
```

## Trial execution sequence

```mermaid
sequenceDiagram
    participant S as Scheduler/CLI
    participant R as Repository
    participant O as Orchestrator
    participant E as Entropy source
    participant P as Prompt renderer
    participant M as Model provider
    S->>R: create immutable ExperimentPlan
    S->>O: execute(plan, trial)
    O->>E: sample(EntropyRequest)
    E-->>O: EntropySample + hash + provenance
    O->>P: render(template, variables)
    P-->>O: RenderedPrompt
    O->>M: generate(request with derived seed)
    M-->>O: ModelResponse + backend metadata
    O->>R: record completed or failed TrialResult
```

## Database model

```mermaid
erDiagram
    HYPOTHESES ||--o{ EXPERIMENTS : pinned_by
    EXPERIMENTS ||--o{ TRIALS : contains
    TRIALS ||--o{ OBSERVATIONS : receives
    HYPOTHESES {
        text id PK
        int revision PK
        text content_hash
        text payload_json
    }
    EXPERIMENTS {
        text id PK
        text config_hash
        text hypothesis_id
        int hypothesis_revision
        text plan_json
    }
    TRIALS {
        text trial_id PK
        text experiment_id FK
        text status
        text result_json
    }
    OBSERVATIONS {
        text id PK
        text trial_id FK
        text observer_id
        text payload_json
    }
```

`observers` are embedded in the immutable plan for provenance and linked from
their separate `Observation` records. A future observer directory may be added
as a repository concern without changing the trial domain.
