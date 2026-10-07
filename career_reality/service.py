"""Source-backed progressive projection, without LLM prose or personal judgment."""

import re
from career_reality.models import Authority as A, Dimension as D, WorkBlock, WorkReply

# Full-utterance grammar, not keyword interception. Unrecognized questions leave
# the existing QA route intact. This is intentionally not universal intent NLP.
PREFIX = r"(?:(?:那|那么|请问|想了解|能说说|可以说说)[，, ]*)?(?:(?:这个方向|这类工作|这种工作|刚才那个方向|刚才的方向|它)[，, ]*)?"
GRAMMAR = {
    D.PURPOSE: r"(?:为什么需要这种工作|为什么存在|主要解决什么问题|整体在解决什么问题|存在的目的是什么|有什么意义)",
    D.WORK: r"(?:整体(?:是)?做什么(?:的)?|平时(?:主要)?做什么|主要做什么|具体做什么|一天(?:大概)?怎么工作|日常工作是什么|有哪些任务)",
    D.SITUATION: r"(?:还有(?:别的|其他)?工作情境吗|还有别的例子吗|再举一个例子|能举个例子吗|还有什么工作情境)",
    D.COLLABORATION: r"(?:(?:平时|通常|主要)?(?:跟谁|和谁|与谁)(?:合作|协作)|需要跟哪些人合作|协作对象有哪些)",
    D.IO: r"(?:工作成果是什么|产出是什么|输入和输出是什么|需要哪些输入|会产出什么|最后交付什么)",
    D.STYLE: r"(?:工作方式是什么|通常怎么开展工作|工作节奏是什么|工作方式有什么特点)",
    D.CAPABILITIES: r"(?:需要哪些能力|涉及哪些能力|技术含量高吗|技术含量怎么样|会用到什么能力)",
    D.VARIATIONS: r"(?:有没有不同路线|里面有没有不同路线|有哪些不同工作形态|有哪些子路径|有什么不同路线)",
    D.UNKNOWN: r"(?:还有什么不确定|哪些信息还不知道|有哪些未知|资料有什么局限)",
}
CHIPS = ("平时主要做什么？", "通常跟谁合作？", "需要哪些能力？", "还有别的工作情境吗？")


def followup_dimension(text):
    for dimension, grammar in GRAMMAR.items():
        if re.fullmatch(PREFIX + grammar + r"[？?。.! ]*", text.strip()):
            return dimension
    return None


def explicitly_scoped(text):
    """Unknown explicit work-context questions get a safe local answer, not facts."""
    return bool(re.fullmatch(PREFIX + r"(?:工资多少|薪资如何|有什么资格要求|适合我吗|我适合吗|"
        r"哪家公司在招聘|有什么招聘机会|晋升快吗|需要什么执照|工作时长是多少)[？?。.! ]*", text.strip()) or
        re.match(r"^关于刚才的工作情境[，,：:]", text.strip()))


def supported_blocks(source, situation):
    fields = {
        "purpose": (source.purpose,), "situation": (situation.situation,),
        "problem": (situation.problem,), "why_it_matters": (situation.why_it_matters,),
        **{name: getattr(situation, name) for name in (
            "typical_tasks", "inputs", "outputs", "collaborators", "work_style", "capabilities_involved", "uncertainties")},
        "internal_variations": source.internal_variations, "source_uncertainties": source.uncertainties,
    }
    result = {}
    for field, texts in fields.items():
        authority = A.UNKNOWN if "uncertainties" in field else A.EXAMPLE if field in {"situation", "problem", "why_it_matters"} else A.SOURCE_FACT
        for index, text in enumerate(texts):
            ref = f"{source.source_id}@{source.version}:{situation.situation_id}:{field}:{index}"
            result[ref] = WorkBlock(source_ref=ref, authority=authority, text=text)
    return result


FIELDS = {
    D.PURPOSE: ("purpose",), D.WORK: ("typical_tasks",),
    D.SITUATION: ("situation", "problem", "why_it_matters", "outputs"),
    D.COLLABORATION: ("collaborators",), D.IO: ("inputs", "outputs"),
    D.STYLE: ("work_style",), D.CAPABILITIES: ("capabilities_involved",),
    D.VARIATIONS: ("internal_variations",), D.UNKNOWN: ("uncertainties", "source_uncertainties"),
}


class CareerRealityService:
    def reply(self, source, dimension, situation_index=0, *, opening=False):
        situation = source.situations[situation_index]
        fields = ("purpose", *FIELDS[D.SITUATION]) if opening else FIELDS[dimension]
        blocks = supported_blocks(source, situation)
        selected = tuple(block for ref, block in blocks.items() if ref.split(":")[-2] in fields)
        reply = WorkReply(source_id=source.source_id, source_version=source.version,
            dimension=dimension, situation_id=situation.situation_id, blocks=selected)
        self.validate(reply, source)
        return reply

    def validate(self, reply, source):
        reply = WorkReply.model_validate(reply.model_dump())
        if (reply.source_id, reply.source_version) != (source.source_id, source.version):
            raise ValueError("WRONG_SOURCE")
        situation = next((s for s in source.situations if s.situation_id == reply.situation_id), None)
        if situation is None:
            raise ValueError("WRONG_SITUATION")
        supported = supported_blocks(source, situation)
        if len({b.source_ref for b in reply.blocks}) != len(reply.blocks):
            raise ValueError("DUPLICATE_REFERENCE")
        if any(supported.get(b.source_ref) != b for b in reply.blocks):
            raise ValueError("UNSUPPORTED_CLAIM")
        return reply
