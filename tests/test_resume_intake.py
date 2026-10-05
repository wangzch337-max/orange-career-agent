"""Focused C.1 parsing, resource, provenance and ephemeral authority boundaries."""

from dataclasses import asdict
from io import BytesIO
import logging
from uuid import uuid4
from zipfile import ZipFile

import pytest

from resume_intake.models import UploadedResume, ResumeParseStatus as Status
from resume_intake.parser import parse_resume
from resume_intake.policy import MAX_UPLOAD_BYTES, display_filename, file_type
from resume_intake.session import ResumeSessionState
from tests.resume_doubles import pdf_bytes, docx_bytes, replace_zip, SYNTHETIC_TEXT
from ui.chat_runtime import Workspace


def parse(name, data):
    return parse_resume(UploadedResume("public-synthetic-source", display_filename(name), file_type(name), len(data), data))


def test_valid_pdf_and_ordered_page_provenance():
    result = parse("synthetic.pdf", pdf_bytes(SYNTHETIC_TEXT, "Second page work responsibilities and collaboration records"))
    assert result.status == Status.READY
    assert result.document.page_count == 2
    assert [block.page_number for block in result.document.blocks] == [1, 2]
    assert [block.location for block in result.document.blocks] == ["page/1", "page/2"]
    assert all(block.source_id == result.document.source_id and block.source_type == "pdf" for block in result.document.blocks)
    assert len({block.block_id for block in result.document.blocks}) == 2


def test_valid_docx_paragraph_table_order_and_locations():
    result = parse("synthetic.docx", docx_bytes())
    assert result.status == Status.READY
    blocks = result.document.blocks
    assert [block.text for block in blocks[:4]] == [SYNTHETIC_TEXT, "Work responsibilities", "Coordinate public synthetic delivery records", "Professional qualification: synthetic safety course"]
    assert [block.kind for block in blocks[:4]] == ["paragraph", "table_cell", "table_cell", "paragraph"]
    assert blocks[1].location == "body/2/table/row/1/cell/1/1"
    assert blocks[3].location == "body/3"
    assert blocks[4].location == "section/1/header/1"
    assert result.document.page_count is None
    assert all(block.page_number is None and block.source_type == "docx" for block in blocks)


@pytest.mark.parametrize("suffix", ["doc", "docm", "rtf", "pages", "png", "zip", "exe", ""])
def test_unsupported_extension(suffix):
    result = parse("synthetic." + suffix, pdf_bytes())
    assert result.status == Status.UNSUPPORTED and result.document is None


@pytest.mark.parametrize("suffix", ["pdf", "docx"])
def test_empty_file(suffix):
    result = parse("empty." + suffix, b"")
    assert result.status == Status.PARSE_FAILED and result.error_code == "EMPTY_FILE"


def test_oversized_upload():
    assert parse("large.pdf", b"%PDF-" + b"x" * MAX_UPLOAD_BYTES).status == Status.TOO_LARGE


@pytest.mark.parametrize("name,data", [("fake.pdf", b"not a PDF"), ("fake.docx", b"not a ZIP"), ("disguised.pdf", docx_bytes()), ("disguised.docx", pdf_bytes())])
def test_fake_extension_rejected(name, data):
    assert parse(name, data).status == Status.PARSE_FAILED


def test_generic_zip_is_not_docx():
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr("note.txt", "public synthetic")
    assert parse("fake.docx", data.getvalue()).error_code == "INVALID_DOCX_CONTAINER"


def test_encrypted_pdf_and_scan_only_safe_states():
    assert parse("encrypted.pdf", pdf_bytes(encrypted=True)).status == Status.ENCRYPTED
    blank = parse("scan.pdf", pdf_bytes(""))
    assert blank.status == Status.SCAN_OR_IMAGE_ONLY and blank.document is None
    assert parse("tiny.pdf", pdf_bytes("abc")).status == Status.SCAN_OR_IMAGE_ONLY


def test_pdf_page_limit():
    assert parse("many.pdf", pdf_bytes(*([SYNTHETIC_TEXT] * 31))).error_code == "PAGE_LIMIT"


@pytest.mark.parametrize("path", ["../escape.xml", "/escape.xml", "word/../../escape.xml", "word\\escape.xml", "C:/escape.xml"])
def test_archive_path_escape_rejected(path):
    result = parse("path.docx", replace_zip(docx_bytes(), {path: b"synthetic"}))
    assert result.error_code == "UNSAFE_ARCHIVE_PATH"


def test_archive_bomb_bounded():
    result = parse("bomb.docx", replace_zip(docx_bytes(), {"word/bomb.xml": b"x" * 100_000}))
    assert result.error_code == "ARCHIVE_LIMIT"


def test_entry_count_limit():
    result = parse("many.docx", replace_zip(docx_bytes(), {f"word/extra{i}.xml": b"<a/>" for i in range(257)}))
    assert result.error_code == "ARCHIVE_LIMIT"


@pytest.mark.parametrize("part", ["word/vbaProject.bin", "word/embeddings/oleObject1.bin"])
def test_active_docx_content_rejected(part):
    assert parse("active.docx", replace_zip(docx_bytes(), {part: b"synthetic"})).error_code == "ACTIVE_CONTENT_UNSUPPORTED"


def test_doctype_never_resolves_external_entities():
    xml = b'<!DOCTYPE a [<!ENTITY private SYSTEM "file:///not-accessed/synthetic">]><a>&private;</a>'
    assert parse("entity.docx", replace_zip(docx_bytes(), {"word/extra.xml": xml})).error_code == "ACTIVE_CONTENT_UNSUPPORTED"


def test_relationship_traversal_rejected():
    xml = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="other" Target="../../escape.xml"/></Relationships>'
    assert parse("relations.docx", replace_zip(docx_bytes(), {"word/_rels/extra.xml.rels": xml})).error_code == "UNSAFE_ARCHIVE_PATH"


def test_hidden_embedded_object_relation_rejected():
    xml = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="../hidden.bin"/></Relationships>'
    assert parse("embedded.docx", replace_zip(docx_bytes(), {"word/_rels/extra.xml.rels": xml, "hidden.bin": b"synthetic"})).error_code == "ACTIVE_CONTENT_UNSUPPORTED"


def test_macro_content_type_even_with_docx_suffix_rejected():
    original = docx_bytes()
    with ZipFile(BytesIO(original)) as archive:
        types = archive.read("[Content_Types].xml").replace(b"wordprocessingml.document.main+xml", b"ms-word.document.macroEnabled.main+xml")
    assert parse("macro.docx", replace_zip(original, {"[Content_Types].xml": types})).error_code == "ACTIVE_CONTENT_UNSUPPORTED"


def test_external_hyperlink_is_never_fetched():
    from docx import Document
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    document = Document(BytesIO(docx_bytes()))
    document.part.relate_to("https://not-fetched.invalid/public-synthetic", RT.HYPERLINK, is_external=True)
    output = BytesIO()
    document.save(output)
    assert parse("external.docx", output.getvalue()).status == Status.READY


def test_pdf_script_and_attachment_are_not_processed():
    from pypdf import PdfReader, PdfWriter
    from pypdf.actions import JavaScript
    writer = PdfWriter()
    writer.append_pages_from_reader(PdfReader(BytesIO(pdf_bytes())))
    writer.add_open_action(JavaScript("throw new Error('public synthetic never executed');"))
    writer.add_attachment("public-synthetic.exe", b"public synthetic never processed")
    output = BytesIO()
    writer.write(output)
    result = parse("inactive.pdf", output.getvalue())
    assert result.status == Status.READY
    assert [block.text for block in result.document.blocks] == [SYNTHETIC_TEXT]


def test_pdf_stream_configuration_is_scoped_and_text_limit_fails_closed(monkeypatch):
    from pypdf import get_configuration
    before = get_configuration()
    monkeypatch.setattr("resume_intake.parser.MAX_TEXT_CHARACTERS", 25)
    result = parse("limited.pdf", pdf_bytes())
    assert result.error_code == "TEXT_LIMIT" and result.document is None
    assert get_configuration() is before


def test_docx_block_limit_fails_closed(monkeypatch):
    monkeypatch.setattr("resume_intake.parser.MAX_BLOCKS", 2)
    result = parse("limited.docx", docx_bytes())
    assert result.error_code == "TEXT_LIMIT" and result.document is None


def test_filename_is_display_only_and_repr_has_no_text():
    data = pdf_bytes()
    upload = UploadedResume("source", display_filename("../../private/<script>\x00resume.pdf"), "pdf", len(data), data)
    assert upload.display_name == "_script_resume.pdf"
    assert "script" not in repr(upload) and SYNTHETIC_TEXT not in repr(upload)
    assert parse("C:\\outside\\resume.PDF", data).status == Status.READY
    assert display_filename("\u202eresume.pdf") == "resume.pdf"


def test_parser_failure_and_logs_are_redacted(monkeypatch, caplog):
    def bad(*_args, **_kwargs):
        logging.getLogger("pypdf._reader").warning("private-name private-text /private/path")
        raise RuntimeError("private-name private-text /private/path")
    monkeypatch.setattr("resume_intake.parser.PdfReader", bad)
    result = parse("private-name.pdf", pdf_bytes())
    assert result.error_code == "PARSE_FAILED" and result.document is None
    assert "private" not in repr(result) and "private" not in caplog.text


def attach(workspace, name="synthetic.pdf", data=None):
    state = workspace.resume_intake
    state.select(workspace.owner_scope_id, workspace.thread.thread_id, name, data or pdf_bytes())
    assert state.result.status == Status.SELECTED
    return state.parse_pending()


def test_no_raw_file_or_text_persistence_and_zero_provider_or_authority_mutation(tmp_path, monkeypatch):
    with Workspace(str(uuid4()), tmp_path / "chat") as workspace:
        # Existing canonical state starts empty; parsing must not even call a writer.
        def forbidden(*_args, **_kwargs):
            raise AssertionError("Resume intake crossed an authority/provider boundary")
        dependencies = workspace.controller.dependencies
        for agent in (dependencies.self_discovery_agent, dependencies.job_intelligence_agent, dependencies.match_insight_agent):
            monkeypatch.setattr(agent.llm_provider, "generate_structured", forbidden)
        for method in ("save_confirmed_profile", "create_candidate", "create_confirmed", "confirm_candidate", "supersede", "archive", "purge_subject"):
            monkeypatch.setattr(workspace.memory_service, method, forbidden)
        monkeypatch.setattr(workspace.memory_service.profile_store, "save_confirmed_profile", forbidden)
        before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        result = attach(workspace, "../../outside.pdf")
        assert result.status == Status.READY and workspace.resume_intake.pending is None
        assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
        assert workspace.chat.messages == [] and workspace.controller.state is None
        assert workspace.memory_service.profile_store.list_profile_history(workspace.subject_id) == []
        assert workspace.memory_service.memory_store.list_active(workspace.subject_id) == []
        for path in tmp_path.rglob("*"):
            if path.is_file():
                assert SYNTHETIC_TEXT.encode() not in path.read_bytes() and b"%PDF-" not in path.read_bytes()
        events = str([asdict(event) for event in workspace.resume_intake.events])
        assert "outside" not in events and SYNTHETIC_TEXT not in events
        assert {event.event for event in workspace.resume_intake.events} >= {"resume_upload_selected", "resume_parse_started", "resume_parse_completed", "resume_ephemeral_cleanup_completed"}


def test_new_chat_switch_delete_refresh_and_close_clear(tmp_path):
    owner = str(uuid4())
    workspace = Workspace(owner, tmp_path / "chat")
    first = workspace.thread.thread_id
    attach(workspace)
    new = workspace.create_new_thread().thread_id
    assert workspace.resume_intake.result is None and workspace.resume_intake.thread_id == new
    assert workspace.resume_intake.events == []
    workspace.activate(first)
    assert workspace.resume_intake.result is None
    attach(workspace)
    workspace.delete_thread(first)
    assert workspace.resume_intake.result is None
    attach(workspace)
    workspace.close()
    assert workspace.resume_intake.result is None and workspace.resume_intake.pending is None
    with Workspace(owner, tmp_path / "chat") as reopened:
        assert reopened.resume_intake.result is None


def test_separate_owner_and_session_isolation(tmp_path):
    owner = str(uuid4())
    with Workspace(owner, tmp_path / "chat") as one, Workspace(str(uuid4()), tmp_path / "chat") as two, Workspace(owner, tmp_path / "chat") as same_owner_other_session:
        attach(one)
        assert two.resume_intake.result is None and same_owner_other_session.resume_intake.result is None
        with pytest.raises(ValueError, match="RESUME_SCOPE_MISMATCH"):
            one.resume_intake.select(two.owner_scope_id, one.thread.thread_id, "synthetic.pdf", pdf_bytes())
        with pytest.raises(ValueError, match="RESUME_SCOPE_MISMATCH"):
            one.resume_intake.select(owner, two.thread.thread_id, "synthetic.pdf", pdf_bytes())
        assert one.resume_intake.result.status == Status.READY


def test_parse_and_delete_preserve_existing_confirmed_profile(tmp_path, monkeypatch):
    from tests.test_memory_profiles import _profile_v1
    with Workspace(str(uuid4()), tmp_path / "chat") as workspace:
        workspace.memory_service.save_confirmed_profile(workspace.subject_id, _profile_v1())
        canonical = workspace.memory_service.get_current_confirmed_profile(workspace.subject_id)
        history = workspace.memory_service.profile_store.list_profile_history(workspace.subject_id)
        memory_path = workspace.memory_service.database.path
        before = memory_path.read_bytes()
        def forbidden(*_args, **_kwargs):
            raise AssertionError("Intake must not confirm or revise authority")
        monkeypatch.setattr(workspace.memory_service, "save_confirmed_profile", forbidden)
        monkeypatch.setattr(workspace.memory_service.profile_store, "save_confirmed_profile", forbidden)
        old_thread = workspace.thread.thread_id
        assert attach(workspace).status == Status.READY
        assert memory_path.read_bytes() == before
        workspace.delete_thread(old_thread)
        assert workspace.resume_intake.result is None
        assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == canonical
        assert workspace.memory_service.profile_store.list_profile_history(workspace.subject_id) == history
        assert memory_path.read_bytes() == before


def test_clear_invalidates_inflight_result(monkeypatch):
    state = ResumeSessionState("public-synthetic-owner")
    state.bind("public-synthetic-owner", "public-synthetic-thread")
    state.select(state.owner_scope_id, state.thread_id, "synthetic.pdf", pdf_bytes())
    def cleared(upload):
        assert state.result.status == Status.READING
        state.clear()
        return parse_resume(upload)
    monkeypatch.setattr("resume_intake.session.parse_resume", cleared)
    assert state.parse_pending() is None and state.result is None and state.pending is None


def test_dependency_contract_rejects_other_edits():
    from tests.runtime_contract import RESUME_REQUIREMENTS, assert_resume_requirements
    original = b"old-dependencies\n"
    assert_resume_requirements(original + RESUME_REQUIREMENTS, original)
    for changed in (original + RESUME_REQUIREMENTS + b"other-framework\n", b"changed-dependency\n" + RESUME_REQUIREMENTS):
        with pytest.raises(AssertionError):
            assert_resume_requirements(changed, original)
