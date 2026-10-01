"""Scoped context propagation, restored on exit; no global collector instance."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from observability.models import ObservabilityContext


@dataclass(frozen=True)
class DiagnosticBinding:
    context: ObservabilityContext
    collector: object


_binding = ContextVar("orange_diagnostic_binding", default=None)


def current_binding():
    return _binding.get()


@contextmanager
def diagnostic_scope(collector, context):
    token = _binding.set(DiagnosticBinding(context, collector))
    try:
        yield
    finally:
        _binding.reset(token)
