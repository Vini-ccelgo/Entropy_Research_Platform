"""Legacy naming compatibility for the experiment repository port."""

from __future__ import annotations

from core.interfaces import ExperimentRepositoryPort


class BaseLogger(ExperimentRepositoryPort):
    """Deprecated alias: persistence is a repository, not a pipeline step."""
