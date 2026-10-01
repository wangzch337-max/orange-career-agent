"""Public synthetic semantic-memory Demo; local and private-data free."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from data.models import EvidenceSourceType
from memory.embeddings import FakeEmbeddingProvider, LocalEmbeddingProvider
from memory.models import MemoryType, new_subject_id
from memory.service import build_semantic_memory_service


def _rank_rows(results) -> list[dict[str, object]]:
    return [
        {
            "memory_id": result.memory.memory_id,
            "content": result.memory.content,
            "lexical_rank": getattr(result, "lexical_rank", None),
            "semantic_rank": getattr(result, "semantic_rank", None),
            "fusion_rank": getattr(result, "fusion_rank", None),
        }
        for result in results
    ]


def run_public_semantic_demo(*, use_local_model: bool = False) -> dict[str, object]:
    provider = (
        LocalEmbeddingProvider(allow_download=False)
        if use_local_model
        else FakeEmbeddingProvider()
    )
    with TemporaryDirectory(prefix="orange_semantic_memory_demo_") as directory:
        root = Path(directory)
        service = build_semantic_memory_service(
            memory_path=root / "orange_memory.sqlite3",
            vector_path=root / "orange_vectors.sqlite3",
            embedding_provider=provider,
        )
        subject_id = new_subject_id()
        documentation = service.create_confirmed(
            subject_id=subject_id,
            memory_type=MemoryType.USER_FEEDBACK,
            content="I am comfortable with documentation-heavy work.",
            source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
            confirmed_by_user=True,
        )
        service.create_confirmed(
            subject_id=subject_id,
            memory_type=MemoryType.PROJECT_EVIDENCE,
            content="I prefer implementing APIs.",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
            confirmed_by_user=True,
        )
        service.create_confirmed(
            subject_id=subject_id,
            memory_type=MemoryType.PROJECT_EVIDENCE,
            content="I enjoy analyzing datasets.",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
            confirmed_by_user=True,
        )
        service.create_confirmed(
            subject_id=subject_id,
            memory_type=MemoryType.PROJECT_EVIDENCE,
            content="I enjoy building LLM applications and integrating APIs.",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
            confirmed_by_user=True,
        )
        chinese = service.create_confirmed(
            subject_id=subject_id,
            memory_type=MemoryType.CAREER_PREFERENCE,
            content="我喜欢梳理产品需求并撰写清晰文档。",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
            confirmed_by_user=True,
        )
        old_preference = service.create_confirmed(
            subject_id=subject_id,
            memory_type=MemoryType.CAREER_PREFERENCE,
            content="I primarily want Data Analyst roles.",
            source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
            confirmed_by_user=True,
        )
        service.supersede(
            subject_id,
            old_preference.memory_id,
            content="I currently want to prioritize AI Application roles.",
            source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
            confirmed_by_user=True,
        )

        query = "我不排斥需要经常写产品文档的岗位"
        lexical = service.retrieve(subject_id, query)
        semantic = service.retrieve_semantic(subject_id, query, top_k=5)
        hybrid = service.retrieve_hybrid(subject_id, query, top_k=5)

        # Deliberately bypass service synchronization to prove canonical
        # revalidation filters a stale derived vector.
        service.memory_store.archive(subject_id, documentation.memory_id)
        after_stale_archive = service.retrieve_semantic(subject_id, query, top_k=5)
        rebuild = service.rebuild_subject_index(subject_id)
        after_rebuild = service.retrieve_semantic(
            subject_id,
            "I enjoy clarifying product requirements and writing documents",
            top_k=5,
        )
        vector_count_before_purge = service.vector_index.count_subject(subject_id)
        purge = service.purge_subject(subject_id)

        return {
            "provider": provider.provider_name,
            "model_id": provider.model_id,
            "dimension": provider.dimension,
            "subject_id": subject_id,
            "lexical": _rank_rows(lexical),
            "semantic": _rank_rows(semantic),
            "hybrid": _rank_rows(hybrid),
            "documentation_memory_prominent": bool(semantic)
            and semantic[0].memory.memory_id == documentation.memory_id,
            "chinese_memory_id": chinese.memory_id,
            "superseded_memory_excluded": old_preference.memory_id
            not in {item.memory.memory_id for item in hybrid},
            "stale_archived_filtered": documentation.memory_id
            not in {item.memory.memory_id for item in after_stale_archive},
            "rebuild": rebuild.model_dump(mode="json"),
            "english_query_results_after_rebuild": _rank_rows(after_rebuild),
            "vector_count_before_purge": vector_count_before_purge,
            "purged_memory_records": purge.memory_records_deleted,
            "purged_vector_records": purge.vector_records_deleted,
            "canonical_after_purge": len(service.memory_store.list_history(subject_id)),
            "vectors_after_purge": service.vector_index.count_subject(subject_id),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-model",
        action="store_true",
        help="Use the already-cached local multilingual model; never downloads.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run_public_semantic_demo(use_local_model=args.local_model),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
