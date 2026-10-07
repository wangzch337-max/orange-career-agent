"""Transient progressive D.5 presentation, never the persisted chat path."""

from html import escape
import streamlit as st
from evidence_match.session import LABELS
from ui.onboarding.assets import sphere_markup


def render_match_messages(workspace, anchor, reality_offset, landscape_offset, specific_offset):
    session = workspace.evidence_match
    # The transcript entry point validates once before rendering its offsets.
    # Do not re-project/re-read the same sources for every nested empty offset.
    for message in session.messages:
        if (message.anchor, message.reality_offset, message.landscape_offset, message.specific_offset) != (
                anchor, reality_offset, landscape_offset, specific_offset): continue
        with st.chat_message(message.role, avatar=sphere_markup() if message.role == "assistant" else None):
            st.markdown(escape(message.text).replace("\n", "<br>"), unsafe_allow_html=True)
            for index, relation in enumerate(message.relationships):
                st.markdown(f"**{index+1}. {LABELS[relation.relation_type]}**")
                context = message.context
                work = next(s for s in context.work.signals if s.signal_id in relation.work_signal_ids)
                st.text(work.label)
                st.text(relation.reason)
                if message.detailed:
                    st.caption("已确认用户侧材料（自述/审核记录，不是独立资质认证）")
                    evidence = {e.evidence_id:e for e in context.user.evidence}
                    for ref in relation.user_evidence_ids:
                        st.text(evidence[ref].text)
                        st.caption(f"{ref} · {evidence[ref].source_type} · {evidence[ref].source_name}")
                    if not relation.user_evidence_ids: st.text("这项关系目前没有足够的用户侧证据。")
                    st.caption("工作侧：公开合成资料 · " + work.authority.value)
                    for ref in relation.work_evidence_ids: st.caption(ref)
                    for limitation in relation.limitations: st.text(limitation)
                    st.caption(f"画像 v{relation.profile_version} · source v{relation.source_version} · {relation.source_fingerprint}")
                    for provenance in relation.user_sources: st.caption(provenance)
