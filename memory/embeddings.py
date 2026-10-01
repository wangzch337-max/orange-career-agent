"""Local embedding contracts; no cloud provider is permitted in Memory."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence

from memory.errors import EmbeddingProviderError
from memory.models import EmbeddingVector
from observability.instrumentation import observe
from observability.models import DiagnosticComponent as DC


DEFAULT_LOCAL_MODEL_ID = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
DEFAULT_LOCAL_MODEL_DIMENSION = 384
DEFAULT_LOCAL_MODEL_CACHE = Path.home() / ".cache" / "orange" / "fastembed"


class EmbeddingPurpose(str, Enum):
    QUERY = "query"
    PASSAGE = "passage"


class EmbeddingProvider(ABC):
    """Provider-neutral local embedding boundary."""

    provider_name: str
    model_id: str
    dimension: int
    normalization_version: str

    @abstractmethod
    def embed_batch(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose = EmbeddingPurpose.PASSAGE,
    ) -> list[EmbeddingVector]:
        raise NotImplementedError

    def embed_text(
        self,
        text: str,
        *,
        purpose: EmbeddingPurpose = EmbeddingPurpose.PASSAGE,
    ) -> EmbeddingVector:
        return self.embed_batch((text,), purpose=purpose)[0]

    def embed_query(self, text: str) -> EmbeddingVector:
        return self.embed_text(text, purpose=EmbeddingPurpose.QUERY)

    def embed_passages(self, texts: Sequence[str]) -> list[EmbeddingVector]:
        return self.embed_batch(texts, purpose=EmbeddingPurpose.PASSAGE)

    def _vector(self, values: Iterable[float]) -> EmbeddingVector:
        return EmbeddingVector(
            values=[float(value) for value in values],
            provider_name=self.provider_name,
            model_id=self.model_id,
            dimension=self.dimension,
            normalization_version=self.normalization_version,
        )

    @staticmethod
    def _validate_texts(texts: Sequence[str]) -> tuple[str, ...]:
        values = tuple(texts)
        if not values or any(not isinstance(text, str) or not text.strip() for text in values):
            raise ValueError("Embedding input must contain non-empty text.")
        return values


class FakeEmbeddingProvider(EmbeddingProvider):
    """Stable SHA-256 projection used by offline tests, not a quality model."""

    provider_name = "fake_local"
    model_id = "stable-sha256-projection-v1"
    normalization_version = "unicode-nfkc-token-l2-v1"

    def __init__(self, *, dimension: int = 48) -> None:
        if dimension < 8:
            raise ValueError("Fake embedding dimension must be at least 8.")
        self.dimension = dimension

    @observe(DC.EMBEDDING, "embedding_batch")
    def embed_batch(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose = EmbeddingPurpose.PASSAGE,
    ) -> list[EmbeddingVector]:
        del purpose  # Fake architecture tests do not simulate model conventions.
        return [self._vector(self._project(text)) for text in self._validate_texts(texts)]

    def _project(self, text: str) -> list[float]:
        normalized = unicodedata.normalize("NFKC", text).casefold().strip()
        tokens = re.findall(r"\w+", normalized, flags=re.UNICODE)
        features = tokens or [normalized]
        vector = [0.0] * self.dimension
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            for offset in range(0, len(digest), 4):
                chunk = digest[offset : offset + 4]
                index = int.from_bytes(chunk[:2], "big") % self.dimension
                sign = 1.0 if chunk[2] & 1 else -1.0
                magnitude = 1.0 + (chunk[3] / 255.0)
                vector[index] += sign * magnitude
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            vector[0] = 1.0
            norm = 1.0
        return [value / norm for value in vector]


class LocalEmbeddingProvider(EmbeddingProvider):
    """FastEmbed CPU adapter with explicit offline-by-default model loading."""

    provider_name = "fastembed_local"
    normalization_version = "fastembed-model-normalization-v1"

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_LOCAL_MODEL_ID,
        dimension: int = DEFAULT_LOCAL_MODEL_DIMENSION,
        cache_dir: str | Path | None = None,
        allow_download: bool = False,
        batch_size: int = 32,
    ) -> None:
        if dimension < 1 or batch_size < 1:
            raise ValueError("Embedding dimension and batch size must be positive.")
        self.model_id = model_id
        self.dimension = dimension
        self.cache_dir = str(cache_dir or DEFAULT_LOCAL_MODEL_CACHE)
        self.allow_download = allow_download
        self.batch_size = batch_size
        self._model: object | None = None

    @observe(DC.EMBEDDING, "embedding_batch")
    def embed_batch(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose = EmbeddingPurpose.PASSAGE,
    ) -> list[EmbeddingVector]:
        values = self._validate_texts(texts)
        model = self._load_model()
        try:
            if purpose == EmbeddingPurpose.QUERY:
                generated = model.query_embed(values, batch_size=self.batch_size)
            else:
                generated = model.passage_embed(values, batch_size=self.batch_size)
            vectors = [self._vector(vector.tolist()) for vector in generated]
        except Exception as exc:
            raise EmbeddingProviderError("Local embedding inference failed.") from exc
        if len(vectors) != len(values):
            raise EmbeddingProviderError("Local embedding batch returned an invalid count.")
        return vectors

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            import onnxruntime
            from fastembed import TextEmbedding

            onnxruntime.disable_telemetry_events()
            metadata = {
                item["model"]: item for item in TextEmbedding.list_supported_models()
            }.get(self.model_id)
            if metadata is None:
                raise EmbeddingProviderError("The selected local model is not supported.")
            if int(metadata["dim"]) != self.dimension:
                raise EmbeddingProviderError(
                    "Configured dimension does not match local model metadata."
                )
            self._model = TextEmbedding(
                model_name=self.model_id,
                cache_dir=self.cache_dir,
                providers=("CPUExecutionProvider",),
                local_files_only=not self.allow_download,
            )
        except EmbeddingProviderError:
            raise
        except Exception as exc:
            mode = "download-enabled" if self.allow_download else "offline cache-only"
            raise EmbeddingProviderError(
                f"Local embedding model failed to load in {mode} mode."
            ) from exc
        return self._model
