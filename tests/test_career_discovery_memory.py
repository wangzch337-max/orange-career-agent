"""New explicit read policy; existing consumers and authority are unchanged."""

from dataclasses import replace
from uuid import uuid4
import pytest

from career_background_evaluation.harness import CapturingFake
from career_discovery.context import CareerDiscoveryContextBuilder, workspace_inputs
from career_discovery.models import DiscoveryError, Status
from data.models import EvidenceSourceType
from memory.integration import MemoryContextCoordinator, MemoryPolicyRegistry
from memory.models import MemoryConsumer, MemoryType, MemoryUseCase
from tests.career_discovery_doubles import prepared, proposal_from_payload


@pytest.fixture
def h(tmp_path):
    value = prepared(tmp_path)
    yield value
    value.close()


def make(h, type=MemoryType.GOAL, subject=None, **kwargs):
    return h.workspace.memory_service.create_confirmed(subject_id=subject or h.workspace.subject_id,
        memory_type=type, content="public synthetic career preference", source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True, **kwargs)


def test_discovery_policy_has_exact_allowlist_and_wrong_consumer_rejected(h):
    policy = MemoryPolicyRegistry().get(MemoryUseCase.CAREER_DIRECTION_DISCOVERY)
    assert policy.consumer == MemoryConsumer.CAREER_DIRECTION_DISCOVERY_SERVICE
    assert set(policy.allowed_memory_types) == {MemoryType.CAREER_PREFERENCE, MemoryType.GOAL, MemoryType.USER_FEEDBACK}
    assert (policy.top_k, policy.max_records, policy.max_characters) == (5, 3, 1800)
    with pytest.raises(PermissionError):
        MemoryContextCoordinator(h.workspace.memory_service).retrieve(subject_id=h.workspace.subject_id,
            use_case=policy.use_case, consumer=MemoryConsumer.ROLE_MEMORY_CONTEXT_SERVICE, query="career")


def test_candidate_superseded_archived_cross_owner_disallowed_types_excluded(h):
    service, subject = h.workspace.memory_service, h.workspace.subject_id
    allowed = make(h)
    wrong = make(h, subject="subject_other")
    excluded = make(h, type=MemoryType.PROJECT_EVIDENCE)
    archived = make(h)
    service.archive(subject, archived.memory_id)
    candidate = service.create_candidate(subject_id=subject, memory_type=MemoryType.GOAL,
        content="public synthetic career preference", source_type=EvidenceSourceType.MODEL_INFERENCE)
    old = make(h)
    replacement = service.supersede(subject, old.memory_id, content="public synthetic career preference",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, confirmed_by_user=True)
    before = service.memory_store.list_history(subject)
    inputs = workspace_inputs(h.workspace, current_statement="探索相邻方向", include_memory=True)
    ids = {s.memory_id for s in inputs.memory.items}
    assert ids.isdisjoint({wrong.memory_id, excluded.memory_id, archived.memory_id, candidate.memory_id, old.memory_id})
    assert ids <= {allowed.memory_id, replacement.memory_id, *[m.memory_id for m in h.memories() if m.memory_type in {MemoryType.GOAL, MemoryType.CAREER_PREFERENCE, MemoryType.USER_FEEDBACK}]}
    assert len(ids) <= 3 and before == service.memory_store.list_history(subject)


def test_cross_owner_context_rejected(h):
    inputs = workspace_inputs(h.workspace, include_memory=True)
    memory = inputs.memory.model_copy(update={"subject_id": "other_subject"})
    with pytest.raises(DiscoveryError):
        CareerDiscoveryContextBuilder().build(replace(inputs, memory=memory), "cross")


@pytest.mark.parametrize("operation", ["archive", "supersede", "content_tamper"])
def test_canonical_memory_revalidated_before_selection(h, operation):
    session = h.workspace.career_discovery
    session.provider_factory = lambda: CapturingFake(proposal_from_payload)
    result = session.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向")
    token = session.token()
    memory_id = result.directions[0].supporting_memory_refs[0]
    service, subject = h.workspace.memory_service, h.workspace.subject_id
    if operation == "archive": service.archive(subject, memory_id)
    elif operation == "supersede":
        service.supersede(subject, memory_id, content="different confirmed goal",
            source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, confirmed_by_user=True)
    else:
        # Simulate a faulty canonical reader without mutating DB/production code.
        old = service.memory_store.get
        service.memory_store.get = lambda subject, id: old(subject, id).model_copy(update={"content": "tampered"})
    assert not session.select(token, result.directions[0].direction_id)
    assert session.status == Status.STALE and session.selected_direction_id is None


def test_forged_memory_context_content_rejected_before_provider(h):
    session = h.workspace.career_discovery
    original = session.input_factory
    def wrong(**kwargs):
        value = original(**kwargs)
        if value.memory and value.memory.items:
            memory = value.memory.model_copy(update={"items": [value.memory.items[0].model_copy(update={"content": "forged history"})]})
            return replace(value, memory=memory)
        return value
    session.input_factory = wrong
    session.provider_factory = lambda: pytest.fail("provider before canonical validation")
    assert session.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向") is None
    assert session.status == Status.INVALID_REFERENCE
