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
        def summary(items):
            responses = [item.response for item in items if item.response]
            return {"n": len(items), "missing_responses": len(items) - len(responses),
                    "response_length": dist([len(response.text) for response in responses], "characters"),
                    "completion_tokens": dist([response.completion_tokens for response in responses if response.completion_tokens is not None], "tokens"),
                    "latency": dist([response.latency_ms for response in responses], "milliseconds"),
                    "failures": sum(item.status.value == "failed" for item in items),
                    "duplicates": sum(n - 1 for n in Counter(response.text for response in responses).values() if n > 1)}
        grouped = {}
        for execution in executions:
            prompt = str(execution.prompt_revision_reference.prompt_id) if execution.prompt_revision_reference else "unavailable"
            group = execution.provenance.prompt.metadata.get("question_group", "unclassified") if execution.provenance.prompt else "unclassified"
            key = f"group={group}|condition={execution.condition_id or 'unavailable'}|prompt={prompt}"
            grouped.setdefault(key, []).append(execution)
        conversation = {}
        for execution in executions:
            if execution.conversation:
                key = f"condition={execution.condition_id}|turn={execution.conversation.turn_index}"
                conversation.setdefault(key, []).append(execution)
        return {"counts":{"executions":len(executions),"status":dict(statuses),"duplicate_responses":duplicates},"response_length":dist(lengths,"characters"),"latency":dist(latencies,"milliseconds"),"completion_tokens":dist(tokens,"tokens"),"lexical":{"unique_terms":len(words),"top_terms":words.most_common(20)},"conditions":{"entropy_source_policy_counts":{f"{a}|{b}":n for (a,b),n in conditions.items()},"by_prompt_and_condition":{key: summary(items) for key, items in grouped.items()},"conversation_by_condition_and_turn":{key: summary(items) for key, items in conversation.items()},"disclosure":"Conditions include source and policy; model, prompt, runtime, and software differences must be inspected from provenance. A deterministic entropy stream does not by itself make provider generation deterministic."},"assumptions":["descriptive statistics only","executions may not be independent","conversation turns from one trajectory are dependent observations","provider seed support must be interpreted according to each execution's recorded capability snapshot; LM Studio is best-effort"]}
