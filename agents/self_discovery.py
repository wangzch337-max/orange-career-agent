"""Provider-independent, evidence-backed Phase 3 Self-Discovery Agent."""

from __future__ import annotations

from typing import Dict, Optional

from agents.base import BaseAgent, record_agent_event, record_tool_event
from agents.profile_assembler import ProfileAssembler
from agents.self_discovery_evidence import SourceEvidenceBuilder
from agents.self_discovery_models import (
    CareerPreferenceSignal,
    GoalExtractionSignal,
    InterestExtractionSignal,
    SelfDiscoveryExtraction,
    SelfDiscoveryResult,
    SkillSignal,
    StrengthSignal,
    ValueExtractionSignal,
)
from data.models import (
    AgentName,
    ClarificationQuestion,
    EventType,
    GoalType,
    InferenceType,
    ProfileUncertainty,
    Severity,
)
from providers.base import LLMProvider
from providers.models import GenerationOptions
from providers.prompts import (
    SELF_DISCOVERY_PROMPT_NAME,
    SELF_DISCOVERY_PROMPT_VERSION,
    build_self_discovery_messages,
    load_self_discovery_prompt,
)
from tools.base import CourseDataProvider
from workflows.stages import WorkflowStage
from workflows.state import WorkflowState


def public_offline_extraction() -> SelfDiscoveryExtraction:
    """Canned public response for free, deterministic integration tests."""

    inferred = InferenceType.EVIDENCE_SUPPORTED_INFERENCE
    explicit = InferenceType.EXPLICIT_FACT
    return SelfDiscoveryExtraction(
        skills=[
            SkillSignal(label="Artificial Intelligence", description="课程证据支持基础 AI 概念与问题建模经验。", confidence=0.82, evidence_ids=["course_001"], inference_type=inferred),
            SkillSignal(label="AI Product Thinking", description="课程证据支持从用户问题到 AI 产品概念的练习。", confidence=0.80, evidence_ids=["course_002"], inference_type=inferred),
            SkillSignal(label="Data Analytics", description="课程证据支持使用模拟数据进行分析与展示。", confidence=0.80, evidence_ids=["course_003"], inference_type=inferred),
        ],
        interests=[InterestExtractionSignal(label="AI 产品与 AI 应用方向", description="用户明确陈述的职业兴趣。", confidence=1.0, evidence_ids=["career_001"], inference_type=explicit)],
        values=[
            ValueExtractionSignal(label="持续学习", description="用户明确列出的职业价值。", confidence=1.0, evidence_ids=["value_001"], inference_type=explicit),
            ValueExtractionSignal(label="实际影响", description="用户明确列出的职业价值。", confidence=1.0, evidence_ids=["value_002"], inference_type=explicit),
        ],
        goals=[GoalExtractionSignal(goal_type=GoalType.CAREER_GOAL, label="比较三类 AI 相关实习并识别下一步能力证据", description="用户明确陈述的短期探索目标。", confidence=1.0, evidence_ids=["career_002"], inference_type=explicit)],
        strengths=[StrengthSignal(label="AI 应用原型实践", description="项目证据支持完成小型 AI 应用原型的实践模式。", confidence=0.78, evidence_ids=["project_001"], inference_type=inferred)],
        development_areas=[],
        career_preferences=[CareerPreferenceSignal(label="探索 AI 产品与应用角色", description="来自用户明确的职业兴趣范围，尚未固定单一岗位。", confidence=0.95, evidence_ids=["career_001", "career_002"], inference_type=explicit)],
        profile_uncertainties=[ProfileUncertainty(topic="技术深度与产品工作的偏好平衡", reason="现有证据没有说明两类工作内容的相对偏好。", evidence_ids=["career_001"], importance=Severity.MEDIUM)],
        clarification_questions=[ClarificationQuestion(question_id="question_001", question="你更希望下一段经历偏向技术实现，还是产品发现与跨职能协作？", topic="technical_product_balance", reason="用于澄清当前较宽的 AI 产品与应用探索范围。", priority=Severity.MEDIUM, related_evidence_ids=["career_001"])],
    )


class SelfDiscoveryAgent(BaseAgent):
    """Extract candidate signals through an injected provider, then assemble deterministically."""

    name = AgentName.SELF_DISCOVERY

    def __init__(self, course_provider: CourseDataProvider, llm_provider: LLMProvider, *, evidence_builder: Optional[SourceEvidenceBuilder] = None, profile_assembler: Optional[ProfileAssembler] = None, generation_options: Optional[GenerationOptions] = None) -> None:
        self.course_provider = course_provider
        self.llm_provider = llm_provider
        self.evidence_builder = evidence_builder or SourceEvidenceBuilder()
        self.profile_assembler = profile_assembler or ProfileAssembler()
        self.generation_options = generation_options or GenerationOptions(model="fake-self-discovery-v2", max_retries=0)

    def discover(self, user_input: Dict[str, object], courses: list) -> SelfDiscoveryResult:
        evidence = self.evidence_builder.build(user_input, courses)
        response = self.llm_provider.generate_structured(
            build_self_discovery_messages(load_self_discovery_prompt(), evidence.source_evidence),
            SelfDiscoveryExtraction,
            self.generation_options,
            prompt_name=SELF_DISCOVERY_PROMPT_NAME,
            prompt_version=SELF_DISCOVERY_PROMPT_VERSION,
        )
        response.data.validate_evidence_ids(evidence.source_evidence)
        metadata = response.safe_metadata()
        metadata["evidence_count"] = len(evidence.source_evidence)
        metadata["signal_counts"] = response.data.signal_counts()
        return self.profile_assembler.assemble(
            profile_id=str(user_input.get("profile_id", "profile_demo_001")),
            extraction=response.data,
            evidence=evidence,
            extraction_metadata=metadata,
            usage=response.usage,
        )

    def run(self, state: WorkflowState) -> WorkflowState:
        if state.stage != WorkflowStage.SELF_DISCOVERY:
            raise ValueError("Self-Discovery Agent 只能在 self_discovery 阶段运行")
        state = record_agent_event(state, self.name, EventType.AGENT_STARTED, "开始执行 evidence-backed Self-Discovery。")
        courses = state.course_records
        if not courses:
            state = record_tool_event(state, self.course_provider.name, EventType.TOOL_CALLED, "读取公开的本地课程 fixture。")
            courses = self.course_provider.load()
            state = record_tool_event(state, self.course_provider.name, EventType.TOOL_COMPLETED, "课程 fixture 读取完成。", {"record_count": len(courses)})

        if state.user_profile is not None:
            return record_agent_event(
                state.validated_copy(course_records=courses, profile_confirmed=False),
                self.name,
                EventType.PROFILE_CONFIRMATION_REQUIRED,
                f"保留用户修订后的 UserProfile v{state.user_profile.version}；等待确认。",
                [item.id for item in state.user_profile.evidence],
                safe_metadata={"profile_version": state.user_profile.version},
            )

        evidence = self.evidence_builder.build(state.user_input, courses)
        state = record_agent_event(state, self.name, EventType.SOURCE_EVIDENCE_BUILT, "确定性 SourceEvidence 已建立。", [item.id for item in evidence.domain_evidence], safe_metadata={"evidence_count": len(evidence.source_evidence)})
        result = self.discover(state.user_input, courses)
        counts = result.extraction_metadata.get("signal_counts", {})
        state = record_agent_event(
            state,
            self.name,
            EventType.LLM_EXTRACTION_COMPLETED,
            "结构化候选信号抽取完成。",
            safe_metadata={
                "provider": result.extraction_metadata.get("provider"),
                "model": result.extraction_metadata.get("model"),
                "prompt_name": SELF_DISCOVERY_PROMPT_NAME,
                "prompt_version": SELF_DISCOVERY_PROMPT_VERSION,
                "signal_counts": counts,
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "total_tokens": result.usage.total_tokens,
                "latency_ms": result.extraction_metadata.get("latency_ms"),
            },
        )
        state = record_agent_event(state, self.name, EventType.EVIDENCE_VALIDATION_COMPLETED, "所有候选信号的 evidence ID 已通过确定性校验。", safe_metadata={"evidence_count": len(result.user_profile.evidence)})
        state = state.validated_copy(course_records=courses, user_profile=result.user_profile, profile_confirmed=False, profile_uncertainties=result.uncertainties, clarification_questions=result.clarification_questions, self_discovery_metadata=result.extraction_metadata)
        state = record_agent_event(state, self.name, EventType.PROFILE_ASSEMBLED, "确定性 ProfileAssembler 已生成 UserProfile v1。", [item.id for item in result.user_profile.evidence], safe_metadata={"profile_version": 1, "signal_counts": counts})
        if result.clarification_questions:
            state = record_agent_event(state, self.name, EventType.CLARIFICATION_QUESTIONS_CREATED, "已创建少量结构化澄清问题。", safe_metadata={"question_count": len(result.clarification_questions)})
        return record_agent_event(state, self.name, EventType.PROFILE_CONFIRMATION_REQUIRED, "UserProfile 草案已生成；必须等待用户确认。", safe_metadata={"profile_version": 1, "confirmed": False})
