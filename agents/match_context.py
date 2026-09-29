"""Minimal deterministic context for cross-domain evidence comparison."""

from __future__ import annotations

from typing import Iterable, List

from agents.match_insight_models import (
    JobSignalCategory,
    JobSignalRef,
    MatchContext,
    MatchEvidenceRef,
    ProfileSignalCategory,
    ProfileSignalRef,
)
from data.models import EvidenceItem, JobIntelligenceRecord, UserProfile
from workflows.stages import ProfileNotConfirmedError


class MatchContextBuilder:
    """Expose only confirmed signals and evidence needed for one comparison."""

    def build(
        self,
        profile: UserProfile,
        intelligence: JobIntelligenceRecord,
    ) -> MatchContext:
        if not profile.confirmed:
            raise ProfileNotConfirmedError("MatchContext 只接受已确认的 UserProfile")

        profile_signals = [
            *[
                ProfileSignalRef(
                    signal_id=item.skill_id,
                    category=ProfileSignalCategory.SKILL,
                    label=item.label,
                    description=item.description or "",
                    evidence_ids=item.evidence_ids,
                    confirmed_by_user=item.confirmed_by_user,
                )
                for item in profile.skills
            ],
            *[
                ProfileSignalRef(
                    signal_id=item.interest_id,
                    category=ProfileSignalCategory.INTEREST,
                    label=item.label,
                    description=item.description or "",
                    evidence_ids=item.evidence_ids,
                    confirmed_by_user=item.confirmed_by_user,
                )
                for item in profile.interests
            ],
            *[
                ProfileSignalRef(
                    signal_id=item.value_id,
                    category=ProfileSignalCategory.VALUE,
                    label=item.label,
                    description=item.description or "",
                    evidence_ids=item.evidence_ids,
                    confirmed_by_user=item.confirmed_by_user,
                )
                for item in profile.values
            ],
            *[
                ProfileSignalRef(
                    signal_id=item.goal_id,
                    category=ProfileSignalCategory.GOAL,
                    label=item.label,
                    description=item.description or "",
                    evidence_ids=item.evidence_ids,
                    confirmed_by_user=item.confirmed_by_user,
                    goal_type=item.goal_type,
                )
                for item in profile.goals
            ],
            *[
                ProfileSignalRef(
                    signal_id=item.preference_id,
                    category=ProfileSignalCategory.CAREER_PREFERENCE,
                    label=item.label,
                    description=item.description or "",
                    evidence_ids=item.evidence_ids,
                    confirmed_by_user=item.confirmed_by_user,
                )
                for item in profile.career_preferences
            ],
            *[
                ProfileSignalRef(
                    signal_id=item.statement_id,
                    category=ProfileSignalCategory.STRENGTH,
                    label=item.text,
                    evidence_ids=item.evidence_ids,
                    confirmed_by_user=item.confirmed_by_user,
                )
                for item in profile.strengths
            ],
            *[
                ProfileSignalRef(
                    signal_id=item.statement_id,
                    category=ProfileSignalCategory.DEVELOPMENT_AREA,
                    label=item.text,
                    evidence_ids=item.evidence_ids,
                    confirmed_by_user=item.confirmed_by_user,
                )
                for item in profile.development_areas
            ],
        ]
        if not all(item.confirmed_by_user for item in profile_signals):
            raise ProfileNotConfirmedError("已确认画像中的 Match signals 必须由用户确认")

        job_signals = [
            *self._job_refs(intelligence.actual_work, JobSignalCategory.ACTUAL_WORK),
            *self._job_refs(intelligence.required_capabilities, JobSignalCategory.REQUIRED_CAPABILITY),
            *self._job_refs(intelligence.preferred_capabilities, JobSignalCategory.PREFERRED_CAPABILITY),
            *self._job_refs(intelligence.technology_signals, JobSignalCategory.TECHNOLOGY),
            *self._job_refs(intelligence.work_style, JobSignalCategory.WORK_STYLE),
            *self._job_refs(intelligence.collaboration_context, JobSignalCategory.COLLABORATION_CONTEXT),
            *self._job_refs(intelligence.growth_exposure, JobSignalCategory.GROWTH_EXPOSURE),
            *self._job_refs(intelligence.potential_friction, JobSignalCategory.POTENTIAL_FRICTION),
        ]
        for item in intelligence.uncertainties:
            if not item.uncertainty_id:
                raise ValueError("Job uncertainty 缺少稳定 ID")
            job_signals.append(
                JobSignalRef(
                    signal_id=item.uncertainty_id,
                    category=JobSignalCategory.UNCERTAINTY,
                    label=item.topic,
                    description=item.reason,
                    evidence_ids=item.evidence_ids,
                )
            )

        profile_ids = {
            evidence_id for item in profile_signals for evidence_id in item.evidence_ids
        }
        job_ids = {evidence_id for item in job_signals for evidence_id in item.evidence_ids}
        return MatchContext(
            profile_id=profile.profile_id,
            profile_version=profile.version,
            job_id=intelligence.job_id,
            intelligence_id=intelligence.intelligence_id,
            role_title=intelligence.role_title,
            profile_signals=profile_signals,
            profile_evidence=self._evidence_refs(profile.evidence, profile_ids),
            job_signals=job_signals,
            job_evidence=self._evidence_refs(intelligence.evidence, job_ids),
        )

    @staticmethod
    def _job_refs(items: Iterable, category: JobSignalCategory) -> List[JobSignalRef]:
        return [
            JobSignalRef(
                signal_id=item.signal_id,
                category=category,
                label=item.label,
                description=item.description,
                evidence_ids=item.evidence_ids,
            )
            for item in items
        ]

    @staticmethod
    def _evidence_refs(
        evidence: Iterable[EvidenceItem],
        included_ids: set[str],
    ) -> List[MatchEvidenceRef]:
        return [
            MatchEvidenceRef(
                evidence_id=item.id,
                text=item.statement,
                source_type=item.source_type.value,
            )
            for item in evidence
            if item.id in included_ids
        ]
