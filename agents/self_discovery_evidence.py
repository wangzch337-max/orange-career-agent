"""Deterministically convert explicit input and records into stable evidence IDs."""

from __future__ import annotations

from typing import Iterable, List, Mapping, Sequence

from data.models import CourseRecord, EvidenceItem, EvidenceSourceType
from agents.self_discovery_models import EvidenceBundle, SelfDiscoverySourceEvidence


class SourceEvidenceBuilder:
    """Build evidence without semantic inference or network access."""

    def build(
        self,
        user_input: Mapping[str, object],
        courses: Sequence[CourseRecord],
    ) -> EvidenceBundle:
        source_items: List[SelfDiscoverySourceEvidence] = []
        domain_items: List[EvidenceItem] = []
        education_summary = self._education_summary(user_input)

        def add(
            evidence_id: str,
            text: str,
            source_type: EvidenceSourceType,
            source_name: str,
            *,
            supports_development_area: bool = False,
        ) -> None:
            normalized = text.strip()
            if not normalized:
                return
            source_items.append(
                SelfDiscoverySourceEvidence(
                    id=evidence_id,
                    text=normalized,
                    source_type=source_type,
                    source_name=source_name,
                    supports_development_area=supports_development_area,
                )
            )
            domain_items.append(
                EvidenceItem(
                    id=evidence_id,
                    source_type=source_type,
                    source_name=source_name,
                    statement=normalized,
                    confidence=1.0,
                    metadata={
                        "supports_development_area": supports_development_area,
                    },
                )
            )

        if education_summary:
            add(
                "user_001",
                education_summary,
                EvidenceSourceType.EXPLICIT_USER_INPUT,
                "education",
            )

        for index, course in enumerate(self._dedupe_courses(courses), start=1):
            add(
                f"course_{index:03d}",
                f"课程：{course.title}。{course.summary}",
                EvidenceSourceType.COURSE,
                course.title,
            )

        projects = user_input.get("project_experiences", user_input.get("project_experience", []))
        if isinstance(projects, Mapping):
            projects = [projects]
        if isinstance(projects, list):
            seen_projects = set()
            project_index = 0
            for raw in projects:
                if not isinstance(raw, Mapping):
                    continue
                name = str(raw.get("name", "未命名项目")).strip()
                details = raw.get("evidence", raw.get("summary", ""))
                if isinstance(details, list):
                    detail_text = "；".join(self._unique_text(details))
                else:
                    detail_text = str(details).strip()
                signature = (name.casefold(), detail_text.casefold())
                if signature in seen_projects:
                    continue
                seen_projects.add(signature)
                project_index += 1
                add(
                    f"project_{project_index:03d}",
                    f"项目：{name}。{detail_text}",
                    EvidenceSourceType.PROJECT,
                    name,
                )

        career_scope = user_input.get("career_scope")
        career_entries: List[str] = []
        if isinstance(career_scope, Mapping):
            regions = career_scope.get("regions", [])
            roles = career_scope.get("role_scope", [])
            if isinstance(regions, list) and regions:
                career_entries.append(f"意向地区：{'、'.join(self._unique_text(regions))}")
            if isinstance(roles, list) and roles:
                career_entries.append(f"职业探索范围：{'、'.join(self._unique_text(roles))}")
        else:
            if user_input.get("career_interest"):
                career_entries.append(f"职业兴趣：{user_input['career_interest']}")
            if user_input.get("career_goal"):
                career_entries.append(f"职业目标：{user_input['career_goal']}")
        for index, text in enumerate(self._unique_text(career_entries), start=1):
            add(
                f"career_{index:03d}",
                text,
                EvidenceSourceType.EXPLICIT_USER_INPUT,
                "career_scope",
            )

        values = user_input.get("career_values", [])
        if isinstance(values, list):
            for index, text in enumerate(self._unique_text(values), start=1):
                add(
                    f"value_{index:03d}",
                    f"明确职业价值：{text}",
                    EvidenceSourceType.EXPLICIT_USER_INPUT,
                    "career_values",
                )

        learning = user_input.get("learning_preferences", [])
        if isinstance(learning, list):
            for index, text in enumerate(self._unique_text(learning), start=1):
                add(
                    f"learning_{index:03d}",
                    f"明确学习与工作方式偏好：{text}",
                    EvidenceSourceType.EXPLICIT_USER_INPUT,
                    "learning_preferences",
                )

        preferences = user_input.get("career_preferences", [])
        if isinstance(preferences, list):
            for index, text in enumerate(self._unique_text(preferences), start=1):
                add(
                    f"preference_{index:03d}",
                    f"明确职业偏好：{text}",
                    EvidenceSourceType.EXPLICIT_USER_INPUT,
                    "career_preferences",
                )

        gaps = user_input.get("explicit_development_areas", [])
        if isinstance(gaps, list):
            for index, text in enumerate(self._unique_text(gaps), start=1):
                add(
                    f"development_{index:03d}",
                    f"用户明确说明的有限经验或能力缺口：{text}",
                    EvidenceSourceType.EXPLICIT_USER_INPUT,
                    "explicit_development_areas",
                    supports_development_area=True,
                )

        return EvidenceBundle(
            source_evidence=source_items,
            domain_evidence=domain_items,
            education_summary=education_summary,
        )

    @staticmethod
    def _education_summary(user_input: Mapping[str, object]) -> str:
        education = user_input.get("education")
        if isinstance(education, Mapping):
            parts = [
                str(education.get(key, "")).strip()
                for key in ("university_context", "academic_level", "program")
            ]
            return "；".join(part for part in parts if part)
        return str(user_input.get("program", "")).strip()

    @staticmethod
    def _unique_text(values: Iterable[object]) -> List[str]:
        result: List[str] = []
        seen = set()
        for value in values:
            text = str(value).strip()
            marker = text.casefold()
            if text and marker not in seen:
                seen.add(marker)
                result.append(text)
        return result

    @staticmethod
    def _dedupe_courses(courses: Sequence[CourseRecord]) -> List[CourseRecord]:
        result: List[CourseRecord] = []
        seen = set()
        for course in courses:
            marker = course.course_id.casefold()
            if marker not in seen:
                seen.add(marker)
                result.append(course)
        return result
