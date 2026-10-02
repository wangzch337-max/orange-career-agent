"""Orange Interactive Demo v0.2 — conversation-first public offline workspace."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from ui.components import (
    apply_demo_style,
    render_actions,
    render_developer_trace,
    render_dynamic_profile,
    render_exploration_map,
    render_job_intelligence,
    render_match_insights,
    render_memory_summary,
    render_role_memory,
    render_profile_review,
    render_public_demo_banner,
    render_role_card,
)
from ui.conversation import QuestionKind
from ui.app_bar import render_app_bar
from ui.onboarding import render_onboarding
from ui.visual_system import TRANSITIONS, render_badges, render_journey, render_panel, render_safe_error
from ui.demo_controller import (
    APPROVED_ROLE_IDS,
    PROFILE_CALIBRATION_OPTIONS,
    ROLE_DEPRIORITIZATION_REASONS,
    ROLE_EXPLORATION_OPTIONS,
    DemoController,
    DemoControllerError,
)
from ui.presentation import (
    ASK_ORANGE_QUESTIONS,
    ROLE_CLARIFICATION_OPTIONS,
    ask_orange_answer,
    career_direction_card_view,
    memory_summary_view,
    role_memory_view,
    safe_error_message,
)
from memory.models import MemoryChangeChoice
from workflows.langgraph_state import GraphErrorCategory, GraphWorkflowStatus


SESSION_CONTROLLER = "orange_demo_controller"
SESSION_PAGE = "orange_demo_page"
SESSION_SELECTED_ROLE = "orange_selected_role"
SESSION_ERROR = "orange_demo_error"


def _initialize_session() -> DemoController:
    if SESSION_CONTROLLER not in st.session_state:
        st.session_state[SESSION_CONTROLLER] = DemoController()
    st.session_state.setdefault(SESSION_PAGE, "welcome")
    st.session_state.setdefault(SESSION_SELECTED_ROLE, None)
    st.session_state.setdefault(SESSION_ERROR, None)
    return st.session_state[SESSION_CONTROLLER]


def _go(page: str) -> None:
    st.session_state[SESSION_PAGE] = page
    st.rerun()


def _reset_demo() -> None:
    controller = st.session_state.get(SESSION_CONTROLLER)
    if isinstance(controller, DemoController):
        controller.close()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state[SESSION_CONTROLLER] = DemoController()
    st.session_state[SESSION_PAGE] = "welcome"
    st.session_state[SESSION_SELECTED_ROLE] = None
    st.session_state[SESSION_ERROR] = None
    st.session_state["orange_reset_notice"] = True
    st.rerun()


def _workflow_complete(controller: DemoController) -> bool:
    return bool(
        controller.state
        and controller.state["workflow_status"] == GraphWorkflowStatus.COMPLETED.value
    )


def _app_bar(controller: DemoController) -> None:
    render_app_bar(controller, go=_go, reset=_reset_demo)


def _welcome() -> None:
    st.title("🍊 Orange")
    st.subheader("通过对话理解自己，再用证据探索职业方向")
    st.write(
        "Orange 不会替你决定应该做什么工作。它会帮助你梳理经历与偏好、"
        "看见仍需验证的问题，并规划下一轮职业探索。"
    )
    st.caption("不做岗位排名 · 从理解你开始，而不是从岗位列表开始")
    with st.container(border=True):
        st.markdown("#### 这次对话会做什么")
        st.write("聊聊你的经历与偏好 → 一起校准职业画像 → 了解值得探索的方向 → 制定验证行动。")
    st.caption("开始职业探索 · 可以保留不确定，也不用现在选定一个职称")
    if st.button("开始和 Orange 对话", type="primary", use_container_width=True):
        _go("conversation")


def _conversation(controller: DemoController) -> None:
    question = controller.conversation.current_question
    if question is None:
        if controller.state is None:
            state = controller.prepare_profile_review()
            if state["workflow_status"] == GraphWorkflowStatus.FAILED.value:
                _set_graph_error(state)
                return
        _go("profile")
        return

    render_journey(controller.conversation.stage)
    left, right = st.columns([1.08, 0.92], gap="large")
    with left:
        st.markdown('<p class="orange-kicker">ORANGE 想先了解</p>', unsafe_allow_html=True)
        st.write(TRANSITIONS[question.stage])
        st.header(question.prompt)
        if question.helper:
            st.caption(question.helper)
        widget_key = f"guided_{question.stage.value}"
        if question.kind == QuestionKind.MULTIPLE:
            answer = st.multiselect("请选择", question.options, key=widget_key)
        else:
            answer = st.radio("请选择", question.options, index=None, key=widget_key)
        with st.expander("可选：再补充一句", expanded=False):
            note = st.text_input(
                "可选：再补充一句",
                max_chars=240,
                key=f"note_{question.stage.value}",
            )
        can_continue = bool(answer)
        if st.button(
            "继续",
            type="primary",
            disabled=not can_continue,
            use_container_width=True,
            key=f"continue_{question.stage.value}",
        ):
            next_stage = controller.submit_conversation_answer(
                question.stage,
                answer,
                note=note,
            )
            if next_stage.value == "profile_review":
                with st.spinner("正在整理公开合成证据…"):
                    state = controller.prepare_profile_review()
                if state["workflow_status"] == GraphWorkflowStatus.FAILED.value:
                    _set_graph_error(state)
                else:
                    _go("profile")
            else:
                st.rerun()
    with right:
        render_dynamic_profile(controller.career_profile_view())


def _profile(controller: DemoController) -> None:
    if controller.state is None:
        _go("conversation")
        return
    render_journey(controller.conversation.stage)
    left, right = st.columns([1.2, 0.8], gap="large")
    with left:
        render_profile_review(controller.profile_review_payload())
        st.markdown("### 快速校准")
        sections = ("能力", "兴趣与工作偏好", "探索方向与未知项", "当前目标")
        calibration: dict[str, str] = {}
        for section in sections:
            calibration[section] = st.radio(
                section,
                PROFILE_CALIBRATION_OPTIONS,
                horizontal=True,
                key=f"calibration_{section}",
            )
            controller.set_profile_calibration(section, calibration[section])
        wants_revision = "我想修改" in calibration.values()
        if wants_revision:
            st.info("v0.2 只使用现有 Phase 6 修订契约：可修改教育背景摘要，不开放任意画像编辑。")
            revised_summary = st.text_input("新的教育背景摘要", max_chars=500)
            if st.button(
                "提交画像修订",
                disabled=not revised_summary.strip(),
                use_container_width=True,
            ):
                controller.revise_profile_summary(revised_summary)
                st.success("已在同一工作流生成新版本，请再次校准。")
                st.rerun()
        if st.button(
            "确认这版职业画像",
            type="primary",
            disabled=wants_revision,
            use_container_width=True,
        ):
            with st.spinner("正在恢复同一工作流并整理三个探索方向…"):
                state = controller.confirm_profile()
            if state["workflow_status"] == GraphWorkflowStatus.FAILED.value:
                _set_graph_error(state)
            else:
                _go("directions")
    with right:
        render_dynamic_profile(controller.career_profile_view())


def _directions(controller: DemoController) -> None:
    st.header("值得探索的方向")
    st.write("下面不是排名，而是三个值得进一步了解的方向。")
    render_badges(("职业画像已确认", "confirmed"))
    st.caption("以下顺序不代表推荐排名；每个方向都有已有交集和仍需验证的部分。")
    jobs = controller.job_records()
    records = {item.job_id: item for item in controller.job_intelligence()}
    results = {item.job_id: item for item in controller.match_results()}
    profile = controller.confirmed_profile()
    columns = st.columns(3)
    for column, job in zip(columns, jobs):
        with column:
            view = career_direction_card_view(
                job,
                records[job.job_id],
                results[job.job_id],
                profile,
            )
            if render_role_card(view, key=f"select_{job.job_id}"):
                st.session_state[SESSION_SELECTED_ROLE] = job.job_id
                _go("role")


def _selected_role() -> str:
    selected = st.session_state.get(SESSION_SELECTED_ROLE)
    if selected not in APPROVED_ROLE_IDS:
        raise ValueError("Select an exploration direction first.")
    return selected


def _role(controller: DemoController) -> None:
    selected = _selected_role()
    job = controller.job_record(selected)
    record = controller.intelligence_for(selected)
    result = controller.match_for(selected)
    profile = controller.confirmed_profile()
    overview, clarify, ask = st.tabs(("岗位理解", "探索澄清", "和 Orange 聊聊这个岗位"))
    with overview:
        st.caption("这是值得了解的方向，不是适配结论。")
        render_job_intelligence(job, record)
        render_panel("你的情况", "以下交集来自当前已确认职业画像和已验证关系，不修改上方岗位事实。")
        card = career_direction_card_view(job, record, result, profile)
        st.markdown("### 你目前已有的交集")
        st.write("、".join(card.validated_overlaps) or "当前还没有直接证据")
        st.markdown("### 还需要确认什么")
        st.write(card.clarification_need)
        _, memory_statements = controller.role_memory_context(selected)
        memory_records = tuple(
            controller.memory_service.memory_store.get(
                controller.subject_id, memory_id
            )
            for statement in memory_statements
            for memory_id in statement.memory_refs
        )
        render_role_memory(
            role_memory_view(
                memory_statements,
                tuple(record for record in memory_records if record is not None),
            )
        )
    with clarify:
        st.header("先验证你对这种工作方式的真实感受")
        prompt = controller.role_clarification_prompt(selected)
        answer = st.radio(
            prompt,
            ROLE_CLARIFICATION_OPTIONS,
            index=None,
            key=f"role_answer_{selected}",
        )
        if st.button(
            "记录本次回答",
            disabled=answer is None,
            key=f"record_role_answer_{selected}",
        ):
            controller.answer_role_clarification(selected, answer)
            st.rerun()
        if selected in controller.role_clarifications:
            st.success("回答已用于本次探索。")
            memory_choice = st.radio(
                "要把这个偏好记入 Orange 对你的长期理解吗？",
                ("仅这次使用", "保存"),
                horizontal=True,
                key=f"memory_choice_{selected}",
            )
            if st.button("确认记忆方式", key=f"save_feedback_{selected}"):
                if memory_choice == "保存":
                    controller.save_role_clarification(selected)
                    st.success("已作为明确确认的用户反馈保存到本次 Demo Memory。")
                else:
                    st.info("保持为本次会话信息，没有写入 MemoryStore。")
        if selected == "job_001":
            st.divider()
            st.markdown("### 结构化偏好变化演示")
            st.caption("当前会话表达优先，但不会自动覆盖已确认的长期 Memory。")
            if st.button("表达：更愿意投入产品沟通与需求分析", key="structured_change"):
                candidate = controller.submit_structured_preference(
                    dimension="work_style.primary_focus",
                    value="product_and_requirement_work",
                    display_label="更愿意投入产品沟通与需求分析。",
                )
                if candidate is not None:
                    st.session_state["orange_memory_change_candidate"] = candidate.candidate_id
                st.rerun()
            candidate_id = st.session_state.get("orange_memory_change_candidate")
            candidate = controller.memory_change_candidates.get(candidate_id)
            if candidate is not None and candidate.status.value == "pending":
                st.warning("这和你现在的回答有些不同。要更新 Orange 对你的长期理解吗？")
                labels = {
                    "是，更新我的长期理解": MemoryChangeChoice.UPDATE_LONG_TERM,
                    "这次先不要修改": MemoryChangeChoice.DEFER,
                    "我还不确定": MemoryChangeChoice.UNCERTAIN,
                }
                selected_choice = st.radio(
                    "请选择",
                    tuple(labels),
                    index=None,
                    key="memory_change_choice",
                )
                if st.button(
                    "确认偏好处理方式",
                    disabled=selected_choice is None,
                    key="resolve_memory_change",
                ):
                    controller.resolve_memory_change(candidate.candidate_id, labels[selected_choice])
                    st.rerun()
            elif candidate is not None:
                status_copy = {
                    "confirmed": "已更新长期理解；画像仍等待单独确认",
                    "deferred": "这次先不要修改；当前表达只用于本次会话",
                    "uncertain": "我还不确定；长期理解保持不变",
                }
                signal = controller.structured_session_signals.get(candidate.dimension)
                if signal is not None:
                    st.write("当前会话表达：" + signal.display_label)
                st.info(status_copy.get(candidate.status.value, candidate.status.value))
        st.divider()
        decision = st.radio(
            "你现在想怎样安排这个方向？",
            ROLE_EXPLORATION_OPTIONS,
            index=None,
            horizontal=True,
            key=f"role_decision_{selected}",
        )
        reason = None
        if decision == "暂时不考虑":
            reason = st.radio(
                "主要原因是什么？",
                ROLE_DEPRIORITIZATION_REASONS,
                index=None,
                key=f"role_reason_{selected}",
            )
        if st.button(
            "更新探索状态",
            disabled=decision is None or (decision == "暂时不考虑" and reason is None),
            key=f"save_role_decision_{selected}",
        ):
            controller.set_role_exploration(selected, decision, reason=reason)
            st.success("已更新本次探索地图；这不是能力差距或不适合结论。")
    with ask:
        st.header("你想先了解哪件事？")
        question = st.selectbox(
            "选择一个问题",
            ASK_ORANGE_QUESTIONS,
            key=f"ask_orange_{selected}",
        )
        st.write(ask_orange_answer(question, record, result, profile))
        st.caption("回答来自预定义菜单和已验证数据；这里没有自由聊天或在线模型。")
    nav = st.columns(3)
    if nav[0].button("查看 Match Insights", type="primary", use_container_width=True):
        _go("match")
    if nav[1].button("查看行动计划", use_container_width=True):
        _go("actions")
    if nav[2].button("回到方向", use_container_width=True):
        _go("directions")


def _match(controller: DemoController) -> None:
    selected = _selected_role()
    render_match_insights(
        controller.match_for(selected),
        controller.confirmed_profile(),
        controller.intelligence_for(selected),
    )
    follow_up = controller.memory_aware_match_follow_up(selected)
    if follow_up is not None:
        with st.container(border=True):
            st.markdown("### 来自长期理解的补充问题")
            st.write(follow_up.text)
            st.caption("来自你之前确认的信息；与已验证 Match 洞察分开展示，不改变关系结论。")
    columns = st.columns(2)
    if columns[0].button("打开行动计划", type="primary", use_container_width=True):
        _go("actions")
    if columns[1].button("返回岗位", use_container_width=True):
        _go("role")


def _actions(controller: DemoController) -> None:
    selected = _selected_role()
    result = controller.match_for(selected)
    events = render_actions(
        result,
        controller.action_statuses,
        controller.actions_needing_evidence_review,
    )
    changed = False
    for action_id, status, already_done in events:
        if controller.action_status(action_id) != status:
            controller.set_action_status(action_id, status)
            changed = True
        if already_done:
            controller.mark_action_already_done(action_id)
            changed = True
    if changed:
        st.rerun()
    if st.button("查看 Career Exploration Map", type="primary", use_container_width=True):
        _go("map")


def _map(controller: DemoController) -> None:
    render_exploration_map(controller.exploration_map())
    if st.button("查看 Orange 对你的长期理解", type="primary", use_container_width=True):
        _go("memory")


def _memory(controller: DemoController) -> None:
    profile = controller.current_profile_from_memory()
    if profile is None:
        render_panel("长期理解还未形成", "当前没有已确认画像。完成对话并确认职业画像后，才会展示你确认的信息。")
        return
    view = memory_summary_view(
        profile,
        controller.active_memories(),
        controller.profile_history(),
        controller.memory_service.memory_store.list_history(controller.subject_id),
        (
            controller.pending_profile_refinement.draft_profile
            if controller.pending_profile_refinement is not None
            else None
        ),
    )
    render_memory_summary(view)
    if controller.pending_profile_refinement is not None:
        st.markdown("### 职业画像修订 · 待确认")
        st.write("当前会话已生成画像草案，但尚未确认，也尚未改变 MatchResult。")
        if st.button("确认画像修订", type="primary"):
            controller.confirm_pending_profile_refinement()
            st.success("已确认新画像版本；未来 Match 需通过正常流程重新运行。")
            st.rerun()


def _set_graph_error(state) -> None:
    category = state.get("safe_error", {}).get(
        "category", GraphErrorCategory.UNEXPECTED_FAILURE.value
    )
    st.session_state[SESSION_ERROR] = (
        "validation_failure"
        if category == GraphErrorCategory.VALIDATION_FAILURE.value
        else "workflow_failure"
    )
    _go("error")


def _error() -> None:
    st.header("Demo 需要重新开始")
    render_safe_error(safe_error_message(st.session_state.get(SESSION_ERROR) or "unexpected_failure"))


def main() -> None:
    st.set_page_config(
        page_title="Orange · 职业探索",
        page_icon="🍊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_demo_style()
    controller = _initialize_session()
    _app_bar(controller)
    render_public_demo_banner()
    if st.session_state.pop("orange_reset_notice", False):
        st.success("已重新开始公开演示。上一轮会话、长期理解和诊断已清空。")
    page = st.session_state[SESSION_PAGE]
    protected = {"directions", "role", "match", "actions", "map", "memory"}
    if page in protected and not _workflow_complete(controller):
        render_panel("职业方向还未开放", "请先完成对话并确认职业画像。Orange 不会跳过你的确认直接给出岗位方向。")
        page = "profile" if controller.state else "conversation"
        st.session_state[SESSION_PAGE] = page
    try:
        {
            "welcome": _welcome,
            "conversation": lambda: _conversation(controller),
            "profile": lambda: _profile(controller),
            "directions": lambda: _directions(controller),
            "role": lambda: _role(controller),
            "match": lambda: _match(controller),
            "actions": lambda: _actions(controller),
            "map": lambda: _map(controller),
            "memory": lambda: _memory(controller),
            "error": _error,
        }[page]()
    except DemoControllerError:
        st.session_state[SESSION_ERROR] = "workflow_failure"
        render_safe_error(safe_error_message("workflow_failure"))
    except (KeyError, TypeError, ValueError):
        st.session_state[SESSION_ERROR] = "validation_failure"
        render_safe_error(safe_error_message("validation_failure"))
    except Exception:
        st.session_state[SESSION_ERROR] = "unexpected_failure"
        render_safe_error(safe_error_message("unexpected_failure"))
    render_developer_trace(controller.safe_trace(), controller.diagnostics_snapshot())
    render_onboarding()


if __name__ == "__main__":
    main()
