"""Exact public source identity and membership; no template synthesis/fallback."""

import hashlib
import json
from pathlib import Path
from career_discovery.context import fingerprint
from specific_role.sources import SpecificRoleRegistry
from ui.conversation_store import _no_credentials
from evidence_validation.models import Inventory

SOURCE_PATH = Path(__file__).resolve().parents[1] / "data/fixtures/evidence_validation/experiments.json"
SOURCE_HASH = "4bbcb8b0db1dc517020720bb9f2ba2b17fc8a5ff5f96fd7297d3b69322f0ce23"


class ExperimentRegistry:
    def __init__(self, path=SOURCE_PATH):
        self.path = Path(path)

    def inventory(self):
        if self.path != SOURCE_PATH or self.path.stat().st_size > 50000:
            raise ValueError("D6_UNAPPROVED_PATH_OR_BUDGET")
        raw = self.path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != SOURCE_HASH:
            raise ValueError("D6_TEMPLATE_FINGERPRINT_MISMATCH")
        text = raw.decode("utf-8")
        _no_credentials(text)
        inventory = Inventory.model_validate(json.loads(text))
        sources = {s.representative_role_id: s for s in SpecificRoleRegistry().inventory().records}
        seen, ids = set(), set()
        for t in inventory.templates:
            s = sources.get(t.role_id)
            if s is None or t.role_id in seen or t.template_id in ids:
                raise ValueError("D6_INVALID_COVERAGE")
            if (t.direction_id, t.archetype_id, t.source_id, t.source_version, t.source_fingerprint,
                t.work_evidence_ids, t.eligible_relation_types, t.unknown_scope, t.partial_scope) != (
                s.parent_direction_id, s.parent_archetype_id, s.source_id, s.version,
                fingerprint(s.model_dump(mode="json")),
                (f"{s.source_id}@{s.version}:{t.role_id}:responsibilities:1",),
                ("UNKNOWN", "RELATED_BUT_PARTIAL"), s.responsibilities[1],
                "独立性与完整责任尚未证实：" + s.responsibilities[1]):
                raise ValueError("D6_INVALID_SOURCE_MEMBERSHIP")
            if any(v in t.model_dump_json().casefold() for v in (
                "fit score", "pass/fail", "qualified", "high fit", "good fit", "匹配度", "你适合", "你缺少", "http://", "https://")):
                raise ValueError("D6_UNSAFE_TEMPLATE")
            seen.add(t.role_id); ids.add(t.template_id)
        if seen != set(sources):
            raise ValueError("D6_INCOMPLETE_COVERAGE")
        return inventory

    def resolve(self, target, work):
        matches = [t for t in self.inventory().templates if (
            t.role_id, t.source_id, t.source_version, t.source_fingerprint, t.work_evidence_ids) == (
            work.role_id, work.source_id, work.source_version, work.source_fingerprint, target.work_evidence_ids)
            and target.relation_type.value in t.eligible_relation_types
            and target.unresolved_scope == (t.partial_scope if target.relation_type.value == "RELATED_BUT_PARTIAL" else t.unknown_scope)]
        if len(matches) > 1:
            raise ValueError("D6_AMBIGUOUS_TEMPLATE")
        return matches[0] if matches else None
