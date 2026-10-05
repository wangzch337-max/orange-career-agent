"""Persistent chat UI contracts, independent of browser-only animation testing."""

import ast
from pathlib import Path
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from ui.boot_loader import BOOT_DONE_KEY
from ui.chat_components import THEME_MODES
from ui.conversation_shell import CHAT_KEY, CONFIRM, DELETE_CONFIRMATION_KEY, INITIAL_SUGGESTIONS
from ui.onboarding.component import (
    CLIENT_SCOPE_KEY, COMPLETED_KEY, COMPONENT_KEY, SESSION_KEY,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_KEY = "orange_chat_workspace_v1"


def app(root, scope, *, later=False):
    value = AppTest.from_file(str(ROOT / "ui/app.py"), default_timeout=15)
    value.session_state["orange_chat_runtime_root"] = root
    value.session_state[CLIENT_SCOPE_KEY] = scope
    value.session_state[COMPONENT_KEY] = {"completed": True, "entry_seen": later, "client_scope": scope}
    value.session_state[COMPLETED_KEY] = True
    value.run()
    assert not value.exception
    return value


def suggestions(value):
    return [button for button in value.button if button.key and button.key.startswith("orange_suggestion_")]


def test_no_browser_scope_means_no_fake_shared_owner_or_runtime_write(tmp_path):
    value = AppTest.from_file(str(ROOT / "ui/app.py")).run()
    assert not value.exception and not value.chat_input
    assert WORKSPACE_KEY not in value.session_state
    assert CLIENT_SCOPE_KEY not in value.session_state


def test_thread_history_selection_rename_and_refresh(tmp_path):
    scope = str(uuid4())
    first = app(tmp_path, scope)
    workspace = first.session_state[WORKSPACE_KEY]
    try:
        first.chat_input[0].set_value("线程 A 的课程项目补充").run()
        thread_a = workspace.thread.thread_id
        first.button(key="orange_new_chat").click().run()
        thread_b = workspace.thread.thread_id
        assert thread_b != thread_a and not first.chat_message
        first.chat_input[0].set_value("线程 B 的职业问题").run()
        first.button(key=f"orange_thread_{thread_a}").click().run()
        assert workspace.thread.thread_id == thread_a
        assert workspace.chat.messages[0].content == "线程 A 的课程项目补充"
        first.text_input(key=f"orange_rename_{thread_a}").set_value("我的课程项目").run()
        first.button(key=f"orange_save_name_{thread_a}").click().run()
        created = workspace.thread.created_at
        assert workspace.thread.title == "我的课程项目"
        assert any(button.label == "保存名称" for button in first.button)
        assert any("开始于" in markdown.value for markdown in first.markdown)
    finally:
        workspace.close()
    refreshed = app(tmp_path, scope)
    try:
        restored = refreshed.session_state[WORKSPACE_KEY]
        assert {thread.thread_id for thread in restored.threads} == {thread_a, thread_b}
        assert restored.thread.title == "我的课程项目"
        assert restored.thread.created_at == created
        assert len(refreshed.chat_message) == 2
        refreshed.button(key=f"orange_thread_{thread_b}").click().run()
        assert restored.chat.messages[0].content == "线程 B 的职业问题"
        assert len(suggestions(refreshed)) > 0
    finally:
        refreshed.session_state[WORKSPACE_KEY].close()


def test_client_b_never_lists_client_a_threads(tmp_path):
    a, b = app(tmp_path, str(uuid4())), app(tmp_path, str(uuid4()))
    try:
        a.chat_input[0].set_value("A 的独立对话").run()
        owned_a = a.session_state[WORKSPACE_KEY].thread.thread_id
        assert owned_a not in {thread.thread_id for thread in b.session_state[WORKSPACE_KEY].threads}
        assert not b.chat_message
        assert not [button for button in b.button if button.key == f"orange_thread_{owned_a}"]
    finally:
        a.session_state[WORKSPACE_KEY].close()
        b.session_state[WORKSPACE_KEY].close()


def test_theme_switch_rename_new_chat_and_selection_do_not_replay_boot(tmp_path, monkeypatch):
    import ui.boot_loader as boot
    sleeps = []
    monkeypatch.setattr(boot, "sleep", sleeps.append)
    value = app(tmp_path, str(uuid4()), later=True)
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        assert sleeps == [.85]
        assert value.session_state[BOOT_DONE_KEY]
        session = value.session_state[SESSION_KEY]
        thread = workspace.thread.thread_id
        value.chat_input[0].set_value(INITIAL_SUGGESTIONS[0]).run()
        message_count = len(workspace.chat.messages)
        for mode in THEME_MODES:
            value.radio(key="orange_appearance").set_value(mode).run()
            assert not value.exception
            assert value.radio(key="orange_appearance").value == mode
            value.run()
            assert value.radio(key="orange_appearance").value == mode
            assert workspace.thread.thread_id == thread
            assert len(workspace.threads) == 1 and len(workspace.chat.messages) == message_count
        value.text_input(key=f"orange_rename_{thread}").set_value("不重播介绍").run()
        value.button(key=f"orange_save_name_{thread}").click().run()
        value.button(key="orange_new_chat").click().run()
        value.button(key=f"orange_thread_{thread}").click().run()
        assert sleeps == [.85]
        assert value.session_state[SESSION_KEY] == session
        assert value.session_state[COMPLETED_KEY] and value.session_state[BOOT_DONE_KEY]
        assert len(workspace.chat.messages) == message_count
    finally:
        workspace.close()


def test_normal_ui_menu_is_chinese_without_dead_upload_or_trace(tmp_path):
    value = app(tmp_path, str(uuid4()))
    try:
        appearance = value.radio(key="orange_appearance")
        assert appearance.label == "外观"
        assert appearance.options == ["跟随系统", "浅色模式", "深色模式"]
        assert {element.proto.popover.label for element in value.get("popover")} == {"···", "＋"}
        visible_text = "\n".join(element.value for element in value.markdown) + "\n" + "\n".join(element.value for element in value.caption)
        for removed in ("关于 Orange Career", "陪你用证据了解自己、比较职业方向。",
                        "本地 Demo · 不是职业排名，也不替你做最终决定。"):
            assert removed not in visible_text
        brand = next(element.value for element in value.markdown if '<div class="orange-chat-brand">' in element.value)
        assert brand == '<div class="orange-chat-brand"><strong>Orange Career</strong><span class="orange-demo-tag">Demo</span></div>'
        source = (ROOT / "ui/conversation_shell.py").read_text()
        menu = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.With)
                    and any(ast.get_source_segment(source, item.context_expr) == 'st.container(key="orange_product_menu", width="content")' for item in node.items))
        assert len(menu.body) == 1 and isinstance(menu.body[0], ast.With)
        popover = menu.body[0]
        assert len(popover.body) == 1
        assert ast.get_source_segment(source, popover.body[0]) == 'st.radio("外观", THEME_MODES, key="orange_appearance")'
        assert len(value.file_uploader) == 1
        upload = value.file_uploader[0]
        assert upload.label == "上传简历"
        assert list(upload.proto.type) == [".pdf", ".docx"]
        assert upload.proto.max_upload_size_mb == 10 and not upload.proto.multiple_files
        assert not [element for element in value.expander if "执行轨迹" in element.label]
        assert len(suggestions(value)) == 4
    finally:
        value.session_state[WORKSPACE_KEY].close()


def test_only_latest_suggestions_and_none_in_composer(tmp_path):
    value = app(tmp_path, str(uuid4()))
    try:
        value.button(key="orange_suggestion_0").click().run()
        value.button(key="orange_suggestion_1").click().run()
        workspace = value.session_state[WORKSPACE_KEY]
        assert len(workspace.chat.messages) == 4
        assert [button.label for button in suggestions(value)] == list(workspace.chat.messages[-1].suggestions)
        assert workspace.chat.messages[1].suggestions != workspace.chat.messages[-1].suggestions
        source = (ROOT / "ui/conversation_shell.py").read_text()
        tree = ast.parse(source)
        bottom = next(node for node in ast.walk(tree) if isinstance(node, ast.With)
                      and any(ast.get_source_segment(source, item.context_expr) == "st.bottom" for item in node.items))
        assert "_suggestions(" not in ast.get_source_segment(source, bottom)
        assert "st.chat_input(" in ast.get_source_segment(source, bottom)
    finally:
        value.session_state[WORKSPACE_KEY].close()


def test_new_chat_reuses_exact_confirmed_profile_without_second_confirmation(tmp_path):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        for choice in (INITIAL_SUGGESTIONS[0], "分析数据、找规律", "用现有 AI / LLM 做真正的应用",
                       "Campus Helper Prototype", "Python", "大部分时间亲手实现东西", "做出真正可使用的产品", CONFIRM):
            workspace.submit(choice)
        value.run()
        assert workspace.controller.state["workflow_status"] == "completed"
        exact = workspace.controller.confirmed_profile().model_dump(mode="json")
        memory = tuple(workspace.controller.active_memories())
        history = tuple(workspace.controller.profile_history())
        old_thread = workspace.thread.thread_id
        value.button(key="orange_new_chat").click().run()
        assert workspace.thread.thread_id != old_thread and not value.chat_message
        value.button(key="orange_suggestion_1").click().run()
        assert not value.exception
        assert workspace.controller.state["self_discovery_call_count"] == 0
        assert workspace.controller.confirmed_profile().model_dump(mode="json") == exact
        assert tuple(workspace.controller.profile_history()) == history
        assert tuple(workspace.controller.active_memories()) == memory
        assert CONFIRM not in [button.label for button in suggestions(value)]
        value.button(key=f"orange_thread_{old_thread}").click().run()
        assert workspace.controller.confirmed_profile().model_dump(mode="json") == exact
        assert len(workspace.chat.messages) == 16
    finally:
        workspace.close()


def test_delete_menu_is_chinese_and_requires_confirm_then_cancel_keeps_everything(tmp_path):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        value.chat_input[0].set_value("合成删除测试消息").run()
        thread, chat, controller = workspace.thread, workspace.chat, workspace.controller
        before = workspace.store.list_messages(workspace.owner_scope_id, thread.thread_id)
        assert any(element.label == "重命名" for element in value.expander)
        request = value.button(key=f"orange_delete_request_{thread.thread_id}")
        assert request.label == "删除对话"
        assert not [button for button in value.button if button.label == "删除"]
        request.click().run()
        assert value.session_state[DELETE_CONFIRMATION_KEY] == (workspace.owner_scope_id, thread.thread_id)
        assert workspace.thread == thread and workspace.chat is chat and workspace.controller is controller
        assert workspace.store.list_messages(workspace.owner_scope_id, thread.thread_id) == before
        assert any("删除这个对话？" in element.value for element in value.markdown)
        assert any("删除后，此对话中的聊天记录将无法恢复。" in element.value for element in value.markdown)
        assert value.button(key="orange_confirm_delete").label == "删除"
        assert value.button(key="orange_cancel_delete").label == "取消"
        value.button(key="orange_cancel_delete").click().run()
        assert DELETE_CONFIRMATION_KEY not in value.session_state
        assert workspace.thread == thread and workspace.chat is chat
        assert workspace.store.list_messages(workspace.owner_scope_id, thread.thread_id) == before
    finally:
        workspace.close()


@pytest.mark.parametrize("active", [False, True], ids=["inactive", "active"])
@pytest.mark.parametrize("theme", THEME_MODES)
def test_confirmed_delete_in_all_themes_keeps_intro_scope_and_boot(tmp_path, monkeypatch, active, theme):
    import ui.boot_loader as boot
    sleeps = []
    monkeypatch.setattr(boot, "sleep", sleeps.append)
    value = app(tmp_path, str(uuid4()), later=True)
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        value.radio(key="orange_appearance").set_value(theme).run()
        value.chat_input[0].set_value("A 的合成消息").run()
        target = workspace.thread
        value.button(key="orange_new_chat").click().run()
        value.chat_input[0].set_value("B 的合成消息").run()
        survivor = workspace.thread
        if active:
            value.button(key=f"orange_thread_{target.thread_id}").click().run()
        current_chat, current_controller = workspace.chat, workspace.controller
        session, scope = value.session_state[SESSION_KEY], value.session_state[CLIENT_SCOPE_KEY]
        value.button(key=f"orange_delete_request_{target.thread_id}").click().run()
        value.button(key="orange_confirm_delete").click().run()
        assert not value.exception
        assert workspace.thread.thread_id == survivor.thread_id
        assert workspace.chat.messages[0].content == "B 的合成消息"
        assert value.session_state[CHAT_KEY] is workspace.chat
        assert value.session_state["orange_demo_controller"] is workspace.controller
        if not active:
            assert workspace.chat is current_chat and workspace.controller is current_controller
        assert not [button for button in value.button if button.key == f"orange_thread_{target.thread_id}"]
        assert DELETE_CONFIRMATION_KEY not in value.session_state
        assert value.session_state[SESSION_KEY] == session and value.session_state[CLIENT_SCOPE_KEY] == scope
        assert value.session_state[COMPLETED_KEY] and value.session_state[BOOT_DONE_KEY]
        assert value.radio(key="orange_appearance").value == theme and sleeps == [.85]
    finally:
        workspace.close()


def test_delete_last_ui_conversation_then_new_chat_and_refresh(tmp_path):
    scope = str(uuid4())
    value = app(tmp_path, scope)
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        value.chat_input[0].set_value("将删除的合成消息").run()
        deleted = workspace.thread.thread_id
        value.button(key=f"orange_delete_request_{deleted}").click().run()
        value.button(key="orange_confirm_delete").click().run()
        assert not value.exception and not value.chat_message
        assert any("现在开始吧" in element.value for element in value.markdown)
        assert len(suggestions(value)) == 4 and len(workspace.threads) == 1
        value.button(key="orange_new_chat").click().run()
        value.chat_input[0].set_value("新对话仍可使用").run()
    finally:
        workspace.close()
    refreshed = app(tmp_path, scope, later=True)
    try:
        restored = refreshed.session_state[WORKSPACE_KEY]
        assert deleted not in {thread.thread_id for thread in restored.threads}
        assert restored.chat.messages[0].content == "新对话仍可使用"
    finally:
        refreshed.session_state[WORKSPACE_KEY].close()


def test_failed_delete_ui_reports_safe_notice_without_reset(tmp_path, monkeypatch):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        target, chat, controller = workspace.thread, workspace.chat, workspace.controller
        def fail(_id):
            raise ValueError("synthetic detail that must not appear")
        monkeypatch.setattr(workspace, "delete_thread", fail)
        value.button(key=f"orange_delete_request_{target.thread_id}").click().run()
        value.button(key="orange_confirm_delete").click().run()
        assert not value.exception and workspace.thread == target
        assert workspace.chat is chat and workspace.controller is controller
        assert "这个对话暂时无法删除" in value.warning[0].value
        assert "synthetic detail" not in value.warning[0].value
    finally:
        workspace.close()


def test_stale_confirmation_cannot_delete_a_different_owner_or_target(tmp_path, monkeypatch):
    from ui import conversation_shell as shell
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        target = workspace.thread
        for pending in (None, (str(uuid4()), target.thread_id), (workspace.owner_scope_id, "conversation_other")):
            state = {} if pending is None else {DELETE_CONFIRMATION_KEY: pending}
            with monkeypatch.context() as context:
                context.setattr(shell.st, "session_state", state)
                shell._confirm_delete(workspace, target.thread_id)
            assert workspace.store.get_thread(workspace.owner_scope_id, target.thread_id) == target
    finally:
        workspace.close()
