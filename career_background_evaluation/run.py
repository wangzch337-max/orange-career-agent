"""python -m career_background_evaluation.run: safe summaries, no live option."""

from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch

from career_background_evaluation.harness import CheckFailure, evaluate_scenario
from career_background_evaluation.scenarios import SCENARIOS


def run():
    attempts = 0
    def blocked(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise AssertionError("Offline evaluation forbids network")
    base = Path(__file__).resolve().parents[1] / "artifacts/evaluation"
    base.mkdir(parents=True, exist_ok=True)
    failures, checks = 0, 0
    with patch.object(socket.socket, "connect", blocked), patch.object(socket, "create_connection", blocked), patch("providers.models.load_llm_settings", blocked), patch("resume_evidence.session._qwen_provider", blocked):
        for scenario in SCENARIOS:
            with TemporaryDirectory(prefix="universal-career-", dir=base) as directory:
                try:
                    count = evaluate_scenario(scenario, Path(directory))
                except Exception as error:
                    failures += 1
                    code = str(error) if isinstance(error, CheckFailure) else "evaluation_exception"
                    print(f"FAIL {scenario.scenario_id} check={code}")
                else:
                    checks += count
                    print(f"PASS {scenario.scenario_id} checks={count}")
    print(f"total={len(SCENARIOS)} checks_passed={checks} PASS={len(SCENARIOS)-failures} FAIL={failures} EXPECTED_UNCERTAINTY=0 NEEDS_REVIEW=0 network_attempts={attempts}")
    return failures or attempts


if __name__ == "__main__":
    raise SystemExit(bool(run()))
