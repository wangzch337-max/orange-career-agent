"""Deterministic validation and assembly for Phase 5 Match results."""

from __future__ import annotations

from typing import Dict, Iterable

from pydantic import ValidationError

from agents.action_renderer import ActionRenderer
from agents.match_evidence_resolver import MatchEvidenceResolver
from agents.match_insight_models import (
    JobSignalCategory,
    MatchActionCandidate,
    MatchContext,
    MatchInsightExtraction,
    NormalizedMatchCandidate,
    ProfileSignalCategory,
)
from data.models import (
    ActionItem,
    ActionType,
    ConfirmedGap,
    EvidenceGap,
    ExperienceDepthGap,
    MatchCoverageMetrics,
    MatchDimension,
    MatchEvidenceLink,
    MatchInsight,
    MatchRelationType,
    MatchResult,
    UserProfile,
)
from providers.errors import LLMStructuredOutputError
from workflows.stages import ProfileNotConfirmedError


class MatchInsightAssembler:
    """Enforce evidence/action invariants and never calculate a fit score."""

    _ACTION_POLICY = {
        MatchRelationType.EVIDENCE_MISSING: {
            ActionType.VERIFY_EXISTING_CAPABILITY,
            ActionType.BUILD_PORTFOLIO_EVIDENCE,
        },
        MatchRelationType.CONFIRMED_GAP: {
            ActionType.DEEPEN_CAPABILITY,
            ActionType.GAIN_PRACTICAL_EXPERIENCE,
        },
        MatchRelationType.EXPERIENCE_DEPTH_GAP: {
            ActionType.BUILD_PORTFOLIO_EVIDENCE,
            ActionType.DEEPEN_CAPABILITY,
            ActionType.GAIN_PRACTICAL_EXPERIENCE,
        },
        MatchRelationType.POTENTIAL_FRICTION: {ActionType.CLARIFY_PREFERENCE},
        MatchRelationType.UNKNOWN: {
            ActionType.CLARIFY_PREFERENCE,
            ActionType.INVESTIGATE_JOB_UNKNOWN,
        },
    }

    def __init__(
        self,
        action_renderer: ActionRenderer | None = None,
        evidence_resolver: MatchEvidenceResolver | None = None,
    ) -> None:
        self.action_renderer = action_renderer or ActionRenderer()
        self.evidence_resolver = evidence_resolver or MatchEvidenceResolver()

    def assemble(
        self,
        *,
        profile: UserProfile,
        context: MatchContext,
        extraction: MatchInsightExtraction,
        analysis_metadata: Dict[str, object],
    ) -> MatchResult:
        if not profile.confirmed:
            raise ProfileNotConfirmedError("MatchInsightAssembler 只接受已确认画像")
        extraction.validate_context(context)
        candidates = extraction.normalized_insights()
        resolved_links = {
            item.candidate_id: self.evidence_resolver.resolve(
                context,
                profile_signal_ids=item.profile_signal_ids,
                job_signal_ids=item.job_signal_ids,
            )
            for item in candidates
        }
        self._validate_relation_semantics(
            candidates,
            resolved_links,
            context,
        )

        insights = [
            self._to_domain(item, resolved_links[item.candidate_id])
            for item in candidates
        ]
        by_id = {item.insight_id: item for item in insights}
        actions = [
            self._validated_action(item, by_id, context)
            for item in extraction.candidate_actions
        ]
        required_ids = {
            item.signal_id
            for item in context.job_signals
            if item.category == JobSignalCategory.REQUIRED_CAPABILITY
        }
        with_user_evidence = {
            signal_id
            for item in insights
            if item.evidence_link.profile_evidence_ids
            for signal_id in item.evidence_link.job_signal_ids
            if signal_id in required_ids
        }
        evidence_missing_ids = {
            signal_id
            for item in insights
            if item.relation_type == MatchRelationType.EVIDENCE_MISSING
            for signal_id in item.evidence_link.job_signal_ids
            if signal_id in required_ids
        }
        metadata = dict(analysis_metadata)
        metadata.update(
            profile_signal_count=len(
                {
                    signal_id
                    for item in insights
                    for signal_id in item.evidence_link.profile_signal_ids
                }
            ),
            job_signal_count=len(
                {
                    signal_id
                    for item in insights
                    for signal_id in item.evidence_link.job_signal_ids
                }
            ),
            resolved_profile_evidence_count=len(
                {
                    evidence_id
                    for item in insights
                    for evidence_id in item.evidence_link.profile_evidence_ids
                }
            ),
            resolved_job_evidence_count=len(
                {
                    evidence_id
                    for item in insights
                    for evidence_id in item.evidence_link.job_evidence_ids
                }
            ),
        )
        return MatchResult(
            match_id=f"match_{profile.profile_id}_{context.job_id}",
            profile_id=profile.profile_id,
            profile_version=profile.version,
            intelligence_id=context.intelligence_id,
            job_id=context.job_id,
            role_title=context.role_title,
            alignments=self._of(insights, MatchRelationType.STRONG_ALIGNMENT),
            partial_alignments=self._of(insights, MatchRelationType.PARTIAL_ALIGNMENT),
            evidence_gaps=[
                EvidenceGap.model_validate(item.model_dump())
                for item in self._of(insights, MatchRelationType.EVIDENCE_MISSING)
            ],
            confirmed_gaps=[
                ConfirmedGap.model_validate(item.model_dump())
                for item in self._of(insights, MatchRelationType.CONFIRMED_GAP)
            ],
            experience_depth_gaps=[
                ExperienceDepthGap.model_validate(item.model_dump())
                for item in self._of(insights, MatchRelationType.EXPERIENCE_DEPTH_GAP)
            ],
            preference_alignments=self._of(
                insights, MatchRelationType.PREFERENCE_ALIGNMENT
            ),
            potential_frictions=self._of(
                insights, MatchRelationType.POTENTIAL_FRICTION
            ),
            unknowns=self._of(insights, MatchRelationType.UNKNOWN),
            action_items=actions,
            coverage_metrics=MatchCoverageMetrics(
                required_capabilities_total=len(required_ids),
                required_capabilities_with_user_evidence=len(with_user_evidence),
                required_capabilities_evidence_missing=len(evidence_missing_ids),
                confirmed_gap_count=sum(
                    item.relation_type == MatchRelationType.CONFIRMED_GAP
                    for item in insights
                ),
            ),
            analysis_metadata=metadata,
        )

    @staticmethod
    def _to_domain(
        candidate: NormalizedMatchCandidate,
        evidence_link: MatchEvidenceLink,
    ) -> MatchInsight:
        try:
            return MatchInsight(
                insight_id=candidate.candidate_id,
                evidence_link=evidence_link,
                **candidate.model_dump(
                    exclude={"candidate_id", "profile_signal_ids", "job_signal_ids"}
                ),
            )
        except ValidationError as exc:
            raise LLMStructuredOutputError.from_pydantic(
                stage="MatchInsightAssembler.MatchInsight",
                error=exc,
            ) from exc

    @staticmethod
    def _of(
        insights: Iterable[MatchInsight],
        relation: MatchRelationType,
    ) -> list[MatchInsight]:
        return [item for item in insights if item.relation_type == relation]

    def _validate_relation_semantics(
        self,
        candidates: Iterable[NormalizedMatchCandidate],
        resolved_links: Dict[str, MatchEvidenceLink],
        context: MatchContext,
    ) -> None:
        profile_by_id = {item.signal_id: item for item in context.profile_signals}
        job_by_id = {item.signal_id: item for item in context.job_signals}
        for item in candidates:
            link = resolved_links[item.candidate_id]
            self._validate_required_references(item, link)
            profile_signals = [profile_by_id[value] for value in link.profile_signal_ids]
            job_signals = [job_by_id[value] for value in link.job_signal_ids]
            categories = {signal.category for signal in profile_signals}
            if item.dimension == MatchDimension.CAREER_PREFERENCE_ALIGNMENT and (
                ProfileSignalCategory.CAREER_PREFERENCE not in categories
            ):
                raise LLMStructuredOutputError(
                    "career_preference_alignment 必须引用已确认 career preference；goal 不能替代偏好",
                    error_code="PREFERENCE_ALIGNMENT_WITHOUT_CONFIRMED_PREFERENCE",
                    stage="MatchInsightAssembler.relation_validation",
                    identifier=item.candidate_id,
                )
            if item.relation_type == MatchRelationType.CONFIRMED_GAP and (
                ProfileSignalCategory.DEVELOPMENT_AREA not in categories
            ):
                raise LLMStructuredOutputError(
                    "confirmed_gap 必须引用已确认的 development-area 证据",
                    error_code="CONFIRMED_GAP_WITHOUT_CONFIRMED_GAP_EVIDENCE",
                    stage="MatchInsightAssembler.relation_validation",
                    identifier=item.candidate_id,
                )
            if item.relation_type == MatchRelationType.EXPERIENCE_DEPTH_GAP and not profile_signals:
                raise LLMStructuredOutputError(
                    "experience_depth_gap 必须引用已有相关经验信号",
                    error_code="EXPERIENCE_DEPTH_GAP_WITHOUT_BASE_EXPERIENCE",
                    stage="MatchInsightAssembler.relation_validation",
                    identifier=item.candidate_id,
                )
            if item.relation_type == MatchRelationType.PREFERENCE_ALIGNMENT and (
                ProfileSignalCategory.CAREER_PREFERENCE not in categories
            ):
                raise LLMStructuredOutputError(
                    "preference_alignment 必须引用已确认 career preference",
                    error_code="PREFERENCE_ALIGNMENT_WITHOUT_CONFIRMED_PREFERENCE",
                    stage="MatchInsightAssembler.relation_validation",
                    identifier=item.candidate_id,
                )
            if item.relation_type == MatchRelationType.POTENTIAL_FRICTION and not categories.intersection(
                {ProfileSignalCategory.CAREER_PREFERENCE, ProfileSignalCategory.VALUE}
            ):
                raise LLMStructuredOutputError(
                    "potential_friction 必须引用已确认 preference 或 value",
                    error_code="POTENTIAL_FRICTION_WITHOUT_CONFIRMED_PREFERENCE",
                    stage="MatchInsightAssembler.relation_validation",
                    identifier=item.candidate_id,
                )

    @staticmethod
    def _validate_required_references(
        item: NormalizedMatchCandidate,
        link: MatchEvidenceLink,
    ) -> None:
        both_sides = {
            MatchRelationType.STRONG_ALIGNMENT,
            MatchRelationType.PARTIAL_ALIGNMENT,
            MatchRelationType.CONFIRMED_GAP,
            MatchRelationType.EXPERIENCE_DEPTH_GAP,
            MatchRelationType.PREFERENCE_ALIGNMENT,
            MatchRelationType.POTENTIAL_FRICTION,
        }
        if (
            item.relation_type == MatchRelationType.EXPERIENCE_DEPTH_GAP
            and not item.profile_signal_ids
        ):
            raise LLMStructuredOutputError(
                "experience_depth_gap 必须引用已有相关经验信号",
                error_code="EXPERIENCE_DEPTH_GAP_WITHOUT_BASE_EXPERIENCE",
                stage="MatchInsightAssembler.relation_validation",
                identifier=item.candidate_id,
            )
        if item.relation_type in both_sides and not item.profile_signal_ids:
            raise LLMStructuredOutputError(
                "该 relation 必须包含用户信号。",
                error_code="RELATION_REQUIRES_PROFILE_SIGNAL",
                stage="MatchInsightAssembler.relation_validation",
                identifier=item.candidate_id,
            )
        if item.relation_type in both_sides and not item.job_signal_ids:
            raise LLMStructuredOutputError(
                "该 relation 必须包含岗位信号。",
                error_code="RELATION_REQUIRES_JOB_SIGNAL",
                stage="MatchInsightAssembler.relation_validation",
                identifier=item.candidate_id,
            )
        if item.relation_type in both_sides and not link.profile_evidence_ids:
            raise LLMStructuredOutputError(
                "该 relation 必须包含用户证据。",
                error_code="RELATION_REQUIRES_PROFILE_EVIDENCE",
                stage="MatchInsightAssembler.relation_validation",
                identifier=item.candidate_id,
            )
        if (
            item.relation_type in both_sides
            or item.relation_type == MatchRelationType.EVIDENCE_MISSING
        ) and not item.job_signal_ids:
            raise LLMStructuredOutputError(
                "该 relation 必须包含岗位信号。",
                error_code="RELATION_REQUIRES_JOB_SIGNAL",
                stage="MatchInsightAssembler.relation_validation",
                identifier=item.candidate_id,
            )
        if (
            item.relation_type in both_sides
            or item.relation_type == MatchRelationType.EVIDENCE_MISSING
        ) and not link.job_evidence_ids:
            raise LLMStructuredOutputError(
                "该 relation 必须包含岗位证据。",
                error_code="RELATION_REQUIRES_JOB_EVIDENCE",
                stage="MatchInsightAssembler.relation_validation",
                identifier=item.candidate_id,
            )
        if item.relation_type == MatchRelationType.UNKNOWN and not any(
            (item.profile_signal_ids, item.job_signal_ids)
        ):
            raise LLMStructuredOutputError(
                "unknown 必须至少引用一侧信号或证据。",
                error_code="RELATION_REQUIRES_REFERENCE",
                stage="MatchInsightAssembler.relation_validation",
                identifier=item.candidate_id,
            )

    def _validated_action(
        self,
        candidate: MatchActionCandidate,
        insights: Dict[str, MatchInsight],
        context: MatchContext,
    ) -> ActionItem:
        related = [insights[insight_id] for insight_id in candidate.related_insight_ids]
        for insight in related:
            allowed = self._ACTION_POLICY.get(insight.relation_type, set())
            if candidate.action_type not in allowed:
                raise LLMStructuredOutputError(
                    "Action type 与所关联 relation 不兼容。",
                    error_code="ACTION_INCOMPATIBLE_WITH_RELATION",
                    stage="MatchInsightAssembler.action_validation",
                    identifier=candidate.action_id,
                )
            if (
                candidate.action_type == ActionType.CLARIFY_PREFERENCE
                and insight.dimension
                not in {
                    MatchDimension.CAREER_PREFERENCE_ALIGNMENT,
                    MatchDimension.VALUE_WORKSTYLE_ALIGNMENT,
                }
            ):
                raise LLMStructuredOutputError(
                    "CLARIFY_PREFERENCE 只能关联偏好或价值观维度",
                    error_code="ACTION_INCOMPATIBLE_WITH_RELATION",
                    stage="MatchInsightAssembler.action_validation",
                    identifier=candidate.action_id,
                )
        supported_targets = {
            item.label for item in [*context.profile_signals, *context.job_signals]
        }
        if candidate.target_label not in supported_targets:
            raise LLMStructuredOutputError(
                "Action target 未出现在已验证的用户或岗位信号中",
                error_code="ACTION_TARGET_UNSUPPORTED",
                stage="MatchInsightAssembler.action_validation",
                identifier=candidate.action_id,
            )
        rendered = self.action_renderer.render(
            action_type=candidate.action_type,
            target_label=candidate.target_label,
            related_insights=related,
        )
        try:
            return ActionItem(
                action_id=candidate.action_id,
                action_type=candidate.action_type,
                description=rendered.description,
                rationale=rendered.rationale,
                priority=candidate.priority,
                expected_evidence=rendered.expected_evidence,
                target_label=candidate.target_label,
                related_insight_ids=candidate.related_insight_ids,
            )
        except ValidationError as exc:
            raise LLMStructuredOutputError.from_pydantic(
                stage="MatchInsightAssembler.ActionItem",
                error=exc,
            ) from exc
