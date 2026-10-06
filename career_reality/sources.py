"""Exact approved identities only. No fuzzy/embedding/job/model fallback."""

import json
from pathlib import Path
from career_discovery.context import fingerprint
from career_discovery.service import identity
from career_reality.models import SourceInventory
from ui.conversation_store import _no_credentials

SOURCE_PATH = Path(__file__).resolve().parents[1] / "data/fixtures/career_reality/work_sources.json"


def direction_key(family, title):
    from types import SimpleNamespace
    return identity(SimpleNamespace(direction_family=family, title=title))


def direction_id(family, title):
    return "direction_" + fingerprint(direction_key(family, title))[:24]


class CareerRealitySourceRegistry:
    """Reload and revalidate public inventory so a changed source invalidates context."""

    def __init__(self, path=SOURCE_PATH):
        self.path = Path(path)  # Code-owned path, never user/provider-selected.

    def inventory(self):
        if self.path.stat().st_size > 100000:
            raise ValueError("SOURCE_BUDGET")
        text = self.path.read_text(encoding="utf-8")
        _no_credentials(text)
        value = SourceInventory.model_validate(json.loads(text))
        ids, keys = set(), set()
        for source in value.records:
            if source.source_id in ids:
                raise ValueError("DUPLICATE_SOURCE")
            ids.add(source.source_id)
            # Trusted demo prose still cannot masquerade as personal judgment.
            prose = source.model_dump_json()
            if any(word in prose.casefold() for word in (
                "你适合", "你不适合", "你缺少", "匹配度", "最适合", "best role", "http://", "https://")):
                raise ValueError("UNSAFE_SOURCE")
            for item in source.identities:
                key = direction_key(item.family, item.title)
                if key in keys:
                    raise ValueError("AMBIGUOUS_IDENTITY")
                keys.add(key)
        return value

    def resolve(self, family, title, selected_id):
        if selected_id != direction_id(family, title):
            raise ValueError("INVALID_DIRECTION_ID")
        key = direction_key(family, title)
        return next((s for s in self.inventory().records
                     if any(direction_key(i.family, i.title) == key for i in s.identities)), None)

    def get(self, source_id):
        return next((s for s in self.inventory().records if s.source_id == source_id), None)
