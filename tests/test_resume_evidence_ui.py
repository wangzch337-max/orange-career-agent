"""Focused native UI consent and Fake-only local end-to-end smoke."""

from uuid import uuid4

import pytest

from providers.fake import FakeLLMProvider
from resume_evidence.session import ResumeAnalysisStatus as Status
from tests.resume_evidence_doubles import docx_for, evidence_output
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
        assert any("主要职业证据" in element.value for element in value.markdown)
        assert any("Fake provider" in element.value for element in value.caption)
        assert not workspace.chat.messages and not value.chat_message
        assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
        value.run()
        value.radio(key="orange_appearance").set_value("深色模式").run()
        assert fake.call_count == 1 and session.bundle is not None
        value.button(key="orange_resume_ai_revoke").click().run()
        assert not session.has_consent and session.bundle is None and fake.call_count == 1
        assert value.button(key="orange_resume_ai_consent")
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
