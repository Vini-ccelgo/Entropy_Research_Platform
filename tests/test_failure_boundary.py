from pathlib import Path
from uuid import uuid4
import pytest
from core.provenance import ModelSnapshot, RuntimeSnapshot, SoftwareSnapshot
from core.science import ExperimentRevision
from core.types import *
from entropy.prng import PrngEntropySource
from entropy.policy import EntropyPolicyRegistry, EntropyPolicySpecification
from runner.orchestrator import TrialOrchestrator

class Model:
    def __init__(self, fail=False, snapshot_fail=False): self.fail,self.snapshot_fail=fail,snapshot_fail
    def provenance_snapshot(self, identifier):
        if self.snapshot_fail: raise RuntimeError("snapshot unavailable")
        return ModelSnapshot(provider="test",model_identifier=identifier,model_artifact_hash="a"*64,provider_configuration_hash="b"*64)
    def generate(self, request):
        if self.fail: raise RuntimeError("provider failed")
        return ModelResponse(text="ok",provider="test",model_identifier="x",latency_ms=1)
class Renderer:
    def __init__(self, fail=False): self.fail=fail
    def render(self,t,v):
        if self.fail: raise ValueError("render failed")
        return RenderedPrompt(template_id=t.id,template_version=t.version,text=t.template.format(**v),variables=v)
class BadEntropy(PrngEntropySource):
    def sample(self, request): raise RuntimeError("entropy failed")

@pytest.mark.parametrize("renderer,entropy,model,missing",[(Renderer(True),PrngEntropySource(1),Model(),"prompt"),(Renderer(),BadEntropy(1),Model(),"entropy_sample"),(Renderer(),PrngEntropySource(1),Model(True),None),(Renderer(),PrngEntropySource(1),Model(snapshot_fail=True),"model")])
def test_pre_and_provider_failures_produce_terminal_evidence(renderer,entropy,model,missing):
    policies=EntropyPolicyRegistry(); policy=policies.register(EntropyPolicySpecification())
    observer=Observer(display_name="o",kind=ObserverKind.HUMAN); hyp=HypothesisReference(hypothesis_id=uuid4(),revision=1,content_hash="a"*64)
    trial=TrialSpec(ordinal=1,prompt=PromptTemplate(id="p",version="1",category="c",goal="g",template="{x}"),prompt_variables={"x":"x"},model_provider="t",model_identifier="m",entropy=EntropyRequest(purpose="seed",application_policy=EntropyApplicationPolicy.DERIVE_MODEL_SEED),entropy_policy=policy)
    experiment=ExperimentRevision.from_plan(ExperimentPlan(name="e",hypothesis=hyp,observers=(observer,),trials=(trial,)),observer.id)
    runtime=RuntimeSnapshot(operating_system="x",operating_system_version="x",architecture="x",python_version="x",runtime_name="x",runtime_version="x")
    execution=TrialOrchestrator(entropy,renderer,model,None,runtime,SoftwareSnapshot(application_version="x",dependency_manifest_hash="b"*64),policies).execute(experiment,trial,uuid4(),uuid4(),1,"k")
    assert execution.status is TrialStatus.FAILED
    assert execution.finished_at is not None
    if missing: assert missing in execution.provenance.unavailable_components
