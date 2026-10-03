"""v1.2 native chat, boot lifecycle and non-destructive conversation contracts."""

import ast
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import subprocess
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from ui.boot_loader import BOOT_DONE_KEY, ENTRY_SEEN_KEY, LOADER_SECONDS, loader_html
from ui.chat_components import orange_mark, shell_stylesheet
from ui.conversation import ConversationStage as Stage, QUESTIONS
from ui.conversation_shell import (
    CHAT_KEY, CONFIRM, INITIAL_CHOICES, INITIAL_SUGGESTIONS, REVISE, REVIEW,
    ChatSession, new_chat,
)
from ui.demo_controller import DemoController
from ui.onboarding.component import CLIENT_SCOPE_KEY, COMPLETED_KEY, COMPONENT_KEY, SESSION_KEY


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = "8e87b9d8c817668bded0e89342432e9cc184fb11"


@pytest.fixture
def controller():
    value = DemoController()
    yield value
    value.close()


@pytest.fixture
def app(tmp_path):
    value = AppTest.from_file(str(ROOT / "ui/app.py"), default_timeout=15)
    scope = str(uuid4())
    value.session_state["orange_chat_runtime_root"] = tmp_path
    value.session_state[CLIENT_SCOPE_KEY] = scope
    value.session_state[COMPONENT_KEY] = {"completed": True, "entry_seen": False, "client_scope": scope}
    value.session_state[COMPLETED_KEY] = True
    value.run()
    assert not value.exception
    yield value
    value.session_state["orange_chat_workspace_v1"].close()


def suggestion_labels(app):
    return tuple(b.label for b in app.button if b.key and b.key.startswith("orange_suggestion_"))


def text(app):
    return "\n".join(str(e.value) for kind in ("markdown", "caption", "info", "warning", "error", "code") for e in getattr(app, kind))


def reach_review(chat, controller):
    for choice in (
        INITIAL_SUGGESTIONS[2], "把一个想法真正做成系统", "把多个 API / 模块连起来",
        "用现有 AI / LLM 做真正的应用", "Campus Helper Prototype",
        "Python、API integration", "大部分时间亲手实现东西", "做出真正可使用的产品",
    ):
        chat.submit(choice, controller)
    assert controller.state["workflow_status"] == "waiting_for_human"


def test_brand_demo_badge_and_empty_line(app):
    body = text(app)
    assert "Orange Career" in body and 'class="orange-demo-tag">Demo<' in body
    assert '<h1>现在开始吧</h1>' in body
    assert "sphere-art" in body
    assert app.sidebar.button[0].label == "＋ 新对话"
    assert len(app.chat_input) == 1
    assert app.chat_input[0].placeholder == "和 Orange 说点什么…"
    assert not app.chat_message


@pytest.mark.parametrize("phrase", ["公开演示模式", "虚构数据", "离线 AI", "重新播放介绍", "重新开始 Demo", "开发者执行轨迹", "诊断尚未开始"])
def test_removed_copy_is_not_rendered_in_normal_shell(app, phrase):
    assert phrase not in text(app)
    assert not [b for b in app.button if phrase in b.label]
    assert not [e for e in app.expander if phrase in e.label]


def test_normal_main_never_calls_legacy_app_bar_or_trace():
    source = (ROOT / "ui/app.py").read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "main")
    body = ast.get_source_segment(source, node)
    for forbidden in ("_app_bar(", "render_public_demo_banner(", "render_developer_trace(", "legacy_main(", "_reset_demo("):
        assert forbidden not in body
    assert "render_conversation_shell(controller)" in body


def test_initial_chips_click_records_exact_utterance_and_changes_options(app):
    assert suggestion_labels(app) == INITIAL_SUGGESTIONS
    app.button(key="orange_suggestion_2").click().run()
    assert not app.exception
    chat = app.session_state[CHAT_KEY]
    assert chat.messages[0].role == "user"
    assert chat.messages[0].content == INITIAL_SUGGESTIONS[2]
    assert chat.messages[1].role == "assistant"
    assert len(app.chat_message) == 2
    assert "现在开始吧" not in text(app)
    assert suggestion_labels(app) == QUESTIONS[Stage.ACTIVITY_PREFERENCE].options


@pytest.mark.parametrize("utterance", INITIAL_SUGGESTIONS)
def test_every_initial_suggestion_maps_only_to_existing_guided_choices(controller, utterance):
    chat = ChatSession()
    chat.submit(utterance, controller)
    assert controller.conversation.answer_for(Stage.CAREER_QUESTION) == INITIAL_CHOICES[utterance]
    assert controller.state is None
    assert controller.conversation.stage == Stage.ACTIVITY_PREFERENCE


def test_typed_chip_and_button_submit_are_equivalent(app):
    app.chat_input[0].set_value(INITIAL_SUGGESTIONS[2]).run()
    typed = app.session_state[CHAT_KEY]
    before = asdict(typed)
    stage = app.session_state["orange_demo_controller"].conversation.stage
    app.sidebar.button[0].click().run()
    app.button(key="orange_suggestion_2").click().run()
    assert asdict(app.session_state[CHAT_KEY]) == before
    assert app.session_state["orange_demo_controller"].conversation.stage == stage


def test_freeform_does_not_guess_choice_or_create_evidence(controller):
    chat = ChatSession()
    before = tuple(controller.active_memories())
    chat.submit("我刚完成一个课程项目\n还不知道怎么描述", controller)
    assert chat.pending_note.startswith("我刚完成")
    assert controller.conversation.stage == Stage.CAREER_QUESTION
    assert not controller.conversation.answers
    assert "补充" in chat.messages[-1].content
    chat.submit(INITIAL_SUGGESTIONS[0], controller)
    assert controller.conversation.notes[Stage.CAREER_QUESTION].startswith("我刚完成")
    assert not chat.pending_note
    assert controller.state is None and tuple(controller.active_memories()) == before


def test_freeform_malicious_markup_rendered_as_text(app):
    app.chat_input[0].set_value('<script>bad()</script>\n**not-authority**').run()
    assert not app.exception
    assert "&lt;script&gt;bad()&lt;/script&gt;" in text(app)
    assert not app.session_state["orange_demo_controller"].conversation.answers


@pytest.mark.parametrize("choice,next_stage", [
    ("把一个想法真正做成系统", Stage.IMPLEMENTATION_DETAIL),
    ("分析数据、找规律", Stage.AI_INTEREST),
    ("我还说不清楚", Stage.AI_INTEREST),
])
def test_original_branching_is_authoritative(controller, choice, next_stage):
    chat = ChatSession()
    chat.submit(INITIAL_SUGGESTIONS[0], controller)
    chat.submit(choice, controller)
    assert controller.conversation.stage == next_stage
    assert chat.suggestions(controller) == QUESTIONS[next_stage].options


def test_multiline_multi_choices_use_existing_validation(controller):
    chat = ChatSession()
    for choice in (INITIAL_SUGGESTIONS[0], "分析数据、找规律", "用现有 AI / LLM 做真正的应用\n思考 AI 应该解决什么用户问题"):
        chat.submit(choice, controller)
    assert controller.conversation.answer_for(Stage.AI_INTEREST) == ("用现有 AI / LLM 做真正的应用", "思考 AI 应该解决什么用户问题")
    assert controller.conversation.stage == Stage.PROJECT_EVIDENCE
    assert "兴趣不等于" in chat.messages[-3].content


def test_incompatible_uncertainty_does_not_advance(controller):
    chat = ChatSession()
    chat.submit(INITIAL_SUGGESTIONS[0], controller)
    chat.submit("分析数据、找规律", controller)
    chat.submit("我还不知道、用现有 AI / LLM 做真正的应用", controller)
    assert controller.conversation.stage == Stage.AI_INTEREST
    assert Stage.AI_INTEREST not in controller.conversation.answers


def test_real_confirmation_gate_same_thread_and_no_rediscovery(controller):
    chat = ChatSession()
    reach_review(chat, controller)
    workflow = controller.workflow_id
    assert chat.messages[-1].structured_payload["kind"] == "profile"
    assert controller.state["match_results"] == []
    chat.submit("AI Product Intern", controller)
    assert controller.state["workflow_status"] == "waiting_for_human"
    assert chat.messages[-1].structured_payload is None
    chat.submit(CONFIRM, controller)
    assert controller.state["workflow_status"] == "completed"
    assert controller.workflow_id == workflow
    assert controller.dependencies.self_discovery_agent.llm_provider.call_count == 1
    assert controller.confirmed_profile().confirmed
    assert chat.messages[-1].structured_payload["kind"] == "directions"


def test_chat_revision_uses_existing_education_summary_contract(controller):
    chat = ChatSession()
    reach_review(chat, controller)
    chat.submit(REVISE, controller)
    chat.submit(CONFIRM, controller)
    assert controller.state["workflow_status"] == "waiting_for_human" and chat.revising
    chat.submit("Public course-based education summary", controller)
    assert not chat.revising
    assert controller.state["profile"]["version"] == 2
    assert controller.state["profile"]["education_summary"] == "Public course-based education summary"
    assert controller.dependencies.self_discovery_agent.llm_provider.call_count == 1
    chat.submit(CONFIRM, controller)
    assert controller.confirmed_profile().version == 2


def test_return_from_revision_and_uncertainty_keep_gate(controller):
    chat = ChatSession()
    reach_review(chat, controller)
    chat.submit(REVISE, controller)
    chat.submit(REVIEW, controller)
    chat.submit("我还不确定", controller)
    assert controller.state["workflow_status"] == "waiting_for_human"
    assert not controller.state["profile"]["confirmed"]
    assert not chat.revising


def test_chat_native_profile_gate_and_payload_render(app):
    chat = app.session_state[CHAT_KEY]
    controller = app.session_state["orange_demo_controller"]
    reach_review(chat, controller)
    app.run()
    assert not app.exception
    assert "这是我目前对你的理解" in text(app)
    assert "待确认" in text(app)
    assert CONFIRM in [b.label for b in app.button]
    next(b for b in app.button if b.label == CONFIRM).click().run(timeout=15)
    assert not app.exception
    assert suggestion_labels(app) == ("AI Product Intern", "AI Application Engineer", "Data Analyst")


@pytest.mark.parametrize("role", ["AI Product Intern", "AI Application Engineer", "Data Analyst"])
def test_post_confirmation_role_and_existing_question_answers(controller, role):
    chat = ChatSession()
    reach_review(chat, controller)
    chat.submit(CONFIRM, controller)
    chat.submit(role, controller)
    assert chat.selected_role
    assert role in chat.messages[-1].content
    chat.submit("我还缺哪些证据？", controller)
    assert chat.messages[-1].content
    assert "看证据关系" in chat.suggestions(controller)
    chat.submit("看证据关系", controller)
    assert len(chat.messages[-1].structured_payload["groups"]) == 8
    chat.submit("看下一步行动", controller)
    assert chat.messages[-1].structured_payload["actions"]
    chat.submit("我的长期理解", controller)
    assert chat.messages[-1].structured_payload["kind"] == "memory"


def test_transcript_role_payloads_are_readonly_and_never_auto_saved(app):
    chat, controller = app.session_state[CHAT_KEY], app.session_state["orange_demo_controller"]
    reach_review(chat, controller)
    chat.submit(CONFIRM, controller)
    before = tuple(controller.active_memories())
    result = controller.match_for("job_001").model_dump(mode="json")
    for choice in ("AI Product Intern", "看证据关系", "看下一步行动", "我的长期理解"):
        chat.submit(choice, controller)
        app.run()
        assert not app.exception
    assert controller.match_for("job_001").model_dump(mode="json") == result
    assert tuple(controller.active_memories()) == before
    assert not app.code


def test_new_chat_keeps_memory_profiles_checkpoint_and_diagnostics(controller, monkeypatch):
    import ui.conversation_shell as shell
    chat = ChatSession()
    reach_review(chat, controller)
    chat.submit(CONFIRM, controller)
    controller.answer_role_clarification("job_001", "很喜欢")
    controller.save_role_clarification("job_001")
    before = (tuple(controller.active_memories()), tuple(controller.profile_history()))
    subject, path, checkpoint, collector = controller.subject_id, controller.memory_service.database.path, controller.checkpointer, controller.diagnostic_collector
    workflow = controller.workflow_id
    profile = controller.current_profile_from_memory().model_dump(mode="json")
    state = {CHAT_KEY: chat, BOOT_DONE_KEY: True, ENTRY_SEEN_KEY: False, COMPLETED_KEY: True, SESSION_KEY: "same-intro-session", "unrelated": object()}
    monkeypatch.setattr(shell, "st", SimpleNamespace(session_state=state))
    new_chat(controller)
    assert controller.workflow_id != workflow and controller.state is None
    assert controller.subject_id == subject and controller.memory_service.database.path == path
    assert controller.checkpointer is checkpoint and controller.diagnostic_collector is collector
    assert (tuple(controller.active_memories()), tuple(controller.profile_history())) == before
    assert controller.current_profile_from_memory().model_dump(mode="json") == profile
    assert state[BOOT_DONE_KEY] and state[COMPLETED_KEY] and state[SESSION_KEY] == "same-intro-session"
    assert state[ENTRY_SEEN_KEY] is False and "unrelated" in state
    assert not state[CHAT_KEY].messages and not controller.conversation.answers
    assert state[CHAT_KEY].suggestions(controller) == INITIAL_SUGGESTIONS
    # A second thread reuses the exact canonical version, never recreates it.
    state[CHAT_KEY].submit(INITIAL_SUGGESTIONS[0], controller)
    assert controller.state["workflow_status"] == "completed"
    assert controller.current_profile_from_memory().model_dump(mode="json") == profile
    assert controller.confirmed_profile().model_dump(mode="json") == profile
    assert controller.state["self_discovery_call_count"] == 0


def test_new_chat_native_button_restores_empty_state(app):
    app.button(key="orange_suggestion_0").click().run()
    controller = app.session_state["orange_demo_controller"]
    memory = tuple(controller.active_memories())
    app.session_state[BOOT_DONE_KEY] = True
    app.session_state[COMPLETED_KEY] = True
    component = app.session_state[COMPONENT_KEY]
    app.session_state[COMPONENT_KEY] = {**component, "completed": True}
    app.sidebar.button[0].click().run()
    assert not app.exception and not app.chat_message
    assert "现在开始吧" in text(app)
    assert tuple(controller.active_memories()) == memory
    assert app.session_state[BOOT_DONE_KEY] and app.session_state[COMPLETED_KEY]


@pytest.mark.parametrize("entry,completed,done,expected_load,expected_done", [
    (None, False, False, False, False), (False, False, False, False, False),
    (False, True, False, False, True), (True, True, False, True, True),
    (True, True, True, False, True), (False, True, True, False, True),
])
def test_boot_entry_matrix_and_one_shot_rerun_latch(monkeypatch, entry, completed, done, expected_load, expected_done):
    import ui.boot_loader as boot
    rendered, sleeps = [], []
    state = {COMPLETED_KEY: completed, BOOT_DONE_KEY: done, "domain": object()}
    if entry is not None:
        state[ENTRY_SEEN_KEY] = entry
    element = SimpleNamespace(markdown=lambda *a, **kw: rendered.append(a[0]), empty=lambda: None)
    monkeypatch.setattr(boot, "st", SimpleNamespace(session_state=state, empty=lambda: element))
    monkeypatch.setattr(boot, "render_onboarding", lambda: None)
    monkeypatch.setattr(boot, "sleep", sleeps.append)
    boot.render_boot()
    assert bool(rendered) == expected_load
    assert bool(state[BOOT_DONE_KEY]) == expected_done
    assert sleeps == ([LOADER_SECONDS] if expected_load else [])
    boot.render_boot()
    assert len(rendered) == int(expected_load)
    assert "domain" in state


def test_bridge_entry_flag_does_not_become_true_after_first_intro(monkeypatch):
    import ui.onboarding.component as bridge
    state = {COMPONENT_KEY: {"entry_seen": False, "completed": True}}
    monkeypatch.setattr(bridge, "st", SimpleNamespace(session_state=state))
    bridge._mirror_entry()
    state[COMPONENT_KEY]["entry_seen"] = True
    bridge._mirror_entry()
    assert state[ENTRY_SEEN_KEY] is False


def test_loader_motion_single_jump_exact_text_quiet_local_and_reduced():
    html = loader_html()
    assert "正在加载中" in html and "sphere-art" in html and "leaf-group" in html
    assert "650ms" in html and "850ms" in html
    assert "1;" in html and "infinite" not in html
    assert "translateY(-12px)" in html
    assert "prefers-reduced-motion:reduce" in html and "animation:none" in html
    for forbidden in ("<script", "<audio", "<video", "AudioContext", "http://localhost", "https://", "progress", "%完成"):
        assert forbidden not in html
    assert .7 <= LOADER_SECONDS <= .9


def test_shell_bounded_widths_and_native_scroll_without_new_js():
    css = shell_stylesheet()
    for value in ("248px", "864px", "max-width:700px", "96px", "80px", "margin-left:auto", "max-width:68%"):
        assert value in css
    source = (ROOT / "ui/conversation_shell.py").read_text()
    assert "st.bottom" in source and "st.chat_input(" in source and "st.chat_message(" in source
    assert "autoscroll=True" in source and "horizontal=True, wrap=True" in source
    for forbidden in ("<script", "javascript:", "https://", "@import", "fetch("):
        assert forbidden not in source + css


@pytest.mark.parametrize("name", ["_conversation", "_profile", "_directions", "_role", "_match", "_actions", "_map", "_memory", "_reset_demo"])
def test_legacy_page_functions_are_byte_preserved(name):
    old = subprocess.check_output(["git", "show", f"{CHECKPOINT}:ui/app.py"], cwd=ROOT, text=True)
    new = (ROOT / "ui/app.py").read_text()
    def function(source):
        return ast.get_source_segment(source, next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name))
    assert function(old) == function(new)


@pytest.mark.parametrize("scope", ["agents", "providers", "memory", "workflows", "evaluation", "observability", "data", "config/prompts", "requirements.txt", "ui/visual_system.py", "ui/app_bar.py"])
def test_v12_does_not_change_authority_or_dependencies(scope):
    if scope == "workflows":
        from tests.v12_contract import assert_v12_delta
        name = "workflows/langgraph_workflow.py"
        assert_v12_delta(name, (ROOT / name).read_bytes(), subprocess.check_output(["git", "show", f"{CHECKPOINT}:{name}"], cwd=ROOT))
        assert subprocess.check_output(["git", "diff", "--name-only", CHECKPOINT, "--", scope], cwd=ROOT, text=True).splitlines() == [name]
        return
    assert not subprocess.check_output(["git", "diff", CHECKPOINT, "--", scope], cwd=ROOT)
    assert not subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "--", scope], cwd=ROOT)
