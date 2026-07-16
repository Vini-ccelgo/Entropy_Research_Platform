"""Pure, seed-only entropy policy domain and registry."""
from __future__ import annotations
from hashlib import sha256
import json
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import Field
from typing import Protocol
from core.types import FrozenModel, EntropySample
from core.types import utc_now

class EntropyPolicySpecification(FrozenModel):
    id: UUID=Field(default_factory=uuid4); revision:int=Field(default=1,ge=1)
    algorithm: str="derive_model_seed"; algorithm_version:str="1"
    byte_start:int=Field(default=0,ge=0); byte_length:int=Field(default=8,ge=1,le=32)
    byte_order:str="big"; target_field:str="seed"
    created_by: UUID=Field(default_factory=uuid4); created_at: datetime=Field(default_factory=utc_now)
    def content_hash(self)->str:
        return sha256(json.dumps(self.model_dump(mode="json",exclude={"id","revision","created_at"}),sort_keys=True,separators=(",",":")).encode()).hexdigest()

class EntropyPolicyReference(FrozenModel):
    policy_id:UUID; revision:int=Field(ge=1); content_hash:str=Field(min_length=64,max_length=64)

class SeedPatch(FrozenModel):
    seed:int=Field(ge=0)

class EntropyApplication(FrozenModel):
    policy:EntropyPolicyReference; algorithm_version:str; configuration_hash:str
    entropy_value_hash:str; byte_start:int; byte_length:int; byte_order:str
    transformation:str; output_commitment:str; applied_request_field:str="seed"
    source_capabilities: dict[str,int|bool|str]=Field(default_factory=dict)

class EntropyPolicy:
    def apply(self,sample:EntropySample,spec:EntropyPolicySpecification)->tuple[SeedPatch,EntropyApplication]:
        if spec.algorithm!="derive_model_seed" or spec.target_field!="seed" or spec.byte_order not in {"big","little"}: raise ValueError("invalid derive_model_seed specification")
        end=spec.byte_start+spec.byte_length
        if len(sample.raw_bytes)<end: raise ValueError("insufficient entropy bytes for policy")
        selected=sample.raw_bytes[spec.byte_start:end]; seed=int.from_bytes(selected,spec.byte_order)
        patch=SeedPatch(seed=seed)
        application=EntropyApplication(policy=EntropyPolicyReference(policy_id=spec.id,revision=spec.revision,content_hash=spec.content_hash()),algorithm_version=spec.algorithm_version,configuration_hash=spec.content_hash(),entropy_value_hash=sample.value_hash,byte_start=spec.byte_start,byte_length=spec.byte_length,byte_order=spec.byte_order,transformation="unsigned_integer",output_commitment=sha256(str(seed).encode()).hexdigest())
        return patch,application

class EntropyPolicyRegistry:
    def __init__(self)->None: self._specs:dict[tuple[UUID,int],EntropyPolicySpecification]={}
    def register(self,spec:EntropyPolicySpecification)->EntropyPolicyReference:
        key=(spec.id,spec.revision)
        if key in self._specs: raise ValueError("policy revision already registered")
        self._specs[key]=spec
        return EntropyPolicyReference(policy_id=spec.id,revision=spec.revision,content_hash=spec.content_hash())
    def resolve(self,reference:EntropyPolicyReference)->tuple[EntropyPolicySpecification,EntropyPolicy]:
        spec=self._specs.get((reference.policy_id,reference.revision))
        if not spec or spec.content_hash()!=reference.content_hash: raise KeyError("pinned entropy policy cannot be resolved")
        if spec.algorithm!="derive_model_seed": raise ValueError("unsupported entropy policy")
        return spec,EntropyPolicy()

class EntropyPolicyRepository(Protocol):
    def register_entropy_policy(self,spec:EntropyPolicySpecification)->EntropyPolicyReference: ...
    def resolve_entropy_policy(self,ref:EntropyPolicyReference)->EntropyPolicySpecification: ...

class PersistentEntropyPolicyRegistry:
    """Durable policy resolution independent of the originating process."""
    def __init__(self,repository:EntropyPolicyRepository)->None: self._repository=repository
    def register(self,spec:EntropyPolicySpecification)->EntropyPolicyReference: return self._repository.register_entropy_policy(spec)
    def resolve(self,reference:EntropyPolicyReference)->tuple[EntropyPolicySpecification,EntropyPolicy]:
        spec=self._repository.resolve_entropy_policy(reference)
        if spec.algorithm!="derive_model_seed": raise ValueError("unsupported entropy policy")
        return spec,EntropyPolicy()
