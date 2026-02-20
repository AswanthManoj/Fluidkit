from fastapi import FastAPI
from fluidkit.models import FunctionMetadata
from typing import Dict, List, Callable, Optional
from fluidkit.utilities import generate_route_path


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
        # TODO: Need to work out so in non dev conditions this doesn't fire
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


fluidkit_registry = FluidKitRegistry()
