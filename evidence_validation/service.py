"""Pure deterministic eligibility and reported-outcome presentation."""

from evidence_match.models import Relation, Authority
from evidence_match.service import ACTIVITY_FIELDS, assemble, proposed, supported_relations
from evidence_match.projection import project_work
from specific_role.sources import SpecificRoleRegistry
from evidence_validation.models import Target

NOTICE = "只减少这一项证据的不确定性，不诊断弱点，不评价职业适配。实验可随时停止；完成不证明能力，产出不证明独立作者身份，自我反思不是技能事实。所有内容仅本次会话有效；当前 D.5 关系不变。"
UNAVAILABLE = "需要当前有效的 D.5 关系，请先明确代表性角色与已确认画像的证据关系。没有启动模型，也没有保存个人分析。"


def targets(result, context):
    # Re-validate the complete admitted parent; do not trust caller-supplied IDs,
    # an UNKNOWN rewritten from a work-side unknown, or a modified relation.
    source = next((s for s in SpecificRoleRegistry().inventory().records
                   if s.representative_role_id == context.work.role_id), None)
    if source is None or project_work(source) != context.work or assemble(context, proposed(context)) != result:
        raise ValueError("D6_UNVALIDATED_PARENT")
    work = {s.signal_id: s for s in context.work.signals}
    eligible = []
    for r in result.relationships:
        s = work[r.work_signal_ids[0]]
        if r.relation_type not in (Relation.UNKNOWN, Relation.PARTIAL):
            continue
        if s.authority != Authority.SOURCE_FACT or s.field not in ACTIVITY_FIELDS:
            continue
        if context.user.partial:
            continue  # Projection omission cannot diagnose absence of experience.
        if r.relation_type == Relation.UNKNOWN:
            known = {k for u in context.user.signals for k in supported_relations(u, s, context)}
            if known:
                continue  # Conflicting confirmed reports need review, not an experiment.
        partial = r.relation_type == Relation.PARTIAL
        eligible.append(Target(relation_id=r.relationship_id, relation_type=r.relation_type,
            work_signal_id=s.signal_id, work_evidence_ids=r.work_evidence_ids, label=s.label,
            unresolved_scope=("独立性与完整责任尚未证实：" if partial else "") + s.label,
            reason="independence_unestablished" if partial else "user_evidence_insufficient"))
    return tuple(eligible)


def summary(target, candidates, outcome):
    lines = ["本次会话待核对摘要", "唯一范围：" + target.unresolved_scope,
             "完成状态（自述）：" + {"not_reported":"未报告", "reported_completed":"报告已完成", "stopped":"已中止"}[outcome.completion]]
    for c in candidates:
        lines.append({"recollection":"回忆", "current_claim":"当前表述", "scope":"范围", "context":"情境"}[c.kind] + "（候选，未确认）：" + c.text)
    for label, items in (("观察自述", outcome.observations), ("文本产出（作者/帮助未验证）", outcome.text_outputs),
                         ("自我反思", outcome.reflections), ("帮助情况自述", outcome.assistance_reports)):
        for text in items:
            lines.append(label + "：" + text)
    lines.append(NOTICE)
    return "\n".join(lines)
