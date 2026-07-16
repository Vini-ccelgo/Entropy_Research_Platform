from hashlib import sha256
from analysis.artifacts import LocalArtifactStore
from analysis.cohort import CohortBuilder

def test_artifact_hash_is_verified(tmp_path):
    artifact=LocalArtifactStore(tmp_path).write("x.json",b"{}","application/json","test","1")
    assert artifact.byte_size==2
    assert sha256((tmp_path/artifact.locator.split("/")[-1]).read_bytes()).hexdigest()==artifact.content_hash

def test_empty_cohort_hash_is_canonical():
    assert CohortBuilder().build([]).input_hash()==CohortBuilder().build([]).input_hash()
