"""Experiment aggregate public types.

``ExperimentPlan`` is an in-memory construction DTO. ``ExperimentRevision``
is the sole registered, persisted experiment definition.
"""

from core.science import ExperimentRevision
from core.types import ExperimentPlan

Experiment = ExperimentRevision

__all__ = ["Experiment", "ExperimentPlan", "ExperimentRevision"]
