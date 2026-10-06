"""External public-only D.3 observer; no product dependency on evaluation."""

from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch
from career_background_evaluation.harness import CareerHarness, CapturingFake, CheckFailure
from career_background_evaluation.scenarios import SCENARIOS
from career_background_evaluation.discovery import program
from role_landscape.models import Dimension

DIRECTIONS = ("Business Analysis", "Knowledge Operations", "Process Improvement")


def evaluate_landscape(root, title):
    h = CareerHarness(root, SCENARIOS[12])
    try:
        h.prepare(); h.resolve_all(); h.confirm(memory=True)
        c, w = h.checks, h.workspace
        before = h.current(), h.memories(), h.history()
        d = w.career_discovery
        d.provider_factory = lambda: CapturingFake(program((title,)))
        result = d.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向")
        selected, token = result.directions[0].direction_id, d.token()
        c.require("d3_parent_selected", w.explore_direction(token, selected))
        s = w.role_landscape
        def no_access(*a, **k): raise CheckFailure("d3_forbidden_authority_access")
        with patch.object(w.memory_service, "retrieve_context", no_access), patch.object(w.memory_service.memory_store, "get", no_access), patch("career_runtime.tools.ToolRegistry.execute", no_access):
            for text in ("这个方向有哪些岗位？", "这个方向有哪些角色类型？", "刚才那个方向有哪些岗位？"):
                c.require("d3_overview", s.submit(text) and s.messages[-1].reply.dimension == Dimension.OVERVIEW)
            c.require("d3_exact_direction", s.source.direction_identity.title == title)
            c.require("d3_membership_grounded", set(s.binding.displayed_role_ids) == {m.role_id for m in s.source.memberships})
            c.require("d3_small_nonranked", len(s.source.roles) == 3 and s.messages[-1].reply.role_ids == s.binding.displayed_role_ids)
            c.require("d3_old_roles_absent", all(v not in s.source.model_dump_json() for v in ("AI Product Intern", "AI Application Engineer", "Data Analyst")))
            for text in ("第一种主要做什么？", "第二种和第一种有什么区别？", "刚才偏系统的那个呢？", "哪个更偏沟通？"):
                c.require("d3_followup", s.submit(text) and s.messages[-1].reply is not None)
                c.require("d3_claim_grounded", s.service.validate(s.messages[-1].reply, s.source) == s.messages[-1].reply)
            for text in ("第四种主要做什么？", "role_missing 平时做什么？", "具体有哪些招聘职位", "那你觉得哪个更适合我？", "还有其他类型吗？"):
                c.require("d3_no_guess_or_match", s.submit(text) and s.messages[-1].reply is None)
            c.require("d3_qa_not_taken", not s.submit("Python decorator 是什么？"))
            stamp = s.binding
            d.invalidate(); w.reload_completed_turn(w.thread.thread_id)
            c.require("d3_qa_context_retained", s.current() and s.binding == stamp)
            c.require("d3_qa_resume", s.submit("刚才第二种角色平时和谁合作？") and s.messages[-1].reply is not None)
            c.require("d3_no_authority_change", before == (h.current(), h.memories(), h.history()))
            c.require("d3_no_match", not w.controller.state or not w.controller.state.get("match_results"))
            c.require("d3_no_persistence", not w.chat.messages and "role_landscape" not in w._snapshot())
            old = s.token(); w.create_new_thread()
            c.require("d3_new_chat_clear", not s.messages and s.binding is None)
            c.require("d3_replay_consumed", s.submit("第一种主要做什么？", token=old) and not s.messages)
            c.require("d3_missing_parent_no_fallback", s.submit("这个方向有哪些岗位？") and s.messages[-1].reply is None)
        h.privacy_checks(before[0])
        return len(c.passed)
    finally:
        h.close()


def run():
    attempts = failures = checks = 0
    def blocked(*a, **k):
        nonlocal attempts
        attempts += 1
        raise AssertionError("Offline D.3 forbids network/config")
    base = Path(__file__).resolve().parents[1] / "artifacts/evaluation"
    base.mkdir(parents=True, exist_ok=True)
    with patch.object(socket.socket, "connect", blocked), patch.object(socket, "create_connection", blocked), patch("providers.models.load_llm_settings", blocked), patch("resume_evidence.session._qwen_provider", blocked):
        for index, title in enumerate(DIRECTIONS, 1):
            with TemporaryDirectory(prefix="landscape-d3-", dir=base) as directory:
                try:
                    count = evaluate_landscape(directory, title)
                except Exception as error:
                    failures += 1
                    print(f"FAIL d3_{index} check={str(error) if isinstance(error, CheckFailure) else 'evaluation_exception'}")
                else:
                    checks += count
                    print(f"PASS d3_{index} checks={count}")
    print(f"D.3 total=3 PASS={3-failures} FAIL={failures} checks_passed={checks} network_attempts={attempts}")
    return failures or attempts


if __name__ == "__main__":
    raise SystemExit(bool(run()))
