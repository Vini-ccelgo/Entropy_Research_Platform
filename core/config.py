"""Configuration loading and validation for immutable experiment plans."""

from __future__ import annotations

import json
from pathlib import Path

from core.types import ExperimentPlan


def load_experiment_plan(path: Path) -> ExperimentPlan:
    """Load a validated experiment plan from JSON.

    YAML support can be added as an input adapter without changing the domain.
    """
    return ExperimentPlan.model_validate(json.loads(path.read_text(encoding="utf-8")))
