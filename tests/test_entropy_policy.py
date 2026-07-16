from hashlib import sha256
import pytest
from core.types import EntropySample
from entropy.policy import EntropyPolicy, EntropyPolicyRegistry, EntropyPolicySpecification
from entropy.policy import PersistentEntropyPolicyRegistry
from database.sqlite_repository import SqliteRepository

def test_seed_policy_is_pinned_and_deterministic():
    registry=EntropyPolicyRegistry(); spec=EntropyPolicySpecification(byte_start=1,byte_length=2,byte_order="big")
    reference=registry.register(spec); resolved,policy=registry.resolve(reference)
    raw=b"\x00\x01\x02"; sample=EntropySample(source="test",raw_bytes=raw,value_hash=sha256(raw).hexdigest())
    patch,application=policy.apply(sample,resolved)
    assert patch.seed==258 and application.applied_request_field=="seed"
    with pytest.raises(KeyError): registry.resolve(reference.model_copy(update={"content_hash":"0"*64}))

def test_seed_policy_rejects_insufficient_bytes():
    raw=b"\x01"; sample=EntropySample(source="test",raw_bytes=raw,value_hash=sha256(raw).hexdigest())
    with pytest.raises(ValueError): EntropyPolicy().apply(sample,EntropyPolicySpecification(byte_length=2))

def test_policy_persists_and_resolves_independently(tmp_path):
    spec=EntropyPolicySpecification(); reference=PersistentEntropyPolicyRegistry(SqliteRepository(tmp_path/"p.db")).register(spec)
    other=PersistentEntropyPolicyRegistry(SqliteRepository(tmp_path/"p.db"))
    assert other.resolve(reference)[0].content_hash()==reference.content_hash
