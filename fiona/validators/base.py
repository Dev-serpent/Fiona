"""Base classes for the Fiona validation agent system."""

from __future__ import annotations

import time
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from fiona.agent_plugin import AgentPlugin


# ======================================================================
# 1. Validation result data type
# ======================================================================


@dataclass
class ValidationFinding:
    """A single issue found during validation.

    Attributes:
        severity: One of ``"error"``, ``"warning"``, ``"info"``.
        message: Human-readable description of the finding.
        location: Optional source location (file path, line number, etc.).
        rule: Name of the rule that triggered this finding.
        suggestion: Optional fix suggestion.
    """

    severity: str  # "error" | "warning" | "info"
    message: str
    location: str | None = None
    rule: str = ""
    suggestion: str | None = None


@dataclass
class ValidationResult:
    """The outcome of a validation run.

    Attributes:
        passed: Whether validation passed without errors.
        findings: List of issues found.
        score: A 0.0–1.0 quality score.
        summary: Short textual summary.
        duration_ms: Runtime in milliseconds.
        validator_name: Name of the validator that produced this result.
    """

    _passed: bool | None = None
    """Internal passed flag.  If ``None``, computed from findings."""
    findings: list[ValidationFinding] = field(default_factory=list)
    score: float = 1.0
    summary: str = ""
    duration_ms: float = 0.0
    validator_name: str = ""

    @property
    def passed(self) -> bool:
        """Whether validation passed (no errors)."""
        if self._passed is not None:
            return self._passed
        return self.error_count == 0

    @passed.setter
    def passed(self, value: bool) -> None:
        self._passed = value

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")


# ======================================================================
# 2. ValidatorAgent base class
# ======================================================================


class ValidatorAgent(AgentPlugin):
    """A FionaPlugin that performs a specific kind of validation.

    Subclasses must implement ``validate()`` and ``get_agent_meta()``.
    """

    @abstractmethod
    def validate(
        self,
        target: Any,
        *,
        rules: list[str] | None = None,
        **kwargs: Any,
    ) -> ValidationResult:
        """Run validation against *target*.

        Args:
            target: The subject of validation (source code string, file
                path, config dict, etc.).
            rules: Optional list of specific rules to check.  If ``None``,
                all applicable rules are checked.
            **kwargs: Additional validator-specific parameters.

        Returns:
            A ``ValidationResult`` with findings and score.
        """
        ...

    def score_from_findings(self, findings: list[ValidationFinding]) -> float:
        """Calculate a 0.0–1.0 quality score from a list of findings.

        Default: 1.0 minus 0.1 per error minus 0.05 per warning (min 0.0).
        """
        score = 1.0
        for f in findings:
            if f.severity == "error":
                score -= 0.1
            elif f.severity == "warning":
                score -= 0.05
        return max(0.0, score)

    def deactivate(self) -> None:
        """Default no-op cleanup.  Subclasses may override."""
        pass

    def format_result(
        self,
        findings: list[ValidationFinding],
        summary: str = "",
    ) -> ValidationResult:
        """Build a ``ValidationResult`` from findings.

        Args:
            findings: List of issues found.
            summary: Optional textual summary.

        Returns:
            A ``ValidationResult``.
        """
        errors = [f for f in findings if f.severity == "error"]
        result = ValidationResult(
            findings=findings,
            score=self.score_from_findings(findings),
            summary=summary or f"Found {len(findings)} issues",
            validator_name=self.get_agent_meta().name,
        )
        # passed is a computed property; we override via _passed
        if len(errors) > 0:
            object.__setattr__(result, "_passed", False)
        return result


__all__ = [
    "ValidationFinding",
    "ValidationResult",
    "ValidatorAgent",
]
