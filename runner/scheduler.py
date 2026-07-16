"""Scheduler port and deterministic in-process implementation."""
from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import Callable
class Scheduler(ABC):
    @property
    @abstractmethod
    def name(self)->str: ...
    @abstractmethod
    def submit(self, job: Callable[[], None])->None: ...
class InlineScheduler(Scheduler):
    @property
    def name(self)->str: return "inline"
    def submit(self,job:Callable[[],None])->None: job()
