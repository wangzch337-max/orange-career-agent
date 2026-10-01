"""Bounded structured context built only from authoritative retrieval results."""

from __future__ import annotations

from collections.abc import Sequence

from memory.models import (
    HybridMemoryRetrievalResult,
    MemoryContext,
    MemoryContextItem,
    MemoryStatus,
)


class MemoryContextBuilder:
    def __init__(
        self,
        *,
        max_records: int = 8,
        max_characters: int | None = 6000,
    ) -> None:
        if max_records < 1:
            raise ValueError("Memory context max_records must be positive.")
        if max_characters is not None and max_characters < 1:
            raise ValueError("Memory context character budget must be positive.")
        self.max_records = max_records
        self.max_characters = max_characters

    def build(
        self,
        subject_id: str,
        results: Sequence[HybridMemoryRetrievalResult],
    ) -> MemoryContext:
        items: list[MemoryContextItem] = []
        character_count = 0
        truncated = False
        for result in results:
            record = result.memory
            if record.subject_id != subject_id or record.status != MemoryStatus.CONFIRMED:
                continue
            if len(items) >= self.max_records:
                truncated = True
                break
            next_count = character_count + len(record.content)
            if self.max_characters is not None and next_count > self.max_characters:
                truncated = True
                continue
            items.append(
                MemoryContextItem(
                    memory_id=record.memory_id,
                    memory_type=record.memory_type,
                    status=record.status,
                    content=record.content,
                    source_type=record.source_type,
                    confidence=record.confidence,
                    authority="active_confirmed",
                    lexical_rank=result.lexical_rank,
                    semantic_rank=result.semantic_rank,
                    fusion_rank=result.fusion_rank,
                )
            )
            character_count = next_count
        return MemoryContext(
            subject_id=subject_id,
            items=items,
            max_records=self.max_records,
            character_count=character_count,
            truncated=truncated,
        )
