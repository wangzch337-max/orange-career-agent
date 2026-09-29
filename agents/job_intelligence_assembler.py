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
            role_title=job.title,
            role_family=job.role_family,
            actual_work=self._map(job.job_id, "actual", extraction.actual_work),
            required_capabilities=self._map(job.job_id, "required", extraction.required_capabilities),
            preferred_capabilities=self._map(job.job_id, "preferred", extraction.preferred_capabilities),
            technology_signals=self._map(job.job_id, "technology", extraction.technology_signals),
            work_style=self._map(job.job_id, "work_style", extraction.work_style_signals),
            collaboration_context=self._map(job.job_id, "collaboration", extraction.collaboration_context),
            growth_exposure=self._map(job.job_id, "growth", extraction.growth_exposure),
            potential_friction=self._map(job.job_id, "friction", extraction.potential_friction),
            uncertainties=[
                item.model_copy(update={"uncertainty_id": f"{job.job_id}_uncertainty_{index:03d}"})
                for index, item in enumerate(extraction.job_uncertainties, start=1)
            ],
            evidence=domain_evidence,
            evidence_ids=referenced_ids,
            analysis_metadata=analysis_metadata,
        )

    @staticmethod
    def _map(
        job_id: str,
        category: str,
        items: list[JobExtractionSignal],
    ) -> list[JobIntelligenceSignal]:
        return [
            JobIntelligenceSignal(
                signal_id=f"{job_id}_{category}_{index:03d}",
                **item.model_dump(),
            )
            for index, item in enumerate(items, start=1)
        ]
