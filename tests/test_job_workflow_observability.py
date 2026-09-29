"""Workflow gate and safe event checks for Phase 4."""

from data.models import EventType
from workflows.stages import WorkflowStage


def test_confirmation_gate_still_prevents_job_analysis(paused_state) -> None:
    assert paused_state.stage == WorkflowStage.AWAITING_PROFILE_CONFIRMATION
    assert paused_state.job_intelligence == []


def test_confirmed_profile_runs_all_twenty_job_analyses(completed_state) -> None:
    assert completed_state.stage == WorkflowStage.COMPLETED
    assert len(completed_state.job_intelligence) == 20


def test_all_required_job_observability_events_are_emitted(completed_state) -> None:
    event_types = {event.event_type for event in completed_state.agent_events}
    assert {
        EventType.JOB_INTELLIGENCE_STARTED,
        EventType.JOB_EVIDENCE_BUILT,
        EventType.JOB_LLM_EXTRACTION_COMPLETED,
        EventType.JOB_EVIDENCE_VALIDATION_COMPLETED,
        EventType.JOB_INTELLIGENCE_ASSEMBLED,
        EventType.JOB_UNCERTAINTIES_IDENTIFIED,
        EventType.JOB_INTELLIGENCE_COMPLETED,
    }.issubset(event_types)


def test_observability_contains_counts_but_no_raw_description_or_secret(completed_state) -> None:
    job_events = [
        event for event in completed_state.agent_events
        if event.event_type.value.startswith("job_")
    ]
    serialized = "\n".join(event.model_dump_json() for event in job_events)
    assert '"job_count":20' in serialized
    assert '"evidence_count":' in serialized
    assert "Support a fictional AI product team" not in serialized
    assert "DASHSCOPE_API_KEY" not in serialized
    assert "Authorization" not in serialized


def test_match_agent_has_no_overall_score(completed_state) -> None:
    assert all("overall_score" not in match.model_dump() for match in completed_state.match_results)
