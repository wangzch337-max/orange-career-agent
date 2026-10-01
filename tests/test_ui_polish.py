"""Presentation contracts, not pixel snapshots or a second evaluation framework."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import subprocess

import pytest
from streamlit.testing.v1 import AppTest

from ui.conversation import ConversationStage, GuidedConversation
from ui.demo_controller import APPROVED_ROLE_TITLES, DemoController
from ui.presentation import (
    CareerProfileView, MemorySummaryView, ProfileChipView, RoleMemoryView,
    career_direction_card_view, career_profile_view, match_insight_groups,
    memory_summary_view,
)
from ui.visual_system import (
    JOURNEY_LABELS, JOURNEY_STAGE, TOKENS, TRANSITIONS,
    badges_html, journey_html, panel_html, stylesheet,
)


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = "53aa2abb7861e3593a6f4d6bb4fa75c8fda75497"


def text(app):
    return "\n".join(str(item.value) for kind in
        ("title", "header", "subheader", "markdown", "caption", "info", "warning", "code")
        for item in getattr(app, kind))


@pytest.fixture
def completed():
    controller = DemoController()
    controller.start()
    controller.confirm_profile()
    yield controller
    controller.close()


def render(source, **state):
    app = AppTest.from_string(source, default_timeout=15)
    for key, value in state.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    return app


def test_authorized_phase8b_checkpoint_and_all_original_tests_preserved():
    message = subprocess.check_output(["git", "show", "-s", "--format=%s", CHECKPOINT], cwd=ROOT, text=True).strip()
    assert message == "feat: add safe observability diagnostics"
    originals = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", CHECKPOINT, "tests"], cwd=ROOT, text=True).splitlines()
    for name in originals:
        original = subprocess.check_output(["git", "show", f"{CHECKPOINT}:{name}"], cwd=ROOT)
        assert (ROOT / name).read_bytes() == original


def test_backend_prompts_providers_and_dependencies_frozen():
    for directory in ("agents", "data", "memory", "providers", "prompts", "workflows", "evaluation", "observability"):
        paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", CHECKPOINT, directory], cwd=ROOT, text=True).splitlines()
        for name in paths:
            original = subprocess.check_output(["git", "show", f"{CHECKPOINT}:{name}"], cwd=ROOT)
            assert (ROOT / name).read_bytes() == original
    for name in ("requirements.txt", "ui/demo_controller.py", "ui/conversation.py", "ui/presentation.py"):
        assert (ROOT / name).read_bytes() == subprocess.check_output(["git", "show", f"{CHECKPOINT}:{name}"], cwd=ROOT)


@pytest.mark.parametrize("key", ["title", "page", "section", "card", "body", "meta", "radius", "accent", "space-lg"])
def test_central_tokens_used_in_bounded_stylesheet(key):
    assert f"--orange-{key}:{TOKENS[key]}" in stylesheet()
    assert "var(--orange-" in stylesheet()
    for banned in ("https://", "@import", "<script", "iframe", "javascript:"):
        assert banned not in stylesheet()


@pytest.mark.parametrize("stage", list(ConversationStage))
def test_journey_is_textual_read_only_and_marks_only_current_stage(stage):
    html = journey_html(stage)
    assert html.count('aria-current="step"') == 1
    assert f"{JOURNEY_LABELS[JOURNEY_STAGE[stage]]} · 当前" in html
    assert "接下来" in html or stage == ConversationStage.PROFILE_REVIEW
    assert "%" not in html and "button" not in html
    assert TRANSITIONS[stage]


def test_html_helpers_escape_all_content_and_reject_unbounded_tones():
    for output in (badges_html((("<script>alert(1)</script>", "unknown"),)), panel_html("<img>", "<iframe>")):
        assert "<script>" not in output and "<img>" not in output and "<iframe>" not in output
        assert "&lt;" in output
    with pytest.raises(ValueError):
        badges_html((("x", 'neutral\" onclick=\"x'),))


def test_landing_positioning_mode_one_primary_cta_and_secondary_trace():
    app = AppTest.from_file(str(ROOT / "ui/app.py")).run()
    assert not app.exception
    body = text(app)
    for phrase in ("🍊 Orange", "通过对话理解自己", "不做岗位排名", "公开演示模式", "虚构数据", "离线 AI"):
        assert phrase in body
    assert app.session_state["orange_demo_controller"].state is None
    assert len([b for b in app.button if b.proto.type == "primary"]) == 1
    assert "开发者执行轨迹（安全）" in [e.label for e in app.expander]
    assert "诊断尚未开始" in body
    assert not app.get("progress")
    app.session_state["orange_demo_controller"].close()


@pytest.mark.parametrize("authority", ["已有证据", "用户刚刚表达", "待确认", "尚不确定"])
def test_profile_authority_states_remain_distinct(authority):
    chip = ProfileChipView("公开合成信号", authority)
    view = CareerProfileView((chip,), (), (), (), ())
    app = render("from ui.components import render_dynamic_profile\nimport streamlit as st\nrender_dynamic_profile(st.session_state.view)", view=view)
    assert ("你刚刚表达" if authority == "用户刚刚表达" else authority) in text(app)
    assert view.demonstrated_capabilities[0].authority == authority


def test_profile_empty_state_and_all_sections():
    app = render("from ui.components import render_dynamic_profile\nimport streamlit as st\nrender_dynamic_profile(st.session_state.view)", view=career_profile_view(GuidedConversation()))
    body = text(app)
    for phrase in ("随着对话进行", "已经表现出的能力", "比较感兴趣 / 投入的事情", "当前值得继续探索的方向", "还需要了解 / 证据不足", "当前目标"):
        assert phrase in body


def test_confirmation_gate_locked_state_cannot_be_bypassed():
    app = AppTest.from_file(str(ROOT / "ui/app.py"))
    app.session_state["orange_demo_page"] = "directions"
    app.run()
    assert "职业方向还未开放" in text(app)
    assert "AI Product Intern" not in text(app)
    assert app.session_state["orange_demo_page"] == "conversation"
    assert len(app.columns) >= 2
    assert not app.get("progress")
    app.session_state["orange_demo_controller"].close()


def test_equal_role_cards_and_meaning(completed):
    views = [career_direction_card_view(job, record, result, completed.confirmed_profile())
        for job, record, result in zip(completed.job_records(), completed.job_intelligence(), completed.match_results())]
    app = render("from ui.components import render_role_card\nimport streamlit as st\nfor i,v in enumerate(st.session_state.views):\n render_role_card(v,key=str(i))", views=views)
    assert tuple(item.value for item in app.subheader) == APPROVED_ROLE_TITLES
    assert len([b for b in app.button if b.label == "深入了解"]) == 3
    assert all(view.one_line in text(app) and view.clarification_need in text(app) for view in views)
    assert not [b for b in app.button if b.proto.type == "primary"]


def test_match_all_eight_groups_disclaimer_neutral_unknown_and_no_visual_score(completed):
    result, profile, record = completed.match_for("job_001"), completed.confirmed_profile(), completed.intelligence_for("job_001")
    before = result.model_dump(mode="json")
    app = render("from ui.components import render_match_insights\nimport streamlit as st\nrender_match_insights(st.session_state.result,st.session_state.profile,st.session_state.record)", result=result, profile=profile, record=record)
    assert "当前没有足够证据，不代表你不具备它。" in [i.value for i in app.info]
    assert "值得继续确认的摩擦" in text(app) and "目前还不知道" in text(app)
    labels = [e.label for e in app.expander]
    assert all(any(label.startswith(g.label) for label in labels) for g in match_insight_groups(result, profile, record))
    assert not app.get("progress") and not app.metric and not app.error
    assert result.model_dump(mode="json") == before


def test_actions_complete_does_not_confirm_profile_and_has_all_task_sections(completed):
    result = completed.match_for("job_001")
    before = completed.confirmed_profile().model_dump(mode="json")
    app = render("from ui.components import render_actions\nimport streamlit as st\nrender_actions(st.session_state.result,{},set())", result=result)
    for phrase in ("WHY · 为什么现在做", "WHAT · 具体怎么做", "EVIDENCE · 要留下什么证据", "已完成不等于能力已确认"):
        assert phrase in text(app)
    completed.set_action_status(result.action_items[0].action_id, "已完成")
    assert completed.confirmed_profile().model_dump(mode="json") == before


def test_no_action_empty_state_does_not_generate_work(completed):
    result = completed.match_for("job_001").model_copy(update={"action_items": []})
    app = render("from ui.components import render_actions\nimport streamlit as st\nrender_actions(st.session_state.result,{},set())", result=result)
    assert "不会为了填满页面生成任务" in text(app)
    assert not app.selectbox


def test_no_memory_empty_state_and_basis_separate(completed):
    app = render("from ui.components import render_role_memory\nimport streamlit as st\nrender_role_memory(st.session_state.view)", view=RoleMemoryView((), ()))
    assert "目前没有与这个岗位相关的已确认历史信息" in text(app)
    assert not app.expander
    statements = completed.role_memory_context("job_001")[1]
    from ui.presentation import role_memory_view
    records = tuple(completed.active_memories())
    view = role_memory_view(statements, records)
    app = render("from ui.components import render_role_memory\nimport streamlit as st\nrender_role_memory(st.session_state.view)", view=view)
    assert "来自你之前确认的信息" in text(app)
    assert "查看依据" in [e.label for e in app.expander]
    assert all(r.memory_id not in text(app) for r in records)


def test_current_and_history_presentation_preserves_truth(completed):
    view = memory_summary_view(completed.confirmed_profile(), completed.active_memories(), completed.profile_history())
    view = replace(view, historical_memory_preferences=("历史合成偏好 A", "历史合成偏好 B"))
    app = render("from ui.components import render_memory_summary\nimport streamlit as st\nrender_memory_summary(st.session_state.view)", view=view)
    assert "画像 v1 · 当前版本" in text(app) and "画像 v2" not in text(app)
    assert "历史合成偏好 A" in text(app) and "历史合成偏好 B" in text(app)
    history = next(e for e in app.expander if "画像版本与历史" in e.label)
    assert history.proto.expanded is False


@pytest.mark.parametrize("category", ["workflow_failure", "validation_failure", "unexpected_failure", "untrusted-exception-text"])
def test_safe_error_has_next_action_and_never_raw_exception(category):
    app = render("from ui.visual_system import render_safe_error\nfrom ui.presentation import safe_error_message\nimport streamlit as st\nrender_safe_error(safe_error_message(st.session_state.category))", category=category)
    assert "下一步" in text(app) and "重新开始 Demo" in text(app)
    assert "untrusted-exception-text" not in text(app)
    assert not app.exception


def test_long_content_smoke_escapes_and_preserves_full_label():
    label = "公开合成的长经历与待核对证据 " * 45 + "<not-html>"
    view = CareerProfileView((ProfileChipView(label, "已有证据"),), (), (), (), ())
    app = render("from ui.components import render_dynamic_profile\nimport streamlit as st\nrender_dynamic_profile(st.session_state.view)", view=view)
    assert label in text(app)
    assert "overflow-wrap:anywhere" in stylesheet()
    assert "@media (max-width:700px)" in stylesheet()


def test_presentation_only_dependency_and_no_external_assets_or_javascript():
    source = (ROOT / "ui/visual_system.py").read_text()
    imported = {n.module.split(".")[0] for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom) and n.module}
    assert imported <= {"__future__", "html", "types", "ui"}
    assert "<script" not in source and "https://" not in source and "iframe" not in source
    app = (ROOT / "ui/app.py").read_text()
    assert 'st.columns([1.08, 0.92], gap="large")' in app
    assert 'expanded=False' in (ROOT / "ui/components.py").read_text()
