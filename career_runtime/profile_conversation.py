"""Bounded ephemeral orchestration over existing C.3/C.4 authority paths.

No domain objects, resume prose or answers enter durable chat storage. UI
callbacks invoke operations; rendering never selects questions or calls a model.
"""

from dataclasses import dataclass, field
from enum import Enum
import re

from clarification.context import explicitly_uncertain
from clarification.needs import generate_needs
from clarification.policy import TurnIntent, ClarificationStatus
from profile_refinement.context import digest
from profile_refinement.models import Status as ProfileStatus, Resolution, ChangeType
from ui.conversation_store import _no_credentials

MAX_ROUNDS = 4
MAX_MESSAGES = 40


class InterviewStage(str, Enum):
    IDLE = "IDLE"
    QUESTION = "QUESTION"
    REVIEW = "REVIEW"
    EDITING = "EDITING"
    SUPPLEMENT = "SUPPLEMENT"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    WORKING = "WORKING"


class Readiness(str, Enum):
    NEEDS_MORE_INFORMATION = "NEEDS_MORE_INFORMATION"
    READY_FOR_PROFILE_REVIEW = "READY_FOR_PROFILE_REVIEW"


@dataclass(frozen=True)
class InterviewToken:
    generation: int
    owner: str
    thread: str
    consent: object = field(repr=False)


@dataclass(frozen=True)
class InterviewMessage:
    anchor: int
    role: str
    kind: str
    text: str = field(default="", repr=False)


@dataclass(frozen=True)
class InterviewEvent:
    event: str
    stage: InterviewStage
    rounds: int
    readiness: Readiness
    error_category: str | None = None


def is_general_question(text: str) -> bool:
    """Conservative question diversion; ambiguous text never becomes a fact."""
    return bool(re.search(r"[?？]|什么是|主要做什么|如何|怎么|怎样|有何区别|区别是什么|"
                          r"\b(?:what|why|how|explain)\b", text, re.I))


class ProfileConversation:
    def __init__(self, workspace):
        self.workspace = workspace
        self.generation = 0
        self.invalidate()

    def invalidate(self):
        self.generation += 1
        self.stage = InterviewStage.IDLE
        self.readiness = Readiness.NEEDS_MORE_INFORMATION
        self.rounds = self.selection_attempts = 0
        self.messages = []
        self.events = []
        self.resume_anchor = len(self.workspace.chat.messages)
        self._token = None
        self._profile_fingerprint = None
        self._statement = ""
        self.skipped = False
        self.bound_reached = False

    def _profile_stamp(self):
        profile = self.workspace.memory_service.get_current_confirmed_profile(self.workspace.subject_id)
        return digest(profile.model_dump(mode="json") if profile else None)

    def token(self):
        return self._token

    @property
    def busy(self):
        return self.stage == InterviewStage.WORKING

    def available(self):
        w = self.workspace
        try:
            return (not w._closed and w.resume_analysis.bundle is not None and
                    w.resume_analysis.consent is not None and
                    w.resume_analysis.consent == w.resume_analysis._identity())
        except Exception:
            return False

    def _current(self, token):
        w = self.workspace
        try:
            return (token is not None and token == self._token and token.generation == self.generation and
                    self.available() and token.owner == w.owner_scope_id and token.thread == w.thread.thread_id and
                    token.consent == w.resume_analysis.consent and self._profile_stamp() == self._profile_fingerprint and
                    w.store.get_thread(token.owner, token.thread) is not None)
        except Exception:
            return False

    def _message(self, text="", *, role="assistant", kind="text"):
        self.messages.append(InterviewMessage(len(self.workspace.chat.messages), role, kind, text))
        del self.messages[:-MAX_MESSAGES]

    def _event(self, event, error=None):
        self.events.append(InterviewEvent(event, self.stage, self.rounds, self.readiness, error))
        del self.events[:-40]

    def _failure(self, error, *, confirmation=False):
        self.stage = InterviewStage.FAILED
        self._event("profile_review_failed", error)
        self._message("这次确认没有完成，请重新核对已有的职业画像；不会自动重试或清空长期记录。" if confirmation else
                      "这次整理没有成功。刚才的回答暂时还在本次会话里，我没有自动修改你的职业画像。"
                      "你可以继续补充，也可以稍后重新开始；本次不会自动重试。")

    def start(self, *, consent=False, expected_consent=None):
        if consent is not True or self.stage != InterviewStage.IDLE or not self.available():
            return False
        w = self.workspace
        if expected_consent != w.resume_analysis.consent or w.agent_session.busy:
            return False
        self._token = InterviewToken(self.generation, w.owner_scope_id, w.thread.thread_id, expected_consent)
        self._profile_fingerprint = self._profile_stamp()
        self._event("profile_interview_started")
        self._advance(self._token)
        return True

    def _advance(self, token):
        if not self._current(token):
            return
        self.stage = InterviewStage.WORKING
        w, session = self.workspace, self.workspace.clarification
        try:
            context = session.builder.build(session._inputs(self._statement),
                                            answers=tuple(session.state.answer_candidates))
            needs = generate_needs(context, closed_need_ids=session.state.asked_need_ids,
                                   closed_topics=session.state.closed_topics)
        except Exception:
            if self._current(token):
                self._failure("CLARIFICATION_CONTEXT_FAILED")
            return
        self.bound_reached = bool(needs and self.selection_attempts >= MAX_ROUNDS)
        self.readiness = (Readiness.NEEDS_MORE_INFORMATION if needs and not self.bound_reached
                          else Readiness.READY_FOR_PROFILE_REVIEW)
        self._event("profile_readiness_evaluated")
        if self.readiness == Readiness.READY_FOR_PROFILE_REVIEW:
            self._create_review(token)
            return
        self.selection_attempts += 1
        session.run(TurnIntent.RESUME_REVIEW, current_statement=self._statement)
        if not self._current(token):
            return
        question = session.current_question()
        if question:
            self.rounds += 1
            self.stage = InterviewStage.QUESTION
            self._message(question.decision.question, kind="question")
            self._event("profile_question_created")
        elif session.status == ClarificationStatus.NO_CLARIFICATION_NEEDED:
            # At most one selector call; one separate bounded proposal only
            # after its validated stop decision. No semantic evaluation loop.
            self.readiness = Readiness.READY_FOR_PROFILE_REVIEW
            self._create_review(token)
        else:
            self._failure(session.status.value)

    def _create_review(self, token):
        if not self._current(token):
            return
        self.stage = InterviewStage.WORKING
        self._message("目前的信息已经足够让我先整理一版职业画像了。"
                      "简历里的经历和刚才聊到的想法会分开处理，不确定的地方也会保留下来。")
        session = self.workspace.profile_refinement
        draft = session.start(explicit_review=True, current_statement=self._statement)
        if not self._current(token):
            return
        if draft is None:
            self._failure(session.status.value)
            return
        self.stage = InterviewStage.REVIEW
        self._message(kind="review")
        self._event("profile_review_created")

    def submit(self, text: str, *, token=None, question_token=None):
        """True means handled ephemerally; False leaves the normal QA path intact."""
        token = token or self._token
        if self.stage in {InterviewStage.IDLE, InterviewStage.CONFIRMED}:
            return False
        if self.busy:
            return True
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 2000:
            return True
        if is_general_question(text):
            return False
        if not self._current(token):
            return True  # Stale profile-related input must not fall into durable QA.
        if self.workspace.agent_session.busy or self.busy:
            return True
        try:
            _no_credentials(text)
        except ValueError:
            self._message("这条内容暂时不能用于完善画像，请不要在聊天中输入密钥等敏感信息。")
            self._event("profile_answer_rejected", "ANSWER_NOT_APPLICABLE")
            return True
        text = text.strip()
        if self.stage == InterviewStage.REVIEW:
            self._message(text, role="user")
            self._message("这句话暂时保留在本次对话里，未改变画像。"
                          "如果想补充这份理解，可以选择「我想修改」或「继续聊聊」。")
            return True
        if self.stage == InterviewStage.QUESTION:
            question = self.workspace.clarification.current_question()
            if question_token is not None and question_token != question:
                return True
            if question is None:
                self._failure("STALE_CLARIFICATION_STATE")
                return True
            if text in {"跳过", "先跳过", "暂时跳过这个问题"}:
                if not self.workspace.clarification.dismiss(question):
                    return True
                self.skipped = True
            elif self.workspace.clarification.answer(question, text) is None:
                return True
        self._message(text, role="user")
        self._event("profile_answer_received")
        if explicitly_uncertain(text):
            self._message("没关系，不确定本身也是有用的信息，我会把它保留下来。")
        elif text in {"跳过", "先跳过", "暂时跳过这个问题"}:
            self._message("可以先跳过，不会替你补出答案。")
        else:
            self._message("明白了，这条信息会帮助我更完整地理解你的职业情况。")
        if self.stage == InterviewStage.EDITING:
            self._statement = text
            self._create_review(token)
        else:
            if self.stage != InterviewStage.QUESTION:
                self._statement = text
            self._advance(token)
        return True

    def continue_talking(self, token, *, edit=False):
        if not self._current(token) or self.stage not in {InterviewStage.REVIEW, InterviewStage.FAILED}:
            return False
        self.workspace.profile_refinement.invalidate()
        self.stage = InterviewStage.EDITING if edit else InterviewStage.SUPPLEMENT
        self._message("当然。你最想修改哪一部分？请直接在下面告诉我。" if edit else
                      "可以继续聊。你还有什么想补充，或希望我了解的职业想法？暂时不确定也没关系。")
        return True

    def confirm(self, token, review_token):
        if not self._current(token) or self.stage != InterviewStage.REVIEW:
            return None
        session = self.workspace.profile_refinement
        draft = session.current_draft()
        if draft is None or review_token != session.token():
            return None
        # One explicit whole-profile confirmation resolves exactly the displayed
        # pending changes. Keep uncertainty; never opt into Memory implicitly.
        for change in draft.changes:
            if change.user_resolution == Resolution.PENDING:
                resolution = (Resolution.UNCERTAIN if change.uncertainty != "none" and
                              change.change_type != ChangeType.REMOVE else Resolution.CONFIRM)
                if not session.resolve(session.token(), change.change_id, resolution):
                    self._failure(session.status.value)
                    return None
        final = session.confirm(session.token(), confirmed_by_user=True, memory_change_id=None)
        if final is None:
            if session.status == ProfileStatus.NO_MATERIAL_CHANGE:
                self.stage = InterviewStage.CONFIRMED
                self._message("没有需要保存的新内容，已有的职业画像保持不变；长期记忆也没有增加。")
                return None
            self._failure(session.status.value, confirmation=True)
            return None
        self._profile_fingerprint = self._profile_stamp()
        self.stage = InterviewStage.CONFIRMED
        self._message("这份职业画像已经由你确认。长期记忆没有自动增加；接下来可以继续比较值得探索的职业方向。")
        self._event("profile_review_confirmed")
        return final
