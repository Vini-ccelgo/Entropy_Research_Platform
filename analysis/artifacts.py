"""Digest-verified local artifact storage."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from analysis.domain import AnalysisArtifact
class LocalArtifactStore:
    def __init__(self,root:Path)->None: self.root=root
    def write(self,name:str,data:bytes,media_type:str,producer_id:str,producer_version:str)->AnalysisArtifact:
        self.root.mkdir(parents=True,exist_ok=True); digest=sha256(data).hexdigest(); path=self.root/f"{digest}-{name}"
        path.write_bytes(data)
        if sha256(path.read_bytes()).hexdigest()!=digest: path.unlink(missing_ok=True); raise IOError("artifact hash verification failed")
        return AnalysisArtifact(name=name,content_hash=digest,locator=str(path),media_type=media_type,byte_size=len(data),producer_id=producer_id,producer_version=producer_version)
