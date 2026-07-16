# Investigation Workspace

The workspace is a dependency-free read-only HTTP surface over SQLite read
models. It never imports the experiment service, orchestrator, scheduler,
entropy source, or model provider.

It provides coordinated research context, evidence, provenance, typed
relationship graph, and journal views. Graph edges are persisted scientific
relations only; no relationship is inferred. Evidence payloads expose the
stored cohort/provenance/disclosure data rather than asserting conclusions.

Run with `dashboard.server.serve(Path("database/experiment.db"))`. The current
server intentionally has no editing, live execution, authentication, or
deployment behavior.
