# Evidence and Analysis Plane

The analysis plane consumes persisted terminal `TrialExecution` evidence and
creates immutable derived evidence. It never invokes orchestration, entropy, or
model adapters, mutates raw records, changes hypothesis state, or asserts
claims.

`AnalysisSpecification` pins analyzer identity/version/parameters. A
`CohortSnapshot` is an ordered execution set with filters, exclusions, and an
input hash. Every invocation creates a new `AnalysisRun` and terminal
`AnalysisResult`; reruns never overwrite prior results. Results carry metrics
and optional digest-addressed artifacts.

The implemented `baseline_descriptive` analyzer reports status/trial counts,
response lengths, latency, completion-token distributions, exact duplicates,
lexical term frequencies, missingness, units, and the explicit assumption that
executions may not be independent. It performs no significance testing or
scientific interpretation.

`CohortBuilder` creates ordered membership only from persisted execution objects
and records filters, explicit exclusions/reasons, ordering rule, evidence
snapshot hash, and membership hash. `LocalArtifactStore` writes JSON and
Markdown artifacts under digest-derived locators and rereads them to verify
SHA-256 before returning artifact metadata. A completed result is created only
after all requested artifact writes have succeeded.
