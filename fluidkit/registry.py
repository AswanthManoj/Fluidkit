import os
import time
import hmac
import logging
import inspect
import hashlib
import linecache
from fastapi import FastAPI
from collections.abc import Callable
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import AsyncExitStack, asynccontextmanager

from fluidkit.models import FunctionMetadata
from fluidkit.utilities import generate_route_path


_preserved: dict[str, object] = {}
logger = logging.getLogger(__name__)


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


class _FluidKitAuthMiddleware(BaseHTTPMiddleware):
    WINDOW = 5

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/remote/"):
            return await call_next(request)

        token = request.headers.get("X-FluidKit-Token")
        if not token:
            return JSONResponse({"message": "Missing authentication token"}, status_code=401)

        parts = token.split(".", 1)
        if len(parts) != 2:
            return JSONResponse({"message": "Malformed authentication token"}, status_code=401)

        ts_str, signature = parts
        try:
            ts = int(ts_str)
        except ValueError:
            return JSONResponse({"message": "Malformed authentication token"}, status_code=401)

        if abs(time.time() - ts) > self.WINDOW:
            return JSONResponse({"message": "Authentication token expired"}, status_code=401)

        secret = os.environ.get("FLUIDKIT_SECRET", "")
        expected = hmac.new(secret.encode(), ts_str.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected):
            return JSONResponse({"message": "Invalid authentication token"}, status_code=401)

        return await call_next(request)


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
        self._route_handlers: dict[str, Callable] = {}
        self.functions: dict[str, FunctionMetadata] = {}
        self._on_change_callbacks: list[Callable[[dict], None]] = []
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        registry = self

        @asynccontextmanager
        async def master_lifespan(app):
            if not os.environ.get("FLUIDKIT_SECRET"):
                logger.warning(
                    "FLUIDKIT_SECRET is not set. "
                    "Remote function routes will reject all requests. "
                    "Set this environment variable to the same value in both FastAPI and SvelteKit."
                )

            for fn in registry._startup_hooks:
                await _invoke(fn)

            async with AsyncExitStack() as stack:
                for cm, has_app_param in registry._lifespan_hooks:
                    if has_app_param:
                        await stack.enter_async_context(cm(app))
                    else:
                        await stack.enter_async_context(cm())
                yield

            for fn in registry._shutdown_hooks:
                await _invoke(fn)

        app = FastAPI(
            title="FluidKit Generated Remote Functions",
            lifespan=master_lifespan,
        )
        app.add_middleware(_FluidKitAuthMiddleware)
        return app

    def on_change(self, callback: Callable[[dict], None]):
        """Register a callback that receives {"action": "register"|"unregister", "key": str, "metadata": FunctionMetadata}."""
        self._on_change_callbacks.append(callback)

    def _notify(self, action: str, metadata: FunctionMetadata):
        key = f"{metadata.module}#{metadata.name}"
        event = {"action": action, "key": key, "metadata": metadata}
        for cb in self._on_change_callbacks:
            cb(event)
        
    def register(self, metadata: FunctionMetadata, handler: Callable):
        key = f"{metadata.module}#{metadata.name}"
        path = generate_route_path(metadata)

        if key in self.functions:
            self.app.router.routes = [r for r in self.app.router.routes if getattr(r, "path", None) != path]

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
        self._notify("register", metadata)

    def get(self, module: str, name: str) -> FunctionMetadata | None:
        return self.functions.get(f"{module}#{name}")

    def get_by_file(self, file_path: str) -> list[FunctionMetadata]:
        return [m for m in self.functions.values() if m.file_path == file_path]

    def unregister(self, module: str, name: str):
        key = f"{module}#{name}"
        if key in self.functions:
            metadata = self.functions[key]
            route_name = f"{metadata.decorator_type.value}_{metadata.name}"
            self.app.router.routes = [
                r for r in self.app.router.routes if not (hasattr(r, "name") and r.name == route_name)
            ]
            self.app.openapi_schema = None
            del self.functions[key]
            if key in self._route_handlers:
                del self._route_handlers[key]
            self._notify("unregister", metadata)

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
