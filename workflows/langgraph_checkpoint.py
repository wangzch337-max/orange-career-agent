"""Checkpoint factories for ephemeral tests and private local persistence."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_CHECKPOINT_PATH = (
    PROJECT_ROOT / "data" / "private" / "runtime" / "orange_workflow.sqlite3"
)


def create_memory_checkpointer() -> InMemorySaver:
    return InMemorySaver()


@contextmanager
def sqlite_checkpointer(
    path: Path = DEFAULT_SQLITE_CHECKPOINT_PATH,
) -> Iterator[SqliteSaver]:
    """Open and close the lightweight local SQLite saver cleanly."""

    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(resolved)) as saver:
        yield saver
