"""Chat presentation adapters over the existing guided flow and public runtime.

No new conversation engine: only exact choices reach GuidedConversation.submit;
unrecognized text is retained as a temporary note, never inferred as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from zoneinfo import ZoneInfo
from html import escape
import sqlite3

import streamlit as st

from ui.chat_components import THEME_MODES, orange_mark, shell_stylesheet
from ui.conversation import ConversationStage, QuestionKind
from ui.demo_controller import DemoController, DemoControllerError
from ui.onboarding.assets import sphere_markup
from ui.presentation import (
    ASK_ORANGE_QUESTIONS, GOAL_TYPE_LABELS, ask_orange_answer,
    career_direction_card_view, match_insight_groups, memory_summary_view,
)
from workflows.langgraph_state import GraphWorkflowStatus


CHAT_KEY = "orange_current_chat_v1"
DELETE_CONFIRMATION_KEY = "orange_delete_confirmation_v1"
INITIAL_SUGGESTIONS = (
    "帮我了解自己", "我想看看适合我的职业方向",
    "我还不知道从哪里开始", "我想了解 AI 相关岗位",
)
INITIAL_CHOICES = {
    INITIAL_SUGGESTIONS[0]: "我只是想先更了解自己",
    INITIAL_SUGGESTIONS[1]: "我知道自己会什么，但不知道这些能力能做什么工作",
    INITIAL_SUGGESTIONS[2]: "我完全不知道自己适合什么岗位",
    # AI curiosity does not establish a career target or an AI capability.
    INITIAL_SUGGESTIONS[3]: "我只是想先更了解自己",
}
CONFIRM = "确认并继续"
REVISE = "我想修改"
REVIEW = "回到画像确认"


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    structured_payload: dict | None = None
    suggestions: tuple[str, ...] = ()


@dataclass
class ChatSession:
    """Presentation transcript; canonical Profile and Memory remain separate."""

    messages: list[ChatMessage] = field(default_factory=list)
    pending_note: str = ""
    revising: bool = False
    selected_role: str | None = None

    def suggestions(self, controller: DemoController) -> tuple[str, ...]:
        if not self.messages:
            return INITIAL_SUGGESTIONS
        status = controller.state["workflow_status"] if controller.state else None
        if status == GraphWorkflowStatus.FAILED.value:
            return ()
        if status == GraphWorkflowStatus.WAITING_FOR_HUMAN.value:
            return (REVIEW,) if self.revising else (CONFIRM, REVISE, "我还不确定")
        if status == GraphWorkflowStatus.COMPLETED.value:
            if self.selected_role:
                return ASK_ORANGE_QUESTIONS + ("看证据关系", "看下一步行动", "比较其他方向", "我的长期理解")
            return tuple(job.title for job in controller.job_records())
        question = controller.conversation.current_question
        return question.options if question else ()

    def submit(self, text: str, controller: DemoController) -> None:
        """Typed text and suggested utterances share exactly this one path."""
        text = text.strip()
        if not text:
            return
        self.messages.append(ChatMessage("user", text))
        try:
            reply = self._reply(text, controller)
        except (DemoControllerError, KeyError, TypeError, ValueError):
            reply = ChatMessage("assistant", "这一步暂时无法继续。当前理解和长期记录没有被清空，你可以开始新对话再试。")
        self.messages.append(replace(reply, suggestions=self.suggestions(controller)))

    def _reply(self, text: str, controller: DemoController) -> ChatMessage:
        if controller.state is None:
            controller.try_reuse_confirmed_profile()
        status = controller.state["workflow_status"] if controller.state else None
        if status == GraphWorkflowStatus.WAITING_FOR_HUMAN.value:
            return self._review_reply(text, controller)
        if status == GraphWorkflowStatus.COMPLETED.value:
            return self._exploration_reply(text, controller)
        if status == GraphWorkflowStatus.FAILED.value:
            return ChatMessage("assistant", "这一步暂时无法继续。可以开始新对话；已确认的长期理解会保留。")
        question = controller.conversation.current_question
        if question is None:
            return self._profile_message(controller)
        answer = INITIAL_CHOICES.get(text, text) if question.stage == ConversationStage.CAREER_QUESTION else text
        # Multi-choice typing uses explicit lines / Chinese list separators only.
        values = tuple(dict.fromkeys(part.strip() for part in answer.replace("、", "\n").splitlines() if part.strip()))
        valid = answer in question.options if question.kind == QuestionKind.SINGLE else bool(values) and all(value in question.options for value in values)
        if not valid:
            self.pending_note = text[:240]
            return ChatMessage("assistant", "我先把这句话留作本轮补充，不把它当作已确认的能力或偏好。\n\n" + self._question_text(question))
        controller.submit_conversation_answer(
            question.stage, answer if question.kind == QuestionKind.SINGLE else values,
            note=self.pending_note,
        )
        self.pending_note = ""
        if controller.conversation.ready_for_profile_review:
            controller.prepare_profile_review()
            return self._profile_message(controller)
        return ChatMessage("assistant", self._question_text(controller.conversation.current_question))

    @staticmethod
    def _question_text(question) -> str:
        # Do not change frozen guided choices or route authority. Only replace
        # the legacy project-stage presentation copy with conversational wording.
        if question.stage == ConversationStage.PROJECT_EVIDENCE:
            return "我们用一个具体项目看看已有证据。你想从哪个项目聊起？"
        text = question.prompt
        if question.kind == QuestionKind.MULTIPLE:
            text += "\n\n可以先选一项，也可以输入多项，用换行或「、」分隔。兴趣不等于已经具备能力。"
        return text

    @staticmethod
    def _profile_message(controller: DemoController) -> ChatMessage:
        return ChatMessage(
            "assistant", "这是我目前对你的理解。\n\n如果基本准确，我们可以继续；如果有不准确的地方，也可以告诉我。确认不等于做出最终职业选择。",
            {"kind": "profile", "profile": controller.profile_review_payload()["profile"]},
        )

    def _review_reply(self, text: str, controller: DemoController) -> ChatMessage:
        if self.revising:
            if text == REVIEW:
                self.revising = False
                return self._profile_message(controller)
            if text == CONFIRM:
                return ChatMessage("assistant", "请先完成修改，或回到画像确认后再继续。")
            # Existing Phase 6 revision supports education summary only.
            controller.revise_profile_summary(text[:500])
            self.revising = False
            return self._profile_message(controller)
        if text == CONFIRM:
            state = controller.confirm_profile()
            if state["workflow_status"] != GraphWorkflowStatus.COMPLETED.value:
                raise DemoControllerError("Workflow did not complete.")
            return self._directions_message(controller)
        if text == REVISE:
            self.revising = True
            return ChatMessage("assistant", "当前支持修改教育背景摘要。请直接输入你希望替换的摘要；其他部分先保留待确认，也可以回到画像确认。")
        return ChatMessage("assistant", "可以保持不确定，也可以修改。只有你明确发送「确认并继续」，我才会继续探索岗位方向。")

    @staticmethod
    def _directions_message(controller: DemoController) -> ChatMessage:
        profile = controller.confirmed_profile()
        cards = tuple(career_direction_card_view(
            job, controller.intelligence_for(job.job_id), controller.match_for(job.job_id), profile,
        ) for job in controller.job_records())
        return ChatMessage("assistant", "我们可以一起比较这三个值得继续了解的方向。下面不是排名，也不是最终职业决定。", {"kind": "directions", "cards": cards})

    def _exploration_reply(self, text: str, controller: DemoController) -> ChatMessage:
        if text in INITIAL_SUGGESTIONS:
            reply = self._directions_message(controller)
            return replace(reply, content="我会沿用你已经确认的职业画像，不需要重复确认。\n\n" + reply.content)
        for job in controller.job_records():
            if text == job.title:
                self.selected_role = job.job_id
                return ChatMessage("assistant", job.title + "\n\n" + ask_orange_answer(
                    ASK_ORANGE_QUESTIONS[0], controller.intelligence_for(job.job_id),
                    controller.match_for(job.job_id), controller.confirmed_profile(),
                ))
        if text == "比较其他方向":
            self.selected_role = None
            return self._directions_message(controller)
        if text == "我的长期理解":
            view = memory_summary_view(
                controller.current_profile_from_memory(), controller.active_memories(),
                controller.profile_history(),
                controller.memory_service.memory_store.list_history(controller.subject_id),
            )
            return ChatMessage("assistant", "这些是你确认过的长期理解；本轮聊天不会自动存入其中。", {"kind": "memory", "view": view})
        if self.selected_role and text in ASK_ORANGE_QUESTIONS:
            return ChatMessage("assistant", ask_orange_answer(
                text, controller.intelligence_for(self.selected_role),
                controller.match_for(self.selected_role), controller.confirmed_profile(),
            ))
        if self.selected_role and text == "看证据关系":
            groups = match_insight_groups(controller.match_for(self.selected_role),
                controller.confirmed_profile(), controller.intelligence_for(self.selected_role))
            return ChatMessage("assistant", "这些是已验证的多维证据关系，不是总体分数。证据缺失不代表你不具备它。", {"kind": "match", "groups": groups})
        if self.selected_role and text == "看下一步行动":
            return ChatMessage("assistant", "我们可以用这些行动继续验证，而不是现在就做定论。", {"kind": "actions", "actions": tuple(controller.match_for(self.selected_role).action_items)})
        return ChatMessage("assistant", "这句话会保留在当前对话，不会自动更新画像或长期理解。可以从下方选一个方向或问题继续比较。")


def new_chat(controller: DemoController) -> None:
    """Clear only conversation presentation; intro/boot/storage latches survive."""
    workspace = st.session_state.get("orange_chat_workspace_v1")
    if workspace is not None:
        workspace.create_new_thread()
        st.session_state["orange_demo_controller"] = workspace.controller
        st.session_state[CHAT_KEY] = workspace.chat
    else:
        controller.new_conversation()
        st.session_state[CHAT_KEY] = ChatSession()
    st.session_state["orange_selected_role"] = None
    st.session_state["orange_demo_error"] = None


def _render_payload(payload: dict) -> None:
    kind = payload["kind"]
    if kind == "profile":
        profile = payload["profile"]
        st.caption(f"职业画像 v{profile['version']} · 待确认")
        for key, label in (("skills", "已有证据的能力"), ("interests", "兴趣"), ("career_preferences", "职业偏好")):
            st.markdown(f"**{label}**")
            st.write("、".join(profile.get(key, [])) or "尚待了解")
        with st.expander("查看其余画像分类"):
            for key, label in (("values", "价值观"), ("strengths", "优势"), ("development_areas", "发展方向"), ("uncertainties", "不确定项"), ("clarification_questions", "澄清问题")):
                st.markdown(f"**{label}**")
                for value in profile.get(key, []):
                    st.write(value)
            st.markdown("**目标**")
            for goal in profile.get("goals", []):
                st.write(f"{goal['label']} · {GOAL_TYPE_LABELS.get(goal['goal_type'], goal['goal_type'])}")
    elif kind == "directions":
        for card in payload["cards"]:
            st.markdown(f"**{card.title}**")
            st.write(card.one_line)
            st.caption(card.why_explore)
            st.write("已有交集：" + ("、".join(card.validated_overlaps) or "当前还没有直接证据"))
            st.write("仍需确认：" + card.clarification_need)
    elif kind == "match":
        for group in payload["groups"]:
            with st.expander(f"{group.label} · {len(group.insights)}"):
                st.caption(group.explanation)
                for insight in group.insights:
                    st.write(insight.title)
                    st.write(insight.description)
    elif kind == "actions":
        for action in payload["actions"]:
            st.write(action.description)
            st.caption("目标：" + action.target_label)
            st.write("预期证据：" + action.expected_evidence)
    elif kind == "memory":
        view = payload["view"]
        for values in (view.confirmed_capabilities, view.work_preferences, view.current_goals, view.user_feedback):
            for value in values:
                st.write(value)


def _select_thread(workspace, thread_id: str) -> None:
    workspace.activate(thread_id)
    st.session_state[CHAT_KEY] = workspace.chat
    st.session_state["orange_demo_controller"] = workspace.controller


def _submit(workspace, text: str, thread_id: str, *, suggested: bool = False, clarification_question=None, profile_question=None) -> None:
    # A queued old chip cannot act on a newly selected conversation.
    if workspace.thread.thread_id != thread_id:
        return
    if workspace.agent_session.busy or workspace.career_discovery.busy:
        return
    if workspace.profile_conversation.submit(text, question_token=profile_question):
        return
    if workspace.career_discovery.answer_pending(text):
        return
    if workspace.evidence_validation.submit(text):
        return
    if workspace.evidence_match.submit(text):
        return
    if workspace.specific_role.submit(text):
        return
    if workspace.role_landscape.submit(text):
        return
    if workspace.career_reality.submit(text):
        return
    if clarification_question is not None:
        # Explicit question-bound answer route; no chat planner, persistence,
        # automatic next question or canonical authority mutation.
        workspace.clarification.answer(clarification_question, text)
        return
    if suggested:
        choices = workspace.chat.messages[-1].suggestions if workspace.chat.messages else INITIAL_SUGGESTIONS
        if text not in choices:
            return
    try:
        if workspace.agent_session.consent:
            workspace.agent_session.queue(text, "suggestion" if suggested else "typed",
                allow_proposal=bool(st.session_state.get("orange_agent_allow_proposal", False)))
        else:
            workspace.submit(text, source="suggestion" if suggested else "typed")
    except ValueError:
        st.session_state["orange_chat_notice"] = "这条消息暂时无法保存，请勿在聊天中输入密钥等敏感信息。"
        return
    st.session_state[CHAT_KEY] = workspace.chat
    st.session_state["orange_demo_controller"] = workspace.controller


def _rename_thread(workspace, thread_id: str, key: str) -> None:
    try:
        workspace.rename(thread_id, st.session_state.get(key, ""))
    except ValueError:
        st.session_state["orange_chat_notice"] = "名称暂时无法保存，请使用简短的普通文字。"


def _request_delete(workspace, thread_id: str) -> None:
    # Menu intent alone is never destructive; keep the exact owner/target pair.
    st.session_state[DELETE_CONFIRMATION_KEY] = (workspace.owner_scope_id, thread_id)


def _cancel_delete() -> None:
    st.session_state.pop(DELETE_CONFIRMATION_KEY, None)


def _confirm_delete(workspace, thread_id: str) -> None:
    if st.session_state.get(DELETE_CONFIRMATION_KEY) != (workspace.owner_scope_id, thread_id):
        return
    try:
        workspace.delete_thread(thread_id)
    except (ValueError, sqlite3.Error):
        st.session_state["orange_chat_notice"] = "这个对话暂时无法删除，请稍后再试。"
    else:
        st.session_state[CHAT_KEY] = workspace.chat
        st.session_state["orange_demo_controller"] = workspace.controller
        # Remove only obsolete widget presentation, not boot/client/theme latches.
        for prefix in ("orange_rename_", "orange_save_name_"):
            st.session_state.pop(prefix + thread_id, None)
    _cancel_delete()


def _thread_menu(workspace, thread) -> None:
    with st.popover("···", help="对话菜单", key=f"orange_thread_menu_{thread.thread_id}"):
        if st.session_state.get(DELETE_CONFIRMATION_KEY) == (workspace.owner_scope_id, thread.thread_id):
            with st.container(key="orange_delete_confirmation"):
                st.markdown("**删除这个对话？**")
                st.write("删除后，此对话中的聊天记录将无法恢复。")
                with st.container(horizontal=True, wrap=False):
                    st.button("取消", key="orange_cancel_delete", on_click=_cancel_delete)
                    with st.container(key="orange_delete_confirm_action", width="content"):
                        st.button("删除", key="orange_confirm_delete", on_click=_confirm_delete,
                                  args=(workspace, thread.thread_id), disabled=workspace.agent_session.busy)
        else:
            with st.expander("重命名"):
                rename_key = f"orange_rename_{thread.thread_id}"
                st.text_input("新名称", value=thread.title, key=rename_key, max_chars=80, disabled=workspace.agent_session.busy)
                st.button("保存名称", key=f"orange_save_name_{thread.thread_id}", on_click=_rename_thread,
                          args=(workspace, thread.thread_id, rename_key), disabled=workspace.agent_session.busy)
            with st.container(key=f"orange_delete_request_action_{thread.thread_id}"):
                st.button("删除对话", key=f"orange_delete_request_{thread.thread_id}",
                          on_click=_request_delete, args=(workspace, thread.thread_id), disabled=workspace.agent_session.busy)


def _suggestions(workspace, suggestions: tuple[str, ...]) -> None:
    with st.container(key="orange_suggestions", horizontal=True, wrap=True):
        for index, suggestion in enumerate(suggestions):
            st.button(suggestion, key=f"orange_suggestion_{index}", on_click=_submit,
                      args=(workspace, suggestion, workspace.thread.thread_id),
                      kwargs={"suggested": True})


def render_conversation_shell(controller: DemoController, workspace=None) -> None:
    workspace = workspace or st.session_state["orange_chat_workspace_v1"]
    workspace.agent_session.start_pending()
    with st.sidebar:
        st.markdown('<div class="orange-chat-brand"><strong>Orange Career</strong><span class="orange-demo-tag">Demo</span></div>', unsafe_allow_html=True)
        st.button("＋ 新对话", key="orange_new_chat", width="stretch", on_click=new_chat, args=(controller,), disabled=workspace.agent_session.busy)
        with st.container(key="orange_thread_history"):
            for thread in workspace.threads:
                with st.container(horizontal=True, wrap=False, vertical_alignment="center"):
                    st.button(thread.title, key=f"orange_thread_{thread.thread_id}",
                              type="primary" if thread.thread_id == workspace.thread.thread_id else "secondary",
                              width="stretch", on_click=_select_thread, args=(workspace, thread.thread_id), disabled=workspace.agent_session.busy)
                    _thread_menu(workspace, thread)
    with st.container(key="orange_thread_header"):
        with st.container(horizontal=True, wrap=False, vertical_alignment="center"):
            started = workspace.thread.created_at.astimezone(ZoneInfo("Asia/Hong_Kong"))
            st.markdown('<div class="orange-thread-start">开始于 ' + started.strftime("%Y年%m月%d日 %H:%M") + '</div>', unsafe_allow_html=True, width="stretch")
            with st.container(key="orange_product_menu", width="content"):
                with st.popover("···", help="Orange Career 菜单"):
                    st.radio("外观", THEME_MODES, key="orange_appearance")
    if notice := st.session_state.pop("orange_chat_notice", None):
        st.warning(notice)
    from ui.agent_activity import render_activity, render_candidates, render_consent, render_pending
    render_consent(workspace)
    st.fragment(run_every=.15 if workspace.agent_session.busy else None)(_render_chat_region)(workspace)


def _render_chat_region(workspace):
    from ui.agent_activity import render_activity, render_candidates, render_pending
    session = workspace.agent_session
    if session.finish_background():
        st.rerun(scope="app")
    if session.last_failure is not None and not session.failure_persisted:
        from career_runtime.session import failure_text
        st.warning(failure_text(session.last_failure))
    chat = workspace.chat
    interview = workspace.profile_conversation
    workspace.career_reality.current()
    workspace.role_landscape.current()
    workspace.specific_role.current()
    workspace.evidence_match.current()
    workspace.evidence_validation.current()
    st.session_state[CHAT_KEY] = chat
    has_resume = workspace.resume_intake.result is not None
    if not chat.messages and not has_resume and not interview.messages and not workspace.career_reality.messages and not workspace.role_landscape.messages and not workspace.specific_role.messages and not workspace.evidence_match.messages and not workspace.evidence_validation.messages:
        if not session.busy:
            st.markdown('<div class="orange-chat-empty">' + orange_mark() + '<h1>现在开始吧</h1></div>', unsafe_allow_html=True)
            from ui.chat_opening import render_opening
            if workspace.career_discovery.result is None and workspace.career_discovery.status.value != "CONSENT_REQUIRED":
                render_opening(workspace)
        if session.busy:
            with st.container(key="orange_transcript", height=600, autoscroll=True):
                render_pending(workspace)
    else:
        # Native autoscroll follows appended messages without a new JS subsystem.
        with st.container(key="orange_transcript", height=600, autoscroll=True):
            stored = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)
            from ui.profile_conversation import render_interview_messages, render_resume_transition
            from ui.career_reality import render_reality_messages
            for index in range(len(chat.messages) + 1):
                if has_resume and index == min(interview.resume_anchor, len(chat.messages)):
                    from ui.resume_upload import render_file_card
                    with st.chat_message("user"):
                        render_file_card(workspace)
                    with st.chat_message("assistant", avatar=sphere_markup()):
                        render_resume_transition(workspace)
                render_interview_messages(workspace, index)
                render_reality_messages(workspace, index)
                if index == len(chat.messages):
                    break
                message = chat.messages[index]
                with st.chat_message(message.role, avatar=sphere_markup() if message.role == "assistant" else None):
                    # User text is escaped, not interpreted as arbitrary Markdown/HTML.
                    if message.role == "user":
                        st.markdown(escape(message.content).replace("\n", "<br>"), unsafe_allow_html=True)
                    else:
                        st.write(message.content)
                        if index < len(stored):
                            render_activity(stored[index].metadata.get("agent_activity", []), key=stored[index].message_id)
                            if stored[index].metadata.get("agent_turn_status") == "CANCELLED" and message.content != "已停止生成":
                                st.caption("已停止生成")
                    if message.structured_payload:
                        _render_payload(message.structured_payload)
                if not session.busy and message.role == "assistant" and index == len(chat.messages) - 1:
                    _suggestions(workspace, message.suggestions)
            render_pending(workspace)
            render_candidates(workspace)
    from ui.career_discovery import render_career_discovery
    from profile_refinement.models import Status as RefinementStatus
    from career_runtime.profile_conversation import InterviewStage
    if not has_resume or interview.stage == InterviewStage.CONFIRMED or (interview.stage == InterviewStage.IDLE and
                          workspace.profile_refinement.status == RefinementStatus.CONFIRMED):
        render_career_discovery(workspace)
    with st.bottom:
        with st.container(key="orange_composer"):
            from ui.resume_upload import render_resume_upload
            render_resume_upload(workspace)
            text = st.chat_input("和 Orange 说点什么…", key="orange_chat_input", max_chars=2000,
                                 disabled=session.busy or interview.busy)
            if session.busy:
                cancelled = session.cancellation_requested
                st.button("停止生成", key="orange_stop_generation", on_click=session.request_cancel, disabled=cancelled,
                          help="保留已经显示的内容，停止本次回答；不会确认画像或记忆。")
    if text:
        _submit(workspace, text, workspace.thread.thread_id,
                profile_question=workspace.clarification.current_question())
        st.rerun()
