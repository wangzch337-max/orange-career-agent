"""Bounded whole-question routing and exact progressive source projection."""

from dataclasses import dataclass
import re
from career_discovery.context import fingerprint
from role_landscape.service import normalized
from specific_role.models import Dimension as D, Authority as A, RoleBlock, RoleReply, SpecificRoleSource

NOTICE = "公开合成代表性角色 · 用来理解一种具体工作形态，不是真实招聘、完整岗位画像或个人适配结论。"
CHIPS = ("这个角色通常和谁合作？", "这个角色最后要交付什么？", "这个角色能决定什么？", "这个角色会不会一直写代码？")
PERSONAL = "当前是在理解工作对象，不是在判断你适不适合。个人证据与工作证据的关系属于后续另行授权的 Match；本次没有生成匹配、排名或确认职业目标。"
UNSUPPORTED = "代表性角色的资料或父上下文不足、已变化，暂时不能继续。没有换成旧岗位，没有调用模型补造。请先回到有效的角色类型探索。"
AMBIGUOUS = "这个引用不能唯一对应当前角色类型。请用当前序号、完整类型名或明确别名再问；我没有猜测或替换角色。"


@dataclass(frozen=True)
class Intent:
    kind: str
    reference: str = ""
    dimension: D | None = None


GRAMMAR = {
    D.PURPOSE: r"(?:存在的目的是什么|主要解决什么问题|为什么需要这种工作)",
    D.WORK: r"(?:(?:具体)?(?:每天|平时|日常|通常)?(?:主要|都)?做什么|有哪些职责|负责什么)",
    D.SITUATION: r"(?:能举个(?:具体)?例子吗|举个工作情境|具体工作情境是什么)",
    D.IO: r"(?:最后(?:要)?交付什么|输入和输出是什么|需要哪些输入|产出是什么|工作成果是什么)",
    D.COLLABORATION: r"(?:(?:一般|通常|平时|主要)?(?:和谁|跟谁|与谁)(?:合作|协作))",
    D.DECISIONS: r"(?:能决定什么|决策边界是什么|哪些事需要升级|什么时候需要人工介入)",
    D.RHYTHM: r"(?:工作节奏是什么|(?:平时)?一天(?:大概)?怎么(?:工作|过|安排)|会不会一直开会)",
    D.TECHNICAL: r"(?:会不会一直写代码|需要写代码吗|会用什么工具|工具深度是什么|技术参与程度是什么)",
    D.CAPABILITIES: r"(?:需要哪些能力|涉及哪些能力|会用到什么能力)",
    D.VARIATION: r"(?:在不同组织有什么变化|有哪些组织差异|在不同公司一样吗)",
    D.UNKNOWN: r"(?:还有什么不确定|有哪些未知|薪资多少|哪家公司在招聘|晋升快吗)",
}


def classify(text, *, active=False):
    if not isinstance(text, str) or not 0 < len(text.strip()) <= 2000:
        return None
    s = normalized(text)
    # Whole-utterance grammar: comparisons remain D.3; direction questions D.2;
    # arbitrary technical/mixed requests remain General QA, even while active.
    if re.fullmatch(r"(?:那)?(?:你觉得)?(?:这个角色|这种角色|它|哪个|哪种|哪一个|哪个岗位|哪种角色|第一种|第二种)(?:更)?适合我(?:吗)?|(?:你觉得)?我能做(?:这个角色)?吗|(?:帮我|给我)(?:推荐|排序)(?:角色|岗位)", s):
        return Intent("personal") if active else None
    if active:
        match = re.fullmatch(r"(?:那)?(?:你觉得)?(.+?)(?:更)?(?:不适合|适合)我(?:吗)?", s)
        if match:
            return Intent("personal", match[1])
        match = re.fullmatch(r"(?:你觉得)?我(?:能做|适合)(.+?)吗", s)
        if match:
            return Intent("personal", match[1])
    match = re.fullmatch(r"(?:请|请问)?(?:详细讲讲|详细说说|展开讲讲|具体介绍)(.+)", s)
    if match:
        return Intent("role", match[1], D.OVERVIEW)
    match = re.fullmatch(r"(?:请|请问)?(.+?)(?:详细讲讲|详细说说|具体介绍一下)", s)
    if match:
        return Intent("role", match[1], D.OVERVIEW)
    for dimension, grammar in GRAMMAR.items():
        match = re.fullmatch(r"(?:那|请问)?(.+?)(?:的)?" + grammar, s)
        if match:
            ref = match[1]
            if ref in ("这个方向", "刚才那个方向", "这类工作", "这种工作"):
                return None
            # Before D.4 starts, ordinary D.3 work/collaboration must stay D.3.
            if active or ref in ("这个角色", "这种角色") or s.endswith(("最后要交付什么", "会不会一直写代码")) or "具体每天" in s:
                return Intent("role", ref, dimension)
    if active:
        for dimension in GRAMMAR:
            if re.fullmatch(GRAMMAR[dimension], s):
                return Intent("role", "它", dimension)
    match = re.fullmatch(r"(这个角色|这种角色|它|第[一二三四五1-5](?:种|个)(?:角色)?)(?:比较|挺|很)?有意思", s)
    if active and match:
        return Intent("interest", match[1])
    return None


def reference_hint(reference, parent=None, specific_source=None):
    """Unknown scoped role references clarify; unrelated nouns remain General QA."""
    ref = normalized(reference).replace("偏系统的那个", "偏系统那个")
    if specific_source is not None and ref == normalized(specific_source.display_name):
        return True
    if ref in ("这个角色", "这种角色", "刚才那个角色", "它"):
        return True
    if re.search(r"第[一二三四五六七八九十1-9](?:种|个)", ref) or ref.startswith("role_") or ref.endswith(("型", "角色", "岗位")):
        return True
    return parent is not None and any(ref == normalized(a) for r in parent.roles for a in (r.display_name, *r.reference_aliases))


def reference_id(reference, parent, displayed, last=None, *, specific_source=None):
    """Resolve an entire reference, never a fuzzy/substring/similarity match."""
    ref = normalized(reference)
    if (specific_source is not None and ref == normalized(specific_source.display_name)
            and last in displayed and specific_source.parent_archetype_id == last):
        return last
    if ref in ("这个角色", "这种角色", "刚才那个角色", "它"):
        if last in displayed:
            return last
        raise ValueError("AMBIGUOUS_REFERENCE")
    match = re.fullmatch(r"(?:刚才)?第([一二三四五六七八九十1-9])(?:种|个)(?:角色|岗位)?", ref)
    if match:
        char = match[1]
        index = "一二三四五六七八九十".index(char) if not char.isdigit() else int(char) - 1
        if index < len(displayed):
            return displayed[index]
        raise ValueError("INVALID_REFERENCE")
    if ref.startswith("role_"):
        if ref in displayed:
            return ref
        raise ValueError("INVALID_REFERENCE")
    # A single explicit authored alias; only the scoped parent supplies aliases.
    ref = ref.replace("偏系统的那个", "偏系统那个")
    found = [r.role_id for r in parent.roles if ref in {
        normalized(a) for a in (r.display_name, *r.reference_aliases)}]
    if len(found) == 1 and found[0] in displayed:
        return found[0]
    raise ValueError("AMBIGUOUS_REFERENCE")


class SpecificRoleService:
    def reply(self, source, dimension):
        source = SpecificRoleSource.model_validate(source.model_dump())
        fields = {D.OVERVIEW:("purpose", "work_situations"), D.IO:("inputs", "outputs")}.get(dimension, (dimension.value,))
        blocks = []
        for name in fields:
            value = getattr(source, name)
            texts = value if isinstance(value, tuple) else (value,)
            if dimension == D.OVERVIEW:
                texts = texts[:1]
            for index, text in enumerate(texts):
                authority = A.UNKNOWN if name == "unknowns" else A.EXAMPLE if name == "work_situations" else A.SOURCE_FACT
                blocks.append(RoleBlock(field=name, text=text, authority=authority,
                    source_ref=f"{source.source_id}@{source.version}:{source.representative_role_id}:{name}:{index}",
                    membership_refs=(f"{source.source_id}@{source.version}:membership:direction_archetype",
                                     f"{source.source_id}@{source.version}:membership:archetype_role")))
        return RoleReply(source_id=source.source_id, source_version=source.version,
            source_fingerprint=fingerprint(source.model_dump(mode="json")), archetype_id=source.parent_archetype_id,
            representative_role_id=source.representative_role_id, dimension=dimension, blocks=tuple(blocks))

    def validate(self, reply, source):
        reply = RoleReply.model_validate(reply.model_dump())
        if reply != SpecificRoleService.reply(self, source, reply.dimension):
            raise ValueError("UNSUPPORTED_SPECIFIC_ROLE_CLAIM")
        return reply
