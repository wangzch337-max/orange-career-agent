"""Streamlit AppTest coverage for the conversation-first public Demo."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest
from tests.ui_legacy import legacy_app

from ui.demo_controller import APPROVED_ROLE_TITLES


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "ui" / "app.py"


def _button(app: AppTest, label: str):
    return next(item for item in app.button if item.label == label)


def _text(app: AppTest) -> str:
    values = []
    for collection in (
        app.title,
        app.header,
        app.subheader,
        app.markdown,
        app.caption,
        app.info,
        app.success,
        app.warning,
        app.error,
        app.code,
    ):
        values.extend(str(item.value) for item in collection)
    return "\n".join(values)


def _single(app: AppTest, value: str) -> None:
    app.radio[0].set_value(value).run()
    _button(app, "继续").click().run()


def _multiple(app: AppTest, values: list[str]) -> None:
    app.multiselect[0].set_value(values).run()
    _button(app, "继续").click().run()


def _reach_profile_review(app: AppTest) -> None:
    _button(app, "开始和 Orange 对话").click().run()
    _single(app, "我有几个方向，但不知道怎么选")
    _single(app, "把一个想法真正做成系统")
    _single(app, "把多个 API / 模块连起来")
    _multiple(
        app,
        ["用现有 AI / LLM 做真正的应用", "思考 AI 应该解决什么用户问题"],
    )
    _single(app, "Campus Helper Prototype")
    _multiple(app, ["Python", "API integration"])
    _single(app, "大部分时间亲手实现东西")
    _single(app, "做出真正可使用的产品")


def _complete_profile(app: AppTest) -> None:
    _reach_profile_review(app)
    _button(app, "确认这版职业画像").click().run(timeout=15)


def test_streamlit_conversation_then_real_interrupt_and_same_thread() -> None:
    app = legacy_app(default_timeout=15).run()
    assert not app.exception
    assert "🍊 Orange" in _text(app)
    assert "公开演示模式" in _text(app)
    assert "不做岗位排名" in _text(app)

    _button(app, "开始和 Orange 对话").click().run()
    assert "你现在最想解决的职业问题是什么？" in _text(app)
    assert "你的动态职业画像" in _text(app)
    assert "Profile 60%" not in _text(app)

    _single(app, "我有几个方向，但不知道怎么选")
    assert "哪类事情最容易让你投入" in _text(app)
    _single(app, "把一个想法真正做成系统")
    assert "最享受哪部分" in _text(app)
    _single(app, "把多个 API / 模块连起来")
    assert "哪些更吸引你" in _text(app)
    _multiple(app, ["用现有 AI / LLM 做真正的应用"])
    _single(app, "Campus Helper Prototype")
    _multiple(app, ["Python"])
    _single(app, "大部分时间亲手实现东西")
    _single(app, "做出真正可使用的产品")

    controller = app.session_state["orange_demo_controller"]
    workflow_id = controller.workflow_id
    assert controller.state["workflow_status"] == "waiting_for_human"
    assert controller.state["__interrupt__"]
    assert controller.state["self_discovery_call_count"] == 1
    assert "这是我目前对你的理解" in _text(app)
    assert "查看完整画像分类" in [item.label for item in app.expander]

    _button(app, "确认这版职业画像").click().run(timeout=15)
    controller = app.session_state["orange_demo_controller"]
    assert controller.workflow_id == workflow_id
    assert controller.state["workflow_id"] == workflow_id
    assert controller.state["workflow_status"] == "completed"
    assert controller.state["self_discovery_call_count"] == 1
    assert controller.dependencies.self_discovery_agent.llm_provider.call_count == 1
    assert tuple(item.value for item in app.subheader[:3]) == APPROVED_ROLE_TITLES
    assert "下面不是排名" in _text(app)


def test_streamlit_role_feedback_match_action_map_and_memory() -> None:
    app = legacy_app(default_timeout=15).run()
    _complete_profile(app)

    role_buttons = [item for item in app.button if item.label == "深入了解"]
    assert len(role_buttons) == 3
    role_buttons[0].click().run()
    assert app.session_state["orange_selected_role"] == "job_001"
    rendered = _text(app)
    assert "一句" not in rendered
    assert "岗位理解" in [item.label for item in app.tabs]
    assert "和 Orange 聊聊这个岗位" in [item.label for item in app.tabs]
    assert "预定义菜单" in rendered

    role_question = next(item for item in app.radio if "产品方案" in item.label)
    role_question.set_value("很喜欢").run()
    _button(app, "记录本次回答").click().run()
    controller = app.session_state["orange_demo_controller"]
    before_ids = {item.memory_id for item in controller.active_memories()}
    memory_choice = next(item for item in app.radio if "长期理解" in item.label)
    memory_choice.set_value("保存").run()
    _button(app, "确认记忆方式").click().run()
    assert len({item.memory_id for item in controller.active_memories()} - before_ids) == 1

    _button(app, "查看 Match Insights").click().run()
    match_text = _text(app)
    match_labels = match_text + "\n" + "\n".join(item.label for item in app.expander)
    for relation_label in (
        "明确契合",
        "部分契合",
        "证据缺失",
        "已确认差距",
        "经验深度差距",
        "偏好契合",
        "潜在摩擦",
        "尚不确定",
    ):
        assert relation_label in match_labels
    assert "不代表你不具备它" in match_text
    assert "不代表你不适合" in match_text

    _button(app, "打开行动计划").click().run()
    action_text = _text(app)
    assert "WHY · 为什么现在做" in action_text
    assert "WHAT · 具体怎么做" in action_text
    assert "EVIDENCE · 要留下什么证据" in action_text
    result = controller.match_for("job_001")
    assert all(item.description in action_text for item in result.action_items)
    assert all(item.expected_evidence in action_text for item in result.action_items)

    if app.selectbox:
        action_status = next(item for item in app.selectbox if "当前状态" in item.label)
        action_status.set_value("进行中").run()
        assert "进行中" in controller.action_statuses.values()

    _button(app, "查看 Career Exploration Map").click().run()
    assert "这不是最终职业决定" in _text(app)
    assert "保持开放" in _text(app)
    _button(app, "查看 Orange 对你的长期理解").click().run()
    memory_text = _text(app)
    assert "Orange 对你的长期理解" in memory_text
    assert "你后来告诉 Orange" in memory_text
    assert "AI Product Intern" in memory_text
    assert "画像 v1 · 当前版本" in memory_text

    trace_text = "\n".join(str(item.value) for item in app.code)
    assert "graph_interrupted" in trace_text
    assert "graph_resumed" in trace_text
    assert "graph_completed" in trace_text
    for forbidden in ("api_key", "authorization", "raw prompt", "chain-of-thought"):
        assert forbidden not in trace_text.casefold()


def test_reset_demo_clears_every_v02_session_concern() -> None:
    app = legacy_app(default_timeout=15).run()
    _complete_profile(app)
    [item for item in app.button if item.label == "深入了解"][1].click().run()
    controller = app.session_state["orange_demo_controller"]
    old_workflow = controller.workflow_id
    old_subject = controller.subject_id
    old_memory_path = controller.memory_service.database.path
    controller.answer_role_clarification("job_007", "可以接受")
    controller.set_role_exploration("job_007", "继续探索")
    action = controller.match_for("job_007").action_items[0]
    controller.set_action_status(action.action_id, "进行中")

    _button(app, "重新开始 Demo").click().run(timeout=15)
    new_controller = app.session_state["orange_demo_controller"]
    assert new_controller.workflow_id != old_workflow
    assert new_controller.subject_id != old_subject
    assert new_controller.memory_service.database.path != old_memory_path
    assert new_controller.state is None
    assert not new_controller.conversation.answers
    assert not new_controller.role_clarifications
    assert not new_controller.role_exploration
    assert not new_controller.action_statuses
    assert not new_controller.structured_session_signals
    assert not new_controller.memory_change_candidates
    assert not new_controller.role_memory_contexts
    assert new_controller.pending_profile_refinement is None
    assert app.session_state["orange_demo_page"] == "welcome"
    assert app.session_state["orange_selected_role"] is None
    assert "🍊 Orange" in _text(app)
