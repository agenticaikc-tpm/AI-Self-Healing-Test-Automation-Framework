"""
failure_analyzer.py
--------------------
Rule-based AI failure analyzer for the Self-Healing Test Automation Framework.

The `FailureAnalyzer` class inspects test exception messages, classifies them
into well-known failure categories, infers a probable root cause, and returns
an actionable healing recommendation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FailureRule:
    """A single pattern-based rule used to classify a failure."""
    category: str
    patterns: List[str]
    root_cause: str
    recommendation: str


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

RULES: List[FailureRule] = [
    FailureRule(
        category="Locator Not Found",
        patterns=[
            r"locator.*not found",
            r"no such element",
            r"element not found",
            r"unable to locate element",
            r"cannot find element",
        ],
        root_cause=(
            "The UI element selector (ID, XPath, CSS, etc.) no longer matches "
            "any element in the current DOM — the element may have been renamed, "
            "moved, or removed after a recent front-end change."
        ),
        recommendation=(
            "Update the failing locator to match the new DOM structure. "
            "Consider switching to a more stable selector strategy "
            "(e.g., data-testid attributes) to reduce future brittleness."
        ),
    ),
    FailureRule(
        category="Element Not Interactable",
        patterns=[
            r"element not interactable",
            r"element is not clickable",
            r"not clickable at point",
            r"element not visible",
            r"element not displayed",
        ],
        root_cause=(
            "The target element exists in the DOM but is currently hidden, "
            "covered by another element, or disabled — often caused by an "
            "animation, modal, or loading overlay that hasn't finished."
        ),
        recommendation=(
            "Add an explicit wait (e.g., WebDriverWait) for the element to become "
            "clickable or visible before interacting with it. "
            "Scroll the element into view if it is outside the viewport."
        ),
    ),
    FailureRule(
        category="Timeout / Slow Response",
        patterns=[
            r"timeout",
            r"timed out",
            r"time.?out",
            r"wait.*exceeded",
            r"took too long",
        ],
        root_cause=(
            "The operation did not complete within the allowed time window. "
            "Possible causes include network latency, a slow backend service, "
            "or a missing/incorrect wait condition."
        ),
        recommendation=(
            "Increase the explicit timeout threshold for this step, or investigate "
            "whether the target service or page has a genuine performance regression. "
            "Replace implicit sleeps with smart waits tied to element state."
        ),
    ),
    FailureRule(
        category="Assertion Error",
        patterns=[
            r"assertionerror",
            r"assert.*failed",
            r"expected.*but.*got",
            r"mismatch",
            r"not equal",
        ],
        root_cause=(
            "A test assertion evaluated to False — the actual value returned "
            "by the application did not match the expected value defined in the test."
        ),
        recommendation=(
            "Review the expected value in the assertion; the application behaviour "
            "may have legitimately changed (requiring a test update) or there may "
            "be a regression in the code under test."
        ),
    ),
    FailureRule(
        category="Network / API Error",
        patterns=[
            r"connection refused",
            r"connection reset",
            r"network.*error",
            r"http\s*\d{3}",
            r"status code [4-5]\d{2}",
            r"requests\.exceptions",
            r"ssl.*error",
        ],
        root_cause=(
            "A network call failed — the target server may be down, "
            "unreachable, or returning an unexpected HTTP error response."
        ),
        recommendation=(
            "Verify that the target environment (staging/prod) is up and accessible. "
            "Check service logs for 4xx/5xx errors and confirm that API contracts "
            "have not changed."
        ),
    ),
    FailureRule(
        category="Import / Module Error",
        patterns=[
            r"importerror",
            r"modulenotfounderror",
            r"cannot import name",
            r"no module named",
        ],
        root_cause=(
            "A Python module or name could not be found at import time. "
            "This usually means a missing dependency, a package that has not "
            "been installed, or a circular import."
        ),
        recommendation=(
            "Run `pip install -r requirements.txt` to ensure all dependencies are "
            "installed. Verify that the module name and package structure are correct."
        ),
    ),
    FailureRule(
        category="File / IO Error",
        patterns=[
            r"filenotfounderror",
            r"no such file or directory",
            r"permissionerror",
            r"ioerror",
            r"oserror",
        ],
        root_cause=(
            "A file or directory operation failed — the target path may not exist, "
            "the process may lack write permissions, or a required fixture file is missing."
        ),
        recommendation=(
            "Confirm that the required file paths exist and that the process has "
            "the appropriate read/write permissions. Use `os.makedirs(..., exist_ok=True)` "
            "to create missing directories before writing."
        ),
    ),
    FailureRule(
        category="Authentication / Session Error",
        patterns=[
            r"unauthorized",
            r"forbidden",
            r"401",
            r"403",
            r"session.*expired",
            r"login.*failed",
            r"invalid.*token",
            r"auth.*error",
        ],
        root_cause=(
            "The test session is not authenticated or the access token has expired. "
            "This can happen when test credentials change or when session cookies "
            "are not properly propagated between test steps."
        ),
        recommendation=(
            "Re-run the login/authentication step before this test, or extend the "
            "session token TTL. Ensure that test credentials in config are up to date."
        ),
    ),
]

# Fallback rule used when no specific rule matches
_FALLBACK_RULE = FailureRule(
    category="Unknown Error",
    patterns=[],
    root_cause=(
        "The failure could not be classified into a known category. "
        "Manual investigation of the full stack trace is required."
    ),
    recommendation=(
        "Review the full exception message and stack trace. "
        "Add a new rule to FailureAnalyzer if this failure type recurs."
    ),
)


# ---------------------------------------------------------------------------
# FailureAnalyzer
# ---------------------------------------------------------------------------

class FailureAnalyzer:
    """
    Classifies test failure messages and provides healing recommendations.

    Usage::

        analyzer = FailureAnalyzer()
        result = analyzer.analyze("Locator #submitBtn not found")
        print(result["category"])        # "Locator Not Found"
        print(result["root_cause"])      # detailed explanation
        print(result["recommendation"])  # actionable fix
    """

    def __init__(self, extra_rules: Optional[List[FailureRule]] = None) -> None:
        """
        Parameters
        ----------
        extra_rules:
            Optional additional :class:`FailureRule` instances to prepend to
            the built-in rule list (higher priority).
        """
        self._rules: List[FailureRule] = (extra_rules or []) + RULES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, error_message: str) -> dict:
        """
        Analyse *error_message* and return a classification dict.

        Parameters
        ----------
        error_message:
            The string representation of the exception raised during the test.

        Returns
        -------
        dict with keys:
            - ``category``       – short label for the failure type
            - ``root_cause``     – plain-English explanation of likely cause
            - ``recommendation`` – actionable healing suggestion
            - ``matched_pattern`` – the regex pattern that triggered the match
              (empty string if no rule matched)
        """
        normalised = error_message.lower()
        matched_rule, matched_pattern = self._match_rule(normalised)

        return {
            "category": matched_rule.category,
            "root_cause": matched_rule.root_cause,
            "recommendation": matched_rule.recommendation,
            "matched_pattern": matched_pattern,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _match_rule(self, normalised_message: str):
        """Return the first matching rule and the pattern that triggered it."""
        for rule in self._rules:
            for pattern in rule.patterns:
                if re.search(pattern, normalised_message):
                    return rule, pattern
        return _FALLBACK_RULE, ""
