"""Focused native UI consent and Fake-only local end-to-end smoke."""

from copy import deepcopy
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from docx import Document
from streamlit.testing.v1 import AppTest

from providers.fake import FakeLLMProvider
from resume_evidence.context import ProviderResumeContextBuilder, content_fingerprint
from resume_evidence.models import ResumeEvidenceBundle, ResumeEvidenceExtraction
from resume_evidence.service import ResumeUsage
from resume_evidence.session import ResumeAnalysisStatus as Status
from resume_evidence.validation import validate_extraction
from resume_intake.models import ResumeParseStatus
from tests.resume_evidence_doubles import docx_for, document_for, evidence_output
from tests.test_chat_product import app, WORKSPACE_KEY


@pytest.mark.parametrize("background,category", [("audit", "work_experience"), ("student", "education")])
def test_local_parse_explicit_consent_fake_source_validation_ready(tmp_path, monkeypatch, background, category):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("C.2 smoke must not construct a live provider")
    monkeypatch.setattr("resume_evidence.session._qwen_provider", forbidden)
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        value.file_uploader[0].upload("public-synthetic.docx", docx_for(background)).run()
        assert not value.exception and workspace.resume_intake.pending is None
        document = workspace.resume_intake.result.document
        fake = FakeLLMProvider(evidence_output(document, category=category))
        workspace.resume_analysis.provider_factory = lambda: fake
        before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        assert not workspace.agent_session.consent
        assert value.button(key="orange_resume_ai_consent") and fake.call_count == 0
        assert not [b for b in value.button if b.key == "orange_resume_ai_analyze"]
        value.button(key="orange_resume_ai_consent").click().run()
        assert workspace.resume_analysis.has_consent and fake.call_count == 0
        assert not workspace.agent_session.consent  # Consent stores remain independent.
        value.button(key="orange_resume_ai_analyze").click().run()
        assert not value.exception
        session = workspace.resume_analysis
        assert session.status == Status.READY and fake.call_count == 1
        assert session.bundle.authority == "candidate" and session.bundle.source_id == document.source_id
        assert session.bundle.category_counts()["projects"] == 0
        assert any("Orange 从简历中整理出的职业证据" == element.value for element in value.subheader)
        assert any("Fake provider" in element.value for element in value.caption)
        assert not workspace.chat.messages
        assert [message.name for message in value.chat_message] == ["user", "assistant"]
        assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
        value.run()
        value.radio(key="orange_appearance").set_value("深色模式").run()
        assert fake.call_count == 1 and session.bundle is not None
        value.button(key="orange_resume_ai_revoke").click().run()
        assert not session.has_consent and session.bundle is None and fake.call_count == 1
        assert value.button(key="orange_resume_ai_consent")
    finally:
        workspace.close()


SUMMARY_TITLE = "Orange 从简历中整理出的职业证据"
QUOTE_ONLY = "PUBLIC_SYNTHETIC_QUOTE_ONLY_MARKER"
PROVIDER_WORDING = "PROVIDER_DESCRIPTION_MUST_NOT_APPEAR"
PUBLIC_FACTS = (
    "Audit Associate", "Public Synthetic Audit Firm", "2021 - 2024",
    "Prepared statutory audit working papers and reconciliation",
    "Reconciled public synthetic accounts", "Financial reporting", "Excel", "Reviewed 12 reports",
    "Public Synthetic Welcome Event", "Coordinated a student welcome event", "Documented event findings",
    "Used Python",
)


@pytest.fixture(autouse=True)
def forbid_live_summary_providers(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Resume summary must not load credentials or construct a live provider")
    monkeypatch.setattr("providers.models.load_llm_settings", forbidden)
    monkeypatch.setattr("resume_evidence.session._qwen_provider", forbidden)


def public_document(text=None):
    document = document_for(source_id="public_summary_source")
    return replace(document, blocks=(replace(document.blocks[0],
        text=text or "\n".join((*PUBLIC_FACTS, QUOTE_ONLY))),))


def public_output(document):
    work = evidence_output(document, claim=PROVIDER_WORDING)["items"][0]
    work.update(responsibilities=[PUBLIC_FACTS[3]], achievements=[PUBLIC_FACTS[4]],
                domain_signals=[PUBLIC_FACTS[5]], tools=[PUBLIC_FACTS[6]], business_metrics=[PUBLIC_FACTS[7]])
    project = evidence_output(document, category="projects", claim=PROVIDER_WORDING)["items"][0]
    project.update(evidence_id="resume_evidence_002", project_name=PUBLIC_FACTS[8],
                   responsibilities=[PUBLIC_FACTS[9]], achievements=[PUBLIC_FACTS[10]])
    general = evidence_output(document, category="skills", claim="Experience with Python")["items"][0]
    general["evidence_id"] = "resume_evidence_003"
    return {"items": [work, project, general], "uncertainties": [
        {"topic": "proficiency", "status": "unclear", "source_block_ids": [document.blocks[0].block_id]},
        {"topic": "career_goal", "status": "not_stated", "source_block_ids": []},
    ]}


def admitted_bundle(document=None, output=None, *, partial=False):
    document = document or public_document()
    output = output if output is not None else public_output(document)
    canonical = validate_extraction(ResumeEvidenceExtraction.model_validate(output),
                                    ProviderResumeContextBuilder().build(document))
    return ResumeEvidenceBundle(**canonical.model_dump(), source_id=document.source_id,
        content_fingerprint=content_fingerprint(document), owner_scope_id="public_summary_owner",
        thread_id="public_summary_thread", context_partial=partial)


def summary_app():
    import streamlit as st
    from ui.resume_evidence import render_evidence_summary
    render_evidence_summary(st.session_state["bundle"])


def analysis_app():
    import streamlit as st
    from ui.resume_evidence import render_resume_analysis
    render_resume_analysis(st.session_state["workspace"])


def summary_view(bundle):
    value = AppTest.from_function(summary_app)
    value.session_state["bundle"] = bundle
    value.run()
    assert not value.exception
    return value


def visible_text(value):
    return "\n".join(element.value for element in
        [*value.subheader, *value.markdown, *value.caption, *value.text]
        if not element.value.startswith("<style>"))


def test_summary_groups_work_projects_and_canonical_general_facts_without_controls():
    bundle = admitted_bundle()
    before = bundle.model_dump_json()
    value = summary_view(bundle)
    text = visible_text(value)
    assert SUMMARY_TITLE in text
    for field in PUBLIC_FACTS:
        assert field in text
    for label in ("工作经历", "项目经历", "职责", "成果", "领域线索", "工具", "业务成果 / 指标", "能力 / 技能"):
        assert label in text
    headings = [m.value for m in value.markdown]
    assert headings.index("**工作经历**") < headings.index("**项目经历**") < headings.index("**能力 / 技能**")
    assert "已通过来源与结构校验" in text and "尚未写入职业画像或长期记忆" in text
    assert "简历证据 ≠ 已确认职业画像。" in text and "你的明确确认" in text
    assert "仍不确定" in text and "熟练度：尚不明确" in text and "职业目标：简历未说明" in text
    assert not value.button and not value.text_input and not value.checkbox
    assert not value.get("json") and not value.code and not value.dataframe
    assert bundle.model_dump_json() == before and value.session_state["bundle"] is bundle


def test_summary_never_renders_provider_descriptions_internal_fields_or_source_quotes():
    bundle = admitted_bundle()
    text = visible_text(summary_view(bundle))
    for secret in (PROVIDER_WORDING, "Experience with Python", QUOTE_ONLY, bundle.source_id,
                   bundle.content_fingerprint, bundle.owner_scope_id, bundle.thread_id,
                   bundle.model_dump_json(), "normalized_claim", "source_quotes", "source_block_ids",
                   "evidence_id", "block_id", "content_fingerprint", "owner_scope_id", "thread_id",
                   "raw_completion", "request_id", "prompt", "80%", "0.8"):
        assert secret not in text
    for item in bundle.items:
        assert item.evidence_id not in text
        for ref in item.source_block_ids:
            assert ref not in text
        for quote in item.source_quotes:
            assert quote.excerpt not in text


def test_typed_presentation_uses_material_fields_when_non_authoritative_wording_differs():
    # UI-only defensive fixture, not a new canonical admission path.
    data = admitted_bundle().model_dump()
    data["items"] = data["items"][:2]
    for item in data["items"]:
        item["normalized_claim"] = PROVIDER_WORDING
    bundle = ResumeEvidenceBundle.model_validate(data)
    assert all(item.canonical_text != item.normalized_claim for item in bundle.items)
    text = visible_text(summary_view(bundle))
    assert PROVIDER_WORDING not in text
    assert all(fact in text for fact in PUBLIC_FACTS[:-1])


@pytest.mark.parametrize("category,label", [
    ("education", "教育经历"), ("responsibilities", "职责"), ("achievements", "成果"),
    ("skills", "能力 / 技能"), ("tools", "工具"), ("domain_knowledge", "领域知识"),
    ("certifications", "证书"), ("professional_qualifications", "专业资格"),
    ("research", "研究经历"), ("leadership", "领导 / 协作经历"), ("collaboration", "协作经历"),
    ("languages", "语言"), ("portfolio", "作品集"), ("business_metrics", "业务成果 / 指标"),
    ("awards", "奖项"), ("publications", "发表"), ("other_evidence", "其他证据"),
    ("uncertainty", "待澄清证据"),
])
def test_general_categories_use_neutral_labels_and_admitted_canonical_text(category, label):
    document = public_document()
    output = evidence_output(document, category=category, claim="Experience with Python")
    bundle = admitted_bundle(document, output)
    assert bundle.items[0].canonical_text == "Used Python"
    text = visible_text(summary_view(bundle))
    assert "**" + label + "**" in text and "• Used Python" in text
    assert "Experience with Python" not in text and QUOTE_ONLY not in text
    assert "**工作经历**" not in text and "**项目经历**" not in text


@pytest.mark.parametrize("topic,label", [
    ("dates", "时间"), ("organization", "机构"), ("proficiency", "熟练度"),
    ("ownership", "责任归属"), ("career_goal", "职业目标"), ("role_overlap", "角色重叠"),
    ("project_work_boundary", "项目 / 工作边界"), ("other", "其他待澄清事项"),
])
@pytest.mark.parametrize("status,label_status", [("unclear", "尚不明确"), ("not_stated", "简历未说明")])
def test_uncertainties_only_render_closed_topic_and_status(topic, label, status, label_status):
    document = public_document()
    output = {"items": [], "uncertainties": [{"topic": topic, "status": status,
        "source_block_ids": [document.blocks[0].block_id] if status == "unclear" else []}]}
    text = visible_text(summary_view(admitted_bundle(document, output)))
    assert "**仍不确定**" in text and f"• {label}：{label_status}" in text
    assert document.blocks[0].block_id not in text and QUOTE_ONLY not in text


@pytest.mark.parametrize("missing", ["organization", "time_range", "tools", "achievements", "all_materials"])
def test_partial_work_fields_do_not_create_empty_sections_or_placeholder_facts(missing):
    document = public_document()
    output = evidence_output(document)
    item = output["items"][0]
    item.update(tools=["Excel"], achievements=[PUBLIC_FACTS[4]])
    if missing == "all_materials":
        for field in ("role_title", "organization", "time_range"):
            item[field] = None
        for field in ("responsibilities", "achievements", "domain_signals", "tools", "business_metrics"):
            item[field] = []
        item["normalized_claim"] = "Audit Associate"
    else:
        item[missing] = None if missing in {"organization", "time_range"} else []
    value = summary_view(admitted_bundle(document, output))
    text = visible_text(value)
    assert "工作经历" in text and "Audit Associate" in text and "项目经历" not in text
    if missing in {"organization", "time_range"}:
        assert PUBLIC_FACTS[1 if missing == "organization" else 2] not in text
    absent = {"tools": "工具", "achievements": "成果", "all_materials": "职责"}.get(missing)
    if absent:
        assert absent not in [caption.value for caption in value.caption]
    assert "未知机构" not in text and "暂无" not in text and "None" not in text
    assert not value.warning and not value.error


@pytest.mark.parametrize("empty", [False, True])
def test_projects_can_omit_name_or_all_materials_without_inventing_content(empty):
    document = public_document()
    output = evidence_output(document, category="projects", claim=PUBLIC_FACTS[9])
    output["items"][0].update(project_name=None, responsibilities=[] if empty else [PUBLIC_FACTS[9]])
    text = visible_text(summary_view(admitted_bundle(document, output)))
    assert "项目经历" in text and PUBLIC_FACTS[9] in text
    assert "Audit Associate" not in text and "工作经历" not in text


def test_zero_items_is_a_successful_empty_summary_with_authority_note():
    value = summary_view(admitted_bundle(output={"items": [], "uncertainties": []}))
    text = visible_text(value)
    assert SUMMARY_TITLE in text and "这份简历暂时没有形成可展示的职业证据候选。" in text
    assert "简历证据 ≠ 已确认职业画像。" in text
    assert not value.warning and not value.error and not value.exception
    assert not value.get("json") and not value.button
    assert "工作经历" not in text and "项目经历" not in text and "仍不确定" not in text


@pytest.mark.parametrize("provider", ["fake", "qwen"])
@pytest.mark.parametrize("partial", [False, True])
def test_analysis_summary_preserves_partial_and_offline_captions_without_provider_call(provider, partial):
    # A presentation-only usage envelope is not a real Qwen call.
    bundle = admitted_bundle(partial=partial)
    def forbidden():
        pytest.fail("Rendering must not analyze, revoke or mutate candidate evidence")
    session = SimpleNamespace(has_consent=True, status=Status.READY, bundle=bundle, used=True,
        usage=ResumeUsage(provider, None, None, None, 0), revoke=forbidden, analyze=forbidden)
    workspace = SimpleNamespace(resume_intake=SimpleNamespace(result=SimpleNamespace(status=ResumeParseStatus.READY)),
        resume_analysis=session, agent_session=SimpleNamespace(busy=False))
    value = AppTest.from_function(analysis_app)
    value.session_state["workspace"] = workspace
    before = bundle.model_dump_json()
    value.run()
    assert not value.exception and SUMMARY_TITLE in visible_text(value)
    captions = [caption.value for caption in value.caption]
    assert ("本次只分析了部分简历内容。" in captions) is partial
    assert any("Fake provider" in text for text in captions) is (provider == "fake")
    assert "qwen" not in "\n".join(e.value for e in [*value.text, *value.subheader]).lower()
    assert [b.key for b in value.button] == ["orange_resume_ai_revoke"]
    assert bundle.model_dump_json() == before and session.bundle is bundle


@pytest.mark.parametrize("status,bundle_present", [(Status.READY, False), (Status.PROVIDER_FAILED, True)])
def test_summary_requires_both_ready_status_and_a_bundle(status, bundle_present):
    session = SimpleNamespace(has_consent=True, status=status, used=True, usage=None,
        bundle=admitted_bundle() if bundle_present else None, revoke=lambda: None)
    value = AppTest.from_function(analysis_app)
    value.session_state["workspace"] = SimpleNamespace(
        resume_intake=SimpleNamespace(result=SimpleNamespace(status=ResumeParseStatus.READY)),
        resume_analysis=session, agent_session=SimpleNamespace(busy=False))
    value.run()
    assert not value.exception and SUMMARY_TITLE not in visible_text(value)


@pytest.mark.parametrize("theme", ["跟随系统", "浅色模式", "深色模式"])
def test_real_shell_summary_theme_rerenders_are_read_only_and_never_reanalyze(tmp_path, monkeypatch, theme):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        document = Document()
        document.add_paragraph("\n".join((*PUBLIC_FACTS, QUOTE_ONLY)))
        data = BytesIO()
        document.save(data)
        value.file_uploader[0].upload("public-synthetic.docx", data.getvalue()).run()
        popovers = [element.proto.popover.label for element in value.get("popover")]
        parsed = workspace.resume_intake.result.document
        fake = FakeLLMProvider(public_output(parsed))
        workspace.resume_analysis.provider_factory = lambda: fake
        def forbidden(*_args, **_kwargs):
            pytest.fail("Read-only Resume summary may not invoke Profile or Memory write paths")
        monkeypatch.setattr(workspace.memory_service.profile_store, "save_confirmed_profile", forbidden)
        for method in ("create_candidate", "create_confirmed", "confirm", "supersede"):
            monkeypatch.setattr(workspace.memory_service.memory_store, method, forbidden)
        value.button(key="orange_resume_ai_consent").click().run()
        assert fake.call_count == 0
        value.button(key="orange_resume_ai_analyze").click().run()
        assert not value.exception and workspace.resume_analysis.status == Status.READY and fake.call_count == 1
        bundle = workspace.resume_analysis.bundle
        before = bundle.model_dump_json()
        clarification = deepcopy(workspace.clarification.state)
        events = tuple(workspace.clarification.events)
        refinement = workspace.profile_refinement.draft
        files = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        value.radio(key="orange_appearance").set_value(theme).run()
        value.run()
        assert not value.exception and value.radio(key="orange_appearance").value == theme
        text = visible_text(value)
        assert SUMMARY_TITLE in text and all(fact in text for fact in PUBLIC_FACTS)
        assert "orange-demo-tag" in text and "Orange Career" in text
        assert len(value.chat_input) == 1 and not workspace.chat.messages
        assert [message.name for message in value.chat_message] == ["user", "assistant"]
        assert [element.proto.popover.label for element in value.get("popover")] == popovers
        assert bundle is workspace.resume_analysis.bundle and bundle.model_dump_json() == before
        assert workspace.clarification.state == clarification and tuple(workspace.clarification.events) == events
        assert workspace.profile_refinement.draft is refinement is None
        assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) is None
        assert not workspace.memory_service.profile_store.list_profile_history(workspace.subject_id)
        assert not workspace.memory_service.memory_store.list_active(workspace.subject_id)
        assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == files
        assert fake.call_count == 1 and not workspace.agent_session.consent
        assert QUOTE_ONLY not in text and PROVIDER_WORDING not in text and "Experience with Python" not in text
    finally:
        workspace.close()


def test_ui_replacement_new_chat_and_delete_remove_consent_candidates(tmp_path):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        value.file_uploader[0].upload("first.docx", docx_for("audit")).run()
        first = workspace.resume_intake.result.document
        fake = FakeLLMProvider(evidence_output(first))
        workspace.resume_analysis.provider_factory = lambda: fake
        value.button(key="orange_resume_ai_consent").click().run()
        value.button(key="orange_resume_ai_analyze").click().run()
        assert fake.call_count == 1 and workspace.resume_analysis.bundle is not None
        value.file_uploader[0].upload("second.docx", docx_for("student")).run()
        assert not value.exception and not workspace.resume_analysis.has_consent
        assert workspace.resume_analysis.bundle is None and fake.call_count == 1
        old = workspace.thread.thread_id
        value.button(key="orange_new_chat").click().run()
        assert workspace.resume_intake.result is None and workspace.resume_analysis.bundle is None
        assert not [b for b in value.button if b.key == "orange_resume_ai_consent"]
        workspace.delete_thread(old)
        assert workspace.resume_analysis.consent is None and fake.call_count == 1
    finally:
        workspace.close()


def test_ui_safe_failure_never_retries_on_rerun(tmp_path):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        value.file_uploader[0].upload("synthetic.docx", docx_for("audit")).run()
        fake = FakeLLMProvider({"raw_completion": "public synthetic invalid output /private/synthetic-path"})
        workspace.resume_analysis.provider_factory = lambda: fake
        value.button(key="orange_resume_ai_consent").click().run()
        value.button(key="orange_resume_ai_analyze").click().run()
        assert not value.exception and fake.call_count == 1
        assert workspace.resume_analysis.status == Status.INVALID_STRUCTURED_OUTPUT
        assert workspace.resume_analysis.bundle is None
        assert any("格式无效" in warning.value for warning in value.warning)
        assert "synthetic-path" not in str([warning.value for warning in value.warning])
        value.run()
        assert fake.call_count == 1
    finally:
        workspace.close()
