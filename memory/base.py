"""Storage abstractions that keep Agents independent from SQLite."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Mapping, Sequence

from data.models import EvidenceSourceType, UserProfile
from memory.models import (
    MemoryRecord,
    MemoryStatus,
    MemoryType,
    ProfileSaveResult,
)


class StructuredProfileStore(ABC):
    @abstractmethod
    def save_confirmed_profile(
        self, subject_id: str, profile: UserProfile
    ) -> ProfileSaveResult:
        raise NotImplementedError

    @abstractmethod
    def get_current_confirmed_profile(self, subject_id: str) -> UserProfile | None:
        raise NotImplementedError

    @abstractmethod
    def get_profile_version(
        self, subject_id: str, profile_id: str, version: int
    ) -> UserProfile | None:
        raise NotImplementedError

    @abstractmethod
    def list_profile_history(self, subject_id: str) -> list[UserProfile]:
        raise NotImplementedError


class MemoryStore(ABC):
    @abstractmethod
    def create_candidate(
        self,
        *,
        subject_id: str,
        memory_type: MemoryType,
        content: str,
        source_type: EvidenceSourceType,
        evidence_refs: Sequence[str] = (),
        confidence: float | None = None,
        metadata: Mapping[str, object] | None = None,
        memory_id: str | None = None,
    ) -> MemoryRecord:
        raise NotImplementedError

    @abstractmethod
    def create_confirmed(
        self,
        *,
        subject_id: str,
        memory_type: MemoryType,
        content: str,
        source_type: EvidenceSourceType,
        confirmed_by_user: bool,
        evidence_refs: Sequence[str] = (),
        confidence: float | None = None,
        metadata: Mapping[str, object] | None = None,
        memory_id: str | None = None,
    ) -> MemoryRecord:
        raise NotImplementedError

    @abstractmethod
    def get(self, subject_id: str, memory_id: str) -> MemoryRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_active(
        self,
        subject_id: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
        metadata_filters: Mapping[str, object] | None = None,
    ) -> list[MemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_history(
        self,
        subject_id: str,
        *,
        statuses: Sequence[MemoryStatus] | None = None,
        memory_types: Sequence[MemoryType] | None = None,
        metadata_filters: Mapping[str, object] | None = None,
    ) -> list[MemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    def confirm(
        self, subject_id: str, memory_id: str, *, confirmed_by_user: bool
    ) -> MemoryRecord:
        raise NotImplementedError

    @abstractmethod
    def supersede(
        self,
        subject_id: str,
        memory_id: str,
        *,
        content: str,
        source_type: EvidenceSourceType,
        confirmed_by_user: bool,
        evidence_refs: Sequence[str] = (),
        confidence: float | None = None,
        metadata: Mapping[str, object] | None = None,
        new_memory_id: str | None = None,
    ) -> MemoryRecord:
        raise NotImplementedError

    @abstractmethod
    def archive(self, subject_id: str, memory_id: str) -> MemoryRecord:
        raise NotImplementedError
