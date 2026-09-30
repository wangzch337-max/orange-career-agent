"""Deterministic exact/lexical retrieval with authority metadata preserved."""

from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from typing import Mapping, Sequence

from memory.base import MemoryStore
from memory.models import (
    MemoryRelevance,
    MemoryRetrievalResult,
    MemoryStatus,
    MemoryType,
)


TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def tokenize(value: str) -> list[str]:
    return list(dict.fromkeys(TOKEN_PATTERN.findall(normalize_text(value))))


class MemoryRetriever(ABC):
    @abstractmethod
    def retrieve(
        self,
        subject_id: str,
        query: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
        metadata_filters: Mapping[str, object] | None = None,
        include_history: bool = False,
        statuses: Sequence[MemoryStatus] | None = None,
        limit: int = 10,
    ) -> list[MemoryRetrievalResult]:
        raise NotImplementedError


class DeterministicMemoryRetriever(MemoryRetriever):
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def retrieve(
        self,
        subject_id: str,
        query: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
        metadata_filters: Mapping[str, object] | None = None,
        include_history: bool = False,
        statuses: Sequence[MemoryStatus] | None = None,
        limit: int = 10,
    ) -> list[MemoryRetrievalResult]:
        normalized_query = normalize_text(query)
        if not normalized_query:
            raise ValueError("Lexical retrieval query cannot be empty.")
        if limit < 1:
            raise ValueError("Retrieval limit must be positive.")
        if statuses is not None and not include_history:
            raise ValueError("Explicit status filtering requires include_history=True.")
        if include_history:
            records = self.store.list_history(
                subject_id,
                statuses=statuses,
                memory_types=memory_types,
                metadata_filters=metadata_filters,
            )
        else:
            records = self.store.list_active(
                subject_id,
                memory_types=memory_types,
                metadata_filters=metadata_filters,
            )
        query_tokens = tokenize(normalized_query)
        results: list[MemoryRetrievalResult] = []
        for record in records:
            normalized_content = normalize_text(record.content)
            content_tokens = set(tokenize(normalized_content))
            matched_tokens = [token for token in query_tokens if token in content_tokens]
            exact_phrase_match = normalized_query in normalized_content
            score = (100 if exact_phrase_match else 0) + (10 * len(matched_tokens))
            if score == 0:
                continue
            results.append(
                MemoryRetrievalResult(
                    memory=record,
                    relevance=MemoryRelevance(
                        score=score,
                        exact_phrase_match=exact_phrase_match,
                        matched_tokens=matched_tokens,
                    ),
                )
            )
        results.sort(
            key=lambda item: (
                -item.relevance.score,
                item.memory.created_at.isoformat(),
                item.memory.memory_id,
            )
        )
        return results[:limit]
