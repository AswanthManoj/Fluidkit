import inspect
import linecache
from fastapi import FastAPI
from fluidkit.models import FunctionMetadata
from typing import Dict, List, Callable, Optional
from fluidkit.utilities import generate_route_path
from contextlib import asynccontextmanager, AsyncExitStack


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


async def _invoke(fn, *args):
    """Call fn with args, awaiting if async."""
    if inspect.iscoroutinefunction(fn):
        await fn(*args)
    else:
        fn(*args)


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
        self._lifespan_hooks: list[tuple] = []
        self._startup_hooks: list[Callable] = []
        self._shutdown_hooks: list[Callable] = []
        self._route_handlers: Dict[str, Callable] = {}
        self.functions: Dict[str, FunctionMetadata] = {}
        self._on_register_callback: Optional[Callable[[FunctionMetadata], None]] = None
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        registry = self

        @asynccontextmanager
        async def master_lifespan(app):
            # User @on_startup hooks — in registration order
            for fn in registry._startup_hooks:
                await _invoke(fn)

            # User @lifespan context managers — enter in order, exit in reverse
            async with AsyncExitStack() as stack:
                for cm, has_app_param in registry._lifespan_hooks:
                    if has_app_param:
                        await stack.enter_async_context(cm(app))
                    else:
                        await stack.enter_async_context(cm())
                yield

            # User @on_shutdown hooks — in registration order
            for fn in registry._shutdown_hooks:
                await _invoke(fn)

        app = FastAPI(
            version="0.1.0",
            title="FluidKit Remote Functions",
            lifespan=master_lifespan,
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

    # ── Registration ──────────────────────────────────────────────────────

    def on_register(self, callback: Callable[[FunctionMetadata], None]):
        self._on_register_callback = callback

    def _fire_on_register(self, metadata: FunctionMetadata):
        if self._on_register_callback:
            self._on_register_callback(metadata)

    def register(self, metadata: FunctionMetadata, handler: Callable):
        key = f"{metadata.module}#{metadata.name}"
        path = generate_route_path(metadata)

        if key in self.functions:
            self.app.router.routes = [
                r for r in self.app.router.routes
                if getattr(r, 'path', None) != path
            ]

        self.functions[key] = metadata
        self._route_handlers[key] = handler

        self.app.add_api_route(
            path,
            handler,
            methods=["POST"],
            response_model=None,
            name=f"{metadata.decorator_type.value}_{metadata.name}",
        )
        self.app.openapi_schema = None

        self._fire_on_register(metadata)

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

    # ── Lifecycle hooks ───────────────────────────────────────────────────

    def on_startup(self, func: Callable) -> Callable:
        """
        Register an async or sync function to run at app startup.

        Example:
```python
            @on_startup
            async def init_db():
                global db
                db = await connect("postgres://...")
```
        """
        self._startup_hooks.append(func)
        return func

    def on_shutdown(self, func: Callable) -> Callable:
        """
        Register an async or sync function to run at app shutdown.

        Example:
```python
            @on_shutdown
            async def cleanup():
                await db.close()
```
        """
        self._shutdown_hooks.append(func)
        return func

    def lifespan(self, func: Callable) -> Callable:
        """
        Register a lifespan context manager for paired setup/teardown.

        The decorated function must be an async generator that yields once.
        Optionally accepts the FastAPI app as a parameter.

        Example:
```python
            @lifespan
            async def manage_redis():
                redis = await aioredis.from_url("redis://localhost")
                yield
                await redis.close()

            @lifespan
            async def manage_db(app):
                db = await connect(app.state.db_url)
                yield
                await db.close()
```
        """
        sig = inspect.signature(func)
        has_app_param = len(sig.parameters) > 0
        cm = asynccontextmanager(func)
        self._lifespan_hooks.append((cm, has_app_param))
        return func


fluidkit_registry = FluidKitRegistry()


lifespan = fluidkit_registry.lifespan
on_startup = fluidkit_registry.on_startup
on_shutdown = fluidkit_registry.on_shutdown
