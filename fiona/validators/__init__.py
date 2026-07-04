"""Validation Agents for Fiona.

Provides a suite of ``AgentPlugin`` subclasses that perform automated
validation across code, security, documentation, testing, and
architecture dimensions.

Each validator is a self-registering agent that can be used like any
other Fiona agent — routed by the Coordinator, composed via ForemanAgent,
or invoked directly.

Usage::

    from fiona.validators import CodeReviewValidator, SecurityReviewValidator

    # The validators register themselves when loaded via the plugin system
    # or can be instantiated directly:
    validator = CodeReviewValidator()
    result = validator.validate(source_code, rules=["style", "security"])
"""

from __future__ import annotations

from fiona.validators.base import ValidationResult, ValidatorAgent

__all__ = [
    "ValidationResult",
    "ValidatorAgent",
]
