"""Fail-closed offline guards for this single-threaded local evaluation process.

These are accident/contract guards, not a security sandbox for hostile native code.
Every blocked attempt is latched even if the scenario catches the exception.
"""

import builtins
import io
import os
import socket
import sqlite3
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from evaluation.taxonomy import FailureTaxonomy


class EvaluationBoundaryError(RuntimeError):
    def __init__(self, category: FailureTaxonomy):
        self.category = category
        super().__init__(category.value)  # never include a URL, path or credential


class OfflineBoundary:
    def __init__(self, temporary_root: Path):
        self.temporary_root = temporary_root.resolve()
        self.attempts: list[FailureTaxonomy] = []
        self.stack = ExitStack()

    def deny(self, category):
        self.attempts.append(category)
        raise EvaluationBoundaryError(category)

    def check_path(self, name, *, database=False):
        if isinstance(name, int):
            return
        try:
            original = Path(os.fsdecode(name))
            if database and str(name).startswith("file:"):
                self.deny(FailureTaxonomy.PRIVATE_DATA_BOUNDARY_VIOLATION)
            path = original.resolve()
        except (TypeError, ValueError):
            return
        parts = path.parts
        private = any(parts[index:index + 2] == ("data", "private") for index in range(len(parts) - 1))
        env = any(p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example")
                  for p in (original, path))
        model = path.suffix in {".onnx", ".safetensors", ".pt", ".pth"}
        db = database or path.suffix in {".db", ".sqlite", ".sqlite3"}
        if private or env or model or (db and not path.is_relative_to(self.temporary_root)):
            self.deny(FailureTaxonomy.PRIVATE_DATA_BOUNDARY_VIOLATION)

    def __enter__(self):
        def blocked(*args, **kwargs):
            self.deny(FailureTaxonomy.NETWORK_BOUNDARY_VIOLATION)

        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection",
                       "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex",
                       "socket.socket.sendto", "socket.socket.send", "socket.socket.sendall",
                       "subprocess.Popen", "os.system"):
            self.stack.enter_context(patch(target, blocked))
        for module, attr in ((builtins, "open"), (io, "open"), (os, "open")):
            original = getattr(module, attr)
            def guarded(name, *args, _original=original, **kwargs):
                self.check_path(name)
                return _original(name, *args, **kwargs)
            self.stack.enter_context(patch.object(module, attr, guarded))
        import pysqlite3
        for module in (sqlite3, pysqlite3):
            original = module.connect
            def guarded_db(name, *args, _original=original, **kwargs):
                if str(name) != ":memory:":
                    self.check_path(name, database=True)
                return _original(name, *args, **kwargs)
            self.stack.enter_context(patch.object(module, "connect", guarded_db))
        # Production imports are allowed; constructing live providers/model loaders is not.
        from providers import qwen
        from memory.embeddings import LocalEmbeddingProvider
        self.stack.enter_context(patch.object(qwen.QwenProvider, "__init__", blocked))
        self.stack.enter_context(patch.object(LocalEmbeddingProvider, "__init__", blocked))
        # The existing adapter remains the only owner/importer of the transport SDK.
        self.stack.enter_context(patch.object(qwen.openai.OpenAI, "__init__", blocked))
        self.stack.enter_context(patch.object(qwen.openai.AsyncOpenAI, "__init__", blocked))
        self.stack.enter_context(patch.object(tempfile, "tempdir", str(self.temporary_root)))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)
