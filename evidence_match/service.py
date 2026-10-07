"""Fake-only bounded relations under the existing Match & Insight Agent."""

from pathlib import Path
from pydantic import Field, create_model
from providers.fake import FakeLLMProvider
from providers.models import LLMMessage, GenerationOptions
from agents.match_insight_models import _scoped_signal_id_type, allowed_match_signal_ids
from agents.match_evidence_resolver import MatchEvidenceResolver
from evidence_match.models import Context, Candidate, Extraction, Relationship, Result, Relation, Authority
from evidence_match.projection import project_user, project_work

PROMPT_NAME, PROMPT_VERSION = "evidence_relationship", "v1"
PROMPT_PATH = Path(__file__).parent / "prompts/relationships_v1.md"
ACTIVITY_FIELDS = {"responsibilities", "inputs", "outputs", "collaborators", "decision_scope", "technical_involvement"}
FACT_CATEGORIES = {"skills", "strengths", "work_experience", "projects", "tools", "collaboration", "other_evidence"}


def supported_relations(signal, work, context):
    """Finite WHOLE owned statements, not keyword/similarity/capability guessing.

    This offline slice intentionally cannot classify arbitrary paraphrases.
    Different depth or unrecognized wording remains UNKNOWN, not a false gap.
    """
    if not signal.eligible or work.authority != Authority.SOURCE_FACT:
        return ()
    statements = {e.text for e in context.user.evidence if e.evidence_id in signal.evidence_ids}
    relations = []
    if work.field in ACTIVITY_FIELDS and signal.category in FACT_CATEGORIES:
        for prefix, relation in (("", Relation.DIRECT), ("曾独立完成：", Relation.DIRECT),
                                 ("仅在协助范围内完成：", Relation.PARTIAL),
                                 ("目前无法独立完成：", Relation.TENSION)):
            if prefix + work.label in statements:
                relations.append(relation)
    if signal.category in {"constraints", "work_style_preferences", "career_preferences", "values"}:
        if work.field == "work_rhythm" and "目前不能接受这种工作安排：" + work.label in statements:
            relations.append(Relation.TENSION)
        if "明确不在本次比较范围：" + work.label in statements:
            relations.append(Relation.NA)
    return tuple(relations)


def proposed(context):
    candidates = []
    for work in context.work.signals:
        known = [(signal, relation) for signal in context.user.signals
                 for relation in supported_relations(signal, work, context)]
        # Conflicting positive/negative reports are not resolved by order.
        if len({r for _, r in known}) > 1:
            known = []
        signal, relation = known[0] if known else (None, Relation.UNKNOWN)
        candidates.append(Candidate(relation_type=relation,
            user_signal_ids=(signal.signal_id,) if signal else (), work_signal_ids=(work.signal_id,)))
    return Extraction(relations=tuple(candidates))


def response_model(context):
    user_ids, work_ids = allowed_match_signal_ids(context)
    user_type = _scoped_signal_id_type(user_ids, error_type="unknown_user_signal", side="user")
    work_type = _scoped_signal_id_type(work_ids, error_type="unknown_work_signal", side="work")
    scoped = create_model("D5ScopedCandidate", __base__=Candidate,
        user_signal_ids=(tuple[user_type, ...], Field(..., max_length=1)),
        work_signal_ids=(tuple[work_type, ...], Field(..., min_length=1, max_length=1)))
    return create_model("D5ScopedExtraction", __base__=Extraction,
                        relations=(tuple[scoped, ...], Field(..., min_length=1, max_length=40)))


REASONS = {
    Relation.DIRECT: "已确认材料明确报告了这项具体活动，与本合成工作项直接对应；不证明整个角色胜任。",
    Relation.PARTIAL: "已确认材料明确限定为协助范围；与工作项相关，但独立性与完整责任尚未得到支持。",
    Relation.UNKNOWN: "当前这个工作项还没有足够的用户侧证据；材料不足不是能力弱点。",
    Relation.TENSION: "当前已确认材料明确报告了限定，与这项具体工作存在张力；不是永久能力标签。",
    Relation.NA: "已确认材料明确将此项排除在本次比较范围外；不是缺证据的替代判断。",
}


def assemble(context, extraction):
    # Provider candidates must exactly equal independently supported relations.
    # No semantic repair, ID replacement, guessing or provider prose admission.
    expected = proposed(context)
    if extraction.model_dump() != expected.model_dump():
        raise ValueError("D5_UNSUPPORTED_RELATION")
    resolver, results = MatchEvidenceResolver(), []
    for index, item in enumerate(extraction.relations):
        link = resolver.resolve(context, profile_signal_ids=item.user_signal_ids, job_signal_ids=item.work_signal_ids)
        sources = tuple(s.source_type + " / " + s.inference_type + " / " + ";".join(s.origins)
                        for s in context.user.signals if s.signal_id in item.user_signal_ids)
        user_scope = tuple(text for signal in context.user.signals if signal.signal_id in item.user_signal_ids
                           for text in signal.scope)
        limitations = (context.work.scope, "公开合成代表性工作；不是实际招聘要求或职业适配结论。",
                       *user_scope, *context.work.variation)
        if context.user.partial:
            limitations += ("用户侧投影为部分材料，省略部分不能视为没有经历。",)
        results.append(Relationship(relationship_id=f"relationship_{index+1:03d}", relation_type=item.relation_type,
            user_signal_ids=item.user_signal_ids, user_evidence_ids=tuple(link.profile_evidence_ids),
            work_signal_ids=item.work_signal_ids, work_evidence_ids=tuple(link.job_evidence_ids),
            reason=REASONS[item.relation_type], limitations=limitations, user_sources=sources,
            uncertainty="insufficient_evidence" if item.relation_type == Relation.UNKNOWN else "limited_scope",
            profile_version=context.user.profile_version, role_id=context.work.role_id, source_id=context.work.source_id,
            source_version=context.work.source_version, source_fingerprint=context.work.source_fingerprint))
    return Result(profile_id=context.user.profile_id, profile_version=context.user.profile_version,
        profile_fingerprint=context.user.profile_fingerprint, role_id=context.work.role_id,
        projection_version=context.work.projection_version, relationships=tuple(results))


def analyze(profile, source, provider=None):
    context = Context(user=project_user(profile), work=project_work(source))
    provider = provider or FakeLLMProvider(proposed(context))
    if not isinstance(provider, FakeLLMProvider):
        raise ValueError("D5_OFFLINE_PROVIDER_REQUIRED")
    response = provider.generate_structured(
        [LLMMessage(role="system", content=PROMPT_PATH.read_text()),
         LLMMessage(role="user", content=context.model_dump_json())], response_model(context),
        GenerationOptions(model="fake-evidence-relationship-v1", max_retries=0),
        prompt_name=PROMPT_NAME, prompt_version=PROMPT_VERSION)
    return assemble(context, response.data), context
