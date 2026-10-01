"""Small presentation-only Orange system; never determines domain authority."""

from __future__ import annotations

from html import escape
from types import MappingProxyType

import streamlit as st

from ui.conversation import ConversationStage


# One bounded palette, scale and surface vocabulary; no font/CDN/JS dependency.
TOKENS = MappingProxyType({
    "ink": "#202a35", "muted": "#596574", "accent": "#9a4209",
    "accent-soft": "#fff0df", "surface": "#ffffff", "canvas": "#faf9f6",
    "line": "#e3e5e8", "neutral": "#eef1f4", "confirmed": "#e9f4ee",
    "space-xs": ".35rem", "space-sm": ".7rem", "space-md": "1rem",
    "space-lg": "1.5rem", "space-xl": "2rem", "radius": "14px",
    "title": "2.65rem", "page": "1.85rem", "section": "1.3rem",
    "card": "1.08rem", "body": "1rem", "meta": ".85rem",
})


def stylesheet() -> str:
    variables = ";".join(f"--orange-{key}:{value}" for key, value in TOKENS.items())
    # Use semantic elements and stable Streamlit test IDs, not generated classes.
    return "<style>:root{" + variables + "}" + """
    .stApp {background:var(--orange-canvas); color:var(--orange-ink);}
    [data-testid="stMainBlockContainer"] {max-width:1200px; padding-top:calc(3.75rem + var(--orange-space-md)); padding-bottom:3rem;}
    h1 {font-size:var(--orange-title)!important; letter-spacing:-.025em;}
    h2 {font-size:var(--orange-page)!important; margin-top:var(--orange-space-lg);}
    h3 {font-size:var(--orange-section)!important;}
    h4 {font-size:var(--orange-card)!important;}
    p, li {line-height:1.65; overflow-wrap:anywhere;}
    [data-testid="stCaptionContainer"] {color:var(--orange-muted);}
    [data-testid="stSidebar"] {background:var(--orange-surface); color:var(--orange-ink); border-right:1px solid var(--orange-line);}
    [data-testid="stSidebar"] h2 {color:var(--orange-ink);}
    [data-testid="stWidgetLabel"],
    [data-testid="stRadio"] [data-testid="stRadioOption"],
    [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"],
    [data-testid="stCheckbox"] [data-baseweb="checkbox"],
    [data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] {color:var(--orange-ink);}
    [data-testid="stVerticalBlockBorderWrapper"] {border-radius:var(--orange-radius); background:var(--orange-surface);}
    [data-testid="stBaseButton-primary"] {background:var(--orange-accent); border-color:var(--orange-accent); color:white;}
    button {min-height:2.6rem; white-space:normal;}
    button:focus-visible, input:focus-visible {outline:2px solid var(--orange-accent); outline-offset:3px;}
    .orange-kicker {color:var(--orange-accent); font-size:var(--orange-meta); font-weight:700; letter-spacing:.06em; margin-bottom:.4rem;}
    .orange-badges {display:flex; flex-wrap:wrap; gap:var(--orange-space-xs); margin:.4rem 0 .7rem;}
    .orange-badge {display:inline-block; font-size:var(--orange-meta); font-weight:600; padding:.2rem .65rem; border-radius:999px; background:var(--orange-neutral); color:var(--orange-ink); overflow-wrap:anywhere;}
    .orange-badge--evidence, .orange-badge--confirmed {background:var(--orange-confirmed);}
    .orange-badge--expressed, .orange-badge--pending {background:var(--orange-accent-soft);}
    .orange-panel {padding:var(--orange-space-md) var(--orange-space-lg); border:1px solid var(--orange-line); border-radius:var(--orange-radius); background:var(--orange-surface); margin-bottom:var(--orange-space-md);}
    .orange-panel p {margin:.4rem 0 0; color:var(--orange-muted); max-width:70ch;}
    .orange-panel strong {font-size:var(--orange-card);}
    .orange-journey {display:flex; flex-wrap:wrap; gap:.45rem; padding:0; margin:.7rem 0 1.5rem; list-style:none;}
    .orange-journey li {font-size:var(--orange-meta); padding:.35rem .7rem; border-radius:999px; border:1px solid var(--orange-line); color:var(--orange-muted);}
    .orange-journey .current {background:var(--orange-accent-soft); color:var(--orange-accent); border-color:var(--orange-accent); font-weight:700;}
    @media (max-width:700px) {
      [data-testid="stMainBlockContainer"] {padding-left:1rem; padding-right:1rem;}
      h1 {font-size:2.1rem!important;} h2 {font-size:1.5rem!important;}
      [data-testid="stHorizontalBlock"] {flex-wrap:wrap;}
      [data-testid="stColumn"] {min-width:min(100%,280px); flex:1 1 280px!important;}
      .orange-panel {padding:var(--orange-space-md);}
    }
    </style>"""


BADGE_TONES = frozenset({"neutral", "evidence", "expressed", "pending", "unknown", "confirmed"})


def badges_html(items: tuple[tuple[str, str], ...]) -> str:
    if any(tone not in BADGE_TONES for _, tone in items):
        raise ValueError("Unsupported presentation tone")
    return '<div class="orange-badges">' + "".join(
        f'<span class="orange-badge orange-badge--{tone}">{escape(label)}</span>'
        for label, tone in items
    ) + "</div>"


def render_badges(*items: tuple[str, str]) -> None:
    st.markdown(badges_html(tuple(items)), unsafe_allow_html=True)


def panel_html(title: str, detail: str) -> str:
    return f'<div class="orange-panel"><strong>{escape(title)}</strong><p>{escape(detail)}</p></div>'


def render_panel(title: str, detail: str) -> None:
    st.markdown(panel_html(title, detail), unsafe_allow_html=True)


JOURNEY_LABELS = ("了解你", "经历", "工作偏好", "探索目标", "确认画像")
# A visual grouping of existing stages, not a new workflow or navigation gate.
JOURNEY_STAGE = MappingProxyType({
    ConversationStage.CAREER_QUESTION: 0, ConversationStage.ACTIVITY_PREFERENCE: 0,
    ConversationStage.IMPLEMENTATION_DETAIL: 0, ConversationStage.AI_INTEREST: 0,
    ConversationStage.PROJECT_EVIDENCE: 1, ConversationStage.PROJECT_CONTRIBUTION: 1,
    ConversationStage.WORK_STYLE: 2, ConversationStage.CAREER_GOAL: 3,
    ConversationStage.PROFILE_REVIEW: 4,
})

TRANSITIONS = MappingProxyType({
    ConversationStage.CAREER_QUESTION: "先从你希望解决的问题聊起，不急着选一个岗位。",
    ConversationStage.ACTIVITY_PREFERENCE: "接下来，回想那些让你愿意投入的事情。",
    ConversationStage.IMPLEMENTATION_DETAIL: "把想法做出来有很多环节，我们再靠近一点。",
    ConversationStage.AI_INTEREST: "现在看看不同 AI 工作方式，哪些让你想继续了解。",
    ConversationStage.PROJECT_EVIDENCE: "兴趣先保持开放。接下来，用一个具体经历看看已有证据。",
    ConversationStage.PROJECT_CONTRIBUTION: "围绕这个项目，区分你亲手做过的部分和仍需核对的能力。",
    ConversationStage.WORK_STYLE: "我们已聊过经历，接下来确认你更喜欢怎样的工作状态。",
    ConversationStage.CAREER_GOAL: "最后，想想你希望下一段经历带来什么。目标可以暂时不明确。",
    ConversationStage.PROFILE_REVIEW: "这是一次校准，不是职业定论。你可以确认、修改或保留不确定。",
})


def journey_html(stage: ConversationStage) -> str:
    current = JOURNEY_STAGE[stage]
    items = []
    for index, label in enumerate(JOURNEY_LABELS):
        state = "已聊过" if index < current else "当前" if index == current else "接下来"
        marker = ' class="current" aria-current="step"' if index == current else ""
        items.append(f'<li{marker}>{label} · {state}</li>')
    return '<ol class="orange-journey" aria-label="职业探索旅程">' + "".join(items) + "</ol>"


def render_journey(stage: ConversationStage) -> None:
    st.markdown(journey_html(stage), unsafe_allow_html=True)


def render_safe_error(message: str) -> None:
    # Caller supplies only existing closed-category product copy, not exceptions.
    render_panel("这一步暂时无法继续", message)
    st.caption("下一步：使用侧栏「重新开始 Demo」，重新进行公开职业探索。")
