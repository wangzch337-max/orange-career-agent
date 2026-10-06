"""Exact direction membership; never reads historical jobs or personal facts."""

import json
from pathlib import Path
from career_reality.sources import direction_id, direction_key
from role_landscape.models import Inventory
from ui.conversation_store import _no_credentials

SOURCE_PATH = Path(__file__).resolve().parents[1] / "data/fixtures/role_landscape/role_sources.json"


class RoleLandscapeRegistry:
    def __init__(self, path=SOURCE_PATH):
        self.path = Path(path)  # Code-owned; not selected by chat/provider.

    def inventory(self):
        if self.path.stat().st_size > 100000:
            raise ValueError("SOURCE_BUDGET")
        text = self.path.read_text(encoding="utf-8")
        _no_credentials(text)
        inventory = Inventory.model_validate(json.loads(text))
        sources, identities, roles = set(), set(), set()
        for source in inventory.records:
            key = direction_key(source.direction_identity.family, source.direction_identity.title)
            if source.source_id in sources or key in identities:
                raise ValueError("AMBIGUOUS_DIRECTION_SOURCE")
            sources.add(source.source_id)
            identities.add(key)
            prose = source.model_dump_json().casefold()
            if any(word in prose for word in ("你适合", "你缺少", "最适合", "匹配度", "http://", "https://")):
                raise ValueError("UNSAFE_SOURCE")
            for role in source.roles:
                if role.role_id in roles:
                    raise ValueError("DUPLICATE_ROLE_ID")
                roles.add(role.role_id)
        return inventory

    def resolve(self, family, title, selected_id):
        if selected_id != direction_id(family, title):
            raise ValueError("INVALID_DIRECTION_ID")
        key = direction_key(family, title)
        return next((s for s in self.inventory().records if
                     direction_key(s.direction_identity.family, s.direction_identity.title) == key), None)
