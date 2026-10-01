"""Explicit offline validation for the cached public multilingual model."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from data.models import EvidenceSourceType
from memory.embeddings import LocalEmbeddingProvider
from memory.models import MemoryType
from memory.service import build_semantic_memory_service


def run_local_embedding_validation() -> dict[str, object]:
    provider = LocalEmbeddingProvider(allow_download=False, batch_size=8)
    load_started = perf_counter()
    provider.embed_query("public synthetic model load check")
    load_ms = round((perf_counter() - load_started) * 1000, 2)

    single_started = perf_counter()
    provider.embed_query("我喜欢把大模型能力做进实际软件系统")
    single_query_ms = round((perf_counter() - single_started) * 1000, 2)

    batch_started = perf_counter()
    provider.embed_passages(
        (
            "I am comfortable with documentation-heavy work.",
            "我喜欢梳理产品需求并撰写清晰文档。",
            "I enjoy building LLM applications and integrating APIs.",
            "I prefer implementing APIs.",
            "I enjoy analyzing datasets.",
        )
    )
    batch_ms = round((perf_counter() - batch_started) * 1000, 2)

    with TemporaryDirectory(prefix="orange_local_embedding_validation_") as directory:
        root = Path(directory)
        service = build_semantic_memory_service(
            memory_path=root / "canonical.sqlite3",
            vector_path=root / "vectors.sqlite3",
            embedding_provider=provider,
        )
        labels_by_id: dict[str, str] = {}

        def add(label: str, content: str, memory_type: MemoryType) -> None:
            record = service.create_confirmed(
                subject_id="subject_public_multilingual",
                memory_type=memory_type,
                content=content,
                source_type=EvidenceSourceType.SYSTEM_FIXTURE,
                confirmed_by_user=True,
            )
            labels_by_id[record.memory_id] = label

        add(
            "english_documentation",
            "I am comfortable with documentation-heavy work.",
            MemoryType.USER_FEEDBACK,
        )
        add(
            "chinese_requirements",
            "我喜欢梳理产品需求并撰写清晰文档。",
            MemoryType.CAREER_PREFERENCE,
        )
        add(
            "mixed_llm_api",
            "I enjoy building LLM applications and integrating APIs.",
            MemoryType.PROJECT_EVIDENCE,
        )
        add(
            "api_distractor",
            "I prefer implementing APIs.",
            MemoryType.PROJECT_EVIDENCE,
        )
        add(
            "dataset_distractor",
            "I enjoy analyzing datasets.",
            MemoryType.PROJECT_EVIDENCE,
        )

        def labels(results) -> list[str]:
            return [labels_by_id[item.memory.memory_id] for item in results]

        english_to_chinese = service.retrieve_semantic(
            "subject_public_multilingual",
            "我不排斥需要经常写产品文档的岗位",
            top_k=5,
        )
        chinese_to_english = service.retrieve_semantic(
            "subject_public_multilingual",
            "I enjoy clarifying product requirements and writing clear documents",
            top_k=5,
        )
        mixed = service.retrieve_semantic(
            "subject_public_multilingual",
            "我喜欢把大模型能力做进实际软件系统",
            top_k=5,
        )
        hybrid = service.retrieve_hybrid(
            "subject_public_multilingual",
            "我不排斥需要经常写产品文档的岗位",
            top_k=5,
        )

    english_labels = labels(english_to_chinese)
    chinese_labels = labels(chinese_to_english)
    mixed_labels = labels(mixed)
    hybrid_labels = labels(hybrid)
    return {
        "provider": provider.provider_name,
        "model_id": provider.model_id,
        "dimension": provider.dimension,
        "license": "Apache-2.0",
        "source": "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q",
        "documented_size_gb": 0.22,
        "load_ms": load_ms,
        "single_query_ms": single_query_ms,
        "batch_ms": batch_ms,
        "english_memory_to_chinese_query": english_labels,
        "chinese_memory_to_english_query": chinese_labels,
        "mixed_technical_query": mixed_labels,
        "hybrid_query": hybrid_labels,
        # A same-topic Chinese memory is intentionally present; top-three is the
        # rank-based acceptance window for the English target, not a score cutoff.
        "english_to_chinese_passed": "english_documentation" in english_labels[:3],
        "chinese_to_english_passed": bool(chinese_labels)
        and chinese_labels[0] == "chinese_requirements",
        "mixed_language_passed": bool(mixed_labels)
        and mixed_labels[0] == "mixed_llm_api",
        "hybrid_contains_documentation": "english_documentation" in hybrid_labels[:3],
    }


def main() -> None:
    print(json.dumps(run_local_embedding_validation(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
