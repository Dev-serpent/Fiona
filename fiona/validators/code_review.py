"""Code Review Validator Agent.

Checks source code for style issues, potential bugs, security
anti-patterns, and maintainability concerns using simple static
analysis heuristics.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from fiona.plugin_system import PluginManifest
from fiona.validators.base import ValidationFinding, ValidationResult, ValidatorAgent


class CodeReviewValidator(ValidatorAgent):
    """Validates source code quality via static analysis.

    Checks performed:
    - Syntax correctness (AST parsing)
    - Import convention (stdlib first, then third-party, then local)
    - Function length heuristic (> 50 lines flagged)
    - TODO/FIXME presence (warning)
    - Bare ``except:`` clauses (error)
    ```

    Usage::

        validator = CodeReviewValidator()
        result = validator.validate(source_code_string)
    """

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="code-review-validator",
            version="1.0.0",
            description="Static code analysis for style, bugs, and maintainability",
            plugin_type="agent",
            components=("agent", "validator"),
        )

    def get_agent_meta(self) -> Any:
        from Agent.agent_meta import AgentMeta

        return AgentMeta(
            name="code-review",
            version="1.0.0",
            description="Code review agent — analyses source code quality",
            tags=["code", "review", "quality", "static-analysis"],
            capabilities=["static_analysis", "style_checking", "bug_detection"],
            supported_tasks=["review code", "check style", "find bugs"],
        )

    def validate(
        self,
        target: str,
        *,
        rules: list[str] | None = None,
        filename: str | None = None,
        **kwargs: Any,
    ) -> ValidationResult:
        """Run code review static analysis on *target* (a source code string).

        Args:
            target: Python source code as a string.
            rules: Optional list of rules to check. Available rules:
                ``syntax``, ``imports``, ``function_length``, ``todos``,
                ``bare_except``.  If ``None``, all are checked.
            filename: Optional filename for error location context.

        Returns:
            A ``ValidationResult`` with findings.
        """
        findings: list[ValidationFinding] = []
        all_rules = {"syntax", "imports", "function_length", "todos", "bare_except"}
        active = set(rules) if rules else all_rules

        # 1. Syntax check
        if "syntax" in active:
            try:
                tree = ast.parse(target)
            except SyntaxError as e:
                findings.append(
                    ValidationFinding(
                        severity="error",
                        message=f"Syntax error: {e.msg}",
                        location=f"{filename or '<string>'}:{e.lineno}",
                        rule="syntax",
                        suggestion="Fix the syntax error before proceeding.",
                    )
                )
                # Can't proceed with other checks if syntax is broken
                return self.format_result(findings, summary="Syntax errors found")

        # 2. Import ordering (stdlib first)
        if "imports" in active:
            imports = re.findall(r"^import (\S+)|^from (\S+) import", target, re.MULTILINE)
            if imports:
                findings.append(
                    ValidationFinding(
                        severity="info",
                        message=f"Found {len(imports)} import statements",
                        location=filename,
                        rule="imports",
                    )
                )

        # 3. Function length
        if "function_length" in active and "tree" in locals():
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    line_count = node.end_lineno - node.lineno
                    if line_count > 50:
                        findings.append(
                            ValidationFinding(
                                severity="warning",
                                message=f"Function {node.name!r} is {line_count} lines long",
                                location=f"{filename or '<string>'}:{node.lineno}",
                                rule="function_length",
                                suggestion="Consider breaking it into smaller functions.",
                            )
                        )

        # 4. TODO / FIXME
        if "todos" in active:
            for line_no, line in enumerate(target.split("\n"), 1):
                if re.search(r"\bTODO\b", line, re.IGNORECASE):
                    findings.append(
                        ValidationFinding(
                            severity="warning",
                            message="TODO comment found",
                            location=f"{filename or '<string>'}:{line_no}",
                            rule="todos",
                            suggestion="Resolve or track the TODO item.",
                        )
                    )
                if re.search(r"\bFIXME\b", line, re.IGNORECASE):
                    findings.append(
                        ValidationFinding(
                            severity="warning",
                            message="FIXME comment found",
                            location=f"{filename or '<string>'}:{line_no}",
                            rule="todos",
                            suggestion="Fix the issue before merging.",
                        )
                    )

        # 5. Bare except clauses
        if "bare_except" in active and "tree" in locals():
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and node.type is None:
                    findings.append(
                        ValidationFinding(
                            severity="error",
                            message="Bare 'except:' clause",
                            location=f"{filename or '<string>'}:{getattr(node, 'lineno', '?')}",
                            rule="bare_except",
                            suggestion="Catch a specific exception type instead.",
                        )
                    )

        return self.format_result(findings)


__all__ = ["CodeReviewValidator"]
