"""Deterministic cohort construction from persisted execution evidence."""
from __future__ import annotations
from analysis.domain import CohortMember,CohortSnapshot,digest
class CohortBuilder:
    def build(self,executions,filters:dict[str,object]|None=None,exclude_failed:bool=False)->CohortSnapshot:
        filters=filters or {}; exclusions={}; included=[]
        for execution in sorted(executions,key=lambda x:str(x.id)):
            if exclude_failed and execution.status.value!="completed": exclusions[str(execution.id)]="non-completed execution"; continue
            included.append(execution)
        members=tuple(CohortMember(execution_id=x.id,inclusion_order=i) for i,x in enumerate(included))
        evidence_hash=digest([x.model_dump(mode="json") for x in included])
        return CohortSnapshot(members=members,filters=filters,exclusions=exclusions,evidence_snapshot_hash=evidence_hash)
