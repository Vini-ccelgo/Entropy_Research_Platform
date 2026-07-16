"""Immutable derived-evidence records for deterministic analyses."""
from __future__ import annotations
import json
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid4
from pydantic import Field
from core.types import FrozenModel, utc_now

def digest(value:object)->str: return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
class AnalysisSpecification(FrozenModel):
    id:UUID=Field(default_factory=uuid4); revision:int=Field(default=1,ge=1)
    analyzer_id:str; analyzer_version:str; parameters:dict[str,object]=Field(default_factory=dict)
    created_by:UUID=Field(default_factory=uuid4); created_at:datetime=Field(default_factory=utc_now)
    def content_hash(self)->str: return digest(self.model_dump(mode="json",exclude={"id","revision","created_at"}))
class AnalysisSpecificationReference(FrozenModel):
    id:UUID; revision:int; content_hash:str
class CohortMember(FrozenModel):
    execution_id:UUID; inclusion_order:int=Field(ge=0)
class CohortSnapshot(FrozenModel):
    id:UUID=Field(default_factory=uuid4); members:tuple[CohortMember,...]; filters:dict[str,object]=Field(default_factory=dict)
    exclusions:dict[str,str]=Field(default_factory=dict); ordering_rule:str="execution_id_ascending"; evidence_snapshot_hash:str=""; created_at:datetime=Field(default_factory=utc_now)
    def input_hash(self)->str: return digest({"members":[m.model_dump(mode="json") for m in self.members],"filters":self.filters,"exclusions":self.exclusions})
class AnalysisArtifact(FrozenModel):
    name:str; content_hash:str; locator:str; media_type:str; byte_size:int=Field(ge=0); created_at:datetime=Field(default_factory=utc_now); producer_id:str; producer_version:str; retention_status:str="retained"
class AnalysisRun(FrozenModel):
    id:UUID=Field(default_factory=uuid4); specification:AnalysisSpecificationReference; cohort:CohortSnapshot
    software_hash:str; runtime_hash:str; started_at:datetime=Field(default_factory=utc_now); finished_at:datetime|None=None; status:str="running"
class AnalysisResult(FrozenModel):
    id:UUID=Field(default_factory=uuid4); run_id:UUID; specification:AnalysisSpecificationReference; cohort_hash:str
    status:str; metrics:dict[str,object]=Field(default_factory=dict); artifacts:tuple[AnalysisArtifact,...]=()
    error_category:str|None=None; error:str|None=None; finished_at:datetime=Field(default_factory=utc_now)
