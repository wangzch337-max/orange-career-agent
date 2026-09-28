"""Phase 1 确定性 Self-Discovery Agent stub。"""

from typing import Dict, List

from data.models import (
    AgentName,
    CandidateSkill,
    EvidenceBackedStatement,
    EvidenceItem,
    EvidenceSourceType,
    EventType,
    Goal,
    GoalHorizon,
    InterestSignal,
    SignalStrength,
    UserProfile,
    ValueSignal,
)
from agents.base import BaseAgent, record_agent_event, record_tool_event
from tools.base import CourseDataProvider
from workflows.stages import WorkflowStage
from workflows.state import WorkflowState


COURSE_SKILL_RULES: Dict[str, str] = {
    "Introduction to Artificial Intelligence": "Artificial Intelligence",
    "AI-Driven Innovation": "AI Product Thinking",
    "Data Analytics for Smart Applications": "Data Analytics",
}


class SelfDiscoveryAgent(BaseAgent):
    """用三个显式课程标题规则验证 evidence-first 数据流。"""

    name = AgentName.SELF_DISCOVERY

    def __init__(self, course_provider: CourseDataProvider) -> None:
        self.course_provider = course_provider

    def run(self, state: WorkflowState) -> WorkflowState:
        if state.stage != WorkflowStage.SELF_DISCOVERY:
            raise ValueError("Self-Discovery Agent 只能在 self_discovery 阶段运行")

        state = record_agent_event(
            state,
            self.name,
            EventType.AGENT_STARTED,
            "开始执行 Phase 1 确定性画像规则。",
        )

        courses = state.course_records
        if not courses:
            state = record_tool_event(
                state,
                self.course_provider.name,
                EventType.TOOL_CALLED,
                "读取公开的本地课程 fixture。",
            )
            courses = self.course_provider.load()
            state = record_tool_event(
                state,
                self.course_provider.name,
                EventType.TOOL_COMPLETED,
                "课程 fixture 读取完成。",
                {"record_count": len(courses)},
            )

        if state.user_profile is not None:
            profile = state.user_profile
        else:
            profile = self._build_profile(state.user_input, courses)

        evidence_ids = [item.id for item in profile.evidence]
        state = state.validated_copy(
            course_records=courses,
            user_profile=profile,
            profile_confirmed=False,
        )
        return record_agent_event(
            state,
            self.name,
            EventType.AGENT_COMPLETED,
            f"生成或校验 UserProfile v{profile.version}；等待用户确认。",
            evidence_ids,
        )

    def _build_profile(self, user_input: dict, courses: list) -> UserProfile:
        career_interest = str(user_input.get("career_interest", "AI 相关职业探索"))
        career_goal = str(user_input.get("career_goal", "比较不同的 AI 相关实习方向"))
        program = str(user_input.get("program", "AI 相关硕士课程"))
        project = user_input.get("project_experience", {})
        project_name = "匿名课程项目"
        project_summary = "完成一个小型 AI 应用原型"
        if isinstance(project, dict):
            project_name = str(project.get("name", project_name))
            project_summary = str(project.get("summary", project_summary))

        evidence: List[EvidenceItem] = [
            EvidenceItem(
                id="ev_user_interest_01",
                source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                source_name="sample_user_input.career_interest",
                statement=career_interest,
                confidence=1.0,
                metadata={"fixture": True},
            ),
            EvidenceItem(
                id="ev_user_goal_01",
                source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                source_name="sample_user_input.career_goal",
                statement=career_goal,
                confidence=1.0,
                metadata={"fixture": True},
            ),
            EvidenceItem(
                id="ev_project_01",
                source_type=EvidenceSourceType.PROJECT,
                source_name=project_name,
                statement=project_summary,
                confidence=1.0,
                metadata={"fixture": True},
            ),
        ]

        skills: List[CandidateSkill] = []
        for course in courses:
            evidence_id = f"ev_course_{course.course_id}"
            evidence.append(
                EvidenceItem(
                    id=evidence_id,
                    source_type=EvidenceSourceType.COURSE,
                    source_name=course.title,
                    statement=course.summary,
                    confidence=1.0,
                    metadata={"course_id": course.course_id, "fixture": True},
                )
            )
            skill_label = COURSE_SKILL_RULES.get(course.title)
            if skill_label:
                skills.append(
                    CandidateSkill(
                        skill_id=f"skill_{course.course_id}",
                        label=skill_label,
                        level="emerging",
                        source_type=EvidenceSourceType.COURSE,
                        confidence=0.8,
                        evidence_ids=[evidence_id],
                    )
                )

        values_input = user_input.get("career_values", ["持续学习"])
        if not isinstance(values_input, list) or not values_input:
            values_input = ["持续学习"]
        values: List[ValueSignal] = []
        for index, label in enumerate(values_input, start=1):
            evidence_id = f"ev_user_value_{index:02d}"
            evidence.append(
                EvidenceItem(
                    id=evidence_id,
                    source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                    source_name=f"sample_user_input.career_values[{index - 1}]",
                    statement=str(label),
                    confidence=1.0,
                    metadata={"fixture": True},
                )
            )
            values.append(
                ValueSignal(
                    value_id=f"value_{index:02d}",
                    label=str(label),
                    importance=None,
                    source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                    confidence=1.0,
                    evidence_ids=[evidence_id],
                )
            )

        return UserProfile(
            profile_id="profile_demo_001",
            education_summary=program,
            skills=skills,
            interests=[
                InterestSignal(
                    interest_id="interest_ai_career_01",
                    label=career_interest,
                    strength=SignalStrength.STRONG,
                    source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                    confidence=1.0,
                    evidence_ids=["ev_user_interest_01"],
                )
            ],
            values=values,
            goals=[
                Goal(
                    goal_id="goal_career_exploration_01",
                    label=career_goal,
                    horizon=GoalHorizon.SHORT,
                    source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                    evidence_ids=["ev_user_goal_01"],
                )
            ],
            strengths=[
                EvidenceBackedStatement(
                    text="具有完成小型 AI 应用项目的公开 Demo 证据。",
                    source_type=EvidenceSourceType.PROJECT,
                    confidence=0.8,
                    evidence_ids=["ev_project_01"],
                )
            ],
            development_areas=[
                EvidenceBackedStatement(
                    text="仍需通过实习或实践项目补充岗位环境证据。",
                    source_type=EvidenceSourceType.SYSTEM_FIXTURE,
                    confidence=0.6,
                    evidence_ids=["ev_user_goal_01"],
                )
            ],
            evidence=evidence,
        )
