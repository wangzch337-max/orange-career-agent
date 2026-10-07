"""D.5 public synthetic external observer; no production imports this module."""

from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch
from data.models import UserProfile, ProfileSectionEntry, EvidenceItem, EvidenceSourceType as S
from specific_role.sources import SpecificRoleRegistry
from evidence_match.models import Relation
from evidence_match.service import analyze


def synthetic_profile(source, base=None):
    """Authored fictional whole-statement records, never a real person's resume."""
    base = base or UserProfile(profile_id="public_d5_synthetic")
    statements = (source.responsibilities[0], "仅在协助范围内完成：" + source.responsibilities[1],
                  "目前无法独立完成：" + source.inputs[0])
    evidence = [EvidenceItem(id=f"public_d5_evidence_{i}", source_type=S.EXPLICIT_USER_INPUT,
        source_name="public_synthetic_d5", statement=text, confidence=1) for i,text in enumerate(statements)]
    entries = [ProfileSectionEntry(entry_id=f"public_d5_entry_{i}", label=text, details=["公开虚构练习；非真实任职记录。"],
        evidence_ids=[evidence[i].id], source_type=S.EXPLICIT_USER_INPUT, confidence=1) for i,text in enumerate(statements)]
    changes = dict(work_experience=[*base.work_experience, *entries], evidence=[*base.evidence, *evidence])
    return (base.create_revision(**changes) if base.confirmed else
            UserProfile.model_validate({**base.model_dump(), **changes})).confirm()


def evaluate_match(root, source):
    from tests.career_discovery_doubles import prepared
    from tests.test_specific_role import expanded
    h = prepared(root)
    try:
        w = h.workspace
        w.memory_service.save_confirmed_profile(w.subject_id, synthetic_profile(source, h.current()))
        records = SpecificRoleRegistry().inventory().records
        peers = [s for s in records if s.direction_identity == source.direction_identity]
        expanded(h, source.direction_identity.title, peers.index(source))
        before = h.current(), h.memories(), h.history()
        c = h.checks
        def forbidden(*a, **k): raise AssertionError("D5_FORBIDDEN_WRITE_OR_MEMORY")
        with patch.object(w.memory_service, "save_confirmed_profile", forbidden), patch.object(w.memory_service, "retrieve_context", forbidden), patch.object(w.store, "append_turn", forbidden):
            s = w.evidence_match
            c.require("d5_admitted", s.submit("这个角色适合我吗？") and s.current())
            c.require("d5_relations", {Relation.DIRECT, Relation.PARTIAL, Relation.UNKNOWN, Relation.TENSION} <= {r.relation_type for r in s.result.relationships})
            user = {i.signal_id:i for i in s.context.user.signals}
            work = {i.signal_id:i for i in s.context.work.signals}
            for r in s.result.relationships:
                c.require("d5_user_ownership", set(r.user_evidence_ids) == {e for ref in r.user_signal_ids for e in user[ref].evidence_ids})
                c.require("d5_work_ownership", set(r.work_evidence_ids) == {e for ref in r.work_signal_ids for e in work[ref].evidence_ids})
                c.require("d5_versions", r.profile_version == before[0].version and r.source_version == source.version and r.source_fingerprint == s.context.work.source_fingerprint)
                c.require("d5_unknown_has_no_false_negative", r.relation_type != Relation.UNKNOWN or not r.user_signal_ids)
                c.require("d5_tension_bilateral", r.relation_type != Relation.TENSION or bool(r.user_signal_ids and r.user_evidence_ids and r.work_evidence_ids))
            c.require("d5_no_score_or_actions", not set(type(s.result).model_fields) & {"fit_score", "percentage", "ranking", "best_role", "good_fit", "bad_fit", "actions"})
            c.require("d5_work_not_qualification", all(r.relation_type == Relation.UNKNOWN for r in s.result.relationships if work[r.work_signal_ids[0]].field == "capabilities_involved"))
            c.require("d5_variation_unknown", s.context.work.variation == source.organizational_variation and s.context.work.unknowns == source.unknowns)
            c.require("d5_authority_unchanged", before == (h.current(), h.memories(), h.history()))
            c.require("d5_no_persistence", not w.chat.messages and "evidence_match" not in w._snapshot())
            c.require("d5_qa_not_taken", not s.submit("Python decorator 是什么？"))
            stamp = s.binding
            w.reload_completed_turn(w.thread.thread_id)
            c.require("d5_qa_resume", s.current() and s.binding == stamp)
            c.require("d5_detail", s.submit("这里具体用了我的哪段经历？"))
            c.require("d5_detail_grounded", s.messages[-1].detailed and s.messages[-1].relationships)
            token = s.token(); w.create_new_thread()
            c.require("d5_new_chat_clears", s.binding is None and not s.messages)
            c.require("d5_replay_consumed", s.submit("我还缺什么？", token=token) and not s.messages)
        return len(c.passed)
    finally:
        h.close()


def run():
    attempts = failures = checks = 0
    def blocked(*a, **k):
        nonlocal attempts
        attempts += 1
        raise AssertionError("D5_OFFLINE_BOUNDARY")
    base = Path(__file__).resolve().parents[1] / "artifacts/evaluation"
    base.mkdir(parents=True, exist_ok=True)
    with patch.object(socket.socket, "connect", blocked), patch.object(socket, "create_connection", blocked), patch("providers.models.load_llm_settings", blocked), patch("resume_evidence.session._qwen_provider", blocked):
        for source in SpecificRoleRegistry().inventory().records:
            with TemporaryDirectory(prefix="d5-", dir=base) as directory:
                try: count = evaluate_match(directory, source)
                except Exception:
                    failures += 1; print(f"FAIL {source.representative_role_id} category=validation")
                else:
                    checks += count; print(f"PASS {source.representative_role_id} checks={count}")
    print(f"D.5 total=9 PASS={9-failures} FAIL={failures} checks_passed={checks} network_attempts={attempts}")
    return failures or attempts


if __name__ == "__main__":
    raise SystemExit(bool(run()))
