"""Public synthetic Phase 7A memory lifecycle Demo; always offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from data.models import EvidenceSourceType, UserProfile
from memory.models import MemoryType, new_subject_id
from memory.service import build_sqlite_memory_service
from memory.sqlite_store import DEFAULT_MEMORY_DATABASE_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PROFILE_PATH = PROJECT_ROOT / "data" / "fixtures" / "public_confirmed_profile.json"


def load_public_confirmed_profile() -> UserProfile:
    return UserProfile.model_validate_json(
        PUBLIC_PROFILE_PATH.read_text(encoding="utf-8")
    )


def run_demo(database_path: Path) -> dict[str, object]:
    service = build_sqlite_memory_service(database_path)
    subject_id = new_subject_id()
    profile = load_public_confirmed_profile()
    saved = service.save_confirmed_profile(subject_id, profile)
    current = service.get_current_confirmed_profile(subject_id)

    old_preference = service.create_confirmed(
        subject_id=subject_id,
        memory_type=MemoryType.CAREER_PREFERENCE,
        content="Primarily exploring data roles.",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
        metadata={"scope": "career_direction"},
    )
    candidate = service.create_candidate(
        subject_id=subject_id,
        memory_type=MemoryType.USER_FEEDBACK,
        content="I may be comfortable with documentation-heavy work.",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
        confidence=0.99,
        metadata={"topic": "documentation_work"},
    )
    active_before_confirmation = service.memory_store.list_active(subject_id)
    confirmed_candidate = service.confirm_candidate(
        subject_id,
        candidate.memory_id,
        confirmed_by_user=True,
    )
    retrieval_before_archive = service.retrieve(subject_id, "documentation work")
    new_preference = service.supersede(
        subject_id,
        old_preference.memory_id,
        content="Primarily exploring AI Application and AI Product roles.",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
        metadata={"scope": "career_direction"},
    )
    active_after_supersede = service.memory_store.list_active(subject_id)
    history_before_purge = service.memory_store.list_history(subject_id)
    archived = service.archive(subject_id, confirmed_candidate.memory_id)
    active_after_archive = service.memory_store.list_active(subject_id)
    purge = service.purge_subject(subject_id)

    return {
        "subject_id": subject_id,
        "schema_version": service.database.schema_version(),
        "profile_created": saved.created,
        "current_profile_version": current.version if current else None,
        "candidate_excluded_before_confirmation": candidate.memory_id
        not in {item.memory_id for item in active_before_confirmation},
        "candidate_confirmed": confirmed_candidate.status.value,
        "lexical_result_ids": [
            item.memory.memory_id for item in retrieval_before_archive
        ],
        "superseding_memory_id": new_preference.memory_id,
        "old_preference_active": old_preference.memory_id
        in {item.memory_id for item in active_after_supersede},
        "new_preference_active": new_preference.memory_id
        in {item.memory_id for item in active_after_supersede},
        "history_contains_superseded": old_preference.memory_id
        in {item.memory_id for item in history_before_purge},
        "archived_status": archived.status.value,
        "archived_excluded": archived.memory_id
        not in {item.memory_id for item in active_after_archive},
        "purged_profile_versions": purge.profile_versions_deleted,
        "purged_memory_records": purge.memory_records_deleted,
        "current_profile_after_purge": service.get_current_confirmed_profile(subject_id),
        "active_memory_after_purge": len(service.memory_store.list_active(subject_id)),
        "history_after_purge": len(service.memory_store.list_history(subject_id)),
        "safe_event_count": len(service.events),
    }


def run_public_demo(*, persistent_memory: bool = False) -> dict[str, object]:
    if persistent_memory:
        return run_demo(DEFAULT_MEMORY_DATABASE_PATH)
    with TemporaryDirectory(prefix="orange_memory_demo_") as directory:
        return run_demo(Path(directory) / "orange_memory.sqlite3")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--persistent-memory",
        action="store_true",
        help="Explicitly use the ignored private memory database instead of a temporary file.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run_public_demo(persistent_memory=args.persistent_memory),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
