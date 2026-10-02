"""Lightweight native Streamlit navigation; no new workflow authority."""

from dataclasses import dataclass
from collections.abc import Callable

import streamlit as st

from ui.onboarding import request_replay
from ui.onboarding.assets import leaf_markup, sphere_markup
from workflows.langgraph_state import GraphWorkflowStatus


@dataclass(frozen=True)
class NavigationItem:
    page: str
    key: str
    label: str
    secondary: bool = False


def navigation_items(status: str | None, has_role: bool) -> tuple[NavigationItem, ...]:
    """Expose exactly the destinations allowed by the previous sidebar."""
    items = [NavigationItem("welcome", "nav_welcome", "职业探索")]
    if status != GraphWorkflowStatus.COMPLETED.value:
        items.append(NavigationItem("profile" if status else "conversation", "nav_conversation", "引导对话"))
    if status == GraphWorkflowStatus.WAITING_FOR_HUMAN.value:
        items.append(NavigationItem("profile", "nav_profile", "画像确认"))
    if status == GraphWorkflowStatus.COMPLETED.value:
        items.append(NavigationItem("directions", "nav_directions", "岗位方向"))
        if has_role:
            items.extend((
                NavigationItem("role", "nav_role", "岗位深入了解", True),
                NavigationItem("match", "nav_match", "Match Insights", True),
                NavigationItem("actions", "nav_actions", "行动计划"),
            ))
        items.extend((
            NavigationItem("map", "nav_map", "Career Exploration Map", True),
            NavigationItem("memory", "nav_memory", "长期理解"),
        ))
    return tuple(items)


def app_bar_stylesheet(active_keys: tuple[str, ...], *, more_active: bool = False) -> str:
    """Stable native test IDs and user-defined keys only; never generated classes."""
    active = ",".join(f".st-key-{key} button" for key in active_keys)
    return """<style>
    [data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display:none;}
    [data-testid="stMainBlockContainer"] {padding-top:1.25rem;}
    .st-key-orange_app_bar {border-bottom:1px solid var(--orange-line); padding-bottom:.7rem; margin-bottom:.35rem;}
    .st-key-orange_app_bar [data-testid="stHorizontalBlock"] {align-items:center; flex-wrap:nowrap !important; gap:.45rem;}
    .st-key-orange_app_bar [data-testid="stColumn"] {min-width:0 !important;}
    .st-key-orange_app_bar [data-testid="stMarkdownContainer"] {min-height:36px; display:flex; align-items:center;}
    .st-key-orange_desktop_nav [data-testid="stColumn"] {flex:0 1 auto !important; width:auto !important;}
    .st-key-orange_app_bar button {border:0; border-radius:999px; background:transparent; font-size:.88rem; white-space:nowrap;}
    .st-key-orange_app_bar button:hover {background:var(--orange-accent-soft);}
    .orange-brand {display:flex; align-items:center; gap:8px; font-size:20px; font-weight:650; color:var(--orange-ink); white-space:nowrap;}
    .orange-brand-icon {position:relative; display:block; width:34px; height:34px; flex:none;}
    .orange-brand-icon > svg {display:block; width:100%; height:100%;}
    .orange-brand-leaf {position:absolute; left:55%; top:25%; width:23%; opacity:.88;}
    .orange-brand-leaf svg {display:block; width:100%; height:auto;}
    .st-key-orange_mobile_nav {display:none;}
    .st-key-orange_app_bar [data-testid="stLayoutWrapper"]:has(> .st-key-orange_mobile_nav) {display:none;}
    .st-key-orange_public_status {font-size:.76rem; color:var(--orange-muted); text-align:right; white-space:nowrap;}
    """ + (f"{active} {{color:var(--orange-accent); background:var(--orange-accent-soft); font-weight:650;}}" if active else "") + (
        '.st-key-orange_more_nav [data-testid="stPopoverButton"] {color:var(--orange-accent); background:var(--orange-accent-soft); font-weight:650;}'
        if more_active else ""
    ) + """
    @media (max-width:900px) {
      .st-key-orange_desktop_nav {display:none;}
      .st-key-orange_app_bar [data-testid="stLayoutWrapper"]:has(> .st-key-orange_desktop_nav) {display:none;}
      .st-key-orange_mobile_nav {display:block;}
      .st-key-orange_app_bar [data-testid="stLayoutWrapper"]:has(> .st-key-orange_mobile_nav) {display:block;}
      .st-key-orange_app_bar > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {flex:1 1 0 !important; width:auto !important;}
      .st-key-orange_app_bar button {padding-left:.45rem; padding-right:.45rem;}
      .orange-brand {font-size:18px; gap:4px;}
      .orange-brand-icon {width:28px; height:28px;}
    }
    </style>"""


def render_app_bar(controller, *, go: Callable[[str], None], reset: Callable[[], None]) -> None:
    """Move navigation/reset surfaces only; the app retains its protected-route gate."""
    state = controller.state
    status = state["workflow_status"] if state else None
    items = navigation_items(status, bool(st.session_state.get("orange_selected_role")))
    page = st.session_state.get("orange_demo_page", "welcome")
    candidates = tuple(item.key for item in items if item.page == page)
    active = candidates[-1:]  # Profile confirmation has one active destination, not two.
    more_active = any(item.page == page and item.secondary for item in items)
    st.markdown(app_bar_stylesheet(active + tuple(f"compact_{key}" for key in active), more_active=more_active), unsafe_allow_html=True)
    mascot = f'<span class="orange-brand-icon">{sphere_markup()}<span class="orange-brand-leaf">{leaf_markup()}</span></span>'

    def button(item: NavigationItem, prefix: str = "") -> None:
        if st.button(item.label, key=prefix + item.key, use_container_width=True):
            # Re-evaluate allowed navigation on every server-side interaction.
            if item in navigation_items(status, bool(st.session_state.get("orange_selected_role"))):
                go(item.page)

    with st.container(key="orange_app_bar"):
        brand, navigation, public, utilities = st.columns([1.65, 6.5, 1, .55], vertical_alignment="center")
        with brand:
            st.markdown(f'<div class="orange-brand">{mascot}<span>Orange</span></div>', unsafe_allow_html=True)
        with navigation:
            with st.container(key="orange_desktop_nav"):
                primary = tuple(item for item in items if not item.secondary)
                secondary = tuple(item for item in items if item.secondary)
                columns = st.columns(len(primary) + bool(secondary))
                for column, item in zip(columns, primary):
                    with column:
                        button(item)
                if secondary:
                    with columns[-1], st.container(key="orange_more_nav"), st.popover("更多页面", use_container_width=True):
                        for item in secondary:
                            button(item)
            with st.container(key="orange_mobile_nav"):
                with st.popover("导航", use_container_width=True):
                    for item in items:
                        button(item, "compact_")
        with public:
            st.markdown('<div class="st-key-orange_public_status">公开演示</div>', unsafe_allow_html=True)
        with utilities, st.popover("···", use_container_width=True):
            if st.button("重新播放介绍", key="replay_intro", use_container_width=True):
                request_replay()
                st.rerun()
            st.caption("仅重置本次公开演示，不影响真实资料。")
            if st.button("重新开始 Demo", key="reset_demo", use_container_width=True):
                reset()
