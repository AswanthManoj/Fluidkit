import os
from fastapi import FastAPI
from typing import Dict, List, Callable, Optional
from fluidkit.models import FunctionMetadata, DecoratorType


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
        """Create pre-configured FastAPI app"""
        app = FastAPI(
            version="0.1.0",
            title="FluidKit Remote Functions",
        )
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )
        return app
    
    def configure(self, dev: bool = False, host: str = "0.0.0.0", port: int = 8000, schema_output: str = "src/lib/fluidkit"):
        self.dev = dev
        self.app.debug = dev
        self.schema_output = schema_output
        display_host = "localhost" if host == "0.0.0.0" else host
        self.base_url = f"http://{display_host}:{port}"

    def on_register(self, callback: Callable[[FunctionMetadata], None]):
        self._on_register_callback = callback

    def _fire_on_register(self, metadata: FunctionMetadata):
        if self._on_register_callback:
            self._on_register_callback(metadata)

    def register(self, metadata: FunctionMetadata, handler: Callable):
        key = f"{metadata.module}#{metadata.name}"

        # If already registered, clean up old route first
        if key in self.functions:
            old_metadata = self.functions[key]
            old_path = self._generate_route_path(old_metadata)
            self.app.router.routes = [
                r for r in self.app.router.routes
                if getattr(r, 'path', None) != old_path
            ]
            self.app.openapi_schema = None

        self.functions[key] = metadata
        self._route_handlers[key] = handler
        
        if self.app:
            self._register_route(metadata, handler)

        if self.dev:
            self._fire_on_register(metadata)

    def _register_route(self, metadata: FunctionMetadata, handler: Callable):
        if not self.app:
            return
        path = self._generate_route_path(metadata)
        self.app.add_api_route(
            path,
            handler,
            methods=["POST"],
            response_model=None,
            name=f"{metadata.decorator_type.value}_{metadata.name}"
        )
        self.app.openapi_schema = None

    def _generate_route_path(self, metadata: FunctionMetadata) -> str:
        """
        Generate route path from module path
        
        Examples:
        __main__ -> /remote/{function_name}
        users.api.get_user -> /remote/users/api/get_user
        src.lib.users.api.get_user -> /remote/users/api/get_user
        src.routes.posts.data.get_posts -> /remote/posts/data/get_posts
        """
        module = metadata.module
        if module == '__main__':
            return f"/remote/{metadata.name}"
        for prefix in ['src.lib.', 'src.routes.', 'src.']:
            if module.startswith(prefix):
                module = module[len(prefix):]
                break
        module_path = module.replace('.', '/')
        if module_path:
            return f"/remote/{module_path}/{metadata.name}"
        else:
            return f"/remote/{metadata.name}"

    def get(self, module: str, name: str) -> FunctionMetadata | None:
        key = f"{module}#{name}"
        return self.functions.get(key)
    
    def get_by_file(self, file_path: str) -> List[FunctionMetadata]:
        return [m for m in self.functions.values() if m.file_path == file_path]
    
    def unregister(self, module: str, name: str):
        """Unregister a function (for HMR when function is removed)"""
        key = f"{module}#{name}"
        if key in self.functions:
            metadata = self.functions[key]
            if self.app:
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
