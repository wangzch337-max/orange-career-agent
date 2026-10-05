"""Chat-native local intake; ordinary AI consent grants no resume-sharing rights."""

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from resume_intake.models import ResumeParseResult, ResumeParseStatus
from resume_intake.policy import MAX_UPLOAD_BYTES, display_filename, file_type


STATUS_COPY = {
    ResumeParseStatus.SELECTED: "已选择简历",
    ResumeParseStatus.READING: "正在读取你的简历…",
    ResumeParseStatus.READY: "已经在本地读取这份简历。",
    ResumeParseStatus.UNSUPPORTED: "仅支持 PDF 或 DOCX 简历。",
    ResumeParseStatus.TOO_LARGE: "文件过大，请上传不超过 10 MiB 的简历。",
    ResumeParseStatus.ENCRYPTED: "无法读取加密 PDF，请上传未加密的文件。",
    ResumeParseStatus.SCAN_OR_IMAGE_ONLY: "这份文件目前无法可靠读取文字，请上传可复制文字的 PDF 或 DOCX。",
    ResumeParseStatus.PARSE_FAILED: "无法安全读取这份文件，请检查文件或换一份 PDF / DOCX。",
}
_WIDGET_KEY = "orange_resume_upload_widget"


def release_upload(uploaded) -> bool:
    """Release only this widget's in-memory bytes in the pinned Streamlit runtime."""
    try:
        ctx = get_script_run_ctx(suppress_warning=True)
        if ctx is not None:
            # Current Streamlit 1.64 memory manager; never remove all session files.
            remove = getattr(ctx.uploaded_file_mgr, "remove_file", None)
            if not callable(remove):
                return False
            remove(ctx.session_id, uploaded.file_id)
        return True
    except Exception:
        return False
    finally:
        uploaded.close()


def render_file_card(workspace) -> None:
    state = workspace.resume_intake
    if state.result is None:
        return
    with st.container(border=True, key="orange_resume_card"):
        st.text(state.display_name)
        st.caption(f"{state.file_type.upper()} · {state.size_bytes / 1024:.1f} KiB")
        st.write(STATUS_COPY[state.result.status])
        if st.button("移除简历", key="orange_resume_remove", disabled=workspace.agent_session.busy):
            state.clear()
            st.rerun()


def render_resume_upload(workspace) -> None:
    """The upload is separate from chat submission and never enters transcript."""
    state = workspace.resume_intake
    key = f"orange_resume_{state.thread_id}_{state.revision}"
    previous = st.session_state.get(_WIDGET_KEY)
    if previous != key and previous is not None:
        old = st.session_state.pop(previous, None)
        if old is not None:
            release_upload(old)
    st.session_state[_WIDGET_KEY] = key
    with st.popover("＋", disabled=workspace.agent_session.busy):
        uploaded = st.file_uploader(
            "上传简历", type=["pdf", "docx"], accept_multiple_files=False,
            max_upload_size=MAX_UPLOAD_BYTES // (1024 * 1024), key=key,
            help="仅在本地读取；不会自动修改画像或记忆，也不会发送给 AI。",
            disabled=workspace.agent_session.busy,
        )
    if uploaded is not None:
        try:
            if uploaded.size > MAX_UPLOAD_BYTES:
                state.clear()
                state.display_name, state.file_type, state.size_bytes = display_filename(uploaded.name), file_type(uploaded.name), uploaded.size
                state.result = ResumeParseResult(ResumeParseStatus.TOO_LARGE, "UPLOAD_LIMIT")
                state._event("resume_validation_failed", state.result.status)
            else:
                state.select(workspace.owner_scope_id, workspace.thread.thread_id, uploaded.name, uploaded.getvalue())
                # A native status delta is delivered before parsing starts, not a fake
                # delay or an AI chat message. The result survives only session reruns.
                with st.status(STATUS_COPY[ResumeParseStatus.READING], expanded=False) as status:
                    parsed = state.parse_pending()
                    if parsed is not None:
                        status.update(label=STATUS_COPY[parsed.status], state="complete" if parsed.status == ResumeParseStatus.READY else "error")
        except Exception:
            state.clear()
            state.result = ResumeParseResult(ResumeParseStatus.PARSE_FAILED, "UPLOAD_READ_FAILED")
        finally:
            if not release_upload(uploaded):
                state.clear()
                state.result = ResumeParseResult(ResumeParseStatus.PARSE_FAILED, "UPLOAD_CLEANUP_FAILED")
            # Rotation also applies to validation failures before parsing.
            state.revision += 1
        st.rerun()
