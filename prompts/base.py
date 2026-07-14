"""Prompt rendering adapter."""

from __future__ import annotations

from string import Formatter

from core.interfaces import PromptRendererPort
from core.types import PromptTemplate, RenderedPrompt


class StrictPromptRenderer(PromptRendererPort):
    """Renders named replacement fields and rejects missing or unused variables."""

    def render(self, template: PromptTemplate, variables: dict[str, str]) -> RenderedPrompt:
        fields = {
            field_name for _, field_name, _, _ in Formatter().parse(template.template)
            if field_name is not None
        }
        missing = fields - variables.keys()
        unused = variables.keys() - fields
        if missing or unused:
            raise ValueError(f"prompt variables mismatch; missing={sorted(missing)}, unused={sorted(unused)}")
        return RenderedPrompt(
            template_id=template.id,
            template_version=template.version,
            text=template.template.format(**variables),
            variables=variables,
        )
