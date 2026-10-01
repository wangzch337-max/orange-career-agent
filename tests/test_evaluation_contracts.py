"""Evaluation semantics, corrupted-observation detection and closed schemas."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from evaluation.checks import derive_status, evaluate_check, normalize_label
from evaluation.models import (
    EvaluationStatus as S, EvaluationLayer, Capability, GoldenScenario, EvaluationFailure,
    RequiredExpectation, ForbiddenExpectation, UncertaintyExpectation, ProvenanceExpectation,
    RelationExpectation, ReviewExpectation, LifecycleExpectation, WorkflowExpectation,
)
from evaluation.registry import ScenarioRegistry
from evaluation.scenarios.catalogue import required, forbidden, provenance, uncertainty, relation
from evaluation.taxonomy import FailureTaxonomy as T, EvaluationSeverity as V, BLOCKING_CATEGORIES, severity_for
from data.models import MatchRelationType as R


@pytest.mark.parametrize("category", list(T))
def test_taxonomy_closed_and_failure_severity_cannot_be_downgraded(category):
    failure = EvaluationFailure(failure_id="SD_001:check", scenario_id="SD_001", check_id="check",
        taxonomy=category, summary="synthetic violation", expected=True, observed=False,
        source_component="synthetic", severity=severity_for(category))
    assert failure.taxonomy == category
    if category in BLOCKING_CATEGORIES:
        assert failure.severity == V.BLOCKING
        with pytest.raises(ValidationError):
            EvaluationFailure.model_validate({**failure.model_dump(), "severity": "MINOR"})


@pytest.mark.parametrize("enum", [S, T, V, EvaluationLayer, Capability])
def test_enums_are_closed(enum):
    with pytest.raises(ValueError):
        enum("invented_value")


@pytest.mark.parametrize("operation,value,expected,passes", [
    ("equals", " ＰＹＴＨＯＮ  ", "python", True),
    ("equals", False, False, True), ("equals", None, True, False), ("equals", None, None, True),
    ("contains", ["API Integration"], "api integration", True),
    ("contains", [], "api integration", False),
    ("subset", ["Python", "SQL"], ["python"], True),
    ("subset", ["Python"], ["SQL"], False),
    ("empty", [], True, True), ("empty", ["SQL"], True, False),
    ("nonempty", ["skill_001"], True, True), ("nonempty", [], True, False),
    ("gte", 3, 2, True), ("gte", 1, 2, False),
])
def test_required_operations_not_exact_sentence_matching(operation, value, expected, passes):
    check = required("structural_rule", "nested.value", expected, operation=operation)
    result = evaluate_check("SD_001", check, {"nested": {"value": value}})
    assert result.passed == passes
    assert bool(result.failure) == (not passes)


def test_label_normalization_is_only_unicode_case_and_whitespace():
    assert normalize_label(" ＡＰＩ   Integration ") == "api integration"
    assert normalize_label("Machine learning") != normalize_label("AI development")


def test_absent_field_cannot_pass_required_null_or_forbidden_rules():
    assert not evaluate_check("SD_001", required("required_null", "absent", None), {}).passed
    assert not evaluate_check("MI_001", forbidden("must_observe_output", "absent", ["score"], T.MATCH_SCORE_INTRODUCED, "keys"), {}).passed


@pytest.mark.parametrize("mode,value,banned", [
    ("values", ["PyTorch"], ["pytorch"]),
    ("keys", {"nested": [{"overall_score": 90}]}, ["overall_score"]),
    ("keys", {"role_ranking": ["first"]}, ["role_ranking"]),
    ("claim_fragments", [{"description": "DO NOT PURSUE this role"}], ["do not pursue"]),
])
def test_forbidden_claims_and_recursive_fields_detect_corruption(mode, value, banned):
    check = forbidden("forbidden_contract", "value", banned, T.EVIDENCE_OVERCLAIM, mode)
    assert not evaluate_check("MI_001", check, {"value": value}).passed
    assert evaluate_check("MI_001", check, {"value": []}).passed


@pytest.mark.parametrize("bad", [[], ["training"], [123], None])
def test_unknown_collapse_fails_not_expected_uncertainty(bad):
    scenario = ScenarioRegistry().select(scenario_ids=["SD_002"])[0]
    check = uncertainty("topics", ["PyTorch"])
    result = evaluate_check(scenario.scenario_id, check, {"topics": bad})
    assert derive_status(scenario, [result]) == S.FAIL


def test_correct_unknown_is_success_not_deficit():
    scenario = ScenarioRegistry().select(scenario_ids=["SD_002"])[0]
    result = evaluate_check(scenario.scenario_id, uncertainty("topics", ["PyTorch"]), {"topics": ["pytorch"]})
    assert derive_status(scenario, [result]) == S.EXPECTED_UNCERTAINTY
    assert result.failure is None


@pytest.mark.parametrize("row", [
    {"refs": ["unknown"], "allowed": ["ev_001"]},
    {"refs": ["ev_001"], "allowed": ["ev_001"], "owned": ["ev_002"]},
    {"refs": ["ev_001", "ev_001"], "allowed": ["ev_001"]},
    {"refs": ["ev_001"], "allowed": ["ev_001"], "signal_ids_valid": False},
    {}, "corrupted_row",
])
def test_evaluator_detects_invalid_and_unrelated_evidence_without_production_acceptance(row):
    result = evaluate_check("MI_001", provenance("links"), {"links": [row]})
    assert not result.passed and result.failure.taxonomy == T.PROVENANCE_MISSING


def test_uncertainty_signal_only_provenance_is_allowed_explicitly():
    row = dict(refs=[], allowed=[], owned=[], allow_empty=True, signal_ids_valid=True)
    assert evaluate_check("MI_006", provenance("links"), {"links": [row]}).passed
    row.pop("allow_empty")
    assert not evaluate_check("MI_006", provenance("links"), {"links": [row]}).passed


@pytest.mark.parametrize("active", [[], ["other_subject_memory"], ["superseded_id"], ["candidate_id"]])
def test_memory_provenance_rejects_nonactive_or_other_subject_reference(active):
    check = provenance("links", "memory")
    assert not evaluate_check("MEM_004", check, {"links": [dict(refs=["active_id"], active_same_subject=active)]}).passed


@pytest.mark.parametrize("field", ["related_ids", "related_ids_valid", "target_owned", "recipe_valid",
                                  "expected_evidence_present", "rationale_present"])
def test_action_provenance_requires_why_target_and_deterministic_recipe(field):
    row = dict(related_ids=["insight_001"], related_ids_valid=True, target_owned=True,
               recipe_valid=True, expected_evidence_present=True, rationale_present=True)
    assert evaluate_check("ACT_001", provenance("rows", "actions"), {"rows": [row]}).passed
    row[field] = [] if field == "related_ids" else False
    assert not evaluate_check("ACT_001", provenance("rows", "actions"), {"rows": [row]}).passed


@pytest.mark.parametrize("relation_type", [R.CONFIRMED_GAP, R.EXPERIENCE_DEPTH_GAP, R.STRONG_ALIGNMENT])
def test_missing_sql_cannot_be_substituted_with_gap_or_capability(relation_type):
    check = relation(R.EVIDENCE_MISSING, "SQL", [R.CONFIRMED_GAP, R.EXPERIENCE_DEPTH_GAP])
    assert not evaluate_check("MI_002", check, {"relations": [dict(relation=relation_type.value, job_labels=["SQL"])]}).passed


@pytest.mark.parametrize("family,taxonomy", [(LifecycleExpectation, T.LIFECYCLE_BYPASS),
                                             (WorkflowExpectation, T.WORKFLOW_GATE_BYPASS)])
def test_explicit_lifecycle_and_workflow_failures_are_blocking(family, taxonomy):
    check = required("explicit_gate", "gate", family=family, taxonomy=taxonomy)
    result = evaluate_check("E2E_003", check, {"gate": False})
    assert result.failure.severity == V.BLOCKING


def test_review_only_for_explicit_noncontract_ambiguity_and_never_masks_failure():
    scenario = ScenarioRegistry().all()[0]
    review = ReviewExpectation(check_id="presentation_review", path="ambiguous", summary="synthetic ambiguity",
                               source_component="report")
    result = evaluate_check(scenario.scenario_id, review, {"ambiguous": True})
    assert derive_status(scenario, [result]) == S.NEEDS_REVIEW
    blocking = evaluate_check(scenario.scenario_id,
        required("confirm_gate", "confirmed", taxonomy=T.PROFILE_CONFIRMATION_BYPASS), {"confirmed": False})
    assert derive_status(scenario, [result, blocking]) == S.FAIL
    with pytest.raises(ValidationError):
        ReviewExpectation.model_validate({**review.model_dump(), "taxonomy": T.AUTHORITY_VIOLATION})


def test_missing_review_observation_is_failure_not_ambiguity():
    review = ReviewExpectation(check_id="presentation_review", path="ambiguous", summary="synthetic ambiguity", source_component="report")
    result = evaluate_check("SD_001", review, {})
    assert not result.passed and not result.review_triggered


@pytest.mark.parametrize("mutation", [
    {"scenario_id": "../../private"}, {"checks": []}, {"expected_failures_allowed": [T.SUBJECT_LEAKAGE]},
    {"expected_status": S.EXPECTED_UNCERTAINTY}, {"extra_score": 99},
])
def test_invalid_scenario_contract_rejected(mutation):
    payload = ScenarioRegistry().all()[0].model_dump()
    with pytest.raises(ValidationError):
        GoldenScenario.model_validate({**payload, **mutation})


def test_duplicate_check_ids_and_missing_journey_steps_rejected():
    payload = ScenarioRegistry().all()[0].model_dump()
    payload["checks"].append(deepcopy(payload["checks"][0]))
    with pytest.raises(ValidationError):
        GoldenScenario.model_validate(payload)
    payload = ScenarioRegistry().select(scenario_ids=["E2E_001"])[0].model_dump()
    with pytest.raises(ValidationError):
        GoldenScenario.model_validate({**payload, "journey_steps": []})


def test_registry_unique_ids_allowlist_and_nonmutating_selection():
    items = ScenarioRegistry().all()
    with pytest.raises(ValueError):
        ScenarioRegistry([items[0], items[0]])
    items[0].input_fixture_refs = ["data/private/confirmed_profile.json"]
    with pytest.raises(ValueError):
        ScenarioRegistry([items[0]])
    registry = ScenarioRegistry()
    first = registry.all()[0]
    first.title = "mutated copy"
    assert registry.all()[0].title != first.title
    with pytest.raises(ValueError):
        registry.select(scenario_ids=["SD_999"])


@pytest.mark.parametrize("layer", list(EvaluationLayer))
def test_registry_filters_all_three_layers(layer):
    selected = ScenarioRegistry().select(layer=layer)
    assert selected and all(item.layer == layer for item in selected)


@pytest.mark.parametrize("capability", list(Capability))
def test_registry_filters_every_capability(capability):
    selected = ScenarioRegistry().select(capability=capability, tags=["offline", "synthetic"])
    assert selected and all(item.capability == capability for item in selected)
