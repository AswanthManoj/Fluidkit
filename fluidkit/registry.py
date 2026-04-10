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
from contextlib import asynccontextmanager
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

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
        protected = request.url.path.startswith("/remote/") or request.url.path == "/__fk_hooks__"
        if not protected:
            return await call_next(request)
        
        if not fluidkit_registry.signed:
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
        self.signed = True
        self._initialized = True
        self._route_handlers: dict[str, Callable] = {}
        self.functions: dict[str, FunctionMetadata] = {}
        self._on_change_callbacks: list[Callable[[dict], None]] = []
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        registry = self

        @asynccontextmanager
        async def master_lifespan(app):
            from fluidkit.hooks import hooks

            if registry.signed and not os.environ.get("FLUIDKIT_SECRET"):
                logger.warning(
                    "FLUIDKIT_SECRET is not set. "
                    "Remote function routes will reject all requests. "
                    "Set this environment variable to the same value in both "
                    "FastAPI and SvelteKit or set `signed` in fluidkit.config.json "
                    "to be `false`"
                )

            if hooks._init_hook is not None:
                await _invoke(hooks._init_hook.func)

            if hooks._lifespan_cm is not None:
                async with hooks._lifespan_cm():
                    yield
            else:
                yield

            if hooks._cleanup_hook is not None:
                await _invoke(hooks._cleanup_hook.func)

        app = FastAPI(
            title="FluidKit Generated Remote Functions",
            lifespan=master_lifespan,
        )
        app.add_middleware(_FluidKitAuthMiddleware)


        @app.post("/__fk_hooks__")
        async def fk_hooks_handler(body: dict):
            from fluidkit.hooks import hooks
            from fluidkit.models import HookRequestContext
            from fluidkit.exceptions import HTTPError, Redirect
            from fluidkit.types import Cookies, HookEvent, _LocalsDict

            if not hooks._handle_hooks:
                return JSONResponse({"__fk_cookies": [], "__fk_locals": {}})

            context = HookRequestContext(
                url=body.get("url", ""),
                method=body.get("method", "GET"),
                headers=body.get("headers", {}),
                cookies=body.get("cookies", []),
                is_remote=False,
            )

            request_cookies = {c["name"]: c["value"] for c in context.cookies}
            cookies = Cookies(request_cookies=request_cookies, allow_set=True)
            locals_ = _LocalsDict()
            hook_event = HookEvent(context=context, cookies=cookies, locals=locals_)
            fk_locals = {}

            try:
                async def noop_resolve():
                    return None

                _, fk_locals = await hooks.run_handle_chain(hook_event, noop_resolve)

                return JSONResponse({
                    "__fk_cookies": cookies.serialize(),
                    "__fk_locals": fk_locals,
                })

            except Redirect as e:
                return JSONResponse({
                    "__fk_cookies": cookies.serialize(),
                    "__fk_locals": fk_locals,
                    "redirect": {"status": e.status, "location": e.location},
                })
            
            except HTTPError as e:
                return JSONResponse({
                    "__fk_cookies": [],
                    "__fk_locals": {},
                    "error": {"status": e.status, "message": e.message},
                }, status_code=e.status)

            except Exception as e:
                logger.exception(e)
                return JSONResponse({
                    "__fk_cookies": [],
                    "__fk_locals": {},
                    "error": {"status": 500, "message": "Internal server error"},
                }, status_code=500)
            
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


fluidkit_registry = FluidKitRegistry()
