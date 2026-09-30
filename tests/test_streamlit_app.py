"""Streamlit AppTest coverage for the full public vertical slice."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

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


def test_streamlit_full_vertical_slice_uses_real_interrupt_and_same_thread() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    assert not app.exception
    assert "🍊 Orange" in _text(app)
    assert "Public Demo" in _text(app)
    assert "Synthetic Data" in _text(app)
    assert "Offline AI Demo" in _text(app)

    _button(app, "开始职业探索").click().run()
    assert "关于你 · 合成演示学生" in _text(app)
    assert "Campus Helper Prototype" in _text(app)

    _button(app, "分析我的职业画像").click().run(timeout=15)
    controller = app.session_state["orange_demo_controller"]
    workflow_id = controller.workflow_id
    assert controller.state["workflow_status"] == "waiting_for_human"
    assert controller.state["__interrupt__"]
    assert controller.state["self_discovery_call_count"] == 1
    assert "认识自己 · 画像确认" in _text(app)
    for section in (
        "技能",
        "兴趣",
        "价值观",
        "目标",
        "优势",
        "发展方向",
        "职业偏好",
        "不确定项",
        "澄清问题",
    ):
        assert section in _text(app)

    _button(app, "确认画像并继续").click().run(timeout=15)
    controller = app.session_state["orange_demo_controller"]
    assert controller.workflow_id == workflow_id
    assert controller.state["workflow_id"] == workflow_id
    assert controller.state["workflow_status"] == "completed"
    assert controller.state["self_discovery_call_count"] == 1
    assert controller.dependencies.self_discovery_agent.llm_provider.call_count == 1
    assert controller.state["report"] is not None
    assert tuple(item.value for item in app.subheader[:3]) == APPROVED_ROLE_TITLES
    assert "顺序不表示推荐或排名" in _text(app)


def test_streamlit_role_match_action_memory_and_safe_trace_render() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    _button(app, "开始职业探索").click().run()
    _button(app, "分析我的职业画像").click().run(timeout=15)
    _button(app, "确认画像并继续").click().run(timeout=15)

    role_buttons = [item for item in app.button if item.label == "查看岗位"]
    assert len(role_buttons) == 3
    role_buttons[1].click().run()
    assert app.session_state["orange_selected_role"] == "job_007"
    assert "AI Application Engineer" in _text(app)
    assert "实际工作" in _text(app)
    assert "必需能力" in _text(app)

    _button(app, "查看匹配洞察").click().run()
    rendered = _text(app)
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
        assert relation_label in rendered
    assert "不代表你不具备它" in rendered
    lowered = rendered.casefold()
    for forbidden in ("overall_score", "fit %", "best role", "top pick", "leaderboard"):
        assert forbidden not in lowered

    _button(app, "查看行动计划").click().run()
    controller = app.session_state["orange_demo_controller"]
    result = controller.match_for("job_007")
    action_text = _text(app)
    assert all(item.description in action_text for item in result.action_items)
    assert all(item.expected_evidence in action_text for item in result.action_items)

    _button(app, "查看 Orange Memory").click().run()
    memory_text = _text(app)
    assert "Orange Memory" in memory_text
    assert "Version 1 · Confirmed" in memory_text
    assert "当前没有单独保存的已确认 MemoryRecord" in memory_text
    assert "v1 — Current" in memory_text

    trace_text = "\n".join(str(item.value) for item in app.code)
    assert "graph_interrupted" in trace_text
    assert "graph_resumed" in trace_text
    assert "graph_completed" in trace_text
    for forbidden in ("api_key", "authorization", "raw prompt", "chain-of-thought"):
        assert forbidden not in trace_text.casefold()


def test_reset_demo_replaces_session_runtime_and_clears_navigation() -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    _button(app, "开始职业探索").click().run()
    _button(app, "分析我的职业画像").click().run(timeout=15)
    controller = app.session_state["orange_demo_controller"]
    old_workflow = controller.workflow_id
    old_memory_path = controller.memory_service.database.path
    _button(app, "重新开始 Demo").click().run(timeout=15)
    new_controller = app.session_state["orange_demo_controller"]
    assert new_controller.workflow_id != old_workflow
    assert new_controller.memory_service.database.path != old_memory_path
    assert new_controller.state is None
    assert app.session_state["orange_demo_page"] == "welcome"
    assert app.session_state["orange_selected_role"] is None
    assert "🍊 Orange" in _text(app)
