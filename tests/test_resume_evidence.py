"""Focused C.2 consent, minimized transport, source validation and authority tests."""

from copy import deepcopy
from dataclasses import asdict, replace
import json
import logging
from uuid import uuid4

import pytest
from pydantic import ValidationError

from providers.fake import FakeLLMProvider
from providers.errors import LLMProviderError
from resume_intake.models import ResumeParseResult, ResumeParseStatus, ParsedResumeDocument, ParsedResumeBlock
from resume_evidence.context import ProviderResumeContextBuilder, content_fingerprint, minimize_text
from resume_evidence.models import ResumeEvidenceExtraction, ResumeEvidenceBundle, WorkExperienceEvidence
from resume_evidence.policy import (MAX_CONTEXT_CHARS, MAX_CONTEXT_JSON_CHARS, MAX_EVIDENCE_ITEMS,
                                    MAX_SOURCE_REFS, MAX_WORK_DETAILS, MAX_UNCERTAINTIES, CATEGORIES)
from resume_evidence.session import ResumeAnalysisStatus as Status
from resume_evidence.validation import validate_extraction, validate_model_claims, ResumeValidationError
from tests.resume_evidence_doubles import document_for, evidence_output, BACKGROUNDS, docx_for
from ui.chat_runtime import Workspace


class RecordingFake(FakeLLMProvider):
    """RAM-only capture of public synthetic requests for boundary assertions."""
    def generate_structured(self, messages, response_model, options, **kwargs):
        self.messages, self.options, self.prompt = messages, options, kwargs
        return super().generate_structured(messages, response_model, options, **kwargs)


@pytest.fixture
def workspace(tmp_path):
    with Workspace(str(uuid4()), tmp_path / "chat") as value:
        yield value


def install(workspace, document=None, output=None):
    document = document or document_for()
    workspace.resume_intake.clear()
    workspace.resume_intake.result = ResumeParseResult(ResumeParseStatus.READY, document=document)
    provider = RecordingFake(output if output is not None else evidence_output(document))
    workspace.resume_analysis.provider_factory = lambda: provider
    return document, provider


def run(workspace):
    assert workspace.resume_analysis.grant_current()
    return workspace.resume_analysis.analyze()


def validate(output, document):
    return validate_extraction(ResumeEvidenceExtraction.model_validate(output), ProviderResumeContextBuilder().build(document))


def diagnose(output, document):
    """Historical model-wording diagnostics, not canonical admission authority."""
    result = validate_model_claims(ResumeEvidenceExtraction.model_validate(output), ProviderResumeContextBuilder().build(document))
    # Positive diagnostics must also remain usable through the production gate.
    assert validate(output, document).items
    return result


def test_no_resume_consent_no_provider_even_with_chat_consent(workspace):
    _, provider = install(workspace)
    workspace.agent_session.set_consent(granted=True)
    assert workspace.agent_session.consent
    assert workspace.resume_analysis.analyze() == Status.CONSENT_REQUIRED
    assert provider.call_count == 0 and workspace.resume_analysis.bundle is None
    workspace.agent_session.set_consent(granted=False)


@pytest.mark.parametrize("field", ["owner_scope_id", "thread_id", "source_id", "fingerprint"])
def test_consent_is_bound_to_complete_identity(workspace, field):
    install(workspace)
    identity = workspace.resume_analysis._identity()
    values = {key: getattr(identity, key) for key in ("owner_scope_id", "thread_id", "source_id", "fingerprint")}
    values[field] = "wrong-public-synthetic-value"
    assert not workspace.resume_analysis.grant(**values)
    assert not workspace.resume_analysis.has_consent


def test_content_change_with_same_source_invalidates_consent(workspace):
    document, provider = install(workspace)
    assert workspace.resume_analysis.grant_current()
    changed = replace(document, blocks=(replace(document.blocks[0], text=document.blocks[0].text + "\nEnglish"),))
    workspace.resume_intake.result = ResumeParseResult(ResumeParseStatus.READY, document=changed)
    assert content_fingerprint(document) != content_fingerprint(changed)
    assert not workspace.resume_analysis.has_consent
    assert workspace.resume_analysis.analyze() == Status.CONSENT_REQUIRED and provider.call_count == 0


@pytest.mark.parametrize("operation", ["replace", "new_chat", "delete", "close", "revoke"])
def test_lifecycle_clears_consent_context_and_candidates(workspace, operation):
    _, provider = install(workspace)
    assert run(workspace) == Status.READY and provider.call_count == 1
    session = workspace.resume_analysis
    old_thread = workspace.thread.thread_id
    if operation == "replace":
        workspace.resume_intake.select(workspace.owner_scope_id, old_thread, "synthetic.docx", docx_for("student"))
        workspace.resume_intake.parse_pending()
    elif operation == "new_chat":
        workspace.create_new_thread()
    elif operation == "delete":
        workspace.delete_thread(old_thread)
    elif operation == "close":
        workspace.close()
    else:
        session.revoke()
    assert session.consent is None and session.bundle is None and session.usage is None
    assert not session.has_consent and provider.call_count == 1


def test_stale_ui_consent_cannot_authorize_replacement(workspace):
    install(workspace)
    old = workspace.resume_analysis._identity()
    install(workspace, document_for("student"))
    assert not workspace.resume_analysis.grant(owner_scope_id=old.owner_scope_id, thread_id=old.thread_id,
                                               source_id=old.source_id, fingerprint=old.fingerprint)


def test_provider_receives_only_minimized_bounded_text_and_options(workspace):
    document, provider = install(workspace)
    assert run(workspace) == Status.READY
    payload = json.loads(provider.messages[1].content)
    assert set(payload) == {"source_id", "partial", "blocks"}
    assert set(payload["blocks"][0]) == {"block_id", "text"}
    assert "data" not in payload and "filename" not in payload and "/Users/" not in provider.messages[1].content
    assert provider.options.model == "qwen3.8-flash" and not provider.options.thinking_enabled
    assert provider.options.max_retries == 0
    assert provider.prompt == {"prompt_name": "resume_evidence", "prompt_version": "v1"}
    assert workspace.resume_analysis.bundle.content_fingerprint == content_fingerprint(document)
    assert workspace.resume_analysis.bundle.authority == "candidate"
    assert workspace.resume_analysis.bundle.items[0].evidence_origin == "resume_provided"


@pytest.mark.parametrize("contact", ["Email: public.person@example.invalid", "Phone: +852 6123 4567",
    "Mobile: 13812345678", "Home address: Flat 2, 12 Sample Street, Sample City",
    "Passport: A1234567", "身份证号码: 123456789012345678", "file:///Users/public-synthetic/resume.docx",
    "http://localhost:8502/private", "/Users/public-synthetic/private/resume.pdf"])
def test_contact_removed_from_provider_context(contact):
    document = document_for()
    document = replace(document, blocks=(replace(document.blocks[0], text=document.blocks[0].text + "\n" + contact),))
    context = ProviderResumeContextBuilder().build(document)
    assert contact not in context.serialized()
    assert all(line in context.blocks[0].text for line in BACKGROUNDS["audit"])
    assert context.redacted_block_count == 1


def test_professional_profile_presence_not_exact_url():
    text, changed = minimize_text("Portfolio: https://behance.net/public-synthetic")
    assert changed and "https://" not in text and "professional profile present" in text


def test_contact_only_document_context_fails():
    document = document_for()
    document = replace(document, blocks=(replace(document.blocks[0], text="Email: public.person@example.invalid\nPhone: +852 6123 4567"),))
    with pytest.raises(ValueError, match="CONTEXT_BUILD_FAILED"):
        ProviderResumeContextBuilder().build(document)


def test_metrics_dates_organization_school_and_role_preserved():
    text = "Audit Associate | Public Synthetic Company | Public College\n2021 - 2024\nReduced cycle time by 18%, revenue $1000000000, 2019-2023\nRevenue +1200000000\nProfessional qualification CPA, English, Excel"
    cleaned, changed = minimize_text(text)
    assert cleaned == text and not changed


def test_context_limits_partial_and_provenance():
    document = document_for()
    blocks = tuple(replace(document.blocks[0], block_id=f"{document.source_id}:block:{i}", text="Public synthetic responsibilities and business metrics " * 50) for i in range(1, 60))
    context = ProviderResumeContextBuilder().build(replace(document, blocks=blocks))
    assert sum(len(block.text) for block in context.blocks) <= MAX_CONTEXT_CHARS
    assert len(context.serialized()) <= MAX_CONTEXT_JSON_CHARS
    assert context.partial and any(block.truncated for block in context.blocks)
    assert {block.block_id for block in context.blocks} <= {block.block_id for block in blocks}
    assert context.input_block_count == 59


@pytest.mark.parametrize("change", ["cross_source", "duplicate_id", "path_id"])
def test_invalid_parsed_document_cannot_build_provider_context(change):
    document = document_for()
    block = document.blocks[0]
    if change == "cross_source":
        document = replace(document, blocks=(replace(block, source_id="other-source"),))
    elif change == "duplicate_id":
        document = replace(document, blocks=(block, block))
    else:
        document = replace(document, source_id="/Users/private/resume.pdf")
    with pytest.raises(ValueError, match="CONTEXT_BUILD_FAILED"):
        ProviderResumeContextBuilder().build(document)


@pytest.mark.parametrize("background", list(BACKGROUNDS))
def test_universal_background_shapes_with_zero_projects(background):
    document = document_for(background)
    category = "education" if background == "student" else "work_experience"
    extraction = validate(evidence_output(document, category=category), document)
    assert len(extraction.items) == 1 and all(item.category != "projects" for item in extraction.items)
    assert "Python" not in extraction.model_dump_json() and "GitHub" not in extraction.model_dump_json()
    if background != "student":
        assert isinstance(extraction.items[0], WorkExperienceEvidence)


@pytest.mark.parametrize("category", list(CATEGORIES))
def test_all_universal_categories_available_and_empty_categories_valid(category):
    document = document_for()
    extraction = validate(evidence_output(document, category=category), document)
    assert extraction.items[0].category == category
    assert ResumeEvidenceExtraction(items=[], uncertainties=[]).items == ()


@pytest.mark.parametrize("bad_ref", ["invented-block", "other-source:block:1"])
def test_unknown_and_cross_resume_refs_rejected(bad_ref):
    document = document_for()
    output = evidence_output(document)
    output["items"][0]["source_block_ids"] = [bad_ref]
    output["items"][0]["source_quotes"][0]["block_id"] = bad_ref
    with pytest.raises(ResumeValidationError, match="INVALID_SOURCE_REFERENCE"):
        validate(output, document)


def test_omitted_real_block_is_not_provider_visible():
    document = document_for()
    blocks = tuple(replace(document.blocks[0], block_id=f"{document.source_id}:block:{i}", text="Work history " * 100) for i in range(1, 50))
    document = replace(document, blocks=blocks)
    output = evidence_output(replace(document, blocks=(blocks[-1],)), category="other_evidence", claim="Work history")
    with pytest.raises(ResumeValidationError, match="INVALID_SOURCE_REFERENCE"):
        validate(output, document)


@pytest.mark.parametrize("mutation", ["no_refs", "unknown_category", "numeric_confidence", "inference_origin", "extra_profile", "missing_items"])
def test_strict_schema_rejects_invalid_output(mutation):
    output = evidence_output(document_for())
    item = output["items"][0]
    if mutation == "no_refs": item["source_block_ids"] = []
    if mutation == "unknown_category": item["category"] = "best_career"
    if mutation == "numeric_confidence": item["confidence"] = 0.98
    if mutation == "inference_origin": item["evidence_origin"] = "model_inference"
    if mutation == "extra_profile": output["confirmed_profile"] = {}
    if mutation == "missing_items": del output["items"]
    with pytest.raises(ValidationError): ResumeEvidenceExtraction.model_validate(output)


@pytest.mark.parametrize("target", ["items", "source_block_ids", "responsibilities", "uncertainties"])
def test_oversized_output_arrays_rejected(target):
    output = evidence_output(document_for())
    if target == "items": output["items"] *= MAX_EVIDENCE_ITEMS + 1
    if target == "source_block_ids": output["items"][0][target] *= MAX_SOURCE_REFS + 1
    if target == "responsibilities": output["items"][0][target] *= MAX_WORK_DETAILS + 1
    if target == "uncertainties": output[target] = [{"topic": "career_goal", "status": "not_stated", "source_block_ids": []}] * (MAX_UNCERTAINTIES + 1)
    with pytest.raises(ValidationError): ResumeEvidenceExtraction.model_validate(output)


def test_exact_duplicate_dedup_and_conflicting_id_rejected():
    document = document_for()
    output = evidence_output(document)
    second = deepcopy(output["items"][0])
    second["evidence_id"] = "resume_evidence_002"
    output["items"].append(second)
    assert len(validate(output, document).items) == 1
    second["evidence_id"] = "resume_evidence_001"
    second["responsibilities"] = []  # Same ID, conflicting supported material facts.
    with pytest.raises(ResumeValidationError, match="EVIDENCE_VALIDATION_FAILED"):
        validate(output, document)


@pytest.mark.parametrize("field,text", [("normalized_claim", "Excellent growth strategist"), ("role_title", "Senior AI Engineer"), ("organization", "Invented Company"), ("responsibilities", ["Owned a commercial product roadmap"])])
def test_inflated_or_unsupported_claim_and_detail_rejected(field, text):
    document = document_for()
    output = evidence_output(document)
    output["items"][0][field] = text
    with pytest.raises(ResumeValidationError, match="EVIDENCE_VALIDATION_FAILED"):
        (diagnose if field == "normalized_claim" else validate)(output, document)


def test_invented_quote_rejected_even_with_real_block_id():
    document = document_for()
    output = evidence_output(document)
    output["items"][0]["source_quotes"][0]["excerpt"] = "AI expert and confirmed career preference"
    with pytest.raises(ResumeValidationError, match="EVIDENCE_VALIDATION_FAILED"):
        validate(output, document)


def test_ambiguous_claim_and_missing_career_goal_stay_uncertain():
    document = document_for()
    output = evidence_output(document)
    output["items"][0].update(confidence="uncertain", uncertainty="unclear_dates", time_range=None)
    output["uncertainties"] = [{"topic": "career_goal", "status": "not_stated", "source_block_ids": []}]
    result = validate(output, document)
    assert result.items[0].confidence == "uncertain" and result.items[0].time_range is None
    assert result.uncertainties[0].status == "not_stated"


def test_career_statement_requires_explicit_intent_and_is_not_profile_preference():
    document = document_for()
    output = evidence_output(document, category="other_evidence")
    output["items"][0]["claim_type"] = "explicit_career_statement"
    with pytest.raises(ResumeValidationError, match="EVIDENCE_VALIDATION_FAILED"):
        validate(output, document)
    document = replace(document, blocks=(replace(document.blocks[0], text="Career objective: seeking operations roles"),))
    output = evidence_output(document, category="other_evidence")
    output["items"][0]["claim_type"] = "explicit_career_statement"
    result = validate(output, document)
    assert result.items[0].evidence_origin == "resume_provided" and not hasattr(result, "career_preferences")


def test_context_failure_is_safe_and_does_not_make_call(workspace, monkeypatch):
    _, provider = install(workspace)
    def fail(*_args): raise RuntimeError("/private/synthetic-path private resume text")
    monkeypatch.setattr(workspace.resume_analysis.builder, "build", fail)
    assert run(workspace) == Status.CONTEXT_BUILD_FAILED and provider.call_count == 0


@pytest.mark.parametrize("failure,expected", [("transport", Status.PROVIDER_FAILED), ("schema", Status.INVALID_STRUCTURED_OUTPUT), ("refs", Status.INVALID_SOURCE_REFERENCE)])
def test_provider_failures_are_safe_no_retries_no_candidates(workspace, failure, expected, caplog):
    document, provider = install(workspace)
    if failure == "transport":
        def bad(*_args, **_kwargs):
            provider.call_count += 1
            logging.getLogger("openai._base_client").warning("public-synthetic-private prompt and completion")
            raise LLMProviderError("/private/synthetic-path raw completion")
        provider.generate_structured = bad
    elif failure == "schema": provider.predefined_response = {"raw_completion": "public synthetic invalid text"}
    else:
        provider.predefined_response["items"][0]["source_block_ids"] = ["invented"]
    assert run(workspace) == expected and provider.call_count == 1
    assert workspace.resume_analysis.bundle is None and workspace.resume_analysis.usage is None
    assert workspace.resume_analysis.analyze() == expected and provider.call_count == 1
    assert "raw completion" not in str(workspace.resume_analysis.events)
    assert "private prompt" not in caplog.text and "raw completion" not in caplog.text


@pytest.mark.parametrize("mutation", ["other_document", "substituted_text", "partial_lie"])
def test_context_must_match_authorized_document_before_provider_call(workspace, monkeypatch, mutation):
    document, provider = install(workspace)
    context = ProviderResumeContextBuilder().build(document)
    if mutation == "other_document":
        context = ProviderResumeContextBuilder().build(document_for("student"))
    elif mutation == "substituted_text":
        context = replace(context, blocks=(replace(context.blocks[0], text="Invented private document"),))
    else:
        document = replace(document, blocks=(document.blocks[0], replace(document.blocks[0], block_id=f"{document.source_id}:block:2")))
        workspace.resume_intake.result = ResumeParseResult(ResumeParseStatus.READY, document=document)
        context = replace(ProviderResumeContextBuilder().build(document), blocks=context.blocks, partial=False)
    monkeypatch.setattr(workspace.resume_analysis.builder, "build", lambda _document: context)
    assert run(workspace) == Status.CONTEXT_BUILD_FAILED and provider.call_count == 0


def test_explicit_intent_on_other_line_does_not_make_work_title_a_preference():
    document = document_for()
    block = replace(document.blocks[0], text="Audit Associate\nCareer objective: seeking education roles")
    document = replace(document, blocks=(block,))
    output = evidence_output(document, category="other_evidence")
    output["items"][0]["claim_type"] = "explicit_career_statement"
    with pytest.raises(ResumeValidationError, match="EVIDENCE_VALIDATION_FAILED"):
        validate(output, document)


def test_negated_skill_does_not_become_positive_capability():
    document = document_for()
    document = replace(document, blocks=(replace(document.blocks[0], text="No Python experience; professional work remains audit"),))
    output = evidence_output(document, category="skills", claim="Python experience")
    with pytest.raises(ResumeValidationError, match="EVIDENCE_VALIDATION_FAILED"):
        validate(output, document)


def test_no_projects_statement_does_not_invalidate_other_work_line():
    document = document_for()
    document = replace(document, blocks=(replace(document.blocks[0], text="No projects listed\n" + document.blocks[0].text),))
    output = evidence_output(document, category="other_evidence", claim="Audit Associate")
    assert validate(output, document).items[0].normalized_claim == "Audit Associate"


def test_actual_qwen_adapter_with_fake_sdk_reuses_strict_non_thinking_contract():
    from types import SimpleNamespace
    from pydantic import SecretStr
    from providers.qwen import QwenProvider
    from resume_evidence.service import ResumeEvidenceExtractor
    document = document_for()
    context = ProviderResumeContextBuilder().build(document)
    calls = []
    def parse_sdk(**kwargs):
        calls.append(kwargs)
        parsed = kwargs["response_format"].model_validate(evidence_output(document))
        return SimpleNamespace(id="public-synthetic-request", usage=None,
                               choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse_sdk)))
    provider = QwenProvider(SecretStr("public-synthetic-placeholder"), SecretStr("https://public-synthetic.invalid"), client=client)
    extraction, usage = ResumeEvidenceExtractor().extract(provider, context)
    assert len(extraction.items) == 1 and usage.provider == "qwen"
    assert len(calls) == 1 and calls[0]["extra_body"] == {"enable_thinking": False}
    assert calls[0]["model"] == "qwen3.8-flash" and calls[0]["response_format"] is ResumeEvidenceExtraction


def test_no_raw_logs_or_structured_payload_and_no_durable_authority_write(workspace, tmp_path, monkeypatch, caplog):
    from tests.test_memory_profiles import _profile_v1
    workspace.memory_service.save_confirmed_profile(workspace.subject_id, _profile_v1())
    document, provider = install(workspace)
    canonical = workspace.memory_service.get_current_confirmed_profile(workspace.subject_id)
    history = workspace.memory_service.profile_store.list_profile_history(workspace.subject_id)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    def forbidden(*_args, **_kwargs): raise AssertionError("Resume extraction crossed authority boundary")
    for method in ("save_confirmed_profile", "create_candidate", "create_confirmed", "confirm_candidate", "supersede", "archive", "purge_subject"):
        monkeypatch.setattr(workspace.memory_service, method, forbidden)
    assert run(workspace) == Status.READY
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == canonical
    assert workspace.memory_service.profile_store.list_profile_history(workspace.subject_id) == history
    assert workspace.memory_service.memory_store.list_active(workspace.subject_id) == []
    assert workspace.chat.messages == [] and "resume" not in str(workspace._snapshot()).lower()
    events = json.dumps([asdict(event) for event in workspace.resume_analysis.events])
    for line in BACKGROUNDS["audit"]:
        assert line not in events and line not in caplog.text and line not in repr(workspace.resume_analysis.bundle)
    assert "messages" not in workspace.resume_analysis.__dict__ and "context" not in workspace.resume_analysis.__dict__
    assert not hasattr(workspace.resume_analysis.bundle, "profile_id")


def test_late_result_after_revoke_or_replace_is_discarded(workspace):
    document, provider = install(workspace)
    original = provider.generate_structured
    def late(*args, **kwargs):
        result = original(*args, **kwargs)
        workspace.resume_analysis.revoke()
        return result
    provider.generate_structured = late
    assert run(workspace) == Status.CONSENT_REQUIRED
    assert workspace.resume_analysis.bundle is None and provider.call_count == 1


def test_revocation_inside_factory_prevents_provider_call(workspace):
    _, provider = install(workspace)
    def factory():
        workspace.resume_analysis.revoke()
        return provider
    workspace.resume_analysis.provider_factory = factory
    assert run(workspace) == Status.CONSENT_REQUIRED and provider.call_count == 0


def test_revocation_during_context_build_cannot_publish_stale_failure(workspace, monkeypatch):
    _, provider = install(workspace)
    def stale(_document):
        workspace.resume_analysis.revoke()
        raise RuntimeError("public synthetic stale context failure")
    monkeypatch.setattr(workspace.resume_analysis.builder, "build", stale)
    assert run(workspace) == Status.CONSENT_REQUIRED and provider.call_count == 0
    assert [event.event for event in workspace.resume_analysis.events] == ["resume_ai_consent_revoked"]


def test_owner_session_and_conversation_isolation(workspace, tmp_path):
    _, provider = install(workspace)
    assert run(workspace) == Status.READY
    with Workspace(str(uuid4()), workspace.root) as other, Workspace(workspace.owner_scope_id, workspace.root) as same_owner_session:
        assert other.resume_analysis.bundle is None and not other.resume_analysis.has_consent
        assert same_owner_session.resume_analysis.bundle is None and not same_owner_session.resume_analysis.has_consent
    old = workspace.thread.thread_id
    workspace.create_new_thread()
    workspace.activate(old)
    assert workspace.resume_analysis.bundle is None and not workspace.resume_analysis.has_consent
    assert provider.call_count == 1


def test_strict_provider_schema_and_universal_prompt():
    from openai.lib._pydantic import to_strict_json_schema
    from resume_evidence.prompt import load_resume_evidence_prompt
    schema = to_strict_json_schema(ResumeEvidenceExtraction)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["items"]["maxItems"] == MAX_EVIDENCE_ITEMS
    prompt = load_resume_evidence_prompt()
    assert all(category in prompt for category in CATEGORIES)
    assert "项目完全可选" in prompt and "不默认学校" in prompt and "不自由改写" in prompt


@pytest.mark.parametrize("invalid", [False, True])
def test_existing_provider_observer_never_records_resume_payload(workspace, invalid):
    from observability.collector import DiagnosticEventCollector
    from observability.context import diagnostic_scope
    from observability.models import ObservabilityContext, run_id
    document, provider = install(workspace)
    if invalid:
        provider.predefined_response = {"Public Synthetic Audit Firm": document.blocks[0].text}
    collector = DiagnosticEventCollector()
    identity = run_id()
    with diagnostic_scope(collector, ObservabilityContext(run_id=identity)):
        status = run(workspace)
    assert status == (Status.INVALID_STRUCTURED_OUTPUT if invalid else Status.READY)
    events = collector.timeline(identity)
    assert events and provider.call_count == 1
    rendered = json.dumps([event.model_dump(mode="json") for event in events])
    for line in BACKGROUNDS["audit"]:
        assert line not in rendered
    assert "source_quotes" not in rendered and "normalized_claim" not in rendered
    assert "resume_evidence@v1" not in rendered


def test_public_c5b_failure_shape_supported_normalization():
    """Public reconstruction, NOT the destroyed live completion or its wording."""
    from career_background_evaluation.scenarios import SCENARIOS, upload_bytes
    from resume_intake.session import ResumeSessionState
    from resume_evidence.context import normalize
    owner, thread = str(uuid4()), str(uuid4())
    intake = ResumeSessionState(owner)
    intake.bind(owner, thread)
    intake.select(owner, thread, "public-synthetic.docx", upload_bytes(SCENARIOS[3]))
    result = intake.parse_pending()
    assert result.status == ResumeParseStatus.READY and intake.pending is None
    document = result.document
    output = evidence_output(document, claim="Experience preparing statutory audit working papers; reconciling financial records")
    claim = output["items"][0]["normalized_claim"]
    # The old whole-phrase-in-one-line contract rejects this genuine paraphrase.
    assert not any(normalize(claim) in normalize(line) for line in document.blocks[0].text.splitlines())
    provider = FakeLLMProvider(output)
    from resume_evidence.service import ResumeEvidenceExtractor
    extraction, usage = ResumeEvidenceExtractor().extract(provider, ProviderResumeContextBuilder().build(document))
    assert extraction.items[0].canonical_label == "Audit Associate"
    assert claim not in extraction.model_dump_json()  # Deterministic rendering, no semantic repair.
    assert extraction.items[0].category == "work_experience" and not any(i.category == "projects" for i in extraction.items)
    assert provider.call_count == 1 and usage.retries == 0


def _grounding_fixture(source, claim, *, category="responsibilities", typed=None):
    document = document_for()
    document = replace(document, blocks=(replace(document.blocks[0], text=source),))
    output = evidence_output(document, category="other_evidence", claim=claim)
    item = output["items"][0]
    item["category"] = category
    if category == "work_experience":
        item.update(role_title=None, organization=None, time_range=None,
                    responsibilities=[], achievements=[], domain_signals=[], tools=[], business_metrics=[])
    elif category == "projects":
        item.update(project_name=None, responsibilities=[], achievements=[])
    item.update(typed or {})
    return document, output


@pytest.mark.parametrize("source,claim", [
    ("Prepared audit working papers.", "Prepared audit working papers."),
    ("Prepared audit working papers.", "PREPARED   AUDIT WORKING PAPERS!"),
    ("Prepared audit working papers.", "Ｅｘｐｅｒｉｅｎｃｅ preparing audit working papers"),
    ("Prepared audit working papers.", "Experience preparing audit working papers."),
    ("Performed account reconciliations.", "Experience with account reconciliation."),
    ("Collaborated with clients during statutory audits.", "Client collaboration during statutory audit work."),
    ("Reviewed tolerances and coordinated preventive maintenance", "Coordinating preventive maintenance; reviewing tolerances"),
    ("Conducted usability interviews and documented accessibility findings", "Documenting accessibility findings · conducting usability interviews"),
    ("Used Excel.", "Experience with Excel."),
    ("Increased conversion by 18%", "Increased conversion by 18%!"),
    ("参与审计底稿整理。", "参与审计底稿整理！"),
])
def test_layered_grounding_accept_matrix(source, claim):
    document, output = _grounding_fixture(source, claim)
    assert diagnose(output, document).items[0].normalized_claim == claim


@pytest.mark.parametrize("source,claim", [
    ("Prepared audit working papers.", "Led audit transformation initiatives across multiple client teams."),
    ("Supported audit engagements.", "Led end-to-end audits independently."),
    ("Used Excel.", "Advanced Excel expert."),
    ("Worked with clients.", "Owned executive stakeholder strategy."),
    ("Increased conversion.", "Increased conversion by 37%."),
    ("Increased conversion by 18%", "Increased conversion by 37%"),
    ("Increased conversion by 18%", "Increased conversion by 18"),
    ("Increased conversion by 18.5%", "Increased conversion by 185%"),
    ("Audit Associate", "Senior Audit Associate"),
    ("Participated in audit review", "Led audit review"),
    ("Performed variance analysis.", "Strong analytical problem-solving ability."),
    ("Prepared audit working papers.", "I prefer a career in Data Analysis."),
    ("Audit Associate", "Expert audit leadership"),
    ("Prepared audit working papers.", "Owned commercial roadmap"),
    ("Reviewed tolerances", "Reviewed account reconciliations"),
    ("Used Excel", "Experience with advanced Excel"),
    ("Used Excel", "Experience"),
    ("Used Excel", "Experience with"),
    ("Used Excel", "with"),
    ("Used Excel", "unrelated"),
    ("Participated in audit review", "Experience performing audit review"),
    ("No Python experience", "Experience with Python"),
    ("May perform account reconciliation", "Experience performing account reconciliation"),
    ("没有主导项目", "主导项目"),
    ("参与审计底稿整理", "独立主导审计转型"),
    # Same tokens aren't sufficient: arguments and causal relationships differ.
    ("Trained clients and reviewed accounts", "Reviewed clients and trained accounts"),
    ("Used Excel\nIncreased conversion by 18%", "Used Excel to increase conversion by 18%"),
    ("Reviewed audit reports", "Reports audit reviewed"),
    ("Collaborated with clients during statutory audits", "Audit collaboration during statutory client work"),
    ("Used Excel", "Used excellent"),
    ("Project ownership: none", "Project ownership"),
])
def test_layered_grounding_reject_matrix(source, claim):
    document, output = _grounding_fixture(source, claim)
    with pytest.raises(ResumeValidationError, match="EVIDENCE_VALIDATION_FAILED"):
        validate(output, document)


def _multi_block_grounding():
    document = document_for()
    texts = ("Audit Associate at Public Synthetic Audit Firm", "Prepared audit working papers", "Reconciled financial records")
    document = replace(document, blocks=tuple(replace(document.blocks[0], block_id=f"{document.source_id}:block:{i}", text=text) for i,text in enumerate(texts,1)))
    _, output = _grounding_fixture(texts[0], "Audit Associate; Experience preparing audit working papers; reconciling financial records",
        category="work_experience", typed={"role_title":"Audit Associate", "organization":"Public Synthetic Audit Firm",
            "responsibilities":[texts[1],texts[2]]})
    # Wrapper scopes the whole claim, not an interior arbitrary phrase.
    output["items"][0]["normalized_claim"] = "Experience preparing audit working papers; reconciling financial records; Audit Associate"
    output["items"][0]["source_block_ids"] = [b.block_id for b in document.blocks]
    output["items"][0]["source_quotes"] = [{"block_id":b.block_id,"excerpt":b.text} for b in document.blocks]
    return document, output


def test_layered_grounding_multi_block_complete_typed_facts():
    document, output = _multi_block_grounding()
    assert validate(output, document).items[0].source_block_ids == tuple(b.block_id for b in document.blocks)


@pytest.mark.parametrize("mutation", ["missing_support", "fake_id", "cross_resume", "fake_excerpt", "omitted_visible_block"])
def test_layered_grounding_multi_block_provenance_fail_closed(mutation):
    document, output = _multi_block_grounding()
    item = output["items"][0]
    expected = "INVALID_SOURCE_REFERENCE"
    context = ProviderResumeContextBuilder().build(document)
    if mutation == "missing_support":
        item["source_block_ids"].pop()
        item["source_quotes"].pop()
        expected = "EVIDENCE_VALIDATION_FAILED"
    elif mutation in {"fake_id","cross_resume"}:
        item["source_block_ids"][0] = "fabricated" if mutation == "fake_id" else "other-resume:block:1"
        item["source_quotes"][0]["block_id"] = item["source_block_ids"][0]
    elif mutation == "fake_excerpt":
        item["source_quotes"][1]["excerpt"] = "Led independently owned transformation"
        expected = "EVIDENCE_VALIDATION_FAILED"
    else:
        context = replace(context, blocks=context.blocks[:-1], partial=True)
    with pytest.raises(ResumeValidationError, match=expected):
        validate_extraction(ResumeEvidenceExtraction.model_validate(output),context)


@pytest.mark.parametrize("field,value", [
    ("role_title","Senior Audit Associate"), ("organization","Unrelated Synthetic Organization"),
    ("time_range","2015 - 2026"), ("responsibilities",["Led end-to-end audit"]),
    ("achievements",["Increased efficiency by 37%"]), ("tools",["Advanced Excel expert"]),
    ("domain_signals",["Executive stakeholder strategy"]), ("business_metrics",["37%"]),
])
def test_layered_grounding_every_typed_work_field_independent(field,value):
    document = document_for()
    output = evidence_output(document)  # normalized_claim is valid; typed smuggling isn't.
    output["items"][0][field] = value
    with pytest.raises(ResumeValidationError,match="EVIDENCE_VALIDATION_FAILED"):
        validate(output,document)


@pytest.mark.parametrize("field,value", [("project_name","Unrelated Project"),("responsibilities",["Owned client roadmap"]),("achievements",["Improved margin by 37%"])])
def test_layered_grounding_project_fields_not_weaker(field,value):
    document, output = _grounding_fixture("Public Synthetic Student Event\nCoordinated welcome event", "Public Synthetic Student Event",
        category="projects",typed={"project_name":"Public Synthetic Student Event","responsibilities":["Coordinated welcome event"]})
    output["items"][0][field] = value
    with pytest.raises(ResumeValidationError,match="EVIDENCE_VALIDATION_FAILED"):
        validate(output,document)


@pytest.mark.parametrize("source,cropped,claim", [
    ("No Python experience", "Python experience", "Python experience"),
    ("Supported colleagues preparing audit working papers", "preparing audit working papers", "Experience preparing audit working papers"),
    ("没有主导项目", "主导项目", "主导项目"),
])
def test_layered_grounding_cropped_qualifier_cannot_launder_support(source,cropped,claim):
    document, output = _grounding_fixture(source,claim)
    output["items"][0]["source_quotes"][0]["excerpt"] = cropped
    with pytest.raises(ResumeValidationError,match="EVIDENCE_VALIDATION_FAILED"):
        validate(output,document)


@pytest.mark.parametrize("background,claim", [
    ("student", "Experience coordinating a student welcome event"),
    ("audit", "Experience preparing statutory audit working papers and reconciliation"),
    ("mechanical", "Experience reviewing tolerances; coordinating preventive maintenance"),
    ("marketing", "Increased conversion by 18%!"),
    ("design", "Experience conducting usability interviews; documenting accessibility findings"),
    ("switcher", "Experience coordinating shift schedules; training colleagues"),
])
def test_layered_grounding_universal_normalization(background,claim):
    document = document_for(background)
    output = evidence_output(document,category="education" if background=="student" else "work_experience",claim=claim)
    result = diagnose(output,document)
    assert len(result.items)==1 and not any(i.category=="projects" for i in result.items)
    assert result.items[0].normalized_claim==claim


def test_layered_grounding_identity_fields_not_inflected_or_reassigned():
    document, output = _grounding_fixture("Audit Associate\nPublic Clients Company", "Public Client Company",
        category="work_experience",typed={"role_title":"Audit Associate","organization":"Public Clients Company"})
    with pytest.raises(ResumeValidationError,match="EVIDENCE_VALIDATION_FAILED"):
        diagnose(output,document)


def test_layered_grounding_invalid_item_rejects_entire_extraction():
    document = document_for()
    output = evidence_output(document)
    bad = deepcopy(output["items"][0])
    bad.update(evidence_id="resume_evidence_002",normalized_claim="Led an unsupported transformation")
    output["items"].append(bad)
    with pytest.raises(ResumeValidationError,match="EVIDENCE_VALIDATION_FAILED"):
        diagnose(output,document)


def test_layered_grounding_contract_prompt_and_schema_agree():
    from resume_evidence.prompt import load_resume_evidence_prompt
    prompt = load_resume_evidence_prompt()
    assert all(term in prompt for term in ("逐字段独立支持","完整事实短语","不自由改写","全部支持块必须引用","中文保持可抽取"))
    schema = ResumeEvidenceExtraction.model_json_schema()
    description = schema["$defs"]["WorkExperienceEvidence"]["properties"]["normalized_claim"]["description"]
    assert "whole supported fact phrases" in description and "all typed fields are checked independently" in description


@pytest.mark.parametrize("source,claim", [
    ("Increased conversion by 18%", "Increased conversion by 18 %"),
    ("Increased conversion by 18 %", "Increased conversion by 18%"),
    ("Conversion change: 18%", "Conversion change: 18 %"),
    ("Managed a budget of $50K", "Managed a budget of $50K!"),
    ("Reviewed invoices totaling HK$20,000", "Reviewed invoices totaling HK$20,000!"),
    ("Achieved a 3x increase", "Achieved a 3x increase!"),
    ("Worked for 10 years", "Worked for 10 years!"),
    ("Coordinated 5 people", "Coordinated 5 people!"),
    ("Recorded change of -18%", "Recorded change of -18 %"),
    ("Recorded change of +18%", "Recorded change of +18 %"),
    ("Reached >=18%", "Reached >=18 %"),
    ("Reached 18%+", "Reached 18 %+"),
    ("工作10年", "工作10年！"),
])
def test_material_qualifier_quantity_accept(source,claim):
    document, output = _grounding_fixture(source,claim)
    assert diagnose(output,document).items[0].normalized_claim == claim


@pytest.mark.parametrize("source,claim", [
    ("Increased conversion by 18%", "Increased conversion by 18"),
    ("Increased conversion by 18 %", "Increased conversion by 18"),
    ("Increased conversion by 18%", "Increased conversion by 18x"),
    ("Increased conversion by 18%", "Increased conversion by 18 dollars"),
    ("Increased conversion by 18%", "Increased conversion by 37%"),
    ("Managed a budget of $50K", "Managed a budget of 50K"),
    ("Managed a budget of $50 K", "Managed a budget of $50"),
    ("Managed a budget of $50K", "Managed a budget of $50M"),
    ("Reviewed invoices totaling HK$20,000", "Reviewed invoices totaling $20,000"),
    ("Reviewed invoices totaling HK$20,000", "Reviewed invoices totaling HK$20"),
    ("Achieved a 3x increase", "Achieved a 3 increase"),
    ("Worked for 10 years", "Worked for 10"),
    ("Worked for 10 years", "Worked for 10 months"),
    ("Coordinated 5 people", "Coordinated 5"),
    ("Recorded change of -18%", "Recorded change of 18%"),
    ("Recorded change of +18%", "Recorded change of 18%"),
    ("Reached >=18%", "Reached 18%"),
    ("Reached 18%+", "Reached 18%"),
    ("Used Python3", "Experience with Python"),
    ("工作10 年", "工作10"),
    ("协调5 人", "协调5"),
])
def test_material_qualifier_quantity_reject(source,claim):
    document, output = _grounding_fixture(source,claim)
    with pytest.raises(ResumeValidationError,match="EVIDENCE_VALIDATION_FAILED"):
        validate(output,document)


@pytest.mark.parametrize("source,claim", [
    ("Project ownership: none", "Project ownership: none"),
    ("Project ownership: none", "Project ownership — none"),
    ("Language: English", "Language: English"),
    ("Language: English", "Language English"),
    ("Certification: CPA", "Certification: CPA"),
    ("Proficiency: basic", "Proficiency: basic"),
    ("Availability: no", "Availability: no"),
    ("No leadership responsibility", "No leadership responsibility!"),
    ("Did not lead the project", "Did not lead the project"),
    ("Participated in implementation", "Participated in implementation!"),
    ("Supported implementation", "Supported implementation!"),
    ("Co-led implementation", "Co-led implementation"),
    ("项目所有权: 无", "项目所有权: 无"),
])
def test_material_qualifier_complete_facts_accept(source,claim):
    document, output = _grounding_fixture(source,claim)
    assert diagnose(output,document).items[0].normalized_claim == claim


@pytest.mark.parametrize("source,claim", [
    ("Project ownership: none", "Project ownership"),
    ("Project ownership (none)", "Project ownership"),
    ("Project ownership: none", "Experience with project ownership"),
    ("No leadership responsibility", "Leadership responsibility"),
    ("Did not lead the project", "Led the project"),
    ("Did not lead the project", "Lead the project"),
    ("Participated in implementation", "Led implementation"),
    ("Supported implementation", "Owned implementation"),
    ("Supported implementation", "Implemented"),
    ("Led implementation", "Participated in implementation"),
    ("Co-led implementation", "Led implementation"),
    ("Implemented under supervision", "Implemented"),
    ("Language: English", "Language"),
    ("Certification: CPA", "Certification"),
    ("Proficiency: basic", "Proficiency"),
    ("Availability: no", "Availability"),
    ("无项目所有权", "项目所有权"),
    ("语言: English", "语言"),
    ("熟练度: 基础", "熟练度"),
])
def test_material_qualifier_deletion_inflation_reject(source,claim):
    document, output = _grounding_fixture(source,claim)
    with pytest.raises(ResumeValidationError,match="EVIDENCE_VALIDATION_FAILED"):
        validate(output,document)


@pytest.mark.parametrize("field,source,claimed", [
    ("business_metrics","Increased conversion by 18%","18"),
    ("business_metrics","Managed a budget of $50K","50K"),
    ("responsibilities","Project ownership: none","Project ownership"),
    ("responsibilities","Did not lead the project","Lead the project"),
    ("tools","Used Python3","Python"),
])
def test_material_qualifier_typed_field_cannot_smuggle(field,source,claimed):
    document, output = _grounding_fixture(source,source,category="work_experience",typed={field:[claimed]})
    with pytest.raises(ResumeValidationError,match="EVIDENCE_VALIDATION_FAILED"):
        validate(output,document)


@pytest.mark.parametrize("source,cropped,claimed", [
    ("Increased conversion by 18%","Increased conversion by 18","Increased conversion by 18"),
    ("Project ownership: none","Project ownership","Project ownership"),
    ("Language: English","Language","Language"),
])
def test_material_qualifier_excerpt_crop_cannot_bypass(source,cropped,claimed):
    document, output = _grounding_fixture(source,claimed)
    output["items"][0]["source_quotes"][0]["excerpt"] = cropped
    with pytest.raises(ResumeValidationError,match="EVIDENCE_VALIDATION_FAILED"):
        validate(output,document)


def test_material_qualifier_student_exact_failure_generic_line_pattern():
    from resume_evidence.models import GeneralResumeEvidence
    document = document_for("student")
    claim = "Experience coordinating a student welcome event"
    output = evidence_output(document,category="education",claim=claim)
    item = output["items"][0]
    assert isinstance(ResumeEvidenceExtraction.model_validate(output).items[0], GeneralResumeEvidence)
    assert "Coordinated a student welcome event" in document.blocks[0].text.splitlines()
    assert "role_title" not in item and "degree" not in item  # No typed degree normalization.
    assert diagnose(output,document).items[0].normalized_claim == claim
    # Same paragraph/line-boundary pattern, unrelated domain and activity.
    other = replace(document,blocks=(replace(document.blocks[0],text="Certificate in Operations\nPublic Synthetic College\nReviewed quality records"),))
    assert validate(evidence_output(other,category="education",claim="Experience reviewing quality records"),other).items


@pytest.mark.parametrize("claim,claim_type,category", [
    ("Expert student event management","reported_fact","education"),
    ("Led the student welcome event independently","reported_fact","education"),
    ("I prefer a Hospitality career","explicit_career_statement","education"),
    ("Strong hospitality expertise","reported_fact","skills"),
    ("Bachelor-level hospitality education","reported_fact","education"),
])
def test_material_qualifier_student_nearby_inflation_reject(claim,claim_type,category):
    document = document_for("student")
    output = evidence_output(document,category=category,claim=claim)
    output["items"][0]["claim_type"] = claim_type
    with pytest.raises(ResumeValidationError,match="EVIDENCE_VALIDATION_FAILED"):
        validate(output,document)


def test_material_qualifier_newline_reordered_facts():
    source = "Reviewed tolerances\nCoordinated preventive maintenance"
    claim = "Experience coordinating preventive maintenance\nreviewing tolerances"
    document, output = _grounding_fixture(source,claim)
    assert diagnose(output,document).items[0].normalized_claim == claim
