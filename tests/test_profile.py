"""UserProfile 版本、确认与历史语义测试。"""

import pytest
from pydantic import ValidationError

from data.models import ProfileStatus, UserProfile


def test_profile_defaults_to_unconfirmed() -> None:
    profile = UserProfile(profile_id="profile_test")
    assert profile.version == 1
    assert profile.confirmed is False
    assert profile.status == ProfileStatus.DRAFT


def test_profile_version_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        UserProfile(profile_id="profile_test", version=0)


def test_profile_revision_increments_version_without_mutating_original() -> None:
    original = UserProfile(profile_id="profile_test", education_summary="原始摘要")
    revision = original.create_revision(education_summary="修订摘要")
    assert original.version == 1
    assert original.education_summary == "原始摘要"
    assert revision.version == 2
    assert revision.education_summary == "修订摘要"
    assert revision.confirmed is False


def test_profile_confirmation_returns_copy() -> None:
    draft = UserProfile(profile_id="profile_test")
    confirmed = draft.confirm()
    assert draft.confirmed is False
    assert confirmed.confirmed is True
    assert confirmed.status == ProfileStatus.CONFIRMED
    assert confirmed.confirmed_at is not None


def test_profile_confirmation_marks_nested_signals_in_demo(paused_state) -> None:
    confirmed = paused_state.user_profile.confirm()
    assert all(skill.confirmed_by_user for skill in confirmed.skills)
    assert all(goal.confirmed_by_user for goal in confirmed.goals)


def test_revision_cannot_override_identity_or_version() -> None:
    profile = UserProfile(profile_id="profile_test")
    with pytest.raises(ValueError, match="受保护字段"):
        profile.create_revision(version=9)
