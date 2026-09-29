"""普通 Python 实现的确定性工作流引擎。"""

from typing import Dict, Optional

from pydantic import JsonValue, ValidationError
from providers.errors import LLMError

from agents.base import record_agent_event, record_tool_event
from agents.job_intelligence import JobIntelligenceAgent
from agents.match_insight import MatchInsightAgent
from agents.self_discovery import SelfDiscoveryAgent
from data.models import AgentName, EventType
from tools.report import DeterministicReportBuilder
from workflows.stages import (
    FixtureLoadError,
    InvalidWorkflowTransition,
    ProfileNotConfirmedError,
    WorkflowStage,
    ensure_transition_allowed,
)
from workflows.state import WorkflowState


class DeterministicWorkflowEngine:
    """按显式状态边调用 Agent stub 与 Report Builder。"""

    def __init__(
        self,
        self_discovery_agent: SelfDiscoveryAgent,
        job_intelligence_agent: JobIntelligenceAgent,
        match_insight_agent: MatchInsightAgent,
        report_builder: DeterministicReportBuilder,
    ) -> None:
        self.self_discovery_agent = self_discovery_agent
        self.job_intelligence_agent = job_intelligence_agent
        self.match_insight_agent = match_insight_agent
        self.report_builder = report_builder

    def create_state(
        self,
        session_id: str,
        user_input: Optional[Dict[str, JsonValue]] = None,
    ) -> WorkflowState:
        return WorkflowState(session_id=session_id, user_input=user_input or {})

    def run_until_pause(self, state: WorkflowState) -> WorkflowState:
        """推进至画像确认门、完成或失败。"""

        while state.stage not in {
            WorkflowStage.AWAITING_PROFILE_CONFIRMATION,
            WorkflowStage.COMPLETED,
            WorkflowStage.FAILED,
        }:
            try:
                if state.stage == WorkflowStage.START:
                    state = self.transition(
                        state,
                        WorkflowStage.SELF_DISCOVERY,
                        "输入已建立，进入自我探索阶段。",
                    )
                elif state.stage == WorkflowStage.SELF_DISCOVERY:
                    state = self.self_discovery_agent.run(state)
                    state = self.transition(
                        state,
                        WorkflowStage.AWAITING_PROFILE_CONFIRMATION,
                        "用户画像尚未确认，工作流暂停在画像确认节点。",
                    )
                elif state.stage == WorkflowStage.JOB_INTELLIGENCE:
                    state = self.job_intelligence_agent.run(state)
                    state = self.transition(
                        state,
                        WorkflowStage.MATCH_INSIGHT,
                        "岗位情报结构已验证，进入 evidence-first Match & Insight。",
                    )
                elif state.stage == WorkflowStage.MATCH_INSIGHT:
                    state = self.match_insight_agent.run(state)
                    state = self.transition(
                        state,
                        WorkflowStage.REPORT,
                        "Match evidence links 已验证，进入报告组装阶段。",
                    )
                elif state.stage == WorkflowStage.REPORT:
                    state = self._build_report(state)
                    state = self.transition(
                        state,
                        WorkflowStage.COMPLETED,
                        "确定性工作流已完成。",
                        EventType.WORKFLOW_COMPLETED,
                    )
                else:
                    raise InvalidWorkflowTransition(f"没有为阶段 {state.stage.value} 定义执行步骤")
            except (FixtureLoadError, ValidationError, LLMError) as exc:
                return self.fail(state, f"结构化数据验证失败：{type(exc).__name__}")
        return state

    def confirm_profile(self, state: WorkflowState) -> WorkflowState:
        """确认画像并打开通往岗位情报的唯一合法边。"""

        if state.stage != WorkflowStage.AWAITING_PROFILE_CONFIRMATION:
            raise InvalidWorkflowTransition("只能在 awaiting_profile_confirmation 阶段确认画像")
        if state.user_profile is None:
            raise ProfileNotConfirmedError("当前没有可确认的 UserProfile")
        confirmed_profile = state.user_profile.confirm()
        state = state.validated_copy(
            user_profile=confirmed_profile,
            profile_confirmed=True,
        )
        return self.transition(
            state,
            WorkflowStage.JOB_INTELLIGENCE,
            "画像已确认，进入岗位情报阶段。",
        )

    def request_profile_revision(self, state: WorkflowState, **changes: object) -> WorkflowState:
        """创建下一画像版本，清理下游结果并返回 Self-Discovery。"""

        if state.stage != WorkflowStage.AWAITING_PROFILE_CONFIRMATION:
            raise InvalidWorkflowTransition("只能在 awaiting_profile_confirmation 阶段修订画像")
        if state.user_profile is None:
            raise ProfileNotConfirmedError("当前没有可修订的 UserProfile")
        revision = state.user_profile.create_revision(**changes)
        state = state.validated_copy(
            user_profile=revision,
            profile_confirmed=False,
            job_records=[],
            job_intelligence=[],
            match_results=[],
            report=None,
        )
        return self.transition(
            state,
            WorkflowStage.SELF_DISCOVERY,
            f"用户请求修改画像，创建 UserProfile v{revision.version} 并返回自我探索阶段。",
        )

    def transition(
        self,
        state: WorkflowState,
        target: WorkflowStage,
        summary: str,
        event_type: EventType = EventType.ROUTING_DECISION,
    ) -> WorkflowState:
        ensure_transition_allowed(state.stage, target)
        if target == WorkflowStage.JOB_INTELLIGENCE and not state.profile_confirmed:
            raise ProfileNotConfirmedError("用户画像未确认，禁止进入岗位情报阶段")
        state = state.validated_copy(stage=target)
        return record_agent_event(
            state,
            AgentName.ORCHESTRATOR,
            event_type,
            summary,
        )

    def fail(self, state: WorkflowState, safe_message: str) -> WorkflowState:
        """将可安全公开的错误摘要写入 terminal FAILED 状态。"""

        if state.stage == WorkflowStage.FAILED:
            return state
        state = state.validated_copy(errors=[*state.errors, safe_message])
        return self.transition(
            state,
            WorkflowStage.FAILED,
            "工作流遇到不可恢复的本地验证错误，已安全停止。",
            EventType.WORKFLOW_FAILED,
        )

    def _build_report(self, state: WorkflowState) -> WorkflowState:
        if state.user_profile is None or not state.profile_confirmed:
            raise ProfileNotConfirmedError("报告需要已确认的 UserProfile")
        state = record_tool_event(
            state,
            self.report_builder.name,
            EventType.TOOL_CALLED,
            "由已校验结构组装 CareerReport。",
        )
        report = self.report_builder.build(
            workflow_id=state.session_id,
            profile=state.user_profile,
            intelligence=state.job_intelligence,
            matches=state.match_results,
        )
        state = state.validated_copy(report=report)
        return record_tool_event(
            state,
            self.report_builder.name,
            EventType.TOOL_COMPLETED,
            "CareerReport 组装完成。",
            {"role_count": len(report.role_insights)},
        )
