"""Isolated offline transcript storage: no canonical authority or private reads."""

from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import subprocess
from uuid import uuid4

import pytest

from ui.conversation import ConversationStage, GuidedConversation
from ui.conversation_store import (
    ConversationMessage, ConversationNotFoundError, ConversationStore,
    ConversationStoreError, ConversationThread, DEFAULT_CONVERSATION_PATH,
    EMPTY_TITLE, INITIAL_TITLE_LIMIT, validate_snapshot,
)


@pytest.fixture
def owner():
    return str(uuid4())


@pytest.fixture
def store(tmp_path):
    return ConversationStore(tmp_path / "conversation.sqlite3")


def test_create_thread_has_opaque_ids_and_aware_immutable_time(store, owner):
    thread = store.create_thread(owner, workflow_thread_id="workflow_synthetic")
    assert thread.thread_id.startswith("conversation_")
    assert thread.owner_scope_id == owner and thread.title == EMPTY_TITLE
    assert thread.created_at.utcoffset() == timedelta(0)
    assert thread.created_at == thread.updated_at
    assert thread.workflow_thread_id == "workflow_synthetic"
    assert thread.profile_id_ref is None and thread.profile_version_ref is None
    with pytest.raises(AttributeError):
        thread.created_at = datetime.now(timezone.utc)


def test_owner_identity_is_stable_across_store_restart(store, owner):
    first = store.ensure_owner(owner)
    restarted = ConversationStore(store.path)
    assert restarted.ensure_owner(owner) == first
    assert restarted.ensure_owner(str(uuid4())).subject_id != first.subject_id


def test_owner_cannot_list_another_scope_threads(store, owner):
    thread = store.create_thread(owner)
    other = str(uuid4())
    assert store.list_threads(other) == ()
    assert store.list_threads(owner) == (thread,)


@pytest.mark.parametrize("operation", ["get", "messages", "snapshot", "rename", "append", "save"])
def test_owner_cannot_access_or_change_another_scope_thread(store, owner, operation):
    thread = store.create_thread(owner)
    other = str(uuid4())
    calls = {
        "get": lambda: store.get_thread(other, thread.thread_id),
        "messages": lambda: store.list_messages(other, thread.thread_id),
        "snapshot": lambda: store.load_snapshot(other, thread.thread_id),
        "rename": lambda: store.rename_thread(other, thread.thread_id, "新标题"),
        "append": lambda: store.append_turn(other, thread.thread_id, "合成用户输入", "安全展示回复"),
        "save": lambda: store.save_snapshot(other, thread.thread_id, {}),
    }
    with pytest.raises(ConversationNotFoundError, match="unavailable"):
        calls[operation]()
    assert store.get_thread(owner, thread.thread_id) == thread
    assert store.list_messages(owner, thread.thread_id) == ()


def test_missing_and_out_of_scope_errors_do_not_reveal_existence(store, owner):
    thread = store.create_thread(owner)
    errors = []
    for scope, thread_id in ((str(uuid4()), thread.thread_id), (owner, "conversation_missing")):
        with pytest.raises(ConversationNotFoundError) as failure:
            store.get_thread(scope, thread_id)
        errors.append(str(failure.value))
    assert errors[0] == errors[1]


def test_turn_messages_order_and_restart_persistence(store, owner):
    thread = store.create_thread(owner)
    pair1 = store.append_turn(owner, thread.thread_id, "用户一", "Orange 一", user_metadata={"source": "typed"}, assistant_metadata={"kind": "text", "suggestions": ["继续了解"]})
    pair2 = store.append_turn(owner, thread.thread_id, "用户二", "Orange 二")
    messages = ConversationStore(store.path).list_messages(owner, thread.thread_id)
    assert messages == pair1 + pair2
    assert [message.role for message in messages] == ["user", "assistant", "user", "assistant"]
    assert len({message.message_id for message in messages}) == 4
    assert messages[0].metadata == {"source": "typed"}
    assert messages[1].metadata["suggestions"] == ["继续了解"]
    assert all(message.created_at.tzinfo is not None for message in messages)


def test_initial_title_is_first_normalized_user_text_and_deterministic(store, owner):
    thread = store.create_thread(owner)
    content = "  帮我\n了解  自己和未来职业方向，先从已有项目经历开始再看看下一步  "
    store.append_turn(owner, thread.thread_id, content, "Orange 合成回复")
    assert store.get_thread(owner, thread.thread_id).title == " ".join(content.split())[:INITIAL_TITLE_LIMIT]
    store.append_turn(owner, thread.thread_id, "后续话题", "后续回复")
    assert store.get_thread(owner, thread.thread_id).title == " ".join(content.split())[:INITIAL_TITLE_LIMIT]


def test_manual_rename_persists_without_mutating_messages_or_references(store, owner):
    thread = store.create_thread(owner, workflow_thread_id="workflow_synthetic", profile_id_ref="profile_synthetic", profile_version_ref=2)
    store.append_turn(owner, thread.thread_id, "用户输入", "Orange 回复")
    before = store.list_messages(owner, thread.thread_id)
    renamed = store.rename_thread(owner, thread.thread_id, "  我的  职业探索  ")
    assert renamed.title == "我的 职业探索"
    assert renamed.created_at == thread.created_at
    assert renamed.updated_at > thread.updated_at
    assert renamed.workflow_thread_id == thread.workflow_thread_id
    assert renamed.profile_id_ref == "profile_synthetic" and renamed.profile_version_ref == 2
    restarted = ConversationStore(store.path)
    assert restarted.get_thread(owner, thread.thread_id) == renamed
    assert restarted.list_messages(owner, thread.thread_id) == before


def test_manual_empty_thread_rename_is_not_overwritten_by_first_message(store, owner):
    thread = store.create_thread(owner)
    store.rename_thread(owner, thread.thread_id, "我命名的对话")
    store.append_turn(owner, thread.thread_id, "首个输入", "回复")
    assert store.get_thread(owner, thread.thread_id).title == "我命名的对话"


@pytest.mark.parametrize("title", ["", "  \n ", "字" * 61, 123])
def test_invalid_rename_is_rejected_without_change(store, owner, title):
    thread = store.create_thread(owner)
    with pytest.raises(ConversationStoreError):
        store.rename_thread(owner, thread.thread_id, title)
    assert store.get_thread(owner, thread.thread_id) == thread


def test_updated_order_advances_even_if_clock_is_equal_or_reverses(tmp_path, owner):
    now = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)
    store = ConversationStore(tmp_path / "clock.sqlite3", clock=lambda: now)
    first, second = store.create_thread(owner), store.create_thread(owner)
    assert [t.thread_id for t in store.list_threads(owner)] == [second.thread_id, first.thread_id]
    now -= timedelta(days=1)
    updated = store.rename_thread(owner, first.thread_id, "更新较早的对话")
    assert updated.created_at == first.created_at
    assert updated.updated_at > second.updated_at
    assert [t.thread_id for t in store.list_threads(owner)] == [first.thread_id, second.thread_id]


def test_opening_thread_and_loading_messages_does_not_update_it(store, owner):
    thread = store.create_thread(owner)
    store.get_thread(owner, thread.thread_id)
    store.list_threads(owner)
    store.list_messages(owner, thread.thread_id)
    store.load_snapshot(owner, thread.thread_id)
    assert store.get_thread(owner, thread.thread_id) == thread


def test_snapshot_restores_closed_guided_state_without_domain_calls(store, owner):
    guided = GuidedConversation()
    guided.submit(ConversationStage.CAREER_QUESTION, "我只是想先更了解自己", note="本轮合成补充")
    snapshot = {
        "stage": guided.stage.value, "answers": {stage.value: answer for stage, answer in guided.answers.items()},
        "notes": {stage.value: note for stage, note in guided.notes.items()},
        "pending_note": "待继续了解", "revising": False, "selected_role": None,
    }
    thread = store.create_thread(owner)
    store.append_turn(owner, thread.thread_id, "首个输入", "下一问题", snapshot=snapshot, workflow_thread_id="workflow_synthetic")
    restored = ConversationStore(store.path).load_snapshot(owner, thread.thread_id)
    assert restored == snapshot
    assert store.get_thread(owner, thread.thread_id).workflow_thread_id == "workflow_synthetic"


def test_snapshot_and_message_write_roll_back_atomically(store, owner):
    thread = store.create_thread(owner)
    with pytest.raises(ConversationStoreError):
        store.append_turn(owner, thread.thread_id, "合成输入", "合成回复", snapshot={"stage": "not_a_stage"})
    assert store.list_messages(owner, thread.thread_id) == ()
    assert store.get_thread(owner, thread.thread_id) == thread


def test_invalid_reference_rolls_back_both_messages_and_thread_update(store, owner):
    thread = store.create_thread(owner)
    with pytest.raises(ConversationStoreError):
        store.append_turn(owner, thread.thread_id, "合成输入", "合成回复", profile_id_ref="profile_synthetic")
    assert store.list_messages(owner, thread.thread_id) == ()
    assert store.get_thread(owner, thread.thread_id) == thread


def test_credential_cannot_be_smuggled_as_structural_reference(store, owner):
    value = "sk-" + "A1b2C3d4" * 5
    with pytest.raises(ConversationStoreError) as error:
        store.create_thread(owner, workflow_thread_id=value)
    assert value not in str(error.value)
    assert store.list_threads(owner) == ()


def test_save_snapshot_updates_only_refs_and_presentation(store, owner):
    thread = store.create_thread(owner)
    saved = store.save_snapshot(owner, thread.thread_id, {}, workflow_thread_id="workflow_synthetic", profile_id_ref="profile_synthetic", profile_version_ref=1)
    assert saved.created_at == thread.created_at and saved.updated_at > thread.updated_at
    assert saved.profile_id_ref == "profile_synthetic" and saved.profile_version_ref == 1
    assert store.list_messages(owner, thread.thread_id) == ()
    assert not list(store.path.parent.glob("*memory*"))


@pytest.mark.parametrize("snapshot", [
    {"profile": {}}, {"memory": []}, {"chain_of_thought": "forbidden"},
    {"prompt": "forbidden"}, {"stage": "work_style"},
    {"answers": {"work_style": "目前还不知道"}},
    {"notes": {"career_question": "unanswered"}}, {"pending_note": "x" * 241},
    {"revising": "false"}, {"selected_role": "unsafe/path"},
])
def test_snapshot_rejects_open_fields_and_inconsistent_routing(snapshot):
    with pytest.raises(ConversationStoreError):
        validate_snapshot(snapshot)


@pytest.mark.parametrize("metadata", [
    {"chain_of_thought": "forbidden"}, {"system_prompt": "forbidden"},
    {"Authorization": "forbidden"}, {"provider_response": {}},
    {"kind": "raw_profile"}, {"kind": []}, {"suggestions": "not_a_list"},
    {"kind": "text", "structured_payload_type": "text"}, {"source": "provider"},
    {"evidence_refs": ["unsafe/path"]},
])
def test_metadata_rejects_secret_or_unbounded_fields(store, owner, metadata):
    thread = store.create_thread(owner)
    with pytest.raises(ConversationStoreError):
        store.append_turn(owner, thread.thread_id, "合成输入", "合成回复", assistant_metadata=metadata)
    assert store.list_messages(owner, thread.thread_id) == ()


@pytest.mark.parametrize("prefix", ["sk-", "ghp_", "github_pat_", "Bearer ", 'api_key="'])
def test_credentials_are_rejected_before_write_with_sanitized_errors(store, owner, prefix):
    thread = store.create_thread(owner)
    value = prefix + "A1b2C3d4" * 5 + ('"' if prefix.endswith('"') else "")
    with pytest.raises(ConversationStoreError) as error:
        store.append_turn(owner, thread.thread_id, value, "安全回复")
    assert value not in str(error.value)
    assert store.list_messages(owner, thread.thread_id) == ()


def test_fake_placeholder_is_allowed_without_real_credentials(store, owner):
    thread = store.create_thread(owner)
    store.append_turn(owner, thread.thread_id, "sk-fake-" + "x" * 30, "合成示例")
    assert len(store.list_messages(owner, thread.thread_id)) == 2


@pytest.mark.parametrize("scope", ["", "owner_a", "../../outside", 42])
def test_scope_must_be_opaque_canonical_identifier(store, scope):
    with pytest.raises(ConversationStoreError):
        store.list_threads(scope)


def test_naive_clock_and_incomplete_profile_references_rejected(tmp_path, owner):
    store = ConversationStore(tmp_path / "naive.sqlite3", clock=lambda: datetime(2026, 10, 2))
    with pytest.raises(ConversationStoreError):
        store.create_thread(owner)
    store = ConversationStore(tmp_path / "refs.sqlite3")
    with pytest.raises(ConversationStoreError):
        store.create_thread(owner, profile_id_ref="profile_synthetic")


def test_runtime_path_is_git_ignored_and_not_canonical_store():
    root = Path(__file__).resolve().parents[1]
    assert DEFAULT_CONVERSATION_PATH == root / "data/local/chat/conversations.sqlite3"
    for suffix in ("", "-journal", "-wal", "-shm"):
        result = subprocess.run(["git", "check-ignore", "-q", str(DEFAULT_CONVERSATION_PATH) + suffix], cwd=root, capture_output=True, check=False)
        assert result.returncode == 0


def test_models_schema_have_no_reasoning_profile_or_memory_payload(store):
    for model in (ConversationThread, ConversationMessage):
        names = {item.name for item in fields(model)}
        assert not names & {"chain_of_thought", "hidden_reasoning", "prompt", "credential", "profile", "memory"}
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"conversation_owners", "conversation_threads", "conversation_messages", "sqlite_sequence"}


def test_delete_removes_thread_messages_metadata_and_snapshot_but_not_owner(store, owner):
    identity = store.ensure_owner(owner)
    thread = store.create_thread(owner, snapshot={"pending_note": "合成本轮备注"})
    store.append_turn(owner, thread.thread_id, "合成输入", "合成回复",
                      assistant_metadata={"kind": "text", "suggestions": ["合成建议"]})
    deleted = store.delete_thread(owner, thread.thread_id)
    assert deleted.thread_id == thread.thread_id
    assert store.list_threads(owner) == () and store.ensure_owner(owner) == identity
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM conversation_messages").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM conversation_threads").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM conversation_owners").fetchone()[0] == 1
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("operation", ["get_thread", "list_messages", "load_snapshot"])
def test_deleted_thread_cannot_be_loaded_after_store_restart(store, owner, operation):
    thread = store.create_thread(owner)
    store.append_turn(owner, thread.thread_id, "合成输入", "合成回复")
    store.delete_thread(owner, thread.thread_id)
    with pytest.raises(ConversationNotFoundError):
        getattr(ConversationStore(store.path), operation)(owner, thread.thread_id)


def test_delete_other_owner_and_unknown_share_safe_error_and_do_not_mutate(store, owner):
    thread = store.create_thread(owner)
    pair = store.append_turn(owner, thread.thread_id, "合成输入", "合成回复")
    errors = []
    for scope, target in ((str(uuid4()), thread.thread_id), (owner, "conversation_missing")):
        with pytest.raises(ConversationNotFoundError) as failure:
            store.delete_thread(scope, target)
        errors.append(str(failure.value))
    assert errors[0] == errors[1]
    assert thread.thread_id not in errors[0] and owner not in errors[0]
    assert store.list_messages(owner, thread.thread_id) == pair


@pytest.mark.parametrize("invalid", ["", "not_a_scope", "../../outside", 42])
def test_delete_requires_valid_owner_scope(store, owner, invalid):
    thread = store.create_thread(owner)
    with pytest.raises(ConversationStoreError):
        store.delete_thread(invalid, thread.thread_id)
    assert store.get_thread(owner, thread.thread_id) == thread


def test_delete_preserves_other_threads_and_other_owners_exactly(store, owner):
    target = store.create_thread(owner)
    survivors = []
    for scope in (owner, str(uuid4())):
        thread = store.create_thread(scope, snapshot={"pending_note": "保留的合成备注"})
        store.append_turn(scope, thread.thread_id, "保留的输入", "保留的回复",
                          assistant_metadata={"suggestions": ["保留的建议"]})
        survivors.append((scope, store.get_thread(scope, thread.thread_id),
                          store.list_messages(scope, thread.thread_id), store.load_snapshot(scope, thread.thread_id)))
    store.delete_thread(owner, target.thread_id)
    for scope, thread, messages, snapshot in survivors:
        assert store.get_thread(scope, thread.thread_id) == thread
        assert store.list_messages(scope, thread.thread_id) == messages
        assert store.load_snapshot(scope, thread.thread_id) == snapshot


def test_delete_rolls_back_messages_if_parent_delete_fails(store, owner):
    thread = store.create_thread(owner, snapshot={"pending_note": "仍保留"})
    pair = store.append_turn(owner, thread.thread_id, "合成输入", "合成回复",
                             assistant_metadata={"suggestions": ["仍保留"]})
    before = store.get_thread(owner, thread.thread_id)
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER fail_delete BEFORE DELETE ON conversation_threads
                      BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.delete_thread(owner, thread.thread_id)
    assert store.get_thread(owner, thread.thread_id) == before
    assert store.list_messages(owner, thread.thread_id) == pair
    assert store.load_snapshot(owner, thread.thread_id)["pending_note"] == "仍保留"


def test_repeated_delete_rejects_without_affecting_remaining_thread(store, owner):
    target, remaining = store.create_thread(owner), store.create_thread(owner)
    store.delete_thread(owner, target.thread_id)
    with pytest.raises(ConversationNotFoundError):
        store.delete_thread(owner, target.thread_id)
    assert store.list_threads(owner) == (remaining,)
