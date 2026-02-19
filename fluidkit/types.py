import uuid
import typing
import inspect
from enum import Enum
from typing import (
    Any, Generic, 
    TypeVar, ParamSpec,  
    Callable, Generator,
    Any, Union, get_origin, get_args
)
from datetime import datetime, date
from dataclasses import dataclass, field
from fastapi import UploadFile, Response


T = TypeVar('T')
P = ParamSpec('P')


class Cookies:
    def __init__(self, request_cookies: dict, allow_set: bool = True) -> None:
        self._cookies_to_set = []
        self.allow_set = allow_set
        self._request_cookies = request_cookies

    def get(self, name: str) -> str | None:
        if self._request_cookies:
            return self._request_cookies.get(name)

    def set(self, name: str, value: str, **kwargs) -> None:
        if not self.allow_set:
            raise RuntimeError("Cannot set cookies in @query or @prerender")
        self._cookies_to_set.append((name, value, kwargs))
    
    def apply_to_response(self, response: Response) -> None:
        """Apply all set_cookie calls to FastAPI Response"""
        for name, value, kwargs in self._cookies_to_set:
            response.set_cookie(name, value, **kwargs)


class RequestEvent:
    def __init__(self, cookies: Cookies, locals: dict):
        self.cookies = cookies
        self.locals = locals


class FileUpload(UploadFile):
    pass


class RemoteProxy(Generic[T]):
    def __init__(self, func_name: str, sig: inspect.Signature, executor: Callable, args: tuple, kwargs: dict):
        self._sig = sig
        self._args = args
        self._kwargs = kwargs
        self._executor = executor
        self._func_name = func_name
    
    def __await__(self) -> Generator[Any, None, T]:
        return self._executor(*self._args, **self._kwargs).__await__()
    
    async def refresh(self) -> T:
        from fluidkit.types import RequestEvent
        from fluidkit.context import get_context, get_request_event

        kwargs = dict(self._kwargs)
    
        request_param = None
        for param_name, param in self._sig.parameters.items():
            if param.annotation is RequestEvent:
                request_param = param_name
                break
        
        if request_param:
            bound = self._sig.bind_partial(*self._args, **self._kwargs)
            if request_param not in bound.arguments:
                try:
                    kwargs[request_param] = get_request_event()
                except RuntimeError:
                    pass

        result = await self._executor(*self._args, **kwargs)
        
        try:
            ctx = get_context()
            bound = self._sig.bind(*self._args, **kwargs)
            args_dict = {
                k: v for k, v in bound.arguments.items()
                if self._sig.parameters[k].annotation is not RequestEvent
            }
            ctx.add_refresh(self._func_name, args_dict, result)
        except RuntimeError:
            import warnings
            warnings.warn(
                f"{self._func_name}.refresh() called outside command/form context. "
                "Result will not be included in response metadata.",
                stacklevel=2
            )
        
        return result
    
    async def set(self, data: T) -> None:
        from fluidkit.context import get_context
        from fluidkit.types import RequestEvent
        
        bound = self._sig.bind(*self._args, **self._kwargs)
        args_dict = {
            k: v for k, v in bound.arguments.items()
            if self._sig.parameters[k].annotation is not RequestEvent
        }
        
        try:
            ctx = get_context()
            ctx.add_set(self._func_name, args_dict, data)
        except RuntimeError:
            import warnings
            warnings.warn(
                f"{self._func_name}.set() called outside command/form context. "
                "Result will not be included in response metadata.",
                stacklevel=2
            )

