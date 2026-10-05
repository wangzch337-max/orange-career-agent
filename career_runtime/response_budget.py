"""Shared, finite response envelope; generation targets are NOT validators.

字符按 Python len / decoded Unicode code points 计数，不是 UTF-8 bytes、
graphemes 或模型 tokens。JSON 转义另有 wire 预算。这里没有 token↔字符
换算保证：8192/6144 是模式相关的资源上限，8000/4000 是提示软目标。
硬上限仍独立校验；provider length 结束不算成功，不裁剪正文来适配目标。

10000 来自历史 runtime schema / 增量投影的防御边界。20000 来自更早
的通用 transcript store，供引导式展示与历史消息使用，不扩大新生成权限。
"""

from dataclasses import asdict, dataclass
from typing import Literal

HARD_VISIBLE_CHARACTERS = 10000
PERSISTENCE_MESSAGE_CHARACTERS = 20000
NORMAL_TARGET_CHARACTERS = 8000
CONTINUATION_TARGET_CHARACTERS = 4000
RESPONSE_TOKEN_CEILING = 8192
CONTINUATION_TOKEN_CEILING = 6144
PLANNER_TOKEN_CEILING = 1800
MAX_WIRE_CHARACTERS = 160000
MAX_STREAM_CHUNKS = 160000
MAX_JSON_HEADER_CHARACTERS = 80
REPETITION_MIN_CHARACTERS = 600  # Allow brief recaps; reject whole substantial copies.


@dataclass(frozen=True)
class ResponseBudget:
    """Closed code-owned modes, not model-controlled output permissions."""

    mode: Literal["normal", "cancelled_continuation"]

    def __post_init__(self):
        if self.mode not in {"normal", "cancelled_continuation"}:
            raise ValueError("Unknown response budget mode.")

    @property
    def target_visible_characters(self):
        return CONTINUATION_TARGET_CHARACTERS if self.mode == "cancelled_continuation" else NORMAL_TARGET_CHARACTERS

    @property
    def provider_max_output_tokens(self):
        return CONTINUATION_TOKEN_CEILING if self.mode == "cancelled_continuation" else RESPONSE_TOKEN_CEILING

    def payload(self):
        return {**asdict(self), "hard_visible_characters": HARD_VISIBLE_CHARACTERS,
            "target_visible_characters": self.target_visible_characters,
            "safety_margin_characters": HARD_VISIBLE_CHARACTERS - self.target_visible_characters,
            "provider_max_output_tokens": self.provider_max_output_tokens}


def response_budget(*, dialogue_act, previous_status, has_cancelled_partial):
    """Only semantic Plan + canonical runtime facts select continuation mode."""
    continuation = dialogue_act == "continue_previous" and previous_status == "CANCELLED" and has_cancelled_partial
    return ResponseBudget("cancelled_continuation" if continuation else "normal")


def validate_continuation_repetition(text, prior_partial):
    """Exact whole-copy guard only; not a paraphrase judge or semantic repair.

    The owned prior body stays local. It is NOT added to provider context. Brief
    linking recaps remain legal; arbitrary partial/paraphrased repetition needs
    model compliance and later manual review.
    """
    if len(prior_partial) >= REPETITION_MIN_CHARACTERS and prior_partial in text:
        raise ValueError("Continuation repeats cancelled body.")
