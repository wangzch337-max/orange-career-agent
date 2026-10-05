"""Persistent local chat workspace over existing canonical workflow interfaces.

Transcript, canonical Memory and workflow checkpoints remain separate stores.
Loading a thread is read-only: no message replay, confirmation or model call.
Opaque browser scopes provide local/demo isolation, not authentication.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import Mapping
from uuid import UUID

from memory.embeddings import FakeEmbeddingProvider
from memory.models import ProfileReference
from memory.service import build_semantic_memory_service
from resume_intake.session import ResumeSessionState
from resume_evidence.session import ResumeAnalysisSession
from clarification.context import workspace_inputs
from clarification.session import ClarificationSession
from profile_refinement.context import workspace_inputs as refinement_inputs
from profile_refinement.session import ProfileRefinementSession
from ui.conversation import ConversationStage, GuidedConversation
from ui.conversation_shell import ChatMessage, ChatSession
from ui.conversation_store import (
    ConversationStore, ConversationStoreError, ConversationThread,
    _content as validate_message_content,
)
from ui.demo_controller import DemoController
from ui.presentation import GOAL_TYPE_LABELS
from workflows.langgraph_checkpoint import sqlite_checkpointer
from workflows.langgraph_workflow import new_workflow_id


DEFAULT_CHAT_ROOT = Path(__file__).resolve().parents[1] / "data/local/chat"


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ConversationStoreError("Visible presentation text is invalid.")
    return value


def flatten_payload(payload: Mapping[str, object] | None) -> str:
    """Project only the already-visible labels/text, never serialize domain objects."""
    if payload is None:
        return ""
    kind = payload.get("kind")
    lines: list[str] = []
    if kind == "profile":
        profile = payload["profile"]
        if not isinstance(profile, Mapping):
            raise ConversationStoreError("Profile presentation is invalid.")
        lines.append(f"职业画像 v{profile['version']} · 待确认")
        for key, label in (
            ("skills", "已有证据的能力"), ("interests", "兴趣"),
            ("career_preferences", "职业偏好"), ("values", "价值观"),
            ("strengths", "优势"), ("development_areas", "发展方向"),
            ("uncertainties", "不确定项"), ("clarification_questions", "澄清问题"),
        ):
            values = profile.get(key, [])
            if not isinstance(values, (list, tuple)):
                raise ConversationStoreError("Profile presentation category is invalid.")
            lines.append(label + "：" + ("、".join(_text(value) for value in values) or "尚待了解"))
        for goal in profile.get("goals", []):
            goal_type = goal["goal_type"]
            lines.append("目标：" + _text(goal["label"]) + " · " + GOAL_TYPE_LABELS.get(goal_type, goal_type))
    elif kind == "directions":
        for card in payload["cards"]:
            lines.extend((_text(card.title), _text(card.one_line), _text(card.why_explore),
                          "已有交集：" + ("、".join(_text(item) for item in card.validated_overlaps) or "当前还没有直接证据"),
                          "仍需确认：" + _text(card.clarification_need)))
    elif kind == "match":
        for group in payload["groups"]:
            lines.extend((_text(group.label), _text(group.explanation)))
            for insight in group.insights:
                lines.extend((_text(insight.title), _text(insight.description)))
    elif kind == "actions":
        for action in payload["actions"]:
            lines.extend((_text(action.description), "目标：" + _text(action.target_label),
                          "预期证据：" + _text(action.expected_evidence)))
    elif kind == "memory":
        view = payload["view"]
        for field, label in (("confirmed_capabilities", "已确认的能力"),
                             ("work_preferences", "工作偏好"), ("current_goals", "当前目标"),
                             ("user_feedback", "用户反馈")):
            values = getattr(view, field)
            if values:
                lines.append(label + "：" + "、".join(_text(value) for value in values))
    else:
        raise ConversationStoreError("Unsupported visible presentation kind.")
    return "\n\n".join(lines)


class Workspace:
    """One browser-scoped persistent workspace; no automatic Memory transcript writes."""

    def __init__(self, owner_scope_id: str, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_CHAT_ROOT
        self.store = ConversationStore(self.root / "conversations.sqlite3")
        identity = self.store.ensure_owner(owner_scope_id)
        self.owner_scope_id = identity.owner_scope_id
        self.subject_id = identity.subject_id
        self.runtime_root = self.root / "runtime" / UUID(self.owner_scope_id).hex
        self.memory_service = build_semantic_memory_service(
            memory_path=self.runtime_root / "memory.sqlite3",
            vector_path=self.runtime_root / "vectors.sqlite3",
            embedding_provider=FakeEmbeddingProvider(),
        )
        self._stack = ExitStack()
        self.checkpointer = self._stack.enter_context(sqlite_checkpointer(self.runtime_root / "checkpoints.sqlite3"))
        self._controller: DemoController | None = None
        self._chat = ChatSession()
        self._thread: ConversationThread | None = None
        self._closed = False
        self.last_checkpoint_cleanup = "not_requested"
        self._agent_session = None
        self.resume_intake = ResumeSessionState(self.owner_scope_id)
        self.resume_analysis = ResumeAnalysisSession(self.owner_scope_id, self.resume_intake)
        self.resume_intake.on_clear = self.resume_analysis.invalidate
        self.clarification = ClarificationSession(self.owner_scope_id,
            lambda **kwargs: workspace_inputs(self, **kwargs))
        self.resume_analysis.on_invalidate = self.clarification.invalidate
        self.profile_refinement = ProfileRefinementSession(self.owner_scope_id,
            lambda **kwargs: refinement_inputs(self, **kwargs), self.memory_service,
            on_confirmed=self._profile_refinement_confirmed)
        self.resume_analysis.on_invalidate = self._invalidate_resume_candidates
        try:
            threads = self.store.list_threads(self.owner_scope_id)
            if threads:
                self.activate(threads[0].thread_id)
            else:
                self.create_new_thread()
        except Exception:
            self.close()
            raise

    @property
    def agent_session(self):
        from career_runtime.session import AgentSession
        if self._agent_session is None:
            self._agent_session = AgentSession(self)
        return self._agent_session

    def _invalidate_resume_candidates(self):
        self.clarification.invalidate()
        self.profile_refinement.invalidate()

    def _profile_refinement_confirmed(self, binding):
        # Called outside the Profile lock. Never clear a later thread/answer.
        with self.clarification._lock:
            if (not self._closed and self._thread is not None and self._thread.thread_id == binding.conversation_id and
                    self.clarification.state.version == binding.clarification_state_version):
                self.clarification.invalidate()

    @property
    def controller(self) -> DemoController:
        if self._controller is None or self._closed:
            raise ConversationStoreError("Conversation workspace is unavailable.")
        return self._controller

    @property
    def chat(self) -> ChatSession:
        return self._chat

    @property
    def thread(self) -> ConversationThread:
        if self._thread is None or self._closed:
            raise ConversationStoreError("Conversation workspace is unavailable.")
        return self._thread

    @property
    def threads(self) -> tuple[ConversationThread, ...]:
        return self.store.list_threads(self.owner_scope_id)

    def _reference(self, thread: ConversationThread) -> ProfileReference | None:
        if thread.profile_id_ref is None:
            return None
        return ProfileReference(subject_id=self.subject_id, profile_id=thread.profile_id_ref,
                                version=thread.profile_version_ref)

    def _new_controller(self, thread: ConversationThread) -> DemoController:
        return DemoController(
            memory_service=self.memory_service, checkpointer=self.checkpointer,
            subject_id=self.subject_id, workflow_id=thread.workflow_thread_id,
            profile_reference=self._reference(thread), seed_public_memory=False,
            checkpoint_mode="sqlite",
        )

    def _snapshot(self) -> dict[str, object]:
        guided = self.controller.conversation
        return {
            "stage": guided.stage.value,
            "answers": {key.value: list(value) if isinstance(value, tuple) else value for key, value in guided.answers.items()},
            "notes": {key.value: value for key, value in guided.notes.items()},
            "pending_note": self.chat.pending_note, "revising": self.chat.revising,
            "selected_role": self.chat.selected_role,
        }

    def create_new_thread(self) -> ConversationThread:
        """Create a fresh context, pinning only a canonical confirmed profile ref."""
        if self._closed:
            raise ConversationStoreError("Conversation workspace is unavailable.")
        if self._agent_session is not None:
            self._agent_session.require_idle()
        current = self.memory_service.get_current_confirmed_profile(self.subject_id)
        refs = {} if current is None else {
            "profile_id_ref": current.profile_id, "profile_version_ref": current.version,
        }
        thread = self.store.create_thread(self.owner_scope_id, workflow_thread_id=new_workflow_id(), **refs)
        self.activate(thread.thread_id)
        return thread

    def activate(self, thread_id: str) -> ConversationThread:
        """Load the owned transcript/snapshot/checkpoint without executing anything."""
        if self._closed:
            raise ConversationStoreError("Conversation workspace is unavailable.")
        if self._agent_session is not None:
            self._agent_session.require_idle()
        self.profile_refinement.invalidate()
        thread = self.store.get_thread(self.owner_scope_id, thread_id)
        messages = self.store.list_messages(self.owner_scope_id, thread_id)
        snapshot = self.store.load_snapshot(self.owner_scope_id, thread_id)
        controller = self._new_controller(thread)
        try:
            controller.restore_workflow()
            controller.conversation = GuidedConversation(
                stage=ConversationStage(snapshot["stage"]),
                answers={ConversationStage(key): tuple(value) if isinstance(value, list) else value
                         for key, value in snapshot["answers"].items()},
                notes={ConversationStage(key): value for key, value in snapshot["notes"].items()},
            )
            chat = ChatSession(
                messages=[ChatMessage(message.role, message.content, None,
                                      tuple(message.metadata.get("suggestions", []))) for message in messages],
                pending_note=snapshot["pending_note"], revising=snapshot["revising"],
                selected_role=snapshot["selected_role"],
            )
        except Exception:
            controller.close()
            raise
        if self._controller is not None:
            self._controller.close()
        if self._agent_session is not None and self._thread is not None and self._thread.thread_id != thread_id:
            self._agent_session.cancel_pending()
            self._agent_session.last_result = None
            self._agent_session.last_error = None
            self._agent_session.last_failure = None
            self._agent_session.failure_persisted = False
            self._agent_session.pending = None
        self._controller, self._chat, self._thread = controller, chat, thread
        self.resume_intake.bind(self.owner_scope_id, thread_id)
        return thread

    def rename(self, thread_id: str, title: str) -> ConversationThread:
        if self._closed:
            raise ConversationStoreError("Conversation workspace is unavailable.")
        renamed = self.store.rename_thread(self.owner_scope_id, thread_id, title)
        if self.thread.thread_id == thread_id:
            self._thread = renamed
        return renamed

    def delete_thread(self, thread_id: str) -> ConversationThread:
        """Delete conversation-owned data without touching canonical authority.

        Checkpoints live in a separate per-owner database. Use its public API
        only for an unreferenced workflow; cleanup failure leaves an unreachable
        checkpoint, never restores a deleted conversation or purges shared data.
        """
        if self._closed:
            raise ConversationStoreError("Conversation workspace is unavailable.")
        if self._agent_session is not None:
            self._agent_session.require_idle()
        if self.thread.thread_id == thread_id:
            self.profile_refinement.invalidate()
        was_active = self.thread.thread_id == thread_id
        deleted = self.store.delete_thread(self.owner_scope_id, thread_id)
        if self.resume_intake.thread_id == thread_id:
            self.resume_intake.clear()
        remaining = self.threads
        workflow_id = deleted.workflow_thread_id
        self.last_checkpoint_cleanup = "not_created"
        if workflow_id is not None:
            if any(thread.workflow_thread_id == workflow_id for thread in remaining):
                self.last_checkpoint_cleanup = "shared_preserved"
            else:
                try:
                    self.checkpointer.delete_thread(workflow_id)
                    self.last_checkpoint_cleanup = "deleted"
                except Exception:
                    # No exception text, transcript, or canonical records escape.
                    self.last_checkpoint_cleanup = "pending"
        if was_active:
            if remaining:
                self.activate(remaining[0].thread_id)
            else:
                self.create_new_thread()
        return deleted

    def submit(self, text: str, *, source: str = "typed") -> None:
        """One typed/suggestion path; persist visible reply and state as one turn."""
        if self._agent_session is not None:
            self._agent_session.require_idle()
        if not isinstance(text, str):
            raise ConversationStoreError("Message content is invalid.")
        text = text.strip()
        if not text:
            return
        validate_message_content(text)
        if source not in ("typed", "suggestion"):
            raise ConversationStoreError("Unsupported message source.")
        self.chat.submit(text, self.controller)
        user, assistant = self.chat.messages[-2:]
        flattened = flatten_payload(assistant.structured_payload)
        visible_content = assistant.content + ("\n\n" + flattened if flattened else "")
        suggestions = tuple(assistant.suggestions)
        kind = assistant.structured_payload["kind"] if assistant.structured_payload else "text"
        state = self.controller.state
        reference = state.get("current_profile_ref") if state else None
        refs = {} if not reference else {
            "profile_id_ref": reference["profile_id"], "profile_version_ref": reference["version"],
        }
        self.store.append_turn(
            self.owner_scope_id, self.thread.thread_id, user.content, visible_content,
            user_metadata={"source": source},
            assistant_metadata={"kind": kind, "suggestions": suggestions},
            snapshot=self._snapshot(), workflow_thread_id=self.controller.workflow_id, **refs,
        )
        # Current view and reload share the same safe flattened transcript, not
        # a duplicate canonical domain object hidden in presentation metadata.
        self.chat.messages[-1] = ChatMessage("assistant", visible_content, None, suggestions)
        self._thread = self.store.get_thread(self.owner_scope_id, self.thread.thread_id)

    def close(self) -> None:
        """Release resources only; never delete transcript/Profile/Memory/checkpoints."""
        if self._closed:
            return
        self.resume_intake.clear()
        if self._agent_session is not None:
            self._agent_session.close()
        if self._controller is not None:
            self._controller.close()
        self._stack.close()
        self._closed = True

    def __enter__(self) -> Workspace:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


PersistentChatWorkspace = Workspace
