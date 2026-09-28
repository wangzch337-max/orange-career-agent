"""Deterministic Phase 4 assembly into the authoritative job record."""

from __future__ import annotations

from typing import Dict

from agents.job_intelligence_models import (
    JobEvidenceBundle,
    JobExtractionSignal,
    JobIntelligenceExtraction,
)
from data.models import (
    EvidenceItem,
    JobIntelligenceRecord,
    JobIntelligenceSignal,
    JobRecord,
)


class JobIntelligenceAssembler:
    """Validate links and copy semantic candidates without adding claims."""

    def assemble(
        self,
        *,
        job: JobRecord,
        extraction: JobIntelligenceExtraction,
        evidence: JobEvidenceBundle,
        analysis_metadata: Dict[str, object],
    ) -> JobIntelligenceRecord:
        extraction.validate_evidence_ids(evidence.source_evidence)
        signals = extraction.signals()
        referenced_ids = list(
            dict.fromkeys(
                evidence_id
                for item in [*signals, *extraction.job_uncertainties]
                for evidence_id in item.evidence_ids
            )
        )
        domain_evidence = [
            EvidenceItem(
                id=item.id,
                source_type=item.source_type,
                source_name=job.source_name,
                statement=item.text,
                confidence=1.0,
                metadata={
                    "job_id": job.job_id,
                    "category": item.category.value,
                    "fixture": job.source_type.value == "system_fixture",
                },
            )
            for item in evidence.source_evidence
        ]
        return JobIntelligenceRecord(
            intelligence_id=f"intelligence_{job.job_id}",
            job_id=job.job_id,
            role_family=job.role_family,
            actual_work=self._map(extraction.actual_work),
            required_capabilities=self._map(extraction.required_capabilities),
            preferred_capabilities=self._map(extraction.preferred_capabilities),
            technology_signals=self._map(extraction.technology_signals),
            work_style=self._map(extraction.work_style_signals),
            collaboration_context=self._map(extraction.collaboration_context),
            growth_exposure=self._map(extraction.growth_exposure),
            potential_friction=self._map(extraction.potential_friction),
            uncertainties=extraction.job_uncertainties,
            evidence=domain_evidence,
            evidence_ids=referenced_ids,
            analysis_metadata=analysis_metadata,
        )

    @staticmethod
    def _map(items: list[JobExtractionSignal]) -> list[JobIntelligenceSignal]:
        return [JobIntelligenceSignal.model_validate(item.model_dump()) for item in items]
