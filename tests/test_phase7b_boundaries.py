"""Phase 7B privacy, dependency and integration-boundary regression tests."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from data.models import EvidenceSourceType
from memory.embeddings import FakeEmbeddingProvider
from memory.errors import VectorIndexError
from memory.models import MemoryType
from memory.service import build_semantic_memory_service


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_vector_database_is_git_ignored_and_untracked() -> None:
    relative = "data/private/memory/orange_vectors.sqlite3"
    assert subprocess.run(
        ["git", "check-ignore", "-q", relative],
        cwd=PROJECT_ROOT,
        check=False,
    ).returncode == 0
    assert relative not in subprocess.check_output(
        ["git", "ls-files"], cwd=PROJECT_ROOT, text=True
    ).splitlines()


def test_phase7b_dependencies_exclude_remote_vector_databases() -> None:
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "pysqlite3==0.6.0" in requirements
    assert "fastembed==0.8.0" in requirements
    assert all(
        name not in requirements.casefold()
        for name in ("chromadb", "faiss", "qdrant", "pinecone", "weaviate", "milvus")
    )


def test_only_vector_index_imports_pysqlite_and_sqlite_vec() -> None:
    importers: dict[str, set[str]] = {}
    for path in (PROJECT_ROOT / "memory").glob("*.py"):
        roots: set[str] = set()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        importers[path.name] = roots
    assert {name for name, roots in importers.items() if "pysqlite3" in roots} == {
        "vector_index.py"
    }
    assert {name for name, roots in importers.items() if "sqlite_vec" in roots} == {
        "vector_index.py"
    }


def test_confirmed_feedback_is_indexed_but_candidate_feedback_is_not(tmp_path) -> None:
    service = build_semantic_memory_service(
        memory_path=tmp_path / "canonical.sqlite3",
        vector_path=tmp_path / "vectors.sqlite3",
        embedding_provider=FakeEmbeddingProvider(),
    )
    candidate = service.record_user_feedback(
        "subject_a", "Session-like unconfirmed feedback", confirmed_by_user=False
    )
    confirmed = service.record_user_feedback(
        "subject_a", "Explicit confirmed feedback", confirmed_by_user=True
    )
    assert service.vector_index.metadata_for(candidate.memory_id) is None
    assert service.vector_index.metadata_for(confirmed.memory_id) is not None


def test_vector_purge_failure_never_preserves_canonical_data(
    tmp_path, monkeypatch
) -> None:
    service = build_semantic_memory_service(
        memory_path=tmp_path / "canonical.sqlite3",
        vector_path=tmp_path / "vectors.sqlite3",
        embedding_provider=FakeEmbeddingProvider(),
    )
    record = service.create_confirmed(
        subject_id="subject_a",
        memory_type=MemoryType.GOAL,
        content="Synthetic purge failure memory",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )

    def fail(_subject_id):
        raise VectorIndexError("synthetic vector cleanup failure")

    monkeypatch.setattr(service.vector_index, "purge_subject", fail)
    result = service.purge_subject("subject_a")
    assert result.memory_records_deleted == 1
    assert result.vector_cleanup_required is True
    assert service.memory_store.get("subject_a", record.memory_id) is None
    assert service.vector_sync_diagnostics[-1].cleanup_required is True


def test_semantic_modules_do_not_reference_profile_job_match_action_or_transcript() -> None:
    combined = "\n".join(
        (PROJECT_ROOT / "memory" / name).read_text(encoding="utf-8")
        for name in ("embeddings.py", "vector_index.py", "semantic.py", "context.py")
    )
    for forbidden in (
        "StructuredProfileStore",
        "JobRecord",
        "MatchResult",
        "ActionItem",
        "chat transcript",
        "conversation log",
    ):
        assert forbidden not in combined


def test_real_model_validation_is_explicit_not_collected_by_pytest() -> None:
    path = PROJECT_ROOT / "memory" / "local_embedding_validation.py"
    assert path.is_file()
    source = path.read_text(encoding="utf-8")
    assert "LocalEmbeddingProvider(allow_download=False" in source
    assert not (PROJECT_ROOT / "tests" / "test_local_embedding_validation.py").exists()
