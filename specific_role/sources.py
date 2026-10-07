"""Pinned independent public material; exact membership, never legacy job fallback."""

import hashlib
import json
from pathlib import Path
from career_discovery.context import fingerprint
from career_reality.sources import direction_id
from role_landscape.sources import RoleLandscapeRegistry
from specific_role.models import Inventory
from ui.conversation_store import _no_credentials

SOURCE_PATH = Path(__file__).resolve().parents[1] / "data/fixtures/specific_role/role_sources.json"
SOURCE_HASH = "78218383b6b87292ad20668a9619354df1c6308f448fcb95548a61c04f7b371a"


class SpecificRoleRegistry:
    """Only code-owned, byte-pinned sources may establish D.4 authority."""

    def __init__(self, path=SOURCE_PATH):
        self.path = Path(path)

    def inventory(self):
        if self.path.stat().st_size > 100000:
            raise ValueError("SOURCE_BUDGET")
        raw = self.path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != SOURCE_HASH:
            raise ValueError("SOURCE_FINGERPRINT_MISMATCH")
        text = raw.decode("utf-8")
        _no_credentials(text)
        inventory = Inventory.model_validate(json.loads(text))
        parents = RoleLandscapeRegistry().inventory().records
        expected = {r.role_id: s for s in parents for r in s.roles}
        seen, ids, source_ids = set(), set(), set()
        for source in inventory.records:
            parent = expected.get(source.parent_archetype_id)
            if parent is None or source.parent_archetype_id in seen:
                raise ValueError("INVALID_ARCHETYPE_MEMBERSHIP")
            if source.representative_role_id in ids or source.source_id in source_ids:
                raise ValueError("DUPLICATE_SPECIFIC_ROLE")
            if (source.direction_identity, source.parent_direction_id, source.parent_source_id,
                source.parent_source_version, source.parent_source_fingerprint) != (
                parent.direction_identity, direction_id(parent.direction_identity.family, parent.direction_identity.title),
                parent.source_id, parent.version, fingerprint(parent.model_dump(mode="json"))):
                raise ValueError("INVALID_PARENT_SOURCE")
            prose = source.model_dump_json().casefold()
            if any(v in prose for v in ("你适合", "你缺少", "最适合", "匹配度", "http://", "https://",
                                       "ai product intern", "ai application engineer", "data analyst")):
                raise ValueError("UNSAFE_SOURCE")
            seen.add(source.parent_archetype_id)
            ids.add(source.representative_role_id)
            source_ids.add(source.source_id)
        if seen != set(expected):
            raise ValueError("INCOMPLETE_ARCHETYPE_COVERAGE")
        return inventory

    def resolve(self, parent, selected_direction_id, archetype_id):
        if selected_direction_id != direction_id(parent.direction_identity.family, parent.direction_identity.title):
            raise ValueError("INVALID_DIRECTION")
        if archetype_id not in {r.role_id for r in parent.roles}:
            raise ValueError("INVALID_ARCHETYPE")
        source = next((s for s in self.inventory().records if s.parent_archetype_id == archetype_id), None)
        if source is None or (source.parent_direction_id, source.parent_source_id,
                source.parent_source_version, source.parent_source_fingerprint) != (
                selected_direction_id, parent.source_id, parent.version, fingerprint(parent.model_dump(mode="json"))):
            raise ValueError("MISSING_OR_STALE_SOURCE")
        return source
