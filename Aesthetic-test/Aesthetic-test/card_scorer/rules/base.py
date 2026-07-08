"""Rule base class.

Every rule must subclass ``Rule`` and implement ``evaluate()``.
Output is always a ``RuleResult`` -- boolean-only outputs are forbidden.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from card_scorer.configs.loader import Config
from card_scorer.models import RuleResult, Severity, ScoringContext


class Rule(ABC):
    """Abstract base for all scoring rules.

    Attributes:
        rule_id: Unique identifier, e.g. "R1.1", "VC-3".
        rule_name: Human-readable name.
        dimension: Which scoring dimension this belongs to.
        severity: Default severity level.
        max_deduction: Maximum points this rule can deduct.
    """

    rule_id: str
    rule_name: str
    dimension: str
    severity: Severity
    max_deduction: float

    def __init__(self) -> None:
        self.cfg = Config.load()

    @abstractmethod
    def evaluate(self, ctx: ScoringContext) -> RuleResult:
        """Evaluate the rule against the scoring context.

        Must return a fully populated RuleResult with:
        - rule_id, rule_name, dimension, passed, score_delta,
          severity, evidence, explanation, suggestion
        """
        ...

    def _pass(self, evidence: dict | None = None) -> RuleResult:
        """Helper to build a passing RuleResult."""
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            dimension=self.dimension,
            passed=True,
            score_delta=0.0,
            severity=self.severity,
            evidence=evidence or {},
            explanation="Pass",
        )

    def _fail(
        self,
        deduction: float,
        evidence: dict,
        explanation: str,
        suggestion: str = "",
    ) -> RuleResult:
        """Helper to build a failing RuleResult (clamped to max_deduction)."""
        actual = min(abs(deduction), self.max_deduction)
        return RuleResult(
            rule_id=self.rule_id,
            rule_name=self.rule_name,
            dimension=self.dimension,
            passed=False,
            score_delta=-actual,
            severity=self.severity,
            evidence=evidence,
            explanation=explanation,
            suggestion=suggestion,
        )
