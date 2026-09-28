"""安全 observability event 测试。"""

from data.models import AgentEvent, EventType, ToolEvent


def test_agent_events_serialize(completed_state) -> None:
    event = completed_state.agent_events[0]
    restored = AgentEvent.model_validate_json(event.model_dump_json())
    assert restored == event


def test_tool_events_serialize(completed_state) -> None:
    event = completed_state.tool_events[0]
    restored = ToolEvent.model_validate_json(event.model_dump_json())
    assert restored == event


def test_routing_events_include_confirmation_summaries(completed_state) -> None:
    routing = [
        event
        for event in completed_state.agent_events
        if event.event_type == EventType.ROUTING_DECISION
    ]
    summaries = [event.summary for event in routing]
    assert any("画像尚未确认" in summary for summary in summaries)
    assert any("画像已确认" in summary for summary in summaries)
    assert all("chain-of-thought" not in summary.casefold() for summary in summaries)
