"""Authoritative structured-profile persistence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.models import UserProfile
from memory.base import StructuredProfileStore
from memory.errors import CorruptStoredProfileError, ProfileVersionConflictError
from memory.sqlite_store import (
    MEMORY_SCHEMA_VERSION,
    SQLiteMemoryDatabase,
    SQLiteStructuredProfileStore,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PROFILE_PATH = PROJECT_ROOT / "data" / "fixtures" / "public_confirmed_profile.json"


def _profile_v1() -> UserProfile:
    return UserProfile.model_validate_json(PUBLIC_PROFILE_PATH.read_text(encoding="utf-8"))


def _profile_v2() -> UserProfile:
    return _profile_v1().create_revision(
        education_summary="Synthetic revised education summary"
    ).confirm()


@pytest.fixture
def profile_store(tmp_path):
    database = SQLiteMemoryDatabase(tmp_path / "memory.sqlite3")
    return database, SQLiteStructuredProfileStore(database)


def test_profile_store_abstraction_and_schema_version(profile_store) -> None:
    database, store = profile_store
    assert isinstance(store, StructuredProfileStore)
    assert database.schema_version() == MEMORY_SCHEMA_VERSION == 1


def test_confirmed_profile_persists_and_revalidates(profile_store) -> None:
    _, store = profile_store
    saved = store.save_confirmed_profile("subject_alpha001", _profile_v1())
    loaded = store.get_current_confirmed_profile("subject_alpha001")
    assert saved.created is True
    assert saved.current is True
    assert isinstance(loaded, UserProfile)
    assert loaded == saved.profile


def test_unconfirmed_profile_is_rejected(profile_store) -> None:
    _, store = profile_store
    draft = _profile_v1().create_revision(education_summary="Draft")
    with pytest.raises(ProfileVersionConflictError):
        store.save_confirmed_profile("subject_alpha001", draft)


def test_profile_versions_are_immutable_and_current_pointer_moves(profile_store) -> None:
    _, store = profile_store
    first = _profile_v1()
    second = _profile_v2()
    store.save_confirmed_profile("subject_alpha001", first)
    store.save_confirmed_profile("subject_alpha001", second)
    history = store.list_profile_history("subject_alpha001")
    assert [item.version for item in history] == [1, 2]
    assert history[0] == first
    assert store.get_profile_version(
        "subject_alpha001", first.profile_id, 1
    ) == first
    assert store.get_current_confirmed_profile("subject_alpha001") == second


def test_exact_duplicate_is_idempotent(profile_store) -> None:
    _, store = profile_store
    profile = _profile_v1()
    first = store.save_confirmed_profile("subject_alpha001", profile)
    repeated = store.save_confirmed_profile("subject_alpha001", profile)
    assert first.created is True
    assert repeated.created is False
    assert repeated.current is True
    assert len(store.list_profile_history("subject_alpha001")) == 1


def test_replayed_confirmation_timestamp_is_semantically_idempotent(profile_store) -> None:
    _, store = profile_store
    draft = _profile_v1().create_revision(education_summary="Replay-safe")
    first_confirmation = draft.confirm()
    second_confirmation = draft.confirm()
    first = store.save_confirmed_profile("subject_alpha001", first_confirmation)
    repeated = store.save_confirmed_profile("subject_alpha001", second_confirmation)
    assert first.created is True
    assert repeated.created is False
    assert len(store.list_profile_history("subject_alpha001")) == 1


def test_conflicting_immutable_profile_identity_is_rejected(profile_store) -> None:
    _, store = profile_store
    profile = _profile_v1()
    store.save_confirmed_profile("subject_alpha001", profile)
    conflicting = profile.model_copy(
        update={"education_summary": "Conflicting semantic content"}
    )
    with pytest.raises(ProfileVersionConflictError):
        store.save_confirmed_profile("subject_alpha001", conflicting)


def test_profile_version_regression_is_rejected(profile_store) -> None:
    _, store = profile_store
    store.save_confirmed_profile("subject_alpha001", _profile_v2())
    with pytest.raises(ProfileVersionConflictError):
        store.save_confirmed_profile("subject_alpha001", _profile_v1())


def test_profile_subject_isolation(profile_store) -> None:
    _, store = profile_store
    store.save_confirmed_profile("subject_alpha001", _profile_v1())
    assert store.get_current_confirmed_profile("subject_beta002") is None
    assert store.list_profile_history("subject_beta002") == []


def test_corrupt_stored_profile_fails_safely(profile_store) -> None:
    database, store = profile_store
    profile = _profile_v1()
    store.save_confirmed_profile("subject_alpha001", profile)
    with database.connection() as connection:
        connection.execute(
            """
            UPDATE profile_versions SET payload_json = ?
            WHERE subject_id = ? AND profile_id = ? AND version = ?
            """,
            ("{invalid", "subject_alpha001", profile.profile_id, profile.version),
        )
        connection.commit()
    with pytest.raises(CorruptStoredProfileError) as captured:
        store.get_current_confirmed_profile("subject_alpha001")
    assert "invalid" not in str(captured.value).casefold()
