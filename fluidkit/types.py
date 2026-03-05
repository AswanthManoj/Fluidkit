import inspect
from fastapi import UploadFile
from fluidkit.models import MutationType
from typing import Any, Generic, TypeVar, ParamSpec, Callable, Generator


T = TypeVar('T')
P = ParamSpec('P')


class Cookies:
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
        if self._request_cookies:
            return self._request_cookies.get(name)

    def set(self, name: str, value: str, **kwargs) -> None:
        if not self.allow_set:
            raise RuntimeError("Cannot set cookies in @query or @prerender")
        self._cookies_to_set.append((name, value, kwargs))

    def serialize(self) -> list[dict]:
        """Serialize cookie-set instructions as JSON-safe dicts for the response payload."""
        result = []
        for name, value, kwargs in self._cookies_to_set:
            entry = {"name": name, "value": value}
            for py_key, js_key in self._OPTION_MAP.items():
                if py_key in kwargs:
                    entry[js_key] = kwargs[py_key]
            result.append(entry)
        return result


class RequestEvent:
    def __init__(self, cookies: Cookies, locals: dict[str, Any]):
        self.cookies: Cookies = cookies
        self.locals: dict[str, Any] = locals


class FileUpload(UploadFile):
    pass


class RemoteProxy(Generic[T]):
    def __init__(self, func_name: str, sig: inspect.Signature, executor: Callable, args: tuple, kwargs: dict):
        self._sig = sig
        self._args = args
        self._kwargs = kwargs
        self._executor = executor
        self._func_name = func_name

    def _get_normalized_kwargs(self, inject_request: bool = True) -> dict:
        """Convert args/kwargs to pure kwargs, optionally inject RequestEvent"""
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
        """Get kwargs dict with RequestEvent params stripped out (for mutation metadata)."""
        kwargs = self._get_normalized_kwargs(inject_request=False)
        return {
            k: v for k, v in kwargs.items()
            if self._sig.parameters[k].annotation is not RequestEvent
        }

    def _get_context_or_warn(self, method_name: str):
        """Return FluidKitContext if available, else warn and return None."""
        from fluidkit.context import get_context
        import warnings

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
        return self._executor(**kwargs).__await__()

    async def refresh(self) -> T:
        kwargs = self._get_normalized_kwargs(inject_request=True)
        result = await self._executor(**kwargs)

        ctx = self._get_context_or_warn("refresh")
        if ctx is not None:
            ctx.add_mutation(MutationType.REFRESH, self._func_name, self._get_serializable_kwargs(), result)

        return result

    async def set(self, data: T) -> None:
        ctx = self._get_context_or_warn("set")
        if ctx is not None:
            ctx.add_mutation(MutationType.SET, self._func_name, self._get_serializable_kwargs(), data)
