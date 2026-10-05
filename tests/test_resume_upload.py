"""Native Streamlit upload/card smoke and touched UI lifecycle regressions."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec
from streamlit.proto.Common_pb2 import FileURLs

from resume_intake.models import ResumeParseStatus as Status
from tests.resume_doubles import pdf_bytes, docx_bytes, SYNTHETIC_TEXT
from tests.test_chat_product import app, WORKSPACE_KEY
from ui.resume_upload import STATUS_COPY, release_upload


@pytest.mark.parametrize("name,data", [("public-synthetic.pdf", pdf_bytes()), ("public-synthetic.docx", docx_bytes())])
def test_native_synthetic_upload_reading_ready_and_rerun_without_reparse(tmp_path, monkeypatch, name, data):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        import ui.resume_upload as upload_ui
        native_status = upload_ui.st.status
        labels = []
        def observed_status(label, **kwargs):
            labels.append(label)
            return native_status(label, **kwargs)
        monkeypatch.setattr(upload_ui.st, "status", observed_status)
        before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        value.file_uploader[0].upload(name, data, "application/octet-stream").run()
        assert not value.exception
        state = workspace.resume_intake
        assert labels == [STATUS_COPY[Status.READING]]
        assert state.result.status == Status.READY and state.pending is None
        assert [event.status for event in state.events[-4:]] == [Status.SELECTED, Status.READING, Status.READY, Status.READY]
        assert any(element.value == name for element in value.text)
        assert any(STATUS_COPY[Status.READY] in element.value for element in value.markdown)
        assert value.file_uploader[0].value is None
        assert workspace.chat.messages == [] and not value.chat_message
        assert SYNTHETIC_TEXT not in "\n".join(element.value for element in value.markdown)
        assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
        result = state.result
        value.run()
        assert not value.exception and state.result is result and len(labels) == 1
        assert workspace.agent_session.provider is None
    finally:
        workspace.close()


def test_remove_and_new_chat_clear_card_without_canonical_deletion(tmp_path):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        value.file_uploader[0].upload("synthetic.pdf", pdf_bytes()).run()
        old_thread = workspace.thread.thread_id
        value.button(key="orange_resume_remove").click().run()
        assert workspace.resume_intake.result is None and workspace.thread.thread_id == old_thread
        assert not value.text and value.file_uploader[0].value is None
        value.file_uploader[0].upload("synthetic.docx", docx_bytes()).run()
        workspace.create_new_thread()
        value.run()
        assert workspace.resume_intake.result is None and workspace.thread.thread_id != old_thread
        assert value.file_uploader[0].value is None
        workspace.activate(old_thread)
        value.run()
        assert workspace.resume_intake.result is None
    finally:
        workspace.close()


def test_error_card_is_safe_and_raw_buffer_removed(tmp_path):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        value.file_uploader[0].upload("../../public-safe.pdf", b"private-synthetic-error-detail").run()
        assert not value.exception
        assert workspace.resume_intake.result.status == Status.PARSE_FAILED
        assert workspace.resume_intake.pending is None and value.file_uploader[0].value is None
        text = "\n".join(element.value for element in value.markdown)
        assert STATUS_COPY[Status.PARSE_FAILED] in text
        assert "private-synthetic-error-detail" not in text and "../../" not in text
        assert any(element.value == "public-safe.pdf" for element in value.text)
        assert workspace.chat.messages == []
    finally:
        workspace.close()


def test_upload_manager_removes_only_exact_session_file_and_closes_buffer(monkeypatch):
    calls = []
    ctx = SimpleNamespace(session_id="synthetic-session", uploaded_file_mgr=SimpleNamespace(remove_file=lambda *args: calls.append(args)))
    monkeypatch.setattr("ui.resume_upload.get_script_run_ctx", lambda **_kwargs: ctx)
    uploaded = UploadedFile(UploadedFileRec("synthetic-file", "synthetic.pdf", "application/pdf", pdf_bytes()), FileURLs())
    release_upload(uploaded)
    assert uploaded.closed and calls == [("synthetic-session", "synthetic-file")]


def test_upload_manager_failure_is_safe_and_buffer_still_closed(monkeypatch):
    def broken(*_args):
        raise RuntimeError("/private/synthetic-path private-detail")
    ctx = SimpleNamespace(session_id="synthetic-session", uploaded_file_mgr=SimpleNamespace(remove_file=broken))
    monkeypatch.setattr("ui.resume_upload.get_script_run_ctx", lambda **_kwargs: ctx)
    uploaded = UploadedFile(UploadedFileRec("synthetic-file", "synthetic.pdf", "application/pdf", pdf_bytes()), FileURLs())
    assert release_upload(uploaded) is False and uploaded.closed


def test_intake_does_not_include_provider_or_authority_calls():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sources = [root / "ui/resume_upload.py", *sorted((root / "resume_intake").glob("*.py"))]
    imports = []
    calls = []
    for path in sources:
        tree = ast.parse(path.read_text())
        imports += [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        calls += [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert not any(name and name.split(".")[0] in {"providers", "memory", "agents", "career_runtime", "workflows"} for name in imports)
    assert not {"generate_structured", "confirm", "save_profile", "append_turn", "submit", "queue", "write_bytes", "write_text", "extractall", "extract"} & set(calls)
