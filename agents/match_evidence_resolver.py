"""Deterministically resolve Match evidence owned by selected context signals."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from agents.match_insight_models import MatchContext
from data.models import MatchEvidenceLink
from providers.errors import LLMStructuredOutputError


class MatchEvidenceResolver:
    """Build authoritative evidence links without semantic inference or LLM calls."""

    def resolve(
        self,
        context: MatchContext,
        *,
        profile_signal_ids: Sequence[str],
        job_signal_ids: Sequence[str],
    ) -> MatchEvidenceLink:
        profile_ids = self._ordered_unique(profile_signal_ids)
        job_ids = self._ordered_unique(job_signal_ids)
        profile_by_id = {item.signal_id: item for item in context.profile_signals}
        job_by_id = {item.signal_id: item for item in context.job_signals}

        self._validate_signal_ids(
            profile_ids,
            profile_by_id,
            side="profile",
            error_code="UNKNOWN_PROFILE_SIGNAL_ID",
        )
        self._validate_signal_ids(
            job_ids,
            job_by_id,
            side="job",
            error_code="UNKNOWN_JOB_SIGNAL_ID",
        )

        profile_evidence_ids = self._owned_evidence_union(
            (profile_by_id[signal_id].evidence_ids for signal_id in profile_ids)
        )
        job_evidence_ids = self._owned_evidence_union(
            (job_by_id[signal_id].evidence_ids for signal_id in job_ids)
        )
        self._validate_context_evidence(
            profile_evidence_ids,
            {item.evidence_id for item in context.profile_evidence},
            side="profile",
        )
        self._validate_context_evidence(
            job_evidence_ids,
            {item.evidence_id for item in context.job_evidence},
            side="job",
        )
        return MatchEvidenceLink(
            profile_signal_ids=profile_ids,
            profile_evidence_ids=profile_evidence_ids,
            job_signal_ids=job_ids,
            job_evidence_ids=job_evidence_ids,
        )

    @staticmethod
    def _ordered_unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @classmethod
    def _owned_evidence_union(
        cls,
        evidence_groups: Iterable[Iterable[str]],
    ) -> list[str]:
        return cls._ordered_unique(
            evidence_id
            for evidence_ids in evidence_groups
            for evidence_id in evidence_ids
        )

    @staticmethod
    def _validate_signal_ids(
        signal_ids: Sequence[str],
        signals_by_id: dict[str, object],
        *,
        side: str,
        error_code: str,
    ) -> None:
        for signal_id in signal_ids:
            if signal_id not in signals_by_id:
                raise LLMStructuredOutputError(
                    f"Match output referenced an unknown {side} signal ID.",
                    error_code=error_code,
                    stage="MatchEvidenceResolver.resolve",
                    identifier=signal_id,
                )

    @staticmethod
    def _validate_context_evidence(
        evidence_ids: Sequence[str],
        available_ids: set[str],
        *,
        side: str,
    ) -> None:
        for evidence_id in evidence_ids:
            if evidence_id not in available_ids:
                raise LLMStructuredOutputError(
                    f"A {side} signal owns evidence absent from MatchContext.",
                    error_code=f"CONTEXT_{side.upper()}_EVIDENCE_UNAVAILABLE",
                    stage="MatchEvidenceResolver.resolve",
                    identifier=evidence_id,
                )
