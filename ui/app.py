"""Orange Interactive Demo v0.1 — public synthetic, offline Streamlit UI."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from ui.components import (
    render_actions,
    render_developer_trace,
    render_job_intelligence,
    render_match_insights,
    render_profile_review,
    render_progress,
    render_public_demo_banner,
    render_role_card,
)
from ui.demo_controller import (
    APPROVED_ROLE_IDS,
    DemoController,
    DemoControllerError,
)
from ui.presentation import safe_error_message
from workflows.langgraph_state import GraphErrorCategory, GraphWorkflowStatus


SESSION_CONTROLLER = "orange_demo_controller"
SESSION_PAGE = "orange_demo_page"
SESSION_SELECTED_ROLE = "orange_selected_role"
SESSION_ERROR = "orange_demo_error"

PAGE_STEPS = {
    "welcome": 1,
    "about": 2,
    "profile": 3,
    "roles": 4,
    "match": 5,
    "actions": 6,
    "memory": 7,
    "error": 1,
}


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
    st.rerun()


def _workflow_complete(controller: DemoController) -> bool:
    return bool(
        controller.state
        and controller.state["workflow_status"] == GraphWorkflowStatus.COMPLETED.value
    )


def _sidebar(controller: DemoController) -> None:
    with st.sidebar:
        st.markdown("## 🍊 Orange")
        st.caption("Interactive Demo v0.1")
        state = controller.state
        if state is None:
            st.caption("画像：尚未分析")
        elif state["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value:
            st.caption("画像：等待确认")
        elif state["workflow_status"] == GraphWorkflowStatus.COMPLETED.value:
            st.caption("画像：已确认 · 岗位与匹配已完成")
        else:
            st.caption("流程：需要处理")

        if st.button("欢迎", key="nav_welcome", use_container_width=True):
            _go("welcome")
        if st.button("关于你", key="nav_about", use_container_width=True):
            _go("about")
        if state and state["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value:
            if st.button("画像确认", key="nav_profile", use_container_width=True):
                _go("profile")
        if _workflow_complete(controller):
            if st.button("岗位探索", key="nav_roles", use_container_width=True):
                _go("roles")
            if st.button("匹配洞察", key="nav_match", use_container_width=True):
                _go("match")
            if st.button("行动计划", key="nav_actions", use_container_width=True):
                _go("actions")
            if st.button("Orange Memory", key="nav_memory", use_container_width=True):
                _go("memory")
        st.divider()
        if st.button("重新开始 Demo", key="reset_demo", use_container_width=True):
            _reset_demo()


def _welcome() -> None:
    render_progress(1)
    st.title("🍊 Orange")
    st.subheader("AI Career Discovery Agent for University Students")
    st.markdown("### 理解自己。理解岗位。基于证据做职业选择。")
    st.write(
        "这是一条完整但克制的职业探索演示：从合成学生背景出发，经过画像确认，"
        "再查看三个代表岗位的证据关系与行动。"
    )
    badges = st.columns(3)
    badges[0].success("Public Demo")
    badges[1].success("Synthetic Data")
    badges[2].success("Offline AI Demo")
    if st.button("开始职业探索", type="primary", use_container_width=True):
        _go("about")


def _about(controller: DemoController) -> None:
    render_progress(2)
    st.header("关于你 · 合成演示学生")
    persona = controller.public_persona
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("#### 教育背景")
            st.write(persona["program"])
        with st.container(border=True):
            st.markdown("#### 项目经历")
            project = persona["project_experience"]
            st.write(project["name"])
            st.caption(project["summary"])
    with right:
        with st.container(border=True):
            st.markdown("#### 职业探索方向")
            st.write(persona["career_interest"])
            st.caption(persona["career_goal"])
        with st.container(border=True):
            st.markdown("#### 目标地区")
            st.write("中国内地代表城市 · 公开虚构岗位")
    if st.button("分析我的职业画像", type="primary", use_container_width=True):
        with st.spinner("正在通过 Orange 工作流整理证据…"):
            state = controller.start()
        if state["workflow_status"] == GraphWorkflowStatus.FAILED.value:
            _set_graph_error(state)
        elif state["workflow_status"] == GraphWorkflowStatus.COMPLETED.value:
            st.session_state[SESSION_SELECTED_ROLE] = (
                st.session_state.get(SESSION_SELECTED_ROLE) or APPROVED_ROLE_IDS[0]
            )
            _go("roles")
        else:
            _go("profile")


def _profile(controller: DemoController) -> None:
    render_progress(3)
    render_profile_review(controller.profile_review_payload())
    if st.button("确认画像并继续", type="primary", use_container_width=True):
        with st.spinner("正在恢复同一工作流并分析三个岗位…"):
            state = controller.confirm_profile()
        if state["workflow_status"] == GraphWorkflowStatus.FAILED.value:
            _set_graph_error(state)
        else:
            st.session_state[SESSION_SELECTED_ROLE] = APPROVED_ROLE_IDS[0]
            _go("roles")


def _roles(controller: DemoController) -> None:
    render_progress(4)
    st.header("岗位探索")
    st.caption("固定展示三个代表岗位；顺序不表示推荐或排名。")
    jobs = controller.job_records()
    intelligence = {item.job_id: item for item in controller.job_intelligence()}
    columns = st.columns(3)
    for column, job in zip(columns, jobs):
        with column:
            if render_role_card(
                job,
                intelligence[job.job_id],
                key=f"select_{job.job_id}",
            ):
                st.session_state[SESSION_SELECTED_ROLE] = job.job_id
                st.rerun()
    selected = st.session_state.get(SESSION_SELECTED_ROLE) or APPROVED_ROLE_IDS[0]
    st.divider()
    render_job_intelligence(
        controller.job_record(selected),
        controller.intelligence_for(selected),
    )
    if st.button("查看匹配洞察", type="primary", use_container_width=True):
        _go("match")


def _match(controller: DemoController) -> None:
    render_progress(5)
    selected = st.session_state.get(SESSION_SELECTED_ROLE) or APPROVED_ROLE_IDS[0]
    render_match_insights(
        controller.match_for(selected),
        controller.confirmed_profile(),
        controller.intelligence_for(selected),
    )
    if st.button("查看行动计划", type="primary", use_container_width=True):
        _go("actions")


def _actions(controller: DemoController) -> None:
    render_progress(6)
    selected = st.session_state.get(SESSION_SELECTED_ROLE) or APPROVED_ROLE_IDS[0]
    render_actions(controller.match_for(selected))
    if st.button("查看 Orange Memory", type="primary", use_container_width=True):
        _go("memory")


def _memory(controller: DemoController) -> None:
    render_progress(7)
    st.header("Orange Memory")
    profile = controller.current_profile_from_memory()
    if profile is None:
        st.warning("当前没有已确认画像。")
        return
    with st.container(border=True):
        st.markdown("#### 当前画像")
        st.write(f"Version {profile.version} · Confirmed")
        preferences = [item.label for item in profile.career_preferences]
        st.write("职业偏好：" + ("、".join(preferences) or "暂无"))
    active = controller.active_memories()
    with st.container(border=True):
        st.markdown("#### 长期确认信息")
        if not active:
            st.caption("当前没有单独保存的已确认 MemoryRecord。")
        for memory in active:
            st.write(f"{memory.memory_type.value} · {memory.content}")
    with st.container(border=True):
        st.markdown("#### 画像历史")
        history = controller.profile_history()
        for item in history:
            current = "Current" if item.version == profile.version else "Historical"
            st.write(f"v{item.version} — {current}")


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
    render_progress(1)
    st.header("Demo 需要重新开始")
    st.error(safe_error_message(st.session_state.get(SESSION_ERROR) or "unexpected_failure"))


def main() -> None:
    st.set_page_config(
        page_title="Orange Interactive Demo",
        page_icon="🍊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    controller = _initialize_session()
    _sidebar(controller)
    render_public_demo_banner()
    page = st.session_state[SESSION_PAGE]
    if page in {"roles", "match", "actions", "memory"} and not _workflow_complete(
        controller
    ):
        page = "profile" if controller.state else "about"
        st.session_state[SESSION_PAGE] = page
    try:
        {
            "welcome": _welcome,
            "about": lambda: _about(controller),
            "profile": lambda: _profile(controller),
            "roles": lambda: _roles(controller),
            "match": lambda: _match(controller),
            "actions": lambda: _actions(controller),
            "memory": lambda: _memory(controller),
            "error": _error,
        }[page]()
    except DemoControllerError:
        st.session_state[SESSION_ERROR] = "workflow_failure"
        st.error(safe_error_message("workflow_failure"))
    except (KeyError, TypeError, ValueError):
        st.session_state[SESSION_ERROR] = "validation_failure"
        st.error(safe_error_message("validation_failure"))
    except Exception:
        st.session_state[SESSION_ERROR] = "unexpected_failure"
        st.error(safe_error_message("unexpected_failure"))
    render_developer_trace(controller.safe_trace())


if __name__ == "__main__":
    main()
