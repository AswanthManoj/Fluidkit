from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from fluidkit.models import MutationEntry, MutationType

if TYPE_CHECKING:
    from fluidkit.types import RequestEvent


class _ContextAccessor:
    """Thin wrapper over ContextVar with a descriptive error on missing get()."""

    __slots__ = ("_var", "_error_msg")

    def __init__(self, name: str, error_msg: str):
        self._var = ContextVar(name)
        self._error_msg = error_msg

    def get(self):
        try:
            return self._var.get()
        except LookupError:
            raise RuntimeError(self._error_msg)

    def set(self, value):
        return self._var.set(value)

    def reset(self, token):
        self._var.reset(token)


class FluidKitContext:
    def __init__(self):
        self.mutations: list[MutationEntry] = []

    def add_mutation(self, mutation_type: MutationType, key: str, args: dict, data: Any):
        self.mutations.append(
            MutationEntry(
                key=key,
                args=args,
                data=data,
                mutation_type=mutation_type,
            )
        )


_current_context = _ContextAccessor(
    "fluidkit_context",
    "No FluidKitContext found. Must call set_context() first.",
)
_current_request = _ContextAccessor(
    "fluidkit_request",
    "No request context. Call only inside remote functions.",
)


get_context = _current_context.get
set_context = _current_context.set
reset_context = _current_context.reset

set_request_event = _current_request.set
reset_request_event = _current_request.reset


def get_request_event() -> RequestEvent:
    """Get the current RequestEvent. Available inside all remote function handlers."""
    return _current_request.get()
