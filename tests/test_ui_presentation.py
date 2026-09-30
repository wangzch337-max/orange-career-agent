"""Presentation mapping tests that keep UI labels separate from domain semantics."""

from __future__ import annotations

from data.models import MatchRelationType
from ui.demo_controller import DemoController
from ui.presentation import (
    RELATION_LABELS,
    grouped_insights,
    insight_view,
    safe_error_message,
)


def _completed_controller() -> DemoController:
    controller = DemoController()
    controller.start()
    controller.confirm_profile()
    return controller


def test_every_match_relation_has_a_chinese_presentation_label_without_mutation() -> None:
    before = tuple(item.value for item in MatchRelationType)
    assert set(RELATION_LABELS) == set(MatchRelationType)
    assert RELATION_LABELS[MatchRelationType.STRONG_ALIGNMENT] == "明确契合"
    assert RELATION_LABELS[MatchRelationType.EVIDENCE_MISSING] == "证据缺失"
    assert RELATION_LABELS[MatchRelationType.PREFERENCE_ALIGNMENT] == "偏好契合"
    assert RELATION_LABELS[MatchRelationType.POTENTIAL_FRICTION] == "潜在摩擦"
    assert tuple(item.value for item in MatchRelationType) == before


def test_grouped_insights_supports_all_eight_authoritative_categories() -> None:
    controller = _completed_controller()
    try:
        groups = grouped_insights(controller.match_results()[0])
        assert [relation for relation, _ in groups] == list(MatchRelationType)
    finally:
        controller.close()


def test_insight_view_preserves_domain_evidence_linkage_and_labels() -> None:
    controller = _completed_controller()
    try:
        profile = controller.confirmed_profile()
        record = controller.job_intelligence()[0]
        result = controller.match_results()[0]
        insight = result.insights()[0]
        view = insight_view(insight, profile, record)
        assert view.insight_id == insight.insight_id
        assert view.profile_evidence_ids == tuple(
            insight.evidence_link.profile_evidence_ids
        )
        assert view.job_evidence_ids == tuple(insight.evidence_link.job_evidence_ids)
        assert view.relation_label == RELATION_LABELS[insight.relation_type]
    finally:
        controller.close()


def test_actions_are_existing_authoritative_text_not_ui_rewrites() -> None:
    controller = _completed_controller()
    try:
        result = controller.match_results()[0]
        report_actions = controller.report().next_actions[result.job_id]
        assert report_actions == [item.description for item in result.action_items]
        assert all(item.expected_evidence for item in result.action_items)
    finally:
        controller.close()


def test_user_error_copy_is_sanitized_and_never_includes_exception_details() -> None:
    sensitive = "secret traceback /Users/private/token"
    for category in (
        "workflow_failure",
        "validation_failure",
        "unexpected_failure",
    ):
        message = safe_error_message(category)
        assert sensitive not in message
        assert "traceback" not in message.casefold()
        assert "token" not in message.casefold()
