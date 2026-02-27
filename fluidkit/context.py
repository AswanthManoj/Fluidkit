from typing import List, Any
from contextvars import ContextVar
from fluidkit.models import MutationType, MutationEntry


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
        self.mutations: List[MutationEntry] = []

    def add_mutation(self, mutation_type: MutationType, key: str, args: dict, data: Any):
        self.mutations.append(MutationEntry(
            key=key,
            args=args,
            data=data,
            mutation_type=mutation_type,
        ))


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

get_request_event = _current_request.get
set_request_event = _current_request.set
reset_request_event = _current_request.reset
