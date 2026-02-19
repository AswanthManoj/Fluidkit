from typing import List, Any
from contextvars import ContextVar
from fluidkit.types import RequestEvent
from fluidkit.models import MutationType, MutationEntry


_current_request: ContextVar['RequestEvent'] = ContextVar('fluidkit_request')
_current_context: ContextVar['FluidKitContext'] = ContextVar('fluidkit_context')


class FluidKitContext:
    def __init__(self):
        self.mutations: List[MutationEntry] = []
    
    def add_refresh(self, key: str, args: dict, data: Any):
        self.mutations.append(MutationEntry(
            key=key,
            args=args,
            data=data,
            mutation_type=MutationType.REFRESH
        ))
    
    def add_set(self, key: str, args: dict, data: Any):
        self.mutations.append(MutationEntry(
            key=key,
            args=args,
            data=data,
            mutation_type=MutationType.SET
        ))

def get_context() -> FluidKitContext:
    try:
        return _current_context.get()
    except LookupError:
        raise RuntimeError("No FluidKitContext found. Must call set_context() first.")

def set_context(ctx: FluidKitContext):
    return _current_context.set(ctx)

def reset_context(token):
    _current_context.reset(token)



def get_request_event() -> RequestEvent:
    try:
        return _current_request.get()
    except LookupError:
        raise RuntimeError("No request context. Call only inside remote functions.")
    
def set_request_event(event: RequestEvent):
    return _current_request.set(event)

def reset_request_event(token):
    _current_request.reset(token)
