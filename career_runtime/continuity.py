"""Runtime-owned conversation facts, not semantic routing or long-term Memory."""

import re

from career_runtime.models import PreviousTurn, StreamMetrics, TurnStatus, SafeFailure


def failure_status(failure):
    if failure is None:
        return TurnStatus.UNKNOWN
    if failure.stage == "persistence":
        return TurnStatus.FAILED_PERSISTENCE
    if failure.reason in {"output_limit", "transport_incomplete", "stream_interrupted"}:
        return TurnStatus.FAILED_TRANSPORT
    if failure.category == "validation_failure":
        return TurnStatus.FAILED_VALIDATION
    if failure.category in {"provider_failure", "provider_unavailable"}:
        return TurnStatus.FAILED_TRANSPORT
    return TurnStatus.UNKNOWN


def message_status(message):
    """Never infer status from prose, including a legacy error-looking string."""
    metadata = message.metadata
    if "agent_turn_status" in metadata:
        return TurnStatus(metadata["agent_turn_status"])
    if "agent_failure" in metadata:
        return failure_status(SafeFailure.model_validate(metadata["agent_failure"]))
    if "agent_stream" in metadata:
        stream = StreamMetrics.model_validate(metadata["agent_stream"])
        if stream.persistence_committed and stream.transport_completed and stream.core_valid and stream.provider_finish_category == "normal_stop":
            return TurnStatus.COMPLETED
    return TurnStatus.UNKNOWN


def previous_from_messages(messages):
    assistant = next((item for item in reversed(messages) if item.role == "assistant"), None)
    return PreviousTurn(status=message_status(assistant), assistant_message_id=assistant.message_id) if assistant else PreviousTurn()


# An OUTPUT integrity guard, never an input-keyword continuation router. Both
# prompts constrain all natural language; this bounded guard covers explicit
# Chinese/English technical-history claims. No repair or extra model is used.
_CLAIMS = (
    re.compile(r"(?:刚才|刚刚|上一(?:条|次|轮)|之前|前一(?:条|次|轮))[^。！？\n]{0,20}(?:没有|没|未)[^。！？\n]{0,10}(?:生成完整|生成完|说完|输出完)"),
    re.compile(r"(?:刚才|刚刚|上一(?:条|次|轮)|之前|前一(?:条|次|轮))[^。！？\n]{0,65}(?:被截断|(?:回答|回复|内容|生成)[^。！？\n]{0,12}(?:截断|未完成|没(?:有)?(?:说|生成|发|输出)完|不完整)|(?:连接|网络|系统|传输)[^。！？\n]{0,12}(?:中断|断开|失败|出错))"),
    re.compile(r"(?:刚才|上一(?:条|次|轮)|之前|前一(?:条|次|轮))[的\s]*(?:中断|截断|失败)[的\s]*(?:回答|回复|内容)"),
    re.compile(r"(?i)(?:previous|last|earlier)[^.?!\n]{0,55}(?:answer|response|reply|connection)[^.?!\n]{0,25}(?:truncat\w*|interrupt\w*|disconnect\w*|incomplete|fail\w*)"),
)
_DENIAL = re.compile(r"(?:没有|并未|不是|未被|未发生|并不|并没有)(?:发生|被|出现|再次|真的|直接|任何){0,2}(?:截断|中断|断开|失败|不完整)|(?i:(?:was not|wasn't|not) (?:truncated|interrupted|disconnected|incomplete|failed))")


def validate_runtime_history(text, previous):
    """Fail closed on unsupported runtime-history assertions; never rewrite text.

    User reports remain feedback, not a source of transport diagnoses. Ordinary
    quoted questions/negations are not asserted runtime facts. A real failure may
    be acknowledged, but its category cannot be changed into another failure.
    """
    for sentence in re.split(r"(?<=[。！？.!?])|\n", text):
        if sentence.rstrip().endswith(("？", "?")):
            continue
        claims = [match.group() for pattern in _CLAIMS for match in pattern.finditer(sentence)]
        if not any(not _DENIAL.search(re.split(r"[，,；;]", claim)[-1]) for claim in claims):
            continue
        if re.search(r"(?:项目|面试|考试|业务|订单|工程|实验).{0,25}(?:失败|中断|截断)", sentence) and not re.search(r"回答|回复|(?i:response|reply)", sentence):
            continue
        if previous.status in {TurnStatus.COMPLETED, TurnStatus.UNKNOWN}:
            raise ValueError("Unsupported runtime history claim.")
        if previous.status != TurnStatus.FAILED_TRANSPORT and re.search(r"(?:连接|网络|传输).{0,12}(?:中断|断开)|(?i:connection.{0,15}(?:interrupt|disconnect))", sentence):
            raise ValueError("Unsupported runtime history claim.")
        if previous.status != TurnStatus.FAILED_TRANSPORT and re.search(r"截断|(?i:truncat)", sentence):
            raise ValueError("Unsupported runtime history claim.")
