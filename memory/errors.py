"""Credential- and payload-safe Phase 7A memory exceptions."""


class MemoryLayerError(RuntimeError):
    """Base error for curated long-term memory operations."""


class MemoryNotFoundError(MemoryLayerError):
    pass


class MemoryConflictError(MemoryLayerError):
    pass


class InvalidMemoryTransitionError(MemoryLayerError):
    pass


class ProfileVersionConflictError(MemoryLayerError):
    pass


class CorruptStoredProfileError(MemoryLayerError):
    pass


class MemoryStoreError(MemoryLayerError):
    pass


class EmbeddingProviderError(MemoryLayerError):
    """Local embedding initialization or inference failed safely."""


class VectorIndexError(MemoryLayerError):
    """Derived vector index operation failed without changing authority."""


class VectorIndexConfigurationError(VectorIndexError):
    """Stored derived-index identity does not match the active provider."""
