"""Bounded whole-utterance grammar and exact, non-ranked source projection."""

from dataclasses import dataclass
import re
from role_landscape.models import Dimension, RoleBlock, RoleReply, RoleLandscapeSource, Authority

NOTICE = "公开合成角色分工 · 只说明这份虚构资料中的代表性类型，不是完整职业分类或真实招聘。顺序仅用于引用，不是排名。"
CHIPS = ("第一种平时都做什么？", "第一种和第二种有什么区别？", "谁更经常跟业务沟通？", "还有别的类型吗？")


def normalized(text):
    return re.sub(r"[\s，,。.!！?？：:]", "", text.casefold())


@dataclass(frozen=True)
class Intent:
    kind: str
    dimension: Dimension | None = None


def classify(text, *, active=False):
    if not isinstance(text, str) or not 0 < len(text.strip()) <= 2000:
        return None
    s = normalized(text)
    if re.fullmatch(r"(?:那|请问|想知道)?(?:刚才那个方向|这个方向|该方向|方向|businessanalysis|knowledgeoperations|processimprovement)?(?:里|里面|下)?(?:有哪(?:些|几种)|有哪些不同的|包含哪些|有哪些代表性)(?:岗位|角色|角色类型|岗位类型|角色分工)(?:类型)?", s):
        return Intent("overview", Dimension.OVERVIEW)
    if re.fullmatch(r".{1,160}(?:有哪些|包含哪些)(?:岗位|角色|角色类型)", s):
        return Intent("unsupported_direction")
    # Scoped explicit unknown identities must not reach the generic role tool.
    if re.fullmatch(r".*role_[a-z0-9_]+.*", s):
        return Intent("role_id", Dimension.WORK)
    if not active:
        return None
    if re.fullmatch(r"(?:刚才)?偏系统(?:的)?那个(?:呢)?", s):
        return Intent("followup", Dimension.TECHNICAL)
    if re.fullmatch(r"第[一二三四五1-5](?:种|个)(?:角色)?(?:比较|挺|很)?有意思", s):
        return Intent("interest")
    if re.fullmatch(r"(?:那|你觉得|那你觉得)?(?:哪个|哪种|哪一个|哪种角色|哪个岗位|第一种|第二种)(?:角色)?(?:更)?适合我(?:吗)?|(?:帮我|给我)(?:推荐|排序)(?:岗位|角色)(?:吧)?", s):
        return Intent("personal")
    if re.fullmatch(r"(?:还有|有没有)(?:别的|其他|更多)(?:岗位|角色|类型|角色类型)(?:吗)?", s):
        return Intent("more")
    if s in ("谁更经常跟业务沟通", "哪个更偏沟通", "哪个更靠近系统落地"):
        return Intent("all", Dimension.COLLABORATION if "沟通" in s else Dimension.TECHNICAL)
    # Split reference and task only after recognizing an entire bounded question.
    for dimension, suffix in (
        (Dimension.WORK, r"(?:平时|通常|日常)?(?:都|具体|主要)?(?:做什么|在做什么|有哪些任务|工作内容是什么)"),
        (Dimension.COLLABORATION, r"(?:平时|通常|主要)?(?:和谁合作|跟谁合作|与谁协作)"),
        (Dimension.TECHNICAL, r"(?:是不是|是否|会不会)?(?:更)?(?:偏技术|偏系统|靠近系统落地)(?:吗)?"),
        (Dimension.COMPARISON, r"(?:有)?什么(?:区别|不同)|区别是什么"),
        (Dimension.OUTPUTS, r"(?:的)?(?:产出|工作成果)(?:是|有)什么"),
        (Dimension.VARIATION, r"(?:有)?(?:哪些|什么)变化"),
        (Dimension.UNKNOWN, r"(?:还有)?什么不确定"),
    ):
        if re.fullmatch(r"(?:那|请问)?(.+?)(?:的)?(?:" + suffix + r")", s):
            return Intent("followup", dimension)
    if s in ("具体有哪些招聘职位", "这些角色真实存在吗", "推荐一个真实岗位"):
        return Intent("unsupported")
    if re.fullmatch(r"(?:这些|这个方向的|刚才的)(?:岗位|角色)(?:工资多少|薪资多少|招聘要求是什么|有哪些具体职位|投哪个|哪个最好)", s):
        return Intent("unsupported")
    return None


def references(text, source, displayed, last):
    """Only current IDs/order and unique authored aliases; no similarity lookup."""
    s = normalized(text)
    found = []
    explicit = re.findall(r"role_[a-z0-9_]+", text.casefold())
    if explicit:
        if any(v not in displayed for v in explicit):
            raise ValueError("INVALID_ROLE_REFERENCE")
        found.extend(explicit)
    for match in re.finditer(r"第([一二三四五六七八九十1-9])(?:种|个)(?:角色|岗位)?", s):
        char = match.group(1)
        index = "一二三四五六七八九十".index(char) if not char.isdigit() else int(char) - 1
        if index >= len(displayed):
            raise ValueError("INVALID_ROLE_REFERENCE")
        found.append(displayed[index])
    for role in source.roles:
        if any(normalized(alias) in s.replace("偏系统的那个", "偏系统那个") for alias in (role.display_name, *role.reference_aliases)):
            found.append(role.role_id)
    if not found and "这两种" in s and len(last) == 2:
        found.extend(last)
    if not found and any(v in s for v in ("这种角色", "刚才那个角色")) and len(last) == 1:
        found.extend(last)
    found = tuple(dict.fromkeys(found))
    if not found:
        raise ValueError("AMBIGUOUS_ROLE_REFERENCE")
    return found


class RoleLandscapeService:
    def reply(self, source, dimension, role_ids=None):
        source = RoleLandscapeSource.model_validate(source.model_dump())
        ids = tuple(r.role_id for r in source.roles) if role_ids is None else tuple(role_ids)
        if not ids or len(set(ids)) != len(ids) or not set(ids) <= {r.role_id for r in source.roles}:
            raise ValueError("INVALID_ROLE_REFERENCE")
        fields = {
            Dimension.OVERVIEW: ("primary_problem", "work_emphasis", "distinction"),
            Dimension.COMPARISON: ("primary_problem", "work_emphasis", "distinction", "technical_system_emphasis", "collaboration"),
        }.get(dimension, (dimension.value,))
        blocks = []
        for role_id in ids:
            role = next(r for r in source.roles if r.role_id == role_id)
            for name in fields:
                value = getattr(role, name)
                for index, text in enumerate(value if isinstance(value, tuple) else (value,)):
                    authority = Authority.UNKNOWN if name == "uncertainties" else (
                        Authority.EXAMPLE if name == "representative_tasks" else Authority.SOURCE_FACT)
                    blocks.append(RoleBlock(role_id=role_id, field=name, text=text, authority=authority,
                        source_ref=f"{source.source_id}@{source.version}:roles:{role_id}:{name}:{index}",
                        membership_ref=f"{source.source_id}@{source.version}:memberships:{role_id}"))
        return RoleReply(source_id=source.source_id, source_version=source.version,
                         dimension=dimension, role_ids=ids, blocks=tuple(blocks))

    def validate(self, reply, source):
        reply = RoleReply.model_validate(reply.model_dump())
        if reply != RoleLandscapeService.reply(self, source, reply.dimension, reply.role_ids):
            raise ValueError("UNSUPPORTED_ROLE_CLAIM")
        return reply
