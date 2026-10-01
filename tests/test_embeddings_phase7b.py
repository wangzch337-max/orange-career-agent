"""Embedding provider contracts remain local, deterministic and offline-first."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from memory.embeddings import (
    DEFAULT_LOCAL_MODEL_DIMENSION,
    DEFAULT_LOCAL_MODEL_ID,
    EmbeddingProvider,
    EmbeddingPurpose,
    FakeEmbeddingProvider,
    LocalEmbeddingProvider,
)


def test_embedding_provider_is_an_explicit_abstraction() -> None:
    assert inspect.isabstract(EmbeddingProvider)
    with pytest.raises(TypeError):
        EmbeddingProvider()


def test_fake_embedding_is_stable_across_instances() -> None:
    first = FakeEmbeddingProvider(dimension=32).embed_text("AI APIs and testing")
    second = FakeEmbeddingProvider(dimension=32).embed_text("AI APIs and testing")
    assert first == second
    assert first.dimension == len(first.values) == 32
    assert first.provider_name == "fake_local"
    assert abs(sum(value * value for value in first.values) - 1.0) < 1e-6


def test_fake_embedding_changes_for_different_text_and_batches() -> None:
    provider = FakeEmbeddingProvider()
    batch = provider.embed_batch(("first text", "second text"))
    assert len(batch) == 2
    assert batch[0].values != batch[1].values
    assert provider.embed_query("first text") == batch[0]


def test_fake_embedding_uses_sha256_not_runtime_hash() -> None:
    source = inspect.getsource(FakeEmbeddingProvider)
    assert "hashlib.sha256" in source
    assert "hash(" not in source


def test_embedding_provider_rejects_empty_input() -> None:
    provider = FakeEmbeddingProvider()
    with pytest.raises(ValueError):
        provider.embed_batch(())
    with pytest.raises(ValueError):
        provider.embed_text("   ")


def test_local_provider_is_lazy_offline_and_explicitly_identified() -> None:
    provider = LocalEmbeddingProvider()
    assert provider.model_id == DEFAULT_LOCAL_MODEL_ID
    assert provider.dimension == DEFAULT_LOCAL_MODEL_DIMENSION == 384
    assert provider.provider_name == "fastembed_local"
    assert provider.allow_download is False
    assert provider._model is None


def test_local_provider_encapsulates_query_and_passage_paths(monkeypatch) -> None:
    calls: list[str] = []

    class StubModel:
        def query_embed(self, texts, **kwargs):
            calls.append("query")
            return iter(np.ones((len(tuple(texts)), 3), dtype=np.float32))

        def passage_embed(self, texts, **kwargs):
            calls.append("passage")
            return iter(np.full((len(tuple(texts)), 3), 0.5, dtype=np.float32))

    provider = LocalEmbeddingProvider(model_id="synthetic", dimension=3)
    monkeypatch.setattr(provider, "_load_model", lambda: StubModel())
    query = provider.embed_batch(("q",), purpose=EmbeddingPurpose.QUERY)
    passage = provider.embed_batch(("p",), purpose=EmbeddingPurpose.PASSAGE)
    assert calls == ["query", "passage"]
    assert query[0].values == [1.0, 1.0, 1.0]
    assert passage[0].values == [0.5, 0.5, 0.5]


def test_memory_embedding_layer_defines_no_cloud_provider() -> None:
    import memory.embeddings as module

    class_names = {
        name
        for name, value in vars(module).items()
        if inspect.isclass(value) and value.__module__ == module.__name__
    }
    assert not any(
        cloud in name.casefold()
        for name in class_names
        for cloud in ("qwen", "openai", "alibaba", "cloud")
    )
