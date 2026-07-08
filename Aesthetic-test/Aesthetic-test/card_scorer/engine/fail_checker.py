"""FAIL Checker.

Determines if a FAIL condition has been triggered.
If any rule with FATAL severity fails, the total score is capped at fail_cap.
"""

from __future__ import annotations

from card_scorer.models import RuleResult, Severity


def check_fail(results: list[RuleResult]) -> bool:
    """Return True if any FATAL rule triggered.

    A FATAL rule triggers FAIL when it did not pass.
    """
    return any(
        r.severity == Severity.FATAL and not r.passed
        for r in results
    )


def get_fail_reasons(results: list[RuleResult]) -> list[RuleResult]:
    """Return the list of FATAL results that triggered FAIL."""
    return [
        r for r in results
        if r.severity == Severity.FATAL and not r.passed
    ]
