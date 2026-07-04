"""Security Review Validator Agent.

Checks source code and configuration for common security issues:
hardcoded secrets, SQL injection, unsafe eval/exec, insecure
deserialisation, and command injection.
"""

from __future__ import annotations

import re
from typing import Any

from fiona.plugin_system import PluginManifest
from fiona.validators.base import ValidationFinding, ValidationResult, ValidatorAgent


# Patterns that indicate potential security issues
_HARDCODED_SECRET_PATTERNS = [
    (r"(?:password|passwd|pwd|secret|api[_-]?key|token)\s*=\s*['\"][^'\"]+['\"]", "Hardcoded credential"),
    (r"(?:password|passwd|pwd|secret|api[_-]?key|token)\s*:\s*['\"][^'\"]+['\"]", "Hardcoded credential (YAML/dict)"),
]

_SQL_INJECTION_PATTERNS = [
    (r'execute\(.*f["\']', "f-string in SQL query"),
    (r'execute\(.*\bf\'', "f-string in SQL execute"),
    (r'raw_sql|RawSQL', "Raw SQL usage"),
]

_UNSAFE_EVAL_PATTERNS = [
    (r'\beval\(', "Use of eval()"),
    (r'\bexec\(', "Use of exec()"),
    (r'pickle\.loads?\(', "Insecure deserialisation (pickle)"),
    (r'yaml\.load\(', "Insecure YAML load (use safe_load)"),
]

_COMMAND_INJECTION_PATTERNS = [
    (r'os\.system\(', "Shell command via os.system()"),
    (r'subprocess\.call\(.*shell=True', "Shell injection via subprocess"),
    (r'subprocess\.Popen\(.*shell=True', "Shell injection via subprocess.Popen"),
    (r'\bexec_\b', "Executing shell commands"),
]


class SecurityReviewValidator(ValidatorAgent):
    """Validates source code for security vulnerabilities.

    Checks:
    - Hardcoded secrets / credentials
    - SQL injection patterns
    - Unsafe eval/exec / deserialisation
    - Command injection risks
    """

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="security-review-validator",
            version="1.0.0",
            description="Static security analysis for common vulnerabilities",
            plugin_type="agent",
            components=("agent", "validator", "security"),
        )

    def get_agent_meta(self) -> Any:
        from Agent.agent_meta import AgentMeta

        return AgentMeta(
            name="security-review",
            version="1.0.0",
            description="Security review agent — finds vulnerabilities in code",
            tags=["security", "audit", "vulnerability", "code"],
            capabilities=["secret_detection", "injection_analysis", "code_audit"],
            supported_tasks=["audit security", "find vulnerabilities", "check secrets"],
        )

    def validate(
        self,
        target: str,
        *,
        rules: list[str] | None = None,
        filename: str | None = None,
        **kwargs: Any,
    ) -> ValidationResult:
        """Run security analysis on *target* (source code or config as a string).

        Args:
            target: Code or configuration text to analyse.
            rules: Rule categories to check: ``secrets``, ``sql_injection``,
                ``unsafe_eval``, ``command_injection``.  All are checked by default.
            filename: Optional filename for location context.

        Returns:
            A ``ValidationResult`` with security findings.
        """
        findings: list[ValidationFinding] = []
        all_rules = {"secrets", "sql_injection", "unsafe_eval", "command_injection"}
        active = set(rules) if rules else all_rules

        lines = target.split("\n")

        if "secrets" in active:
            for pattern, desc in _HARDCODED_SECRET_PATTERNS:
                for line_no, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append(
                            ValidationFinding(
                                severity="error",
                                message=desc,
                                location=f"{filename or '<string>'}:{line_no}",
                                rule="secrets",
                                suggestion="Use environment variables or a secrets manager.",
                            )
                        )
                        # One finding per type is usually enough
                        break

        if "sql_injection" in active:
            for pattern, desc in _SQL_INJECTION_PATTERNS:
                matches = re.finditer(pattern, target, re.IGNORECASE)
                for m in matches:
                    line_no = target[: m.start()].count("\n") + 1
                    findings.append(
                        ValidationFinding(
                            severity="error",
                            message=desc,
                            location=f"{filename or '<string>'}:{line_no}",
                            rule="sql_injection",
                            suggestion="Use parameterised queries instead.",
                        )
                    )

        if "unsafe_eval" in active:
            for pattern, desc in _UNSAFE_EVAL_PATTERNS:
                matches = re.finditer(pattern, target)
                for m in matches:
                    line_no = target[: m.start()].count("\n") + 1
                    findings.append(
                        ValidationFinding(
                            severity="error",
                            message=desc,
                            location=f"{filename or '<string>'}:{line_no}",
                            rule="unsafe_eval",
                            suggestion="Prefer safer alternatives (e.g. ast.literal_eval).",
                        )
                    )

        if "command_injection" in active:
            for pattern, desc in _COMMAND_INJECTION_PATTERNS:
                matches = re.finditer(pattern, target)
                for m in matches:
                    line_no = target[: m.start()].count("\n") + 1
                    findings.append(
                        ValidationFinding(
                            severity="error",
                            message=desc,
                            location=f"{filename or '<string>'}:{line_no}",
                            rule="command_injection",
                            suggestion="Use subprocess with argument lists, not shell strings.",
                        )
                    )

        return self.format_result(findings)


__all__ = ["SecurityReviewValidator"]
