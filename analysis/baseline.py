"""Deterministic descriptive analysis; no interpretations are produced."""
from __future__ import annotations
from collections import Counter
from statistics import mean, pstdev
from core.provenance import TrialExecution

class BaselineAnalyzer:
    id="baseline_descriptive"; version="1"
    def analyze(self, executions:list[TrialExecution])->dict[str,object]:
        statuses=Counter(x.status.value for x in executions); responses=[x.response for x in executions if x.response]
        lengths=[len(x.text) for x in responses]; latencies=[x.latency_ms for x in responses]; tokens=[x.completion_tokens for x in responses if x.completion_tokens is not None]
        texts=[x.text for x in responses]; duplicates=sum(n-1 for n in Counter(texts).values() if n>1)
        def dist(values,unit): return {"n":len(values),"unit":unit,"mean":mean(values) if values else None,"std":pstdev(values) if len(values)>1 else 0 if values else None,"missing":len(executions)-len(values)}
        words=Counter(w.lower() for text in texts for w in text.split())
        conditions=Counter((x.provenance.entropy_source.source_name if x.provenance.entropy_source else "unavailable",str(x.entropy_application.policy.policy_id) if x.entropy_application else "unavailable") for x in executions)
        return {"counts":{"executions":len(executions),"status":dict(statuses),"duplicate_responses":duplicates},"response_length":dist(lengths,"characters"),"latency":dist(latencies,"milliseconds"),"completion_tokens":dist(tokens,"tokens"),"lexical":{"unique_terms":len(words),"top_terms":words.most_common(20)},"conditions":{"entropy_source_policy_counts":{f"{a}|{b}":n for (a,b),n in conditions.items()},"disclosure":"Conditions include source and policy; model, prompt, runtime, and software differences must be inspected from provenance."},"assumptions":["descriptive statistics only","executions may not be independent"]}
