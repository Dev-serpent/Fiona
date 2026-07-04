"""Tests for the Validation Agents system (Phase 10: Validation Agents)."""

from __future__ import annotations

import pytest

from fiona.validators.base import ValidationFinding, ValidationResult, ValidatorAgent
from fiona.validators.code_review import CodeReviewValidator
from fiona.validators.security_review import SecurityReviewValidator
from fiona.validators.docs_review import DocsReviewValidator


# ======================================================================
# 1. Data types
# ======================================================================


class TestValidationFinding:
    def test_create(self):
        f = ValidationFinding(severity="error", message="Something broke")
        assert f.severity == "error"
        assert f.message == "Something broke"
        assert f.location is None
        assert f.rule == ""

    def test_create_full(self):
        f = ValidationFinding(
            severity="warning",
            message="Long function",
            location="file.py:42",
            rule="function_length",
            suggestion="Break it up",
        )
        assert f.location == "file.py:42"
        assert f.suggestion == "Break it up"


class TestValidationResult:
    def test_defaults(self):
        r = ValidationResult()
        assert r.passed
        assert r.findings == []
        assert r.score == 1.0
        assert r.error_count == 0
        assert r.warning_count == 0

    def test_error_count(self):
        r = ValidationResult(
            findings=[
                ValidationFinding(severity="error", message="e1"),
                ValidationFinding(severity="warning", message="w1"),
                ValidationFinding(severity="error", message="e2"),
            ]
        )
        assert r.error_count == 2
        assert r.warning_count == 1

    def test_passed_false_with_errors(self):
        r = ValidationResult(
            findings=[ValidationFinding(severity="error", message="e1")]
        )
        assert not r.passed

    def test_passed_true_with_warnings(self):
        r = ValidationResult(
            findings=[ValidationFinding(severity="warning", message="w1")]
        )
        assert r.passed


# ======================================================================
# 2. ValidatorAgent base class
# ======================================================================


class TestValidatorAgent:
    def test_abc_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ValidatorAgent()  # type: ignore[abstract]

    def test_score_from_findings(self):
        class TestValidator(ValidatorAgent):
            def manifest(self):
                from fiona.plugin_system import PluginManifest
                return PluginManifest(name="test", version="1.0.0", description="t")

            def get_agent_meta(self):
                from Agent.agent_meta import AgentMeta
                return AgentMeta(name="test", version="1.0.0", description="t")

            def validate(self, target, **kwargs):
                return ValidationResult()

        v = TestValidator()

        assert v.score_from_findings([]) == 1.0
        assert v.score_from_findings([ValidationFinding(severity="error", message="e")]) == 0.9
        assert v.score_from_findings([ValidationFinding(severity="warning", message="w")]) == 0.95
        assert v.score_from_findings([
            ValidationFinding(severity="error", message="e"),
            ValidationFinding(severity="error", message="e"),
        ]) == 0.8
        # Should not go below 0
        assert v.score_from_findings([
            ValidationFinding(severity="error", message="e") for _ in range(20)
        ]) == 0.0

    def test_format_result(self):
        class TestValidator(ValidatorAgent):
            def manifest(self):
                from fiona.plugin_system import PluginManifest
                return PluginManifest(name="test", version="1.0.0", description="t")

            def get_agent_meta(self):
                from Agent.agent_meta import AgentMeta
                return AgentMeta(name="my-validator", version="1.0.0", description="t")

            def validate(self, target, **kwargs):
                return ValidationResult()

        v = TestValidator()
        r = v.format_result(
            [ValidationFinding(severity="error", message="fail")],
            summary="Found issues",
        )
        assert not r.passed
        assert r.validator_name == "my-validator"
        assert r.summary == "Found issues"


# ======================================================================
# 3. CodeReviewValidator
# ======================================================================


class TestCodeReviewValidator:
    @pytest.fixture
    def validator(self):
        return CodeReviewValidator()

    def test_get_agent_meta(self, validator):
        meta = validator.get_agent_meta()
        assert meta.name == "code-review"
        assert "code" in meta.tags

    def test_manifest(self, validator):
        m = validator.manifest()
        assert m.name == "code-review-validator"

    def test_validate_clean_code(self, validator):
        code = """import os

def hello():
    return "world"
"""
        result = validator.validate(code)
        assert result.passed

    def test_validate_syntax_error(self, validator):
        code = "def broken("
        result = validator.validate(code)
        assert not result.passed
        assert result.error_count > 0

    def test_validate_bare_except(self, validator):
        code = """try:
    risky()
except:
    pass
"""
        result = validator.validate(code)
        assert not result.passed
        assert any(f.rule == "bare_except" for f in result.findings)

    def test_validate_long_function(self, validator):
        code = "def long():\n" + "    pass\n" * 60
        result = validator.validate(code)
        assert any(f.rule == "function_length" for f in result.findings)

    def test_validate_todo(self, validator):
        code = "# TODO: fix this later\ndef foo(): pass\n"
        result = validator.validate(code)
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert any("TODO" in f.message for f in warnings)

    def test_validate_fixme(self, validator):
        code = "# FIXME: broken\ndef foo(): pass\n"
        result = validator.validate(code)
        warnings = [f for f in result.findings if f.severity == "warning"]
        assert any("FIXME" in f.message for f in warnings)

    def test_validate_with_filename(self, validator):
        code = "def broken("
        result = validator.validate(code, filename="test.py")
        assert any("test.py" in (f.location or "") for f in result.findings)

    def test_validate_specific_rules(self, validator):
        code = """# TODO: fix
def foo():
    pass
"""
        # Only check "todos" rule
        result = validator.validate(code, rules=["todos"])
        assert any(f.rule == "todos" for f in result.findings)
        assert not any(f.rule == "function_length" for f in result.findings)


# ======================================================================
# 4. SecurityReviewValidator
# ======================================================================


class TestSecurityReviewValidator:
    @pytest.fixture
    def validator(self):
        return SecurityReviewValidator()

    def test_get_agent_meta(self, validator):
        meta = validator.get_agent_meta()
        assert meta.name == "security-review"
        assert "security" in meta.tags

    def test_validate_clean_code(self, validator):
        code = "x = 1\ny = x + 2\n"
        result = validator.validate(code)
        assert result.passed

    def test_hardcoded_password(self, validator):
        code = 'password = "supersecret123"'
        result = validator.validate(code)
        assert not result.passed
        assert any(f.rule == "secrets" for f in result.findings)

    def test_hardcoded_api_key(self, validator):
        code = 'API_KEY = "sk-abc123"'
        result = validator.validate(code)
        assert not result.passed

    def test_sql_injection_fstring(self, validator):
        code = 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'
        result = validator.validate(code)
        assert not result.passed
        assert any(f.rule == "sql_injection" for f in result.findings)

    def test_unsafe_eval(self, validator):
        code = 'result = eval(user_input)'
        result = validator.validate(code)
        assert not result.passed
        assert any(f.rule == "unsafe_eval" for f in result.findings)

    def test_unsafe_exec(self, validator):
        code = 'exec(code_string)'
        result = validator.validate(code)
        assert not result.passed

    def test_insecure_pickle(self, validator):
        code = 'data = pickle.loads(raw)'
        result = validator.validate(code)
        assert not result.passed

    def test_command_injection(self, validator):
        code = 'os.system("rm -rf /")'
        result = validator.validate(code)
        assert not result.passed
        assert any(f.rule == "command_injection" for f in result.findings)

    def test_specific_rules_only(self, validator):
        code = """
password = "secret"
result = eval("1+1")
"""
        result = validator.validate(code, rules=["secrets"])
        assert any(f.rule == "secrets" for f in result.findings)
        assert not any(f.rule == "unsafe_eval" for f in result.findings)


# ======================================================================
# 5. DocsReviewValidator
# ======================================================================


class TestDocsReviewValidator:
    @pytest.fixture
    def validator(self):
        return DocsReviewValidator()

    def test_get_agent_meta(self, validator):
        meta = validator.get_agent_meta()
        assert meta.name == "docs-review"
        assert "docs" in meta.tags

    def test_validate_clean_docs(self, validator):
        text = "# Title\n\nThis is documentation.\n\n## Section\n\nContent here.\n"
        result = validator.validate(text)
        assert result.passed

    def test_placeholder_todo(self, validator):
        text = "## Introduction\n\nTODO: write this section\n"
        result = validator.validate(text)
        assert any(f.rule == "placeholders" for f in result.findings)

    def test_placeholder_tbd(self, validator):
        text = "TBD: need to add details"
        result = validator.validate(text)
        assert result.passed  # warnings don't fail validation
        assert result.warning_count > 0
        assert any(f.rule == "placeholders" for f in result.findings)

    def test_long_lines(self, validator):
        text = "A" * 120 + "\n"
        result = validator.validate(text)
        assert any(f.rule == "long_lines" for f in result.findings)

    def test_empty_section(self, validator):
        text = "# Title\n\n## EmptySection\n\n## Next Section\nContent\n"
        result = validator.validate(text)
        assert any(f.rule == "empty_sections" for f in result.findings)

    def test_non_empty_section(self, validator):
        text = "# Title\n\n## Section\nContent here.\n"
        result = validator.validate(text)
        assert not any(f.rule == "empty_sections" for f in result.findings)

    def test_specific_rules(self, validator):
        text = "# Title\n\nTODO: write\n\n" + "A" * 120 + "\n"
        result = validator.validate(text, rules=["long_lines"])
        assert any(f.rule == "long_lines" for f in result.findings)
        assert not any(f.rule == "placeholders" for f in result.findings)
