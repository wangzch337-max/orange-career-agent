"""B.3 static shape matrix and actual SDK parsing over an in-memory transport."""

from copy import deepcopy
import json
import logging

import httpx
from openai import OpenAI
from openai.lib._parsing._completions import type_to_response_format_param
from pydantic import SecretStr, ValidationError
import pytest

from clarification.diagnostics import MAX_PARSE_ERRORS, parse_failure
from clarification.models import ClarificationDecision
from clarification.needs import highest_value_needs
from clarification.policy import ClarificationStatus as Status, TurnIntent
from clarification.service import ClarificationError, ClarificationSelector, PROMPT_PATH, request_model
from clarification.session import ClarificationSession
from providers.errors import LLMStructuredOutputError, SafeValidationDiagnostic
from providers.fake import FakeLLMProvider
from providers.qwen import QwenProvider
from tests.clarification_doubles import InputSource, SelectingFake, inputs_for
from tests.test_clarification import context_for

MARKER = "PUBLIC_SYNTHETIC_REJECTED_CONTENT"


@pytest.fixture(autouse=True)
def no_credentials_or_live_construction(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("B.3 is offline; no configuration or live client")
    monkeypatch.setattr("providers.models.load_llm_settings", forbidden)
    monkeypatch.setattr("resume_evidence.session._qwen_provider", forbidden)
    monkeypatch.setattr(QwenProvider, "_create_client", forbidden)


@pytest.fixture
def context():
    # Ownership need has four optional replies, not just a three-reply example.
    return context_for(inputs_for(goal="财务审计", ambiguity="unclear_ownership"))


def response_for(context, *, ask=True):
    need = highest_value_needs(context.needs)[0]
    return {"should_ask": ask, "selected_need_id": need.need_id if ask else None,
            "question": need.allowed_questions[0] if ask else None,
            "suggested_replies": list(need.allowed_replies) if ask else [],
            "source_refs": list(need.source_refs) if ask else [],
            "reason_summary": "highest_value_supported_need" if ask else "no_useful_question_now",
            "confidence": "grounded"}


@pytest.mark.parametrize("count", [0, 1, 4, None])
@pytest.mark.parametrize("confidence", ["grounded", "uncertain"])
def test_valid_true_matrix(context, count, confidence):
    data = response_for(context)
    data["confidence"] = confidence
    if count is None:
        data.pop("suggested_replies")
    else:
        data["suggested_replies"] = data["suggested_replies"][:count]
    provider = FakeLLMProvider(data)
    decision, usage = ClarificationSelector().select(provider, context)
    assert decision.should_ask and decision.confidence == confidence
    assert len(decision.suggested_replies) == (count or 0)
    assert provider.call_count == 1 and usage.retries == 0


@pytest.mark.parametrize("omitted", [(), ("question",), ("selected_need_id",),
    ("suggested_replies",), ("selected_need_id", "question", "suggested_replies")])
@pytest.mark.parametrize("confidence", ["grounded", "uncertain"])
def test_valid_false_matrix_explicit_null_and_only_equivalent_omissions(context, omitted, confidence):
    data = response_for(context, ask=False)
    data["confidence"] = confidence
    for key in omitted:
        data.pop(key)
    decision, _ = ClarificationSelector().select(FakeLLMProvider(data), context)
    assert not decision.should_ask
    assert decision.question is decision.selected_need_id is None
    assert decision.suggested_replies == decision.source_refs == ()
    assert decision.reason_summary == "no_useful_question_now"


@pytest.mark.parametrize("field", ["should_ask", "reason_summary", "source_refs", "confidence"])
@pytest.mark.parametrize("ask", [True, False])
def test_required_fields_are_never_inferred(context, field, ask):
    data = response_for(context, ask=ask)
    data.pop(field)
    with pytest.raises(ClarificationError) as caught:
        ClarificationSelector().select(FakeLLMProvider(data), context)
    error = caught.value.parse_diagnostic
    assert any(item.field_path == (field,) and item.error_type == "missing" for item in error.errors)


@pytest.mark.parametrize("field", ["selected_need_id", "question"])
@pytest.mark.parametrize("absence", ["omitted", "null"])
def test_asking_cannot_infer_need_or_question(context, field, absence):
    data = response_for(context)
    if absence == "omitted":
        data.pop(field)
    else:
        data[field] = None
    with pytest.raises(ClarificationError):
        ClarificationSelector().select(FakeLLMProvider(data), context)


INVALID_SHAPES = [
    {"selected_need_id": "need_" + "f" * 20},  # unknown/stale request ID
    {"should_ask": False},  # contradictory open need + question
    {"question": "问题一？问题二？"},
    {"questions": ["问题一？", "问题二？"]},
    {"question": "最推荐你转做产品经理？"},
    {"question": "x" * 361},
    {"question": {"text": MARKER}},
    {"selected_need_id": {"id": MARKER}},
    {"should_ask": "true"},
    {"suggested_replies": ["x"] * 5},
    {"suggested_replies": [{"text": MARKER}]},
    {"suggested_replies": [None]},
    {"suggested_replies": None},
    {"suggested_replies": MARKER},
    {"suggested_replies": ["x" * 101]},
    {"suggested_replies": ["推荐转产品经理"]},
    {"reason_summary": "HIGHEST_VALUE_SUPPORTED_NEED"},
    {"reason_summary": MARKER},
    {"confidence": "Grounded"},
    {"confidence": MARKER},
    {"source_refs": ["rs_999"]},
    {"source_refs": ["cv_999"]},  # non-visible/cross-conversation ref
    {"source_refs": ["pf_001"]},  # visible but unrelated to selected need
    {"source_refs": ["unowned_resume_reference"]},
    {"source_refs": ["rs_001"] * 2},
    {"source_refs": ["rs_001"] * 9},
    {"source_refs": [{"ref": MARKER}]},
    {"source_refs": None},
    {MARKER: MARKER},
]


@pytest.mark.parametrize("change", INVALID_SHAPES)
def test_safety_negative_matrix_never_coerced(context, change):
    provider = FakeLLMProvider({**response_for(context), **deepcopy(change)})
    with pytest.raises(ClarificationError):
        ClarificationSelector().select(provider, context)
    assert provider.call_count == 1


@pytest.mark.parametrize("change", [
    {"selected_need_id": "need_" + "a" * 20}, {"question": "仍然在问？"},
    {"suggested_replies": ["隐藏回答"]}, {"source_refs": ["rs_001"]},
    {"reason_summary": "highest_value_supported_need"},
])
def test_false_branch_cannot_hide_open_state(context, change):
    with pytest.raises(ClarificationError):
        ClarificationSelector().select(FakeLLMProvider({**response_for(context, ask=False), **change}), context)


def test_duplicate_allowed_reply_is_semantically_rejected(context):
    reply = highest_value_needs(context.needs)[0].allowed_replies[0]
    with pytest.raises(ClarificationError):
        ClarificationSelector().select(FakeLLMProvider({**response_for(context), "suggested_replies": [reply, reply]}), context)


def test_request_schema_and_sdk_translation_preserve_contract(context):
    model = request_model(highest_value_needs(context.needs))
    local = model.model_json_schema()
    wire = type_to_response_format_param(model)
    assert wire["type"] == "json_schema" and wire["json_schema"]["strict"] is True
    schema = wire["json_schema"]["schema"]
    fields = set(ClarificationDecision.model_fields)
    assert set(schema["required"]) == fields and schema["additionalProperties"] is False
    assert set(local["required"]) == fields - {"selected_need_id", "question", "suggested_replies"}
    for name in ("selected_need_id", "question"):
        assert schema["properties"][name]["anyOf"][-1] == {"type": "null"}
        literal = schema["properties"][name]["anyOf"][0]
        assert literal["type"] == "string" and ("const" in literal or "enum" in literal)
    assert schema["properties"]["suggested_replies"]["maxItems"] == 4
    assert schema["properties"]["suggested_replies"]["items"]["maxLength"] == 100
    assert schema["properties"]["source_refs"]["maxItems"] == 8
    assert schema["properties"]["source_refs"]["items"]["pattern"]
    assert schema["properties"]["confidence"]["enum"] == ["grounded", "uncertain"]
    assert schema["properties"]["reason_summary"]["enum"] == ["highest_value_supported_need", "no_useful_question_now"]
    assert all(len(q) <= 360 for n in context.needs for q in n.allowed_questions)
    assert model.model_config["extra"] == "forbid" and model.model_config["frozen"]
    # SDK changes required-key metadata, not nullable choices or local parsing.
    data = response_for(context, ask=False)
    for key in ("selected_need_id", "question", "suggested_replies"):
        data.pop(key)
    assert not model.model_validate_json(json.dumps(data)).should_ask


def test_prompt_names_all_fields_exact_enums_and_branch_wire_policy():
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    assert all(field in prompt for field in ClarificationDecision.model_fields)
    for enum in ("grounded", "uncertain", "highest_value_supported_need", "no_useful_question_now"):
        assert enum in prompt
    assert "should_ask=true" in prompt and "should_ask=false" in prompt
    assert "全部七个字段" in prompt and "JSON 字符串数组" in prompt
    assert "0–4" in prompt and "null" in prompt and "其他字段不得省略" in prompt


def sdk_provider(data, requests):
    def transport(request):
        requests.append(json.loads(request.content))  # Public synthetic fixtures only.
        return httpx.Response(200, json={"id": "public-synthetic-completion", "object": "chat.completion",
            "created": 1, "model": "qwen3.8-flash", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(data, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})
    client = OpenAI(api_key="synthetic-offline-only", base_url="https://public-synthetic.invalid/v1",
                    max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(transport)))
    provider = QwenProvider(SecretStr("public-synthetic-placeholder"), SecretStr("https://public-synthetic.invalid/v1"), client=client)
    return provider, client


@pytest.mark.parametrize("ask,omit", [(True, False), (True, True), (False, False), (False, True)])
def test_real_sdk_with_fake_http_accepts_equivalent_shapes(context, ask, omit):
    data, requests = response_for(context, ask=ask), []
    if omit:
        for key in (("suggested_replies",) if ask else ("selected_need_id", "question", "suggested_replies")):
            data.pop(key)
    provider, client = sdk_provider(data, requests)
    try:
        decision, usage = ClarificationSelector().select(provider, context)
        assert decision.should_ask == ask and usage.retries == 0 and len(requests) == 1
        assert requests[0]["enable_thinking"] is False
        assert requests[0]["response_format"]["json_schema"]["strict"] is True
    finally:
        client.close()


def test_http_success_stop_then_parse_failure_preserves_only_safe_structure(caplog):
    # Reproduces the observed architectural shape, NOT the discarded live output.
    caplog.set_level(logging.DEBUG)
    inputs = inputs_for()
    context = context_for(inputs)
    data, requests = response_for(context), []
    data.pop("confidence")
    data[MARKER] = {"question": MARKER, "resume": MARKER}
    provider, client = sdk_provider(data, requests)
    session = ClarificationSession(inputs.owner_scope_id, InputSource(inputs), provider_factory=lambda: provider)
    before = inputs.profile.model_dump_json()
    try:
        assert not session.run(TurnIntent.RESUME_REVIEW).should_ask
        assert session.status == Status.INVALID_CLARIFICATION_PLAN
        assert len(requests) == 1 and session.parse_failure is not None
        safe = session.parse_failure.as_dict()
        assert safe["stage"] == "clarification_parse" and safe["schema_version"] == "clarification@v1"
        assert safe["error_count"] == 2 and safe["parser_status"] == "rejected"
        assert any(e["field_path"] == ("confidence",) and e["error_type"] == "missing" for e in safe["errors"])
        assert any(e["field_path"] == ("unknown_field",) and e["error_type"] == "extra_forbidden" for e in safe["errors"])
        rendered = json.dumps(safe) + repr(session.events) + caplog.text + repr(session.parse_failure)
        for forbidden in (MARKER, data["question"], "Audit Associate", "input_value", "input", "completion", "prompt"):
            assert forbidden not in rendered
        assert session.current_question() is None and not session.state.answer_candidates
        assert inputs.profile.model_dump_json() == before and session.usage is session.last_decision is None
        session.run(TurnIntent.RESUME_REVIEW)
        assert len(requests) == 1  # No retry/repair/fallback.
        session.invalidate()
        assert session.parse_failure is None
    finally:
        client.close()


@pytest.mark.parametrize("field,value,error_type,path", [
    ("suggested_replies", [MARKER] * 5, "too_long", ("suggested_replies",)),
    ("suggested_replies", [{"text": MARKER}], "string_type", ("suggested_replies", 0)),
    ("source_refs", [{"ref": MARKER}], "string_type", ("source_refs", 0)),
    ("confidence", MARKER, "literal_error", ("confidence",)),
    ("question", MARKER * 40, "string_too_long", ("question",)),
])
def test_safe_top_level_nested_types_and_lengths(context, field, value, error_type, path):
    data = {**response_for(context), field: value}
    with pytest.raises(ValidationError) as caught:
        ClarificationDecision.model_validate(data)
    failure = parse_failure(caught.value)
    assert any(item.field_path == path and item.error_type == error_type for item in failure.errors)
    assert MARKER not in json.dumps(failure.as_dict())
    assert failure.errors[0].level == ("nested" if len(path) > 1 else "top_level")


def test_diagnostic_fingerprint_never_hashes_raw_values_or_unknown_keys(context):
    fingerprints = []
    for text in (MARKER, "ANOTHER_PUBLIC_SYNTHETIC_REJECTED_VALUE"):
        with pytest.raises(ValidationError) as caught:
            ClarificationDecision.model_validate({**response_for(context), "confidence": text, text: text})
        failure = parse_failure(caught.value)
        fingerprints.append(failure.fingerprint)
        assert text not in repr(failure) and text not in json.dumps(failure.as_dict())
    assert fingerprints[0] == fingerprints[1]


def test_diagnostic_bounds_redact_arbitrary_error_type_stage_and_union_label():
    raw = LLMStructuredOutputError(MARKER, stage=MARKER, error_type=MARKER,
        diagnostics=[SafeValidationDiagnostic(MARKER, MARKER, MARKER,
            ("question", MARKER, -1, 999_999_999, MARKER), MARKER, MARKER)] * 20)
    failure = parse_failure(raw)
    assert failure.error_count == 20 and failure.truncated and len(failure.errors) == MAX_PARSE_ERRORS
    assert failure.errors[0].field_path == ("question", "unknown_field", "unknown_field", "unknown_field")
    assert failure.errors[0].error_type == "validation_error"
    assert MARKER not in repr(failure) + json.dumps(failure.as_dict())


def test_root_branch_failure_has_safe_root_path(context):
    with pytest.raises(ValidationError) as caught:
        ClarificationDecision.model_validate({**response_for(context), "should_ask": False})
    failure = parse_failure(caught.value)
    assert failure.errors[0].field_path == () and failure.errors[0].error_type == "value_error"
    assert failure.errors[0].level == "root"


def test_session_failure_safe_structure_isolated_and_not_authority(tmp_path, caplog):
    from tests.test_clarification_ui import ready, snapshot
    from ui.chat_runtime import Workspace
    from uuid import uuid4
    with Workspace(str(uuid4()), tmp_path) as workspace:
        ready(workspace)
        workspace.clarification.provider_factory = lambda: SelectingFake(transform=lambda d: {**d, "confidence": MARKER})
        before = snapshot(tmp_path)
        workspace.clarification.run(TurnIntent.RESUME_REVIEW)
        assert workspace.clarification.parse_failure
        assert not workspace.memory_service.profile_store.list_profile_history(workspace.subject_id)
        assert not workspace.memory_service.memory_store.list_active(workspace.subject_id)
        assert snapshot(tmp_path) == before
        assert MARKER not in caplog.text + json.dumps(workspace.clarification.parse_failure.as_dict())
        workspace.create_new_thread()
        assert workspace.clarification.parse_failure is None


def test_canonical_input_and_general_qa_not_consumed_after_optional_shape(context):
    source = InputSource(inputs_for())
    fake = SelectingFake(transform=lambda d: {k: v for k, v in d.items() if k != "suggested_replies"})
    session = ClarificationSession(source.value.owner_scope_id, source, provider_factory=lambda: fake)
    assert session.run(TurnIntent.RESUME_REVIEW).should_ask
    question = session.current_question()
    assert fake.payloads[0]["sources"][0]["text"] == source.value.resume.items[0].canonical_text
    calls = source.calls
    session.run(TurnIntent.GENERAL_QA, current_statement="Python generator 是什么？")
    assert source.calls == calls and fake.call_count == 1
    assert session.answer(question, "Python generator 是什么？", intent=TurnIntent.GENERAL_QA) is None
    assert session.current_question() == question and not session.state.answer_candidates
    answer = session.answer(question, "I don't know")
    assert answer.uncertainty == "explicit_uncertainty" and fake.call_count == 1
