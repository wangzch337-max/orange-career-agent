"""D.2 external offline observer; no production dependency on evaluation/tests."""

from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch

from career_background_evaluation.harness import CareerHarness, CapturingFake, CheckFailure
from career_background_evaluation.scenarios import SCENARIOS
from career_background_evaluation.discovery import EXAMPLES, program
from career_reality.models import Status


def evaluate_reality(scenario, root):
    h = CareerHarness(root, scenario)
    try:
        h.prepare(); h.resolve_all(); h.confirm(memory=True)
        c, w = h.checks, h.workspace
        profile, memories, history = h.current(), h.memories(), h.history()
        titles = EXAMPLES[SCENARIOS.index(scenario)]
        d = w.career_discovery
        d.provider_factory = lambda: CapturingFake(program(titles))
        result = d.start(explicitly_requested=True, consent=True, current_statement=scenario.current)
        c.require("reality_valid_readiness", result is not None)
        if result.directions:
            direction = result.directions[0]
            token = d.token()
            c.require("reality_explicit_selection", d.select(token, direction.direction_id))
            # Once D.1 has validated selection, D.2 must never retrieve Memory.
            def no_memory(*_args, **_kwargs):
                raise CheckFailure("reality_memory_access")
            with patch.object(w.memory_service, "retrieve_context", no_memory), patch.object(w.memory_service.memory_store, "get", no_memory):
                active = w.career_reality.start(token, direction.direction_id)
                if active:
                    c.require("reality_source_supported", all(m.reply is None or w.career_reality.service.validate(m.reply, w.career_reality.source) for m in w.career_reality.messages))
                    c.require("reality_capabilities_not_user", w.career_reality.submit("需要哪些能力？") and "不是在判断" in w.career_reality.messages[-1].text)
                    c.require("reality_general_qa_not_taken", not w.career_reality.submit("Transformer 的 attention 是什么？"))
                    d.invalidate()
                    w.reload_completed_turn(w.thread.thread_id)
                    c.require("reality_context_after_qa", w.career_reality.current() and w.career_reality.submit("通常跟谁合作？"))
                    c.require("reality_unknown_not_invented", w.career_reality.submit("这个方向工资多少？") and w.career_reality.messages[-1].reply is None)
                else:
                    c.require("reality_unsupported_safe", w.career_reality.status == Status.UNSUPPORTED and w.career_reality.source is None)
        else:
            c.require("reality_no_direction_no_transition", w.career_reality.status == Status.IDLE)
        c.require("reality_no_profile_mutation", h.current() == profile and h.history() == history)
        c.require("reality_no_memory_mutation", h.memories() == memories)
        c.require("reality_no_chat_snapshot_authority", not w.chat.messages and "career_reality" not in w._snapshot())
        c.require("reality_no_match", not w.controller.state or not w.controller.state.get("match_results"))
        w.create_new_thread()
        c.require("reality_new_thread_cleared", not w.career_reality.messages and w.career_reality.binding is None)
        h.privacy_checks(profile)
        return len(c.passed)
    finally:
        h.close()


def run():
    attempts = failures = checks = 0
    def blocked(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise AssertionError("Offline reality evaluation forbids network/config")
    base = Path(__file__).resolve().parents[1] / "artifacts/evaluation"
    base.mkdir(parents=True, exist_ok=True)
    with patch.object(socket.socket, "connect", blocked), patch.object(socket, "create_connection", blocked), patch("providers.models.load_llm_settings", blocked), patch("resume_evidence.session._qwen_provider", blocked):
        for scenario in SCENARIOS:
            with TemporaryDirectory(prefix="reality-d2-", dir=base) as directory:
                try:
                    count = evaluate_reality(scenario, directory)
                except Exception as error:
                    failures += 1
                    print(f"FAIL {scenario.scenario_id} check={str(error) if isinstance(error, CheckFailure) else 'evaluation_exception'}")
                else:
                    checks += count
                    print(f"PASS {scenario.scenario_id} checks={count}")
    print(f"D.2 total={len(SCENARIOS)} PASS={len(SCENARIOS)-failures} FAIL={failures} checks_passed={checks} network_attempts={attempts}")
    return failures or attempts


if __name__ == "__main__":
    raise SystemExit(bool(run()))
