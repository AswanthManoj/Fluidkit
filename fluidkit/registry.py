import inspect
import linecache
from fastapi import FastAPI
from fluidkit.models import FunctionMetadata
from typing import Dict, List, Callable, Optional
from fluidkit.utilities import generate_route_path


_preserved: dict[str, object] = {}


def preserve(value_or_factory):
    """
    Preserve a value across HMR module re-executions.

    Use this for expensive or stateful objects that should be initialized
    once and never recreated when the module is hot-reloaded — database
    connections, HTTP clients, loaded ML models, etc.

    Accepts either a direct value or a zero-argument factory callable.
    If a factory is provided, it is only called once regardless of how
    many times the module re-executes. If a direct value is provided,
    it is stored on first execution and the new value is silently
    discarded on subsequent reloads.

    The key is automatically derived from the calling module and variable
    name — no manual key management needed.

    Examples:
        ```python
        # Direct value — new instance created but discarded after first run
        client = preserve(httpx.Client())

        # Factory — never constructed more than once
        db = preserve(lambda: Database(url))
        model = preserve(lambda: load_model("weights.pt"))
        ```

    Note:
        Do not use preserve() for plain constants or variables you want
        to update during development. Those update automatically via HMR.
        preserve() is only for values that must survive re-execution.
    """
    frame = inspect.currentframe().f_back
    module = frame.f_globals.get("__name__", "__main__")
    
    try:
        line = linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip()
        var_name = line.split("=")[0].strip()
    except Exception:
        var_name = str(frame.f_lineno)

    key = f"{module}#{var_name}"

    if key not in _preserved:
        if callable(value_or_factory) and not isinstance(value_or_factory, type):
            _preserved[key] = value_or_factory()
        else:
            _preserved[key] = value_or_factory

    return _preserved[key]


class FluidKitRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self.dev = False
        self._initialized = True
        self.app = self._create_app()
        self._route_handlers: Dict[str, Callable] = {}
        self.functions: Dict[str, FunctionMetadata] = {}
        self._on_register_callback: Optional[Callable[[FunctionMetadata], None]] = None

    def _create_app(self) -> FastAPI:
        app = FastAPI(version="0.1.0", title="FluidKit Remote Functions")
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )
        return app

    def on_register(self, callback: Callable[[FunctionMetadata], None]):
        self._on_register_callback = callback

    def _fire_on_register(self, metadata: FunctionMetadata):
        if self._on_register_callback:
            self._on_register_callback(metadata)

    def register(self, metadata: FunctionMetadata, handler: Callable):
        key = f"{metadata.module}#{metadata.name}"

        if key in self.functions:
            old_path = generate_route_path(self.functions[key])
            self.app.router.routes = [
                r for r in self.app.router.routes
                if getattr(r, 'path', None) != old_path
            ]
            self.app.openapi_schema = None

        self.functions[key] = metadata
        self._route_handlers[key] = handler
        self._register_route(metadata, handler)
        if self._on_register_callback:
            self._fire_on_register(metadata)


    def _register_route(self, metadata: FunctionMetadata, handler: Callable):
        from fluidkit.utilities import generate_route_path
        path = generate_route_path(metadata)
        self.app.add_api_route(
            path,
            handler,
            methods=["POST"],
            response_model=None,
            name=f"{metadata.decorator_type.value}_{metadata.name}"
        )
        self.app.openapi_schema = None

    
    def get(self, module: str, name: str) -> FunctionMetadata | None:
        return self.functions.get(f"{module}#{name}")
    
    def get_by_file(self, file_path: str) -> List[FunctionMetadata]:
        return [m for m in self.functions.values() if m.file_path == file_path]
    
    def unregister(self, module: str, name: str):
        key = f"{module}#{name}"
        if key in self.functions:
            metadata = self.functions[key]
            route_name = f"{metadata.decorator_type.value}_{metadata.name}"
            self.app.router.routes = [
                r for r in self.app.router.routes
                if not (hasattr(r, 'name') and r.name == route_name)
            ]
            self.app.openapi_schema = None
            del self.functions[key]
            if key in self._route_handlers:
                del self._route_handlers[key]
            self._fire_on_register(metadata)


fluidkit_registry = FluidKitRegistry()
