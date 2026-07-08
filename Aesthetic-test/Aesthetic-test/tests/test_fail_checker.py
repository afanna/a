"""Tests for FAIL checker."""

from card_scorer.models import RuleResult, Severity
from card_scorer.engine.fail_checker import check_fail, get_fail_reasons


def _result(severity: Severity, passed: bool) -> RuleResult:
    return RuleResult(
        rule_id="test",
        rule_name="test",
        dimension="test",
        passed=passed,
        score_delta=0 if passed else -5,
        severity=severity,
        evidence={},
        explanation="test",
    )


class TestFailChecker:
    def test_no_fail(self):
        results = [_result(Severity.MINOR, False), _result(Severity.MAJOR, False)]
        assert check_fail(results) is False

    def test_fatal_pass_no_fail(self):
        results = [_result(Severity.FATAL, True)]
        assert check_fail(results) is False

    def test_fatal_fail_triggers(self):
        results = [_result(Severity.FATAL, False)]
        assert check_fail(results) is True

    def test_get_fail_reasons(self):
        results = [
            _result(Severity.FATAL, False),
            _result(Severity.MINOR, False),
            _result(Severity.FATAL, True),
        ]
        reasons = get_fail_reasons(results)
        assert len(reasons) == 1
        assert reasons[0].severity == Severity.FATAL
