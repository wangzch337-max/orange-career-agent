"""Bounded dialogue-act routing, applicable only to an owned pending question."""

from dataclasses import dataclass
from enum import Enum
import re

from clarification.context import explicitly_uncertain


class DialogueAct(str, Enum):
    ANSWER = "ANSWER"
    QUESTION = "QUESTION"
    OTHER = "OTHER"


@dataclass(frozen=True)
class PendingClarificationToken:
    owner: str
    thread: str
    request_id: str
    generation: int
    binding_fingerprint: str
    need_id: str


def scope_dialogue_act(text):
    """Do not infer a scope value or recognize a growing list of exact replies.

    Interrogatives/requests remain QA. Declarative topic references, uncertainty,
    and short choice/acceptance constructions may answer a scope question.
    Other or mixed utterances leave the pending interaction untouched.
    """
    if not isinstance(text, str) or not 0 < len(text.strip()) <= 1200:
        return DialogueAct.OTHER
    text = text.strip()
    if re.search(r"[?？]|什么是|是什么|为什么|如何|怎么|怎样|能否|能不能|可否|是不是|解释|介绍|讲解|讲讲|说说|"
                 r"\b(?:what|why|how|explain|describe)\b", text, re.I):
        return DialogueAct.QUESTION
    if explicitly_uncertain(text) or re.search(r"相邻|邻近|跨行业|跨度|方向|已有经验|现有经验|"
                                              r"\b(?:adjacent|cross.industry|scope)\b", text, re.I):
        return DialogueAct.ANSWER
    # Lexical dialogue acts, not career preferences or phrase-to-direction rules.
    if len(text) <= 48 and re.search(r"(?:都|两|任一|均|随).{0,12}(?:可|行|看|好)|"
                                     r"(?:可|愿意|没关系|不限|尚未|还没|未定)|"
                                     r"\b(?:both|either|okay|unsure|undecided)\b", text, re.I):
        return DialogueAct.ANSWER
    return DialogueAct.OTHER
