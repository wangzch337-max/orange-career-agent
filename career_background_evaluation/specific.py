"""External, public-only nine-archetype D.4 observer, never a product dependency."""

from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch
from career_background_evaluation.harness import CareerHarness, CapturingFake, CheckFailure
from career_background_evaluation.scenarios import SCENARIOS
from career_background_evaluation.discovery import program
from specific_role.models import Dimension, Authority

DIRECTIONS = ("Business Analysis", "Knowledge Operations", "Process Improvement")
QUESTIONS = ("这个角色存在的目的是什么？", "这个角色具体每天做什么？", "能举个具体例子吗？",
    "这个角色最后要交付什么？", "这个角色通常和谁合作？", "这个角色能决定什么？",
    "这个角色工作节奏是什么？", "会不会一直写代码？", "这个角色需要哪些能力？",
    "这个角色在不同组织有什么变化？", "这个角色还有什么不确定？")


def evaluate_specific(root, title, index):
    h = CareerHarness(root, SCENARIOS[12])
    try:
        h.prepare(); h.resolve_all(); h.confirm(memory=True)
        c, w = h.checks, h.workspace
        before = h.current(), h.memories(), h.history()
        d = w.career_discovery
        d.provider_factory = lambda: CapturingFake(program((title,)))
        result = d.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向")
        c.require("d4_valid_parent_selection", w.explore_direction(d.token(), result.directions[0].direction_id))
        parent, s = w.role_landscape, w.specific_role
        c.require("d4_d3_opened", parent.submit("这个方向有哪些岗位？") and parent.current())
        def forbidden(*a, **k): raise CheckFailure("d4_forbidden_authority_access")
        with patch.object(w.memory_service, "retrieve_context", forbidden), patch.object(w.memory_service.memory_store, "get", forbidden), patch("career_runtime.tools.ToolRegistry.execute", forbidden):
            c.require("d4_open", s.submit(f"详细讲讲第{index+1}种角色") and s.current())
            c.require("d4_exact_archetype", s.source.parent_archetype_id == parent.source.roles[index].role_id)
            c.require("d4_membership", s.source.membership.direction_id == parent.binding.direction_id and
                      s.source.membership.archetype_id == s.binding.archetype_id and
                      s.source.membership.representative_role_id == s.binding.representative_role_id)
            c.require("d4_small_opening", len(s.messages[-1].reply.blocks) == 2)
            for text, dimension in zip(QUESTIONS, list(Dimension)[1:]):
                c.require("d4_followup", s.submit(text) and s.messages[-1].reply.dimension == dimension)
                reply = s.messages[-1].reply
                c.require("d4_exact_grounding", s.service.validate(reply, s.source) == reply)
                c.require("d4_both_membership_refs", all(len(b.membership_refs) == 2 for b in reply.blocks))
            c.require("d4_unknown_preserved", all(b.authority == Authority.UNKNOWN for b in s.messages[-1].reply.blocks))
            c.require("d4_independent_increment", all(text not in parent.source.roles[index].model_dump_json()
                for field in ("decision_scope", "work_situations", "inputs", "outputs", "work_rhythm", "technical_involvement") for text in getattr(s.source, field)))
            c.require("d4_comparison_not_taken", not s.submit("第一种和第二种有什么区别？"))
            c.require("d4_d3_difference_retained", parent.submit("第一种和第二种有什么区别？") and parent.messages[-1].reply is not None)
            c.require("d4_direction_not_taken", not s.submit("这个方向整体在解决什么问题？"))
            c.require("d4_d2_purpose_retained", w.career_reality.submit("这个方向整体在解决什么问题？"))
            for text in ("这个角色适合我吗？", "你觉得我能做吗？", "这个角色很有意思"):
                c.require("d4_no_personal_authority", s.submit(text) and s.messages[-1].reply is None)
            c.require("d4_qa_not_taken", not s.submit("Transformer 的 attention 是什么？"))
            stamp = s.binding
            d.invalidate(); w.reload_completed_turn(w.thread.thread_id)
            c.require("d4_qa_retains_context", s.current() and s.binding == stamp)
            c.require("d4_qa_resume", s.submit("这个角色通常和谁合作？") and s.messages[-1].reply is not None)
            c.require("d4_authority_unchanged", before == (h.current(), h.memories(), h.history()))
            c.require("d4_no_match", not w.controller.state or not w.controller.state.get("match_results"))
            c.require("d4_no_persistence", not w.chat.messages and "specific_role" not in w._snapshot())
            c.require("d4_no_legacy_source", all(name not in s.source.model_dump_json() for name in ("AI Product Intern", "AI Application Engineer", "Data Analyst")))
            old = s.token(); w.create_new_thread()
            c.require("d4_new_chat_clears", not s.messages and s.binding is None)
            c.require("d4_replay_consumed", s.submit("这个角色通常和谁合作？", token=old) and not s.messages)
            c.require("d4_missing_parent_no_fallback", s.submit("详细讲讲第一种角色") and s.messages[-1].reply is None)
        h.privacy_checks(before[0])
        return len(c.passed)
    finally:
        h.close()


def run():
    attempts = failures = checks = 0
    def blocked(*a, **k):
        nonlocal attempts
        attempts += 1
        raise AssertionError("Offline D.4 forbids network/config")
    base = Path(__file__).resolve().parents[1] / "artifacts/evaluation"
    base.mkdir(parents=True, exist_ok=True)
    with patch.object(socket.socket, "connect", blocked), patch.object(socket, "create_connection", blocked), patch("providers.models.load_llm_settings", blocked), patch("resume_evidence.session._qwen_provider", blocked):
        for title in DIRECTIONS:
            for index in range(3):
                with TemporaryDirectory(prefix="specific-d4-", dir=base) as directory:
                    try:
                        count = evaluate_specific(directory, title, index)
                    except Exception as error:
                        failures += 1
                        print(f"FAIL d4_{DIRECTIONS.index(title)+1}_{index+1} check={str(error) if isinstance(error, CheckFailure) else 'evaluation_exception'}")
                    else:
                        checks += count
                        print(f"PASS d4_{DIRECTIONS.index(title)+1}_{index+1} checks={count}")
    print(f"D.4 total=9 PASS={9-failures} FAIL={failures} checks_passed={checks} network_attempts={attempts}")
    return failures or attempts


if __name__ == "__main__":
    raise SystemExit(bool(run()))
