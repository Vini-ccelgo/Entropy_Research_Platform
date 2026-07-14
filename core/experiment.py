"""Experiment aggregate compatibility module.

The immutable :class:`ExperimentPlan` is the experiment definition; execution
is owned by the application-layer trial orchestrator.
"""

from core.types import ExperimentPlan

Experiment = ExperimentPlan

__all__ = ["Experiment", "ExperimentPlan"]
