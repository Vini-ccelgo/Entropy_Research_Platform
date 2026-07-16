"""Explicit composition root and adapter registry."""
from __future__ import annotations
from collections.abc import Callable
class AdapterRegistry:
    def __init__(self)->None: self._factories:dict[str,Callable[...,object]]={}
    def register(self,name:str,factory:Callable[...,object])->None:
        if name in self._factories: raise ValueError(f"adapter already registered: {name}")
        self._factories[name]=factory
    def create(self,name:str,**settings):
        try: return self._factories[name](**settings)
        except KeyError as exc: raise KeyError(f"unknown adapter: {name}") from exc

def build_experiment_service(*, records, control, scheduler, orchestrator, actor_id):
    """Explicit composition root; callers provide only configured adapters."""
    from core.experiment_service import ExperimentService
    return ExperimentService(records, control, scheduler, orchestrator, actor_id)
