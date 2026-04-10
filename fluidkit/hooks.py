"""
Server hooks for FluidKit.

Provides decorators for lifecycle and request middleware hooks
that mirror SvelteKit's hooks.server.ts behavior.

Usage:
    from fluidkit import hooks

    @hooks.handle
    async def auth(event, resolve):
        event.locals["user"] = await verify(event.cookies.get("token"))
        return await resolve(event)

    @hooks.handle
    async def logging(event, resolve):
        start = time.time()
        response = await resolve(event)
        print(f"took {time.time() - start:.2f}s")
        return response

    @hooks.init
    async def setup():
        await db.connect()

    @hooks.cleanup
    async def teardown():
        await db.close()

    @hooks.lifespan
    async def manage_redis():
        global redis
        redis = await aioredis.from_url("redis://localhost")
        yield
        await redis.close()

    @hooks.handle_error
    async def on_error(error, event, status, message):
        return {"message": "Something went wrong"}

    @hooks.handle_validation_error
    async def on_validation_error(issues, event):
        return {"message": "Invalid input"}
"""

import sys
import inspect
import logging
import asyncio
import functools
from typing import Any
from dataclasses import dataclass
from collections.abc import Callable
from fluidkit.types import HookEvent
from fluidkit.models import HookType
from contextlib import asynccontextmanager


# ── Hook Entry ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class _HookEntry:
    """Metadata for a registered hook function."""

    func: Callable
    module: str
    name: str
    file_path: str | None
    lineno: int

    @property
    def location(self) -> str:
        path = self.file_path or self.module
        return f"{path}:{self.lineno} ({self.name})"


# ── Validation Helpers ──────────────────────────────────────────────────

def _count_required_params(func: Callable) -> int:
    """Count parameters that have no default value, excluding *args/**kwargs."""
    sig = inspect.signature(func)
    return sum(
        1 for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )


def _make_entry(func: Callable) -> _HookEntry:
    """Create a _HookEntry from a function."""
    return _HookEntry(
        func=func,
        module=func.__module__,
        name=func.__name__,
        file_path=inspect.getfile(func) if hasattr(func, "__code__") else None,
        lineno=func.__code__.co_firstlineno if hasattr(func, "__code__") else 0,
    )


def _validate_callable(func: Any, decorator_name: str) -> None:
    """Ensure the decorated value is callable."""
    if not callable(func):
        raise TypeError(
            f"@hooks.{decorator_name} expects a callable, "
            f"got {type(func).__name__}"
        )


def _validate_param_count(func: Callable, decorator_name: str, expected: int) -> None:
    """Ensure the function has the expected number of required parameters."""
    count = _count_required_params(func)
    if count != expected:
        sig = inspect.signature(func)
        params = ", ".join(sig.parameters.keys())
        raise TypeError(
            f"@hooks.{decorator_name} expects {expected} required "
            f"parameter{'s' if expected != 1 else ''}, "
            f"got {count}: ({params})"
        )


def _validate_generator(func: Callable) -> None:
    """Ensure the function is an async or sync generator."""
    if not (inspect.isasyncgenfunction(func) or inspect.isgeneratorfunction(func)):
        raise TypeError(
            f"@hooks.lifespan expects a generator function that yields once. "
            f"Use 'yield' to separate setup and teardown:\n\n"
            f"  @hooks.lifespan\n"
            f"  async def manage():\n"
            f"      resource = await setup()\n"
            f"      yield\n"
            f"      await resource.close()"
        )


def _check_duplicate(
    existing: _HookEntry | None,
    new_func: Callable,
    decorator_name: str,
) -> None:
    if existing is None:
        return
    if existing.module == new_func.__module__:
        if existing.name != new_func.__name__:
            logging.getLogger(__name__).warning(
                "@hooks.%s: replacing '%s' with '%s' in %s — "
                "only one %s hook is allowed per application.",
                decorator_name, existing.name, new_func.__name__,
                new_func.__module__, decorator_name,
            )
        return
    raise RuntimeError(
        f"@hooks.{decorator_name} is already registered at {existing.location}. "
        f"Only one {decorator_name} hook is allowed. "
        f"Combine your logic into a single function "
        f"or remove one of the registrations."
    )


# ── Wrapping Helper ──────────────────────────────────────────────────

def _make_wrapper(func: Callable, hook_type: HookType) -> Callable:
    """Create a thin wrapper preserving signature, stamped for HMR detection.
    For generators (lifespan), also attaches the async context manager."""
    if inspect.isasyncgenfunction(func):
        @functools.wraps(func)
        async def wrapper():
            async for v in func():
                yield v

        @asynccontextmanager
        async def _cm():
            async for v in func():
                yield v

        wrapper.__fluidkit_cm__ = _cm

    elif inspect.isgeneratorfunction(func):
        @functools.wraps(func)
        def wrapper():
            yield from func()

        @asynccontextmanager
        async def _cm():
            gen = func()
            try:
                next(gen)
                yield
            except StopIteration:
                return
            try:
                next(gen)
            except StopIteration:
                pass

        wrapper.__fluidkit_cm__ = _cm

    elif inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

    else:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

    wrapper.__fluidkit__ = hook_type
    return wrapper


# ── Hooks ───────────────────────────────────────────────────────────────

class _Hooks:
    """Server hook decorators and registry.

    Lifecycle:
        @hooks.init         -- run once at startup (single)
        @hooks.cleanup      -- run once at shutdown (single)
        @hooks.lifespan     -- paired setup/teardown via generator (single)

    Request middleware:
        @hooks.handle       -- wraps every request (multiple, ordered)
        @hooks.handle_error -- catches unexpected errors (single)
        @hooks.handle_validation_error -- catches validation failures (single)

    Ordering:
        hooks.sequence(fn1, fn2, fn3) -- explicit handle hook order
    """

    def __init__(self):
        self._handle_hooks: list[_HookEntry] = []
        self._sequence_order: list[tuple[str, str]] | None = None
        self._sequence_module: str | None = None

        self._init_hook: _HookEntry | None = None
        self._cleanup_hook: _HookEntry | None = None
        self._lifespan_hook: _HookEntry | None = None
        self._lifespan_cm: Callable | None = None
        self._handle_error_hook: _HookEntry | None = None
        self._handle_validation_error_hook: _HookEntry | None = None

    # ── Lifecycle ───────────────────────────────────────────────────

    def init(self, func: Callable) -> Callable:
        """Register a server init hook. Runs once at startup.

        Accepts async or sync functions with no required parameters.

        Example:
```python
            @hooks.init
            async def setup():
                global db
                db = await connect("postgres://...")
```
        """
        _validate_callable(func, "init")
        _validate_param_count(func, "init", 0)
        _check_duplicate(self._init_hook, func, "init")
        wrapper = _make_wrapper(func, HookType.INIT)
        self._init_hook = _make_entry(wrapper)
        return wrapper

    def cleanup(self, func: Callable) -> Callable:
        """Register a server cleanup hook. Runs once at shutdown.

        Accepts async or sync functions with no required parameters.

        Example:
```python
            @hooks.cleanup
            async def teardown():
                await db.close()
```
        """
        _validate_callable(func, "cleanup")
        _validate_param_count(func, "cleanup", 0)
        _check_duplicate(self._cleanup_hook, func, "cleanup")
        wrapper = _make_wrapper(func, HookType.CLEANUP)
        self._cleanup_hook = _make_entry(wrapper)
        return wrapper

    def lifespan(self, func: Callable) -> Callable:
        """Register a lifespan hook for paired setup/teardown.

        The function must be a generator (async or sync) that yields once.
        Code before yield runs at startup, code after runs at shutdown.

        Example:
```python
            @hooks.lifespan
            async def manage_redis():
                global redis
                redis = await aioredis.from_url("redis://localhost")
                yield
                await redis.close()
```
        """
        _validate_callable(func, "lifespan")
        _validate_generator(func)
        _validate_param_count(func, "lifespan", 0)
        _check_duplicate(self._lifespan_hook, func, "lifespan")
        wrapper = _make_wrapper(func, HookType.LIFESPAN)
        self._lifespan_hook = _make_entry(wrapper)
        self._lifespan_cm = wrapper.__fluidkit_cm__
        return wrapper

    # ── Request Middleware ───────────────────────────────────────────

    def handle(self, func: Callable) -> Callable:
        """Register a handle hook. Runs on every server request.

        Multiple handle hooks are allowed and execute in source order
        (top-to-bottom within a file, file import order across files).
        Use hooks.sequence() to set explicit order.

        The function receives (event, resolve) and must return a response.

        Example:
```python
            @hooks.handle
            async def auth(event, resolve):
                token = event.cookies.get("access_token")
                event.locals["user"] = await verify_token(token)
                return await resolve(event)
```
        """
        _validate_callable(func, "handle")
        _validate_param_count(func, "handle", 2)

        wrapper = _make_wrapper(func, HookType.HANDLE)
        entry = _make_entry(wrapper)

        # Replace existing entry from same module+name (HMR re-registration)
        self._handle_hooks = [
            h for h in self._handle_hooks
            if not (h.module == entry.module and h.name == entry.name)
        ]
        self._handle_hooks.append(entry)
        self._handle_hooks.sort(key=lambda h: (h.module, h.lineno))

        return wrapper

    def handle_error(self, func: Callable) -> Callable:
        """Register an error handler hook. Catches unexpected errors.

        Must accept 4 parameters: error, event, status, message.
        Must return a dict matching App.Error shape (at minimum {message: str}).

        Example:
```python
            @hooks.handle_error
            async def on_error(error, event, status, message):
                error_id = str(uuid4())
                logger.exception(error, extra={"error_id": error_id})
                return {"message": "Something went wrong", "error_id": error_id}
```
        """
        _validate_callable(func, "handle_error")
        _validate_param_count(func, "handle_error", 4)
        _check_duplicate(self._handle_error_hook, func, "handle_error")
        wrapper = _make_wrapper(func, HookType.HANDLE_ERROR)
        self._handle_error_hook = _make_entry(wrapper)
        return wrapper

    def handle_validation_error(self, func: Callable) -> Callable:
        """Register a validation error handler hook.

        Called when a remote function argument fails schema validation.
        Must accept 2 parameters: issues, event.
        Must return a dict matching App.Error shape (at minimum {message: str}).

        Example:
```python
            @hooks.handle_validation_error
            async def on_validation_error(issues, event):
                return {"message": "Invalid request"}
```
        """
        _validate_callable(func, "handle_validation_error")
        _validate_param_count(func, "handle_validation_error", 2)
        _check_duplicate(self._handle_validation_error_hook, func, "handle_validation_error")
        wrapper = _make_wrapper(func, HookType.HANDLE_VALIDATION_ERROR)
        self._handle_validation_error_hook = _make_entry(wrapper)
        return wrapper

    # ── Ordering ────────────────────────────────────────────────────

    def sequence(self, *funcs: Callable) -> None:
        """Set explicit execution order for handle hooks.

        Each function must already be registered with @hooks.handle.
        Order follows the argument order.

        Example:
```python
            hooks.sequence(auth, rate_limit, logging)
```
        """
        if not funcs:
            raise ValueError("hooks.sequence() requires at least one function")

        caller_module = sys._getframe(1).f_globals.get("__name__")
        if self._sequence_order is not None and self._sequence_module != caller_module:
            raise RuntimeError(
                f"hooks.sequence() is already configured in {self._sequence_module}. "
                f"Only one sequence() call is allowed per application."
            )

        registered = {(h.module, h.name) for h in self._handle_hooks}

        order = []
        for func in funcs:
            _validate_callable(func, "sequence")
            key = (func.__module__, func.__name__)
            if key not in registered:
                raise ValueError(
                    f"hooks.sequence() received '{func.__name__}' from "
                    f"{func.__module__}, but it is not registered with "
                    f"@hooks.handle. Decorate it first."
                )
            order.append(key)

        self._sequence_order = order
        self._sequence_module = caller_module

    # ── Retrieval ───────────────────────────────────────────────────

    def get_handle_chain(self) -> list[Callable]:
        """Return handle hooks in execution order.

        If sequence() was called, follows that order, skipping any
        entries that no longer exist. Remaining unsequenced hooks
        are appended in default (module, lineno) order.
        Otherwise follows default ordering for all hooks.
        """
        if self._sequence_order is not None:
            lookup = {(h.module, h.name): h.func for h in self._handle_hooks}

            chain = []
            sequenced = set()
            for key in self._sequence_order:
                func = lookup.get(key)
                if func is not None:
                    chain.append(func)
                    sequenced.add(key)

            for h in self._handle_hooks:
                key = (h.module, h.name)
                if key not in sequenced:
                    chain.append(h.func)

            return chain

        return [h.func for h in self._handle_hooks]

    @property
    def has_hooks(self) -> bool:
        """True if any hooks are registered."""
        return bool(
            self._handle_hooks
            or self._init_hook
            or self._cleanup_hook
            or self._lifespan_hook
            or self._handle_error_hook
            or self._handle_validation_error_hook
        )

    # ── Execution chain ─────────────────────────────────────────────────

    async def run_handle_chain(self, event: HookEvent, call_next: Callable) -> tuple[Any, dict]:
        """
        Run the handle chain against the given event.

        call_next is a coroutine that executes the actual remote function.
        Returns (result, serializable_locals) where serializable_locals is
        the JSON-safe subset of event.locals to forward to SvelteKit.
        """
        chain = self.get_handle_chain()

        def build_resolve(index: int) -> Callable:
            async def resolve(ev: HookEvent) -> Any:
                if index >= len(chain):
                    return await call_next()
                return await self._invoke_hook(chain[index], ev, build_resolve(index + 1))
            return resolve

        result = await build_resolve(0)(event)

        return result, event.locals.serializable()
    
    @staticmethod
    async def _invoke_hook(handler: Callable, event: HookEvent, resolve: Callable) -> Any:
        if inspect.iscoroutinefunction(handler):
            return await handler(event, resolve)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, handler, event, resolve)

    async def _invoke_handle_error(
        self,
        error: Exception,
        event: Any,
        status: int,
        message: str,
    ) -> dict | None:
        """
        Invoke handle_error hook if registered.
        Returns the custom body dict on success, None if not registered or if the hook itself raises.
        Intentional exceptions (HTTPError, Redirect) must never reach this.
        """
        if self._handle_error_hook is None:
            return None
        try:
            func = self._handle_error_hook.func
            if inspect.iscoroutinefunction(func):
                return await func(error, event, status, message)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, func, error, event, status, message)
        except Exception:
            return None

    async def _invoke_handle_validation_error(
        self,
        issues: list,
        event: Any,
    ) -> dict | None:
        """
        Invoke handle_validation_error hook if registered.
        Returns the custom body dict on success, None if not registered or if the hook itself raises.
        issues is pydantic's e.errors() structured list.
        """
        if self._handle_validation_error_hook is None:
            return None
        try:
            func = self._handle_validation_error_hook.func
            if inspect.iscoroutinefunction(func):
                return await func(issues, event)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, func, issues, event)
        except Exception:
            return None

    # ── HMR Support ─────────────────────────────────────────────────

    def _reconcile_module(self, module_name: str, module) -> None:
        """Remove hooks whose functions no longer exist in the module.
        Called after HMR re-execution. Preserves hooks that were
        re-registered during re-execution."""
        self._handle_hooks = [
            h for h in self._handle_hooks
            if h.module != module_name
            or (
                module is not None
                and getattr(getattr(module, h.name, None), '__fluidkit__', None) == HookType.HANDLE
            )
        ]

        if self._sequence_module == module_name:
            self._sequence_order = None
            self._sequence_module = None

        for attr, expected_type in (
            ("_init_hook", HookType.INIT),
            ("_cleanup_hook", HookType.CLEANUP),
            ("_lifespan_hook", HookType.LIFESPAN),
            ("_handle_error_hook", HookType.HANDLE_ERROR),
            ("_handle_validation_error_hook", HookType.HANDLE_VALIDATION_ERROR),
        ):
            entry = getattr(self, attr)
            if entry is not None and entry.module == module_name:
                current = getattr(module, entry.name, None) if module is not None else None
                if getattr(current, '__fluidkit__', None) != expected_type:
                    setattr(self, attr, None)

        if self._lifespan_hook is None:
            self._lifespan_cm = None

        if self._sequence_order is not None:
            remaining = {(h.module, h.name) for h in self._handle_hooks}
            if not any(key in remaining for key in self._sequence_order):
                self._sequence_order = None
                self._sequence_module = None

    # ── Dev Summary ─────────────────────────────────────────────────

    def _get_summary_lines(self) -> list[str]:
        """Return human-readable summary lines for CLI startup display."""
        if not self.has_hooks:
            return []

        lines = ["hooks registered:"]

        if self._handle_hooks:
            chain = self.get_handle_chain()
            lookup = {id(h.func): h for h in self._handle_hooks}
            names = []
            for func in chain:
                entry = lookup.get(id(func))
                if entry:
                    names.append(entry.location)
            lines.append(f"  handle: {' -> '.join(names)}")
            if self._sequence_order:
                lines.append("    (explicit sequence)")

        for label, attr in (
            ("init", "_init_hook"),
            ("cleanup", "_cleanup_hook"),
            ("lifespan", "_lifespan_hook"),
            ("handle_error", "_handle_error_hook"),
            ("handle_validation_error", "_handle_validation_error_hook"),
        ):
            entry = getattr(self, attr)
            if entry is not None:
                lines.append(f"  {label}: {entry.location}")

        return lines


hooks = _Hooks()
