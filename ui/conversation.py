"""Deterministic guided-conversation contracts for the public Demo."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class ConversationStage(str, Enum):
    """Presentation stages only; this is not a second domain workflow."""

    CAREER_QUESTION = "career_question"
    ACTIVITY_PREFERENCE = "activity_preference"
    IMPLEMENTATION_DETAIL = "implementation_detail"
    AI_INTEREST = "ai_interest"
    PROJECT_EVIDENCE = "project_evidence"
    PROJECT_CONTRIBUTION = "project_contribution"
    WORK_STYLE = "work_style"
    CAREER_GOAL = "career_goal"
    PROFILE_REVIEW = "profile_review"


class QuestionKind(str, Enum):
    SINGLE = "single"
    MULTIPLE = "multiple"


@dataclass(frozen=True)
class GuidedQuestion:
    stage: ConversationStage
    prompt: str
    options: tuple[str, ...]
    kind: QuestionKind = QuestionKind.SINGLE
    helper: str = ""


CAREER_QUESTION_OPTIONS = (
    "我完全不知道自己适合什么岗位",
    "我有几个方向，但不知道怎么选",
    "我知道自己会什么，但不知道这些能力能做什么工作",
    "我已经有目标岗位，想验证自己和它的关系",
    "我只是想先更了解自己",
)

ACTIVITY_PREFERENCE_OPTIONS = (
    "把一个想法真正做成系统",
    "分析数据、找规律",
    "思考一个产品应该怎么工作",
    "深入研究一个技术问题",
    "和别人讨论需求、协调推进",
    "我还说不清楚",
)

IMPLEMENTATION_DETAIL_OPTIONS = (
    "写代码实现核心功能",
    "把多个 API / 模块连起来",
    "调试和解决问题",
    "设计系统结构",
    "看最终用户真正使用",
    "都有一些",
)

AI_INTEREST_OPTIONS = (
    "用现有 AI / LLM 做真正的应用",
    "训练、优化模型本身",
    "分析数据和规律",
    "研究新的算法或技术方法",
    "思考 AI 应该解决什么用户问题",
    "我还不知道",
)

PROJECT_EVIDENCE_OPTIONS = (
    "Campus Helper Prototype",
    "我还不能判断哪个项目最能代表我",
)

PROJECT_CONTRIBUTION_OPTIONS = (
    "Python",
    "API integration",
    "data processing",
    "LLM integration",
    "software architecture",
    "testing",
    "UI",
    "product thinking",
)

WORK_STYLE_OPTIONS = (
    "大部分时间亲手实现东西",
    "分析问题和数据",
    "沟通并定义需求",
    "深入一个专业技术方向",
    "希望几种方式都有",
    "目前还不知道",
)

CAREER_GOAL_OPTIONS = (
    "快速积累技术能力",
    "做出真正可使用的产品",
    "找到自己最擅长的方向",
    "深入某个专业领域",
    "接触不同业务和问题",
    "还没有明确答案",
)


QUESTIONS: Mapping[ConversationStage, GuidedQuestion] = {
    ConversationStage.CAREER_QUESTION: GuidedQuestion(
        stage=ConversationStage.CAREER_QUESTION,
        prompt="你现在最想解决的职业问题是什么？",
        options=CAREER_QUESTION_OPTIONS,
        helper="先选最接近的一项。它只帮助 Orange 决定接下来问什么。",
    ),
    ConversationStage.ACTIVITY_PREFERENCE: GuidedQuestion(
        stage=ConversationStage.ACTIVITY_PREFERENCE,
        prompt="在你做过的课程或项目里，哪类事情最容易让你投入？",
        options=ACTIVITY_PREFERENCE_OPTIONS,
    ),
    ConversationStage.IMPLEMENTATION_DETAIL: GuidedQuestion(
        stage=ConversationStage.IMPLEMENTATION_DETAIL,
        prompt="在把东西做出来的过程中，你最享受哪部分？",
        options=IMPLEMENTATION_DETAIL_OPTIONS,
    ),
    ConversationStage.AI_INTEREST: GuidedQuestion(
        stage=ConversationStage.AI_INTEREST,
        prompt="AI 里的工作方式差别很大。下面哪些更吸引你？",
        options=AI_INTEREST_OPTIONS,
        kind=QuestionKind.MULTIPLE,
        helper="可以多选；选择兴趣不等于已经具备对应能力。",
    ),
    ConversationStage.PROJECT_EVIDENCE: GuidedQuestion(
        stage=ConversationStage.PROJECT_EVIDENCE,
        prompt="哪一个公开合成项目最能代表你目前的能力？",
        options=PROJECT_EVIDENCE_OPTIONS,
        helper="Demo 只使用公开虚构资料。",
    ),
    ConversationStage.PROJECT_CONTRIBUTION: GuidedQuestion(
        stage=ConversationStage.PROJECT_CONTRIBUTION,
        prompt="在这个项目里，你实际参与了哪些部分？",
        options=PROJECT_CONTRIBUTION_OPTIONS,
        kind=QuestionKind.MULTIPLE,
        helper="这些是本次会话里的明确表达；仍需与已有证据区分。",
    ),
    ConversationStage.WORK_STYLE: GuidedQuestion(
        stage=ConversationStage.WORK_STYLE,
        prompt="如果公司和薪资相近，哪种工作方式更吸引你？",
        options=WORK_STYLE_OPTIONS,
        helper="这不是性格测试，只用于比较工作方式。",
    ),
    ConversationStage.CAREER_GOAL: GuidedQuestion(
        stage=ConversationStage.CAREER_GOAL,
        prompt="未来一两年，你最希望工作给你带来什么？",
        options=CAREER_GOAL_OPTIONS,
    ),
}


@dataclass
class GuidedConversation:
    """Small deterministic state machine for product interaction only."""

    stage: ConversationStage = ConversationStage.CAREER_QUESTION
    answers: dict[ConversationStage, str | tuple[str, ...]] = field(
        default_factory=dict
    )
    notes: dict[ConversationStage, str] = field(default_factory=dict)

    @property
    def current_question(self) -> GuidedQuestion | None:
        return QUESTIONS.get(self.stage)

    @property
    def ready_for_profile_review(self) -> bool:
        return self.stage == ConversationStage.PROFILE_REVIEW

    def submit(
        self,
        stage: ConversationStage,
        answer: str | Sequence[str],
        *,
        note: str = "",
    ) -> ConversationStage:
        """Validate one answer and advance through explicit routing rules."""

        if stage != self.stage:
            raise ValueError("Conversation answer does not match the current stage.")
        question = QUESTIONS.get(stage)
        if question is None:
            raise ValueError("The current conversation stage does not accept answers.")
        normalized = self._normalize_answer(question, answer)
        self.answers[stage] = normalized
        if note.strip():
            self.notes[stage] = note.strip()[:240]
        self.stage = self._next_stage(stage, normalized)
        return self.stage

    def answer_for(self, stage: ConversationStage) -> str | tuple[str, ...] | None:
        return self.answers.get(stage)

    @staticmethod
    def _normalize_answer(
        question: GuidedQuestion,
        answer: str | Sequence[str],
    ) -> str | tuple[str, ...]:
        if question.kind == QuestionKind.SINGLE:
            if not isinstance(answer, str) or answer not in question.options:
                raise ValueError("Select one of the available guided choices.")
            return answer
        if isinstance(answer, str):
            values = (answer,)
        else:
            values = tuple(dict.fromkeys(answer))
        if not values or any(value not in question.options for value in values):
            raise ValueError("Select at least one available guided choice.")
        if "我还不知道" in values and len(values) > 1:
            raise ValueError("Uncertain cannot be combined with other AI interests.")
        return values

    @staticmethod
    def _next_stage(
        stage: ConversationStage,
        answer: str | tuple[str, ...],
    ) -> ConversationStage:
        if stage == ConversationStage.CAREER_QUESTION:
            return ConversationStage.ACTIVITY_PREFERENCE
        if stage == ConversationStage.ACTIVITY_PREFERENCE:
            return (
                ConversationStage.IMPLEMENTATION_DETAIL
                if answer == "把一个想法真正做成系统"
                else ConversationStage.AI_INTEREST
            )
        if stage == ConversationStage.IMPLEMENTATION_DETAIL:
            return ConversationStage.AI_INTEREST
        if stage == ConversationStage.AI_INTEREST:
            return ConversationStage.PROJECT_EVIDENCE
        if stage == ConversationStage.PROJECT_EVIDENCE:
            return (
                ConversationStage.PROJECT_CONTRIBUTION
                if answer == "Campus Helper Prototype"
                else ConversationStage.WORK_STYLE
            )
        if stage == ConversationStage.PROJECT_CONTRIBUTION:
            return ConversationStage.WORK_STYLE
        if stage == ConversationStage.WORK_STYLE:
            return ConversationStage.CAREER_GOAL
        if stage == ConversationStage.CAREER_GOAL:
            return ConversationStage.PROFILE_REVIEW
        raise ValueError("Conversation routing is undefined for this stage.")


def conversation_progress(stage: ConversationStage) -> tuple[int, int]:
    """Return a UI-only stage indicator without claiming profile completeness."""

    ordered = (
        ConversationStage.CAREER_QUESTION,
        ConversationStage.ACTIVITY_PREFERENCE,
        ConversationStage.IMPLEMENTATION_DETAIL,
        ConversationStage.AI_INTEREST,
        ConversationStage.PROJECT_EVIDENCE,
        ConversationStage.PROJECT_CONTRIBUTION,
        ConversationStage.WORK_STYLE,
        ConversationStage.CAREER_GOAL,
        ConversationStage.PROFILE_REVIEW,
    )
    position = ordered.index(stage) + 1
    return position, len(ordered)
