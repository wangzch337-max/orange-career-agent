"""Deterministic conversion from JobRecord fields to stable evidence units."""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

from agents.job_intelligence_models import (
    JobEvidenceBundle,
    JobEvidenceCategory,
    JobSourceEvidence,
)
from data.models import JobRecord


class JobEvidenceBuilder:
    """Build evidence without semantic enrichment, web access, or an LLM."""

    _SUFFIX = {
        JobEvidenceCategory.TITLE: "title",
        JobEvidenceCategory.SUMMARY: "summary",
        JobEvidenceCategory.RESPONSIBILITY: "resp",
        JobEvidenceCategory.REQUIREMENT: "req",
        JobEvidenceCategory.PREFERRED_QUALIFICATION: "pref",
        JobEvidenceCategory.TECHNOLOGY: "tech",
        JobEvidenceCategory.LOCATION: "location",
        JobEvidenceCategory.EMPLOYMENT_TYPE: "employment",
    }

    def build(self, job: JobRecord) -> JobEvidenceBundle:
        candidates: List[Tuple[JobEvidenceCategory, str]] = [
            (JobEvidenceCategory.TITLE, job.title),
            (JobEvidenceCategory.SUMMARY, job.description),
            *self._items(JobEvidenceCategory.RESPONSIBILITY, job.responsibilities),
            *self._items(JobEvidenceCategory.REQUIREMENT, job.requirements),
            *self._items(
                JobEvidenceCategory.PREFERRED_QUALIFICATION,
                job.preferred_qualifications,
            ),
            *self._items(JobEvidenceCategory.TECHNOLOGY, job.technology_tags),
            (JobEvidenceCategory.LOCATION, f"{job.city} / {job.region.value}"),
            (JobEvidenceCategory.EMPLOYMENT_TYPE, job.employment_type.value),
        ]
        seen = set()
        category_counts: dict[JobEvidenceCategory, int] = {}
        evidence: List[JobSourceEvidence] = []
        safe_job_id = re.sub(r"[^a-zA-Z0-9_]+", "_", job.job_id).strip("_")
        for category, raw_text in candidates:
            text = raw_text.strip()
            normalized = " ".join(text.casefold().split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            category_counts[category] = category_counts.get(category, 0) + 1
            evidence.append(
                JobSourceEvidence(
                    id=(
                        f"{safe_job_id}_{self._SUFFIX[category]}_"
                        f"{category_counts[category]:03d}"
                    ),
                    job_id=job.job_id,
                    category=category,
                    text=text,
                    source_type=job.source_type,
                )
            )
        return JobEvidenceBundle(source_evidence=evidence)

    @staticmethod
    def _items(
        category: JobEvidenceCategory,
        values: Iterable[str],
    ) -> List[Tuple[JobEvidenceCategory, str]]:
        return [(category, value) for value in values]
