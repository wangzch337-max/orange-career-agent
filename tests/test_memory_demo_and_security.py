"""Public Demo, filesystem boundary and prohibited-capability tests."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from data.models import EvidenceSourceType
from memory.base import MemoryStore, StructuredProfileStore
from memory.demo import run_public_demo
from memory.models import MemoryType
from memory.retriever import MemoryRetriever
from memory.service import MemoryService, build_sqlite_memory_service
from memory.sqlite_store import DEFAULT_MEMORY_DATABASE_PATH
from workflows.langgraph_checkpoint import DEFAULT_SQLITE_CHECKPOINT_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_memory_database_is_separate_private_ignored_path() -> None:
    assert DEFAULT_MEMORY_DATABASE_PATH != DEFAULT_SQLITE_CHECKPOINT_PATH
    assert DEFAULT_MEMORY_DATABASE_PATH.relative_to(PROJECT_ROOT).as_posix() == (
        "data/private/memory/orange_memory.sqlite3"
    )
    assert subprocess.run(
        ["git", "check-ignore", "-q", "data/private/memory/orange_memory.sqlite3"],
        cwd=PROJECT_ROOT,
        check=False,
    ).returncode == 0


def test_public_demo_completes_full_synthetic_memory_lifecycle() -> None:
    result = run_public_demo()
    assert result["subject_id"].startswith("subject_")
    assert result["profile_created"] is True
    assert result["candidate_excluded_before_confirmation"] is True
    assert result["candidate_confirmed"] == "confirmed"
    assert result["lexical_result_ids"]
    assert result["old_preference_active"] is False
    assert result["new_preference_active"] is True
    assert result["history_contains_superseded"] is True
    assert result["archived_excluded"] is True
    assert result["current_profile_after_purge"] is None
    assert result["active_memory_after_purge"] == 0
    assert result["history_after_purge"] == 0


def test_default_public_demo_does_not_create_private_memory_database(tmp_path, monkeypatch) -> None:
    private_path = tmp_path / "should_not_exist.sqlite3"
    monkeypatch.setattr("memory.demo.DEFAULT_MEMORY_DATABASE_PATH", private_path)
    run_public_demo()
    assert not private_path.exists()


def test_memory_code_has_no_vector_embedding_qwen_or_network_imports() -> None:
    forbidden_roots = {
        "chromadb",
        "faiss",
        "pinecone",
        "weaviate",
        "qdrant_client",
        "pymilvus",
        "sentence_transformers",
        "sqlite_vec",
        "openai",
        "httpx",
        "requests",
        "socket",
    }
    imported_roots = set()
    for path in (PROJECT_ROOT / "memory").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
    assert imported_roots.isdisjoint(forbidden_roots)


def test_agents_contain_no_sql_or_memory_database_access() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "agents").rglob("*.py")
    ).casefold()
    assert "sqlite3" not in combined
    assert "select * from" not in combined
    assert "orange_memory.sqlite3" not in combined


def test_memory_demo_never_references_private_golden_case() -> None:
    source = (PROJECT_ROOT / "memory" / "demo.py").read_text(encoding="utf-8")
    assert "golden_case" not in source
    assert "data/private" not in source


def test_memory_service_coordinates_abstract_boundaries_and_safe_events(tmp_path) -> None:
    service = build_sqlite_memory_service(tmp_path / "memory.sqlite3")
    assert isinstance(service, MemoryService)
    assert isinstance(service.profile_store, StructuredProfileStore)
    assert isinstance(service.memory_store, MemoryStore)
    assert isinstance(service.retriever, MemoryRetriever)

    private_marker = "PRIVATE_RAW_MEMORY_CONTENT_MUST_NOT_BE_LOGGED"
    record = service.create_candidate(
        subject_id="subject_events001",
        memory_type=MemoryType.CAREER_INSIGHT,
        content=private_marker,
        source_type=EvidenceSourceType.MODEL_INFERENCE,
        confidence=0.99,
    )
    event_payload = service.events[-1].model_dump_json()
    assert record.status.value == "candidate"
    assert private_marker not in event_payload
    assert record.memory_id in event_payload
    assert "career_insight" in event_payload
