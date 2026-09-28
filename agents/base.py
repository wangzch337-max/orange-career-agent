"""不依赖 Agent framework 的轻量接口与事件辅助函数。"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from pydantic import JsonValue

from data.models import AgentEvent, AgentName, EventType, ToolEvent
from utils.ids import next_sequence_id
from workflows.state import WorkflowState


class BaseAgent(ABC):
    """Phase 1 Agent 的最小可测试契约。"""

    name: AgentName

    @abstractmethod
    def run(self, state: WorkflowState) -> WorkflowState:
        """消费并返回一个经过验证的 Shared State。"""


def record_agent_event(
    state: WorkflowState,
    agent_name: AgentName,
    event_type: EventType,
    summary: str,
    evidence_ids: Optional[List[str]] = None,
    safe_metadata: Optional[Dict[str, JsonValue]] = None,
) -> WorkflowState:
    existing_ids = [event.event_id for event in state.agent_events]
    event = AgentEvent(
        event_id=next_sequence_id("agent_event", existing_ids),
        event_type=event_type,
        component=agent_name.value,
        agent_name=agent_name,
        summary=summary,
        evidence_ids=evidence_ids or [],
        safe_metadata=safe_metadata or {},
    )
    return state.validated_copy(agent_events=[*state.agent_events, event])


def record_tool_event(
    state: WorkflowState,
    tool_name: str,
    event_type: EventType,
    summary: str,
    safe_metadata: Optional[dict] = None,
) -> WorkflowState:
    existing_ids = [event.event_id for event in state.tool_events]
    event = ToolEvent(
        event_id=next_sequence_id("tool_event", existing_ids),
        event_type=event_type,
        component=tool_name,
        tool_name=tool_name,
        summary=summary,
        safe_metadata=safe_metadata or {},
    )
    return state.validated_copy(tool_events=[*state.tool_events, event])
