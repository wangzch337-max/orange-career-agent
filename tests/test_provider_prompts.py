"""Versioned prompt and message construction tests."""

import json

from providers.demo import load_demo_input
from providers.models import MessageRole
from providers.prompts import (
    PROMPT_NAME,
    PROMPT_PATH,
    PROMPT_VERSION,
    build_profile_signal_messages,
    load_profile_signal_prompt,
)


def test_prompt_file_exists_and_is_versioned() -> None:
    assert PROMPT_PATH.is_file()
    assert PROMPT_PATH.name == "profile_signal_extraction_v1.md"
    assert PROMPT_NAME == "profile_signal_extraction"
    assert PROMPT_VERSION == "v1"


def test_prompt_contains_required_safety_boundaries() -> None:
    prompt = load_profile_signal_prompt()
    for phrase in ("不得虚构", "evidence_ids", "人格", "不进行职位推荐", "不生成最终"):
        assert phrase in prompt


def test_messages_are_limited_to_system_and_user() -> None:
    demo_input = load_demo_input()
    messages = build_profile_signal_messages(
        load_profile_signal_prompt(), demo_input.source_evidence
    )
    assert [item.role for item in messages] == [MessageRole.SYSTEM, MessageRole.USER]
    payload = json.loads(messages[1].content)
    assert len(payload["source_evidence"]) == 3
