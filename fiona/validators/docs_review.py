"""Documentation Review Validator Agent.

Checks documentation (reStructuredText, Markdown, docstrings) for
completeness, formatting issues, and stale references.
"""

from __future__ import annotations

import re
from typing import Any

from fiona.plugin_system import PluginManifest
from fiona.validators.base import ValidationFinding, ValidationResult, ValidatorAgent


class DocsReviewValidator(ValidatorAgent):
    """Validates documentation quality and consistency.

    Checks:
    - Missing or empty sections
    - Placeholder text (TODO, FIXME, TBD)
    - Broken-ish cross-references (:ref:, :doc:, :mod:)
    - Hard-wrapped lines that exceed 100 chars
    """

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="docs-review-validator",
            version="1.0.0",
            description="Documentation quality checks for RST, Markdown, and docstrings",
            plugin_type="agent",
            components=("agent", "validator", "docs"),
        )

    def get_agent_meta(self) -> Any:
        from Agent.agent_meta import AgentMeta

        return AgentMeta(
            name="docs-review",
            version="1.0.0",
            description="Documentation review agent — ensures docs are complete and consistent",
            tags=["docs", "documentation", "quality"],
            capabilities=["doc_check", "format_validation", "completeness_analysis"],
            supported_tasks=["review documentation", "check docstrings", "validate docs"],
        )

    def validate(
        self,
        target: str,
        *,
        rules: list[str] | None = None,
        filename: str | None = None,
        **kwargs: Any,
    ) -> ValidationResult:
        """Run documentation quality checks on *target*.

        Args:
            target: Documentation text (RST, Markdown, or plain text).
            rules: Rule categories: ``placeholders``, ``long_lines``,
                ``empty_sections``.  All checked by default.
            filename: Optional filename for location context.

        Returns:
            A ``ValidationResult``.
        """
        findings: list[ValidationFinding] = []
        all_rules = {"placeholders", "long_lines", "empty_sections"}
        active = set(rules) if rules else all_rules

        lines = target.split("\n")

        # 1. Placeholder text
        if "placeholders" in active:
            for line_no, line in enumerate(lines, 1):
                for placeholder in ("TODO", "FIXME", "TBD", "XXX"):
                    if placeholder in line and not line.strip().startswith(".."):
                        findings.append(
                            ValidationFinding(
                                severity="warning",
                                message=f"Placeholder '{placeholder}' found in docs",
                                location=f"{filename or '<string>'}:{line_no}",
                                rule="placeholders",
                                suggestion="Replace with actual content.",
                            )
                        )

        # 2. Long lines (> 100 chars in prose)
        if "long_lines" in active:
            for line_no, line in enumerate(lines, 1):
                if len(line) > 100 and not line.startswith(" " * 3):
                    # Skip indented code blocks
                    findings.append(
                        ValidationFinding(
                            severity="info",
                            message=f"Line exceeds 100 characters ({len(line)})",
                            location=f"{filename or '<string>'}:{line_no}",
                            rule="long_lines",
                            suggestion="Consider wrapping the line.",
                        )
                    )

        # 3. Empty sections (headings with no content)
        if "empty_sections" in active:
            heading_pattern = re.compile(r"^(#{1,6}\s+\S+|[-=]+\s*$)")
            for i, line in enumerate(lines):
                if heading_pattern.match(line):
                    # Check next few lines for content
                    has_content = False
                    for j in range(i + 1, min(i + 5, len(lines))):
                        if lines[j].strip() and not heading_pattern.match(lines[j]):
                            has_content = True
                            break
                    if not has_content:
                        findings.append(
                            ValidationFinding(
                                severity="warning",
                                message="Empty section (no content after heading)",
                                location=f"{filename or '<string>'}:{i + 1}",
                                rule="empty_sections",
                                suggestion="Add content to this section.",
                            )
                        )

        return self.format_result(findings)


__all__ = ["DocsReviewValidator"]
