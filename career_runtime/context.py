"""Minimal bounded provider context; never dump databases or canonical objects."""

import json
import re
from typing import Literal

from career_runtime.models import Contract, ContextItem
from career_runtime.continuity import message_status
from career_runtime.models import TurnStatus
from providers.models import LLMMessage

MAX_HISTORY_CHARACTERS = 4500
MAX_CONTEXT_CHARACTERS = 10000
MAX_RECENT_MESSAGES = 6


class RecentTurn(Contract):
    role: Literal["user", "assistant"]
    text: str
    message_id: str = ""
    provenance: Literal["user_message", "completed_assistant", "legacy_assistant", "cancelled_assistant"] = "user_message"
    excerpted: bool = False
    profile_version: int | None = None


_SECTION = re.compile(r"(?m)^(?:#{1,6}\s+[^\n]+|(?:\d{1,2}[.、)]|[一二三四五六七八九十]+[、.]|第[一二三四五六七八九十\d]+[^\n]{0,15}[：:])[^\n]{0,100})$")
_EXCERPT = "\n【上下文摘录：部分原文省略，原回答完成状态不变】\n"


def excerpt(text, budget, *, prefer_tail=False):
    """Deterministic head + bounded section samples + tail; never a summary call."""
    if len(text) <= budget:
        return text, False
    if budget < 180:
        return text[:budget], True
    available = budget - len(_EXCERPT) * 2
    head = available // 5
    tail = available // 2 if prefer_tail else available // 5
    middle_budget = available - head - tail
    sections = list(_SECTION.finditer(text))[:16]
    if sections:
        width = max(1, (middle_budget - len(sections)) // len(sections))
        snippets = []
        for index, section in enumerate(sections):
            end = sections[index+1].start() if index+1 < len(sections) else len(text)
            block = text[section.start():end]
            if len(block) <= width:
                snippets.append(block)
            else:
                lead = max(min(len(section.group()) + 25, width), width * 3 // 4)
                snippets.append(block[:lead] + block[-(width-lead):] if width > lead else block[:width])
        middle = "\n".join(snippets)[:middle_budget]
    else:
        # Preserve the middle even without markdown/numbered headings.
        start = max(head, (len(text)-middle_budget)//2)
        middle = text[start:start+middle_budget]
    return (text[:head] + _EXCERPT + middle + _EXCERPT + text[-tail:])[:budget], True


def semantic_message(message):
    meta = message.metadata
    if meta.get("kind", meta.get("structured_payload_type", "text")) != "text":
        return False
    if message.role == "assistant":
        status = message_status(message)
        if status == TurnStatus.CANCELLED:
            return bool(meta.get("agent_stream", {}).get("partial_response")) and "agent_failure" not in meta
        return status in {TurnStatus.COMPLETED, TurnStatus.UNKNOWN} and not (
            "agent_failure" in meta or any(item.get("stage") == "failed" for item in meta.get("agent_activity", [])))
    return message.role == "user"


def recent_turns(messages, *, prioritized_ids=()):
    """At most six provenance-bearing messages / 4500 serialized characters.

    Always protect the newest eligible assistant + preceding user first. A plan
    can then prioritize explicit available IDs; no user-keyword routing exists.
    Failure notices and structured presentation payloads are not semantic text.
    """
    window = list(messages[-12:])
    eligible = [index for index, message in enumerate(window) if semantic_message(message)]
    assistant = next((i for i in reversed(eligible) if window[i].role == "assistant"), None)
    priority = [] if assistant is None else [assistant]
    previous_user = next((i for i in reversed(eligible) if window[i].role == "user" and (assistant is None or i < assistant)), None)
    if previous_user is not None:
        priority.append(previous_user)
    priority += [i for i in reversed(eligible) if window[i].message_id in prioritized_ids]
    priority += list(reversed(eligible))
    remaining, selected, seen = MAX_HISTORY_CHARACTERS-2, {}, set()
    for index in priority:
        if index in seen:
            continue
        seen.add(index)
        if len(selected) >= MAX_RECENT_MESSAGES or remaining < 260:
            break
        message = window[index]
        provenance = "user_message" if message.role == "user" else "completed_assistant" if message_status(message) == TurnStatus.COMPLETED else "cancelled_assistant" if message_status(message) == TurnStatus.CANCELLED else "legacy_assistant"
        item = RecentTurn(role=message.role, text="", message_id=message.message_id, provenance=provenance,
            profile_version=message.metadata.get("agent_profile_stamp", {}).get("version"))
        overhead = len(item.model_dump_json()) + 1
        allocation = min(remaining-overhead, 2800 if index == assistant else 650 if index == previous_user else remaining-overhead)
        if allocation < 120:
            continue
        prefer_tail = provenance == "cancelled_assistant"
        text, clipped = excerpt(message.content, allocation, prefer_tail=prefer_tail)
        item = item.model_copy(update={"text": text, "excerpted": clipped})
        # JSON escaping overhead is bounded too, not just visible prose.
        while len(item.model_dump_json())+1 > remaining and len(text) >= 120:
            allocation -= max(1, len(item.model_dump_json())+1-remaining)
            text, clipped = excerpt(message.content, max(0, allocation), prefer_tail=prefer_tail)
            item = item.model_copy(update={"text": text, "excerpted": clipped})
        if len(item.model_dump_json())+1 <= remaining:
            selected[index] = item
            remaining -= len(item.model_dump_json())+1
    return [selected[i] for i in sorted(selected)]


def bounded_items(items: list[ContextItem]) -> list[ContextItem]:
    result, size = [], 0
    for item in items:
        amount = len(item.model_dump_json())
        if size + amount > MAX_CONTEXT_CHARACTERS:
            break
        result.append(item)
        size += amount
    return result


def messages_for(prompt: str, payload: dict) -> list[LLMMessage]:
    # Role-separated policy and explicitly untrusted data, not concatenated instructions.
    from ui.conversation_store import _no_credentials
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    _no_credentials(content)
    return [LLMMessage(role="system", content=prompt),
            LLMMessage(role="user", content=content)]
