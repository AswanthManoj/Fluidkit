import json
import inspect
from fastapi import UploadFile
from pydantic import BaseModel
from collections.abc import Callable, Generator
from typing import Any, Generic, ParamSpec, TypeVar
from fluidkit.models import MutationType, HookRequestContext


T = TypeVar("T")
P = ParamSpec("P")


class _LocalsDict(dict):
    """
    A dict subclass that tracks which keys hold JSON-serializable values.
    Serializability is checked at write time so filtering at response time
    is a cheap set lookup instead of a re-serialization attempt.
    """
    def __init__(self):
        super().__init__()
        self._serializable: set[str] = set()

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        try:
            if isinstance(value, BaseModel):
                value.model_dump_json()
            else:
                json.dumps(value)
            self._serializable.add(key)
        except (TypeError, ValueError):
            self._serializable.discard(key)

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._serializable.discard(key)

    def serializable(self) -> dict:
        """Return only the JSON-serializable entries, with Pydantic models dumped to dicts."""
        result = {}
        for k in self._serializable:
            if k not in self:
                continue
            v = self[k]
            result[k] = v.model_dump() if isinstance(v, BaseModel) else v
        return result


class Cookies:
    """
    Cookie interface available on both RequestEvent and HookEvent.

    A single Cookies instance is shared across the hook chain and the
    remote function within the same request. This means cookies written
    by a hook are visible to the function and vice versa. All writes are
    collected and serialized once at response time into __fk_cookies.

    Raises RuntimeError if set() is called inside @query or @prerender,
    where cookie writes are not permitted.
    """

    _OPTION_MAP = {
        "path": "path",
        "secure": "secure",
        "domain": "domain",
        "max_age": "maxAge",
        "expires": "expires",
        "httponly": "httpOnly",
        "samesite": "sameSite",
    }

    def __init__(self, request_cookies: dict, allow_set: bool = True) -> None:
        self._cookies_to_set: list[tuple[str, str, dict]] = []
        self.allow_set = allow_set
        self._request_cookies = request_cookies

    def get(self, name: str) -> str | None:
        """Get an incoming request cookie by name."""
        return self._request_cookies.get(name)

    def set(self, name: str, value: str, **kwargs) -> None:
        """
        Queue a cookie to be set on the client.

        Keyword arguments map to standard cookie attributes:
        path, secure, domain, max_age, expires, httponly, samesite.

        Raises RuntimeError inside @query and @prerender.
        """
        if not self.allow_set:
            raise RuntimeError("Cannot set cookies in @query or @prerender")
        self._cookies_to_set.append((name, value, kwargs))

    def fork(self, allow_set: bool) -> "Cookies":
        """
        Return a view of this Cookies instance with a different allow_set permission.
        Both the original and the fork write to the same underlying list, so cookies
        set through either are collected together at serialize time.
        """
        view = Cookies.__new__(Cookies)
        view._cookies_to_set = self._cookies_to_set  # shared reference
        view._request_cookies = self._request_cookies
        view.allow_set = allow_set
        return view

    def serialize(self) -> list[dict]:
        """Serialize all queued cookie instructions as JSON-safe dicts."""
        result = []
        for name, value, kwargs in self._cookies_to_set:
            entry = {"name": name, "value": value}
            for py_key, js_key in self._OPTION_MAP.items():
                if py_key in kwargs:
                    entry[js_key] = kwargs[py_key]
            result.append(entry)
        return result


class RequestEvent:
    """
    Event object available inside all remote function handlers via get_request_event().

    url:     full request URL — None if called outside a remote function context
    method:  HTTP method — None if called outside a remote function context  
    headers: incoming request headers — None if called outside a remote function context
    cookies: read incoming cookies or queue outgoing ones (write disallowed in @query/@prerender)
    locals:  arbitrary per-request data; serializable values are forwarded to SvelteKit
             via __fk_locals in the response
    """

    def __init__(self, cookies: Cookies, locals: _LocalsDict | None = None):
        self.url: str | None = None
        self.method: str | None = None
        self.headers: dict[str, str] | None = None
        self.cookies: Cookies = cookies
        self.locals: _LocalsDict = locals if locals is not None else _LocalsDict()

    def _populate_request(self, context: HookRequestContext) -> None:
        self.url = context.url
        self.method = context.method
        self.headers = context.headers


class HookEvent:
    """
    Event object passed to @hooks.handle handlers.

    Shares the same Cookies instance as RequestEvent so cookie writes
    from hooks and from the remote function are collected together and
    serialized once. locals is also shared so values set in a hook are
    visible inside the remote function and forwarded to SvelteKit.

    url:       full request URL
    method:    HTTP method
    headers:   incoming request headers
    cookies:   shared Cookies instance
    locals:    shared _LocalsDict instance
    is_remote: always True for remote function calls
    """

    def __init__(
        self,
        context: HookRequestContext,
        cookies: Cookies,
        locals: _LocalsDict | None = None,
    ) -> None:
        self.url: str = context.url
        self.method: str = context.method
        self.headers: dict[str, str] = context.headers
        self.is_remote: bool = context.is_remote
        self.cookies: Cookies = cookies
        self.locals: _LocalsDict = locals if locals is not None else _LocalsDict()


class FileUpload(UploadFile):
    """Represents an uploaded file in a @form handler."""
    pass


class RemoteProxy(Generic[T]):
    def __init__(self, func_name: str, sig: inspect.Signature, executor: Callable, args: tuple, kwargs: dict):
        """
        Returned when a @query, @command, @form, or @prerender decorated function
        is called locally (i.e. from within another Python remote function or command).

        Supports three usage patterns:
        await fn(args)         -- direct call, returns result
        await fn(args).refresh() -- re-execute and record a REFRESH mutation
        fn(args).set(data)     -- record a SET mutation without re-executing
        """
        self._sig = sig
        self._args = args
        self._kwargs = kwargs
        self._executor = executor
        self._func_name = func_name

    def __init__(self, func_name: str, sig: inspect.Signature, executor: Callable, args: tuple, kwargs: dict):
        self._sig = sig
        self._args = args
        self._kwargs = kwargs
        self._executor = executor
        self._func_name = func_name

    def _get_normalized_kwargs(self, inject_request: bool = True) -> dict:
        """Bind args/kwargs to the signature, optionally injecting the current RequestEvent."""
        from fluidkit.context import get_request_event

        bound = self._sig.bind_partial(*self._args, **self._kwargs)
        kwargs = dict(bound.arguments)
        if inject_request:
            for param_name, param in self._sig.parameters.items():
                if param.annotation is RequestEvent and param_name not in kwargs:
                    try:
                        kwargs[param_name] = get_request_event()
                    except RuntimeError:
                        pass
                    break
        return kwargs

    def _get_serializable_kwargs(self) -> dict:
        """Return kwargs with RequestEvent params stripped (used for mutation metadata)."""
        kwargs = self._get_normalized_kwargs(inject_request=False)
        return {k: v for k, v in kwargs.items() if self._sig.parameters[k].annotation is not RequestEvent}

    def _get_context_or_warn(self, method_name: str):
        """Return the current FluidKitContext or warn and return None if not in a command/form."""
        import warnings
        from fluidkit.context import get_context
        try:
            return get_context()
        except RuntimeError:
            warnings.warn(
                f"{self._func_name}.{method_name}() called outside command/form context. "
                "Result will not be included in response metadata.",
                stacklevel=3,
            )
            return None

    def __await__(self) -> Generator[Any, None, T]:
        kwargs = self._get_normalized_kwargs(inject_request=True)
        async def _wrap():
            return self._executor(**kwargs)
        return _wrap().__await__()

    def refresh(self) -> T:
        """Re-execute the function and record a REFRESH mutation in the current context."""
        kwargs = self._get_normalized_kwargs(inject_request=True)
        result = self._executor(**kwargs)
        ctx = self._get_context_or_warn("refresh")
        if ctx is not None:
            ctx.add_mutation(MutationType.REFRESH, self._func_name, self._get_serializable_kwargs(), result)
        return result

    def set(self, data: T) -> None:
        """Record a SET mutation with the given data without re-executing the function."""
        ctx = self._get_context_or_warn("set")
        if ctx is not None:
            ctx.add_mutation(MutationType.SET, self._func_name, self._get_serializable_kwargs(), data)


class AsyncRemoteProxy(RemoteProxy[T]):
    """
    Async variant of RemoteProxy for coroutine-based remote functions.
    """

    def __await__(self) -> Generator[Any, None, T]:
        kwargs = self._get_normalized_kwargs(inject_request=True)
        return self._executor(**kwargs).__await__()

    async def refresh(self) -> T:
        """Re-execute the async function and record a REFRESH mutation in the current context."""
        kwargs = self._get_normalized_kwargs(inject_request=True)
        result = await self._executor(**kwargs)
        ctx = self._get_context_or_warn("refresh")
        if ctx is not None:
            ctx.add_mutation(MutationType.REFRESH, self._func_name, self._get_serializable_kwargs(), result)
        return result

    async def set(self, data: T) -> None:
        """Record a SET mutation with the given data without re-executing the function."""
        ctx = self._get_context_or_warn("set")
        if ctx is not None:
            ctx.add_mutation(MutationType.SET, self._func_name, self._get_serializable_kwargs(), data)
