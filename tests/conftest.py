"""Phase 1/2 共用离线测试 fixture。"""

import socket
import pytest

from agents.orchestrator import OrchestratorAgent
from workflows.demo import load_user_input


@pytest.fixture(autouse=True)
def block_live_network(monkeypatch):
    """Every automated test fails immediately if code opens a real socket."""

    def blocked(*args, **kwargs):
        raise AssertionError("自动化测试禁止 live network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def orchestrator() -> OrchestratorAgent:
    return OrchestratorAgent.create_default()


@pytest.fixture
def paused_state(orchestrator: OrchestratorAgent):
    state = orchestrator.engine.create_state("test_session", load_user_input())
    return orchestrator.run(state)


@pytest.fixture
def completed_state(orchestrator: OrchestratorAgent, paused_state):
    return orchestrator.confirm_and_continue(paused_state)
