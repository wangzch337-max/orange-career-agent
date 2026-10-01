"""Deterministic observation checks. No prose similarity, repair, or model judge."""

import unicodedata
import math
from collections.abc import Mapping

from evaluation.models import (
    CheckResult, EvaluationFailure, EvaluationStatus, ForbiddenExpectation,
    GoldenScenario, ProvenanceExpectation, RelationExpectation, ReviewExpectation,
    UncertaintyExpectation,
)
from evaluation.taxonomy import severity_for


MISSING = object()


def normalize_label(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def lookup(observation: Mapping, path: str):
    value = observation
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return MISSING
        value = value[part]
    return value


def _normalized(value):
    if isinstance(value, str):
        return normalize_label(value)
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    return value


def _keys(value):
    if isinstance(value, Mapping):
        return set(value) | set().union(*(_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value), set())
    return set()


def _texts(value):
    if isinstance(value, str):
        return [normalize_label(value)]
    if isinstance(value, Mapping):
        return [text for item in value.values() for text in _texts(item)]
    if isinstance(value, list):
        return [text for item in value for text in _texts(item)]
    return []


def safe_observed(value):
    """Keep useful structural diagnostics without copying labels or source text."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    if isinstance(value, (list, dict, str)):
        return {"type": type(value).__name__, "count": len(value)}
    return {"type": type(value).__name__}


def evidence_valid(rows) -> bool:
    """Rows pin allowed evidence and, for Match, the exact union of signal owners."""
    if not isinstance(rows, list) or not rows:
        return False
    for row in rows:
        if not isinstance(row, Mapping):
            return False
        refs = row.get("refs", [])
        allowed = row.get("allowed", [])
        if (not refs and not row.get("allow_empty", False)) or not set(refs).issubset(allowed) or len(refs) != len(set(refs)):
            return False
        if "owned" in row and set(refs) != set(row["owned"]):
            return False
        if not row.get("signal_ids_valid", True):
            return False
    return True


def memory_valid(rows) -> bool:
    return isinstance(rows, list) and bool(rows) and all(
        isinstance(row, Mapping) and
        row.get("refs") and all(
            ref in row.get("active_same_subject", []) for ref in row["refs"]
        ) for row in rows
    )


def actions_valid(rows) -> bool:
    return isinstance(rows, list) and bool(rows) and all(
        isinstance(row, Mapping) and
        row.get("related_ids") and row.get("related_ids_valid")
        and row.get("target_owned") and row.get("recipe_valid")
        and row.get("expected_evidence_present") and row.get("rationale_present")
        for row in rows
    )


def evaluate_check(scenario_id: str, check, observation: Mapping) -> CheckResult:
    value = lookup(observation, check.path)
    review = False
    if isinstance(check, ReviewExpectation):
        review = value is True
        passed = value is False  # missing observation is still a contract failure
        expected = "no explicit presentation ambiguity"
    elif isinstance(check, ProvenanceExpectation):
        passed = {"evidence": evidence_valid, "memory": memory_valid,
                  "actions": actions_valid}[check.scope](value)
        expected = f"valid {check.scope} ownership and references"
    elif isinstance(check, UncertaintyExpectation):
        passed = isinstance(value, list) and all(isinstance(item, str) for item in value) and set(map(normalize_label, check.topics)).issubset(
            set(map(normalize_label, value))
        )
        expected = check.topics
    elif isinstance(check, RelationExpectation):
        rows = value if isinstance(value, list) and all(isinstance(row, Mapping) for row in value) else []
        selected = [row for row in rows if check.job_label is None or
                    normalize_label(check.job_label) in map(normalize_label, row.get("job_labels", []))]
        passed = any(row.get("relation") == check.relation.value for row in selected) and not any(
            row.get("relation") in {item.value for item in check.forbidden_substitutions}
            for row in selected
        )
        expected = {"relation": check.relation.value, "job_label": check.job_label}
    elif isinstance(check, ForbiddenExpectation):
        if check.mode == "keys":
            passed = value is not MISSING and value is not None and set(check.forbidden).isdisjoint(_keys(value))
        elif check.mode == "claim_fragments":
            passed = value is not MISSING and value is not None and not any(
                normalize_label(str(fragment)) in text for fragment in check.forbidden for text in _texts(value)
            )
        else:
            values = value if isinstance(value, list) else [value]
            passed = value is not MISSING and value is not None and not any(
                _normalized(item) in _normalized(values) for item in check.forbidden
            )
        expected = {"forbidden": check.forbidden, "mode": check.mode}
    else:
        expected = check.expected
        actual, wanted = _normalized(value), _normalized(check.expected)
        if check.operation == "equals":
            passed = value is not MISSING and actual == wanted
        elif check.operation == "contains":
            passed = isinstance(actual, list) and wanted in actual
        elif check.operation == "subset":
            passed = isinstance(actual, list) and isinstance(wanted, list) and all(item in actual for item in wanted)
        elif check.operation == "empty":
            passed = value in ([], {}, "")
        elif check.operation == "nonempty":
            passed = bool(value)
        else:
            passed = isinstance(value, (int, float)) and value >= check.expected
    finding = None
    if not passed:
        finding = EvaluationFailure(
            failure_id=f"{scenario_id}:{check.check_id}", taxonomy=check.taxonomy,
            scenario_id=scenario_id, check_id=check.check_id, summary=check.summary,
            expected=expected, observed=("explicit ambiguity" if review else safe_observed(value)),
            source_component=check.source_component, evidence_refs=check.evidence_refs,
            memory_refs=check.memory_refs, severity=severity_for(check.taxonomy),
        )
    return CheckResult(check_id=check.check_id, kind=check.kind, summary=check.summary,
                       passed=passed, review_triggered=review, failure=finding)


def derive_status(scenario: GoldenScenario, checks: list[CheckResult]) -> EvaluationStatus:
    if any(not check.passed and not check.review_triggered for check in checks):
        return EvaluationStatus.FAIL
    if any(check.review_triggered for check in checks):
        return EvaluationStatus.NEEDS_REVIEW
    if scenario.expected_status == EvaluationStatus.EXPECTED_UNCERTAINTY:
        return EvaluationStatus.EXPECTED_UNCERTAINTY
    return EvaluationStatus.PASS
