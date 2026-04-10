import asyncio
import logging
import inspect
import concurrent.futures
from functools import update_wrapper
from collections.abc import Awaitable, Callable
from typing import overload, ParamSpec, TypeVar, Dict

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from fluidkit.context import (
    set_context,
    reset_context,
    FluidKitContext,
    reset_request_event,
)
from fluidkit.exceptions import HTTPError, Redirect
from fluidkit.models import (
    DecoratorType,
    FluidKitEnvelope,
    create_error_response,
    create_query_response,
    create_command_response,
    create_redirect_response,
    create_batch_query_response,
)
from fluidkit.registry import fluidkit_registry
from fluidkit.utilities import (
    extract_metadata,
    parse_request_data,
    build_json_response,
    setup_request_context,
    inject_request_if_needed,
)
from fluidkit.types import RemoteProxy, AsyncRemoteProxy, FileUpload, RequestEvent, HookEvent


T = TypeVar("T")
P = ParamSpec("P")
logger = logging.getLogger(__name__)


# =================================================================================
# Internal helpers
# =================================================================================


def _error_response(e: Exception, status: int = 500, message: str | None = None) -> JSONResponse:
    if status == 500:
        logger.exception(e)
    content = create_error_response(
        e=e if status == 500 else None,
        message=message,
        dev=fluidkit_registry.dev,
    )
    return JSONResponse(
        status_code=status,
        content=content.model_dump(by_alias=True, exclude_none=True),
    )


def _http_error_response(e: HTTPError) -> JSONResponse:
    return JSONResponse(
        status_code=e.status,
        content=create_error_response(message=e.message, dev=fluidkit_registry.dev).model_dump(
            by_alias=True, exclude_none=True
        ),
    )


def _validation_error_response(e: ValidationError, func_name: str, module: str) -> JSONResponse:
    errors = e.errors()
    if errors:
        first = errors[0]
        loc = first.get("loc", ())
        field = loc[-1] if loc else "input"
        msg = first.get("msg", "invalid value")
    else:
        field = "input"
        msg = "invalid value"
    message = f"Validation error in {module}.{func_name}(): {field} - {msg}"
    if fluidkit_registry.dev:
        logger.warning(message)
    return _error_response(e, status=400, message=message)


def _type_error_response(e: TypeError, func_name: str, module: str) -> JSONResponse:
    message = f"Invalid arguments for {module}.{func_name}(): {e}"
    if fluidkit_registry.dev:
        logger.warning(message)
    return _error_response(e, status=400, message=message)


def _wrap_and_register(func, metadata, sig):
    """Create the RemoteProxy or AsyncRemoteProxy wrapper. Shared by all decorators."""
    proxy_cls = AsyncRemoteProxy if inspect.iscoroutinefunction(func) else RemoteProxy
    def wrapper(*args, **kwargs):
        return proxy_cls(
            sig=sig, args=args,
            kwargs=kwargs, executor=func,
            func_name=f"{metadata.module}#{metadata.name}",
        )
    update_wrapper(wrapper, func)
    wrapper.__fluidkit__ = metadata.decorator_type
    return wrapper


def _make_remote(
    func: Callable,
    decorator_type: DecoratorType,
    *,
    allow_set_cookies: bool = False,
    use_context: bool = False,
    use_form_parsing: bool = False,
    redirect_behavior: str = "none",
    catch_value_error: bool = False,
):
    """
    Core factory — builds the FastAPI handler, registers the route,
    and returns (wrapper, metadata).

    Behavior matrix:
      query:     context=no,  cookies=ro, body=json, redirect=none,    valuerror=no
      command:   context=yes, cookies=rw, body=json, redirect=warn,    valuerror=no
      form:      context=yes, cookies=rw, body=form, redirect=respond, valuerror=yes
      prerender: context=no,  cookies=ro, body=json, redirect=none,    valuerror=no
    """
    from fluidkit.hooks import hooks

    metadata, request_param_name, sig = extract_metadata(func=func, decorator_type=decorator_type)

    _validators: Dict[str, TypeAdapter] = {}
    for param_name, param in sig.parameters.items():
        if param.annotation is inspect.Parameter.empty:
            continue
        if param.annotation is RequestEvent:
            continue
        if param.annotation is FileUpload:
            continue
        _validators[param_name] = TypeAdapter(param.annotation)

    _valid_params = frozenset(sig.parameters.keys())
    _is_coroutine = inspect.iscoroutinefunction(func)

    async def fastapi_handler(request: Request):
        request_event, cookies, request_event_token = setup_request_context(
            request=request, allow_set_cookies=allow_set_cookies
        )
        ctx = None
        fk_locals = {}
        ctx_token = None
        hook_context = None

        try:
            if use_form_parsing:
                body, hook_context = await parse_request_data(request, sig)
            else:
                raw = await request.json()
                envelope = FluidKitEnvelope.model_validate(raw)
                body, hook_context = envelope.fk_payload, envelope.fk_context
            
            if hook_context is not None:
                request_event._populate_request(hook_context)

            async def call_next():
                nonlocal ctx, ctx_token
                if use_context:
                    ctx = FluidKitContext()
                    ctx_token = set_context(ctx)

                kwargs = inject_request_if_needed(
                    sig=sig, args=(), kwargs=dict(body),
                    request_event=request_event,
                    request_param_name=request_param_name,
                )
                for param_name, adapter in _validators.items():
                    if param_name in kwargs:
                        kwargs[param_name] = adapter.validate_python(kwargs[param_name])
                kwargs = {k: v for k, v in kwargs.items() if k in _valid_params}

                if _is_coroutine:
                    return await func(**kwargs)
                return await asyncio.to_thread(func, **kwargs)

            if hook_context is not None and hooks._handle_hooks:
                hook_event = HookEvent(
                    context=hook_context,
                    cookies=cookies.fork(allow_set=True),
                    locals=request_event.locals,
                )
                result, fk_locals = await hooks.run_handle_chain(hook_event, call_next)
            else:
                result = await call_next()
                fk_locals = request_event.locals.serializable()

            if use_context:
                response_data = create_command_response(result, ctx.mutations, cookies.serialize(), fk_locals)
            else:
                response_data = create_query_response(result, fk_locals)

            return build_json_response(response_data)

        except Redirect as e:
            if redirect_behavior == "respond":
                response_data = create_redirect_response(e.status, e.location, cookies.serialize(), fk_locals)
                return build_json_response(response_data)
            if redirect_behavior == "warn":
                logger.warning(
                    "@command '%s' raised Redirect — redirects are not supported in commands "
                    "and will be ignored on the client. Use @form if redirect behavior is needed.",
                    func.__name__,
                )
                response_data = create_command_response(None, ctx.mutations if ctx else [], cookies.serialize(), fk_locals)
                return build_json_response(response_data)
            return _error_response(e)

        except HTTPError as e:
            return _http_error_response(e)

        except ValidationError as e:
            custom = await hooks._invoke_handle_validation_error(e.errors(), request_event)
            if custom is not None:
                return JSONResponse(status_code=400, content=custom)
            return _validation_error_response(e, func.__name__, metadata.module)
        
        except TypeError as e:
            message = f"Invalid arguments for {metadata.module}.{func.__name__}(): {e}"
            custom = await hooks._invoke_handle_error(e, request_event, 400, message)
            if custom is not None:
                return JSONResponse(status_code=400, content=custom)
            return _type_error_response(e, func.__name__, metadata.module)

        except ValueError as e:
            if catch_value_error:
                message = f"Invalid data in {func.__name__}(): {e}"
                custom = await hooks._invoke_handle_error(e, request_event, 400, message)
                if custom is not None:
                    return JSONResponse(status_code=400, content=custom)
                return _error_response(e, status=400, message=message)
            custom = await hooks._invoke_handle_error(e, request_event, 500, str(e))
            if custom is not None:
                return JSONResponse(status_code=500, content=custom)
            return _error_response(e)

        except Exception as e:
            custom = await hooks._invoke_handle_error(e, request_event, 500, str(e))
            if custom is not None:
                return JSONResponse(status_code=500, content=custom)
            return _error_response(e)

        finally:
            if ctx_token is not None:
                reset_context(ctx_token)
            reset_request_event(request_event_token)

    fastapi_handler.__name__ = func.__name__
    fastapi_handler.__doc__ = func.__doc__

    fluidkit_registry.register(metadata, fastapi_handler)

    wrapper = _wrap_and_register(func, metadata, sig)
    return wrapper, metadata


# =================================================================================
# Public decorators
# =================================================================================


class _Query:
    """
    Create a remote query function for reading data.

    Queries are read-only operations that can be called from SvelteKit components.
    They support caching and can be refreshed on demand.

    Example:
    ```python
        @query
        async def get_user(user_id: str) -> User:
            return await db.get_user(user_id)
    ```
    """
    @overload
    def __call__(cls, func: Callable[P, Awaitable[T]]) -> Callable[P, AsyncRemoteProxy[T]]: ...

    @overload
    def __call__(cls, func: Callable[P, T]) -> Callable[P, RemoteProxy[T]]: ...

    def __call__(cls, func):
        wrapper, _ = _make_remote(func, DecoratorType.QUERY)
        return wrapper
    
    @staticmethod
    @overload
    def batch(func: Callable[P, Awaitable[T]]) -> Callable[P, AsyncRemoteProxy[T]]: ...

    @staticmethod
    @overload
    def batch(func: Callable[P, T]) -> Callable[P, RemoteProxy[T]]: ...

    @staticmethod
    def batch(func):
        """
        Create a batched remote query function.

        Batches concurrent calls into a single request. The decorated function
        receives a list of all arguments and must return a callable that
        resolves each individual call.

        Example:
        ```python
            @query.batch
            async def get_weather(city_ids: list[str]):
                weather = await db.get_bulk(city_ids)
                lookup = {w.city_id: w for w in weather}
                return lambda city_id: lookup.get(city_id)
        ```
        """
        from fluidkit.hooks import hooks

        metadata, request_param_name, sig = extract_metadata(func=func, decorator_type=DecoratorType.QUERY_BATCH)

        _is_coroutine = inspect.iscoroutinefunction(func)

        async def fastapi_handler(request: Request):
            request_event, cookies, request_event_token = setup_request_context(
                request=request, allow_set_cookies=False
            )
            fk_locals = {}
            hook_context = None

            try:
                raw = await request.json()
                envelope = FluidKitEnvelope.model_validate(raw)
                body = envelope.fk_payload
                hook_context = envelope.fk_context
                if hook_context is not None:
                    request_event._populate_request(hook_context)
                args_list = body.get("args", [])

                async def call_next():
                    if _is_coroutine:
                        resolver = await func(args_list)
                    else:
                        resolver = await asyncio.to_thread(func, args_list)
                    if not callable(resolver):
                        param_name = metadata.parameters[0].name if metadata.parameters else "items"
                        raise TypeError(
                            f"@query.batch '{func.__name__}' must return a callable, "
                            f"got {type(resolver).__name__}. Expected pattern:\n\n"
                            f"  @query.batch\n"
                            f"  async def {func.__name__}({param_name}: list[...]):\n"
                            f"      ...\n"
                            f"      return lambda item: result_for(item)\n"
                        )
                    return [resolver(arg, i) for i, arg in enumerate(args_list)]

                if hook_context is not None and hooks._handle_hooks:
                    hook_event = HookEvent(
                        context=hook_context,
                        cookies=cookies.fork(allow_set=True),
                        locals=request_event.locals,
                    )
                    result, fk_locals = await hooks.run_handle_chain(hook_event, call_next)
                else:
                    result = await call_next()
                    fk_locals = request_event.locals.serializable()

                response_data = create_batch_query_response(result, fk_locals)
                return build_json_response(response_data)

            except HTTPError as e:
                return _http_error_response(e)

            except Exception as e:
                custom = await hooks._invoke_handle_error(e, request_event, 500, str(e))
                if custom is not None:
                    return JSONResponse(status_code=500, content=custom)
                return _error_response(e)

            finally:
                reset_request_event(request_event_token)

        fastapi_handler.__name__ = func.__name__
        fastapi_handler.__doc__ = func.__doc__

        if _is_coroutine:
            async def _single_executor(**kwargs):
                single_arg = next(iter(kwargs.values()))
                resolver = await func([single_arg])
                return resolver(single_arg, 0)
        else:
            def _single_executor(**kwargs):
                single_arg = next(iter(kwargs.values()))
                resolver = func([single_arg])
                return resolver(single_arg, 0)

        update_wrapper(_single_executor, func)

        fluidkit_registry.register(metadata, fastapi_handler)
        return _wrap_and_register(_single_executor, metadata, sig)


class _Command:
    """
    Create a remote command function for mutations.

    Commands perform write operations and can update query caches in a single
    request using .refresh() or .set() within the function body.

    Example:
    ```python
        @command
        async def add_like(post_id: str) -> None:
            await db.increment_likes(post_id)
            await get_posts().refresh()
    ```
    """
    @overload
    def __call__(cls, func: Callable[P, Awaitable[T]]) -> Callable[P, AsyncRemoteProxy[T]]: ...

    @overload
    def __call__(cls, func: Callable[P, T]) -> Callable[P, RemoteProxy[T]]: ...

    def __call__(cls, func):
        wrapper, _ = _make_remote(
            func, DecoratorType.COMMAND,
            allow_set_cookies=True, use_context=True, redirect_behavior="warn",
        )
        return wrapper


class _Form:
    """
    Create a remote form handler with progressive enhancement.

    Forms work without JavaScript and support file uploads, nested
    Pydantic models, and complex types natively.

    Example:
    ```python
        @form
        async def create_post(title: str, photo: FileUpload) -> None:
            await storage.save(photo.filename, await photo.read())
            raise Redirect(303, '/posts')
    ```
    """
    @overload
    def __call__(cls, func: Callable[P, Awaitable[T]]) -> Callable[P, AsyncRemoteProxy[T]]: ...

    @overload
    def __call__(cls, func: Callable[P, T]) -> Callable[P, RemoteProxy[T]]: ...

    def __call__(cls, func):
        wrapper, _ = _make_remote(
            func, DecoratorType.FORM,
            allow_set_cookies=True, use_context=True,
            use_form_parsing=True, redirect_behavior="respond", catch_value_error=True,
        )
        return wrapper


class _Prerender:
    """
    Create a remote function that prerenders data at build time.

    Args:
        inputs: List of input values or callable returning list.
        dynamic: If True, allows runtime calls with non-prerendered arguments.

    Example:
    ```python
        @prerender
        async def get_posts() -> list[Post]:
            return await db.get_posts()

        @prerender(inputs=['post-1', 'post-2'], dynamic=True)
        async def get_post(slug: str) -> Post:
            return await db.get_post(slug)
    ```
    """
    @overload
    def __call__(cls, func: Callable[P, Awaitable[T]]) -> Callable[P, AsyncRemoteProxy[T]]: ...

    @overload
    def __call__(cls, func: Callable[P, T]) -> Callable[P, RemoteProxy[T]]: ...

    def __call__(cls, func=None, *, inputs=None, dynamic=False):
        def decorator(fn):
            wrapper, metadata = _make_remote(fn, decorator_type=DecoratorType.PRERENDER)
            metadata.prerender_dynamic = dynamic

            if callable(inputs):
                result = inputs()
                if inspect.isawaitable(result):
                    try:
                        asyncio.get_running_loop()
                        with concurrent.futures.ThreadPoolExecutor(1) as pool:
                            metadata.prerender_inputs = pool.submit(asyncio.run, result).result()
                    except RuntimeError:
                        metadata.prerender_inputs = asyncio.run(result)
                else:
                    metadata.prerender_inputs = result
            else:
                metadata.prerender_inputs = inputs

            return wrapper

        if func is None:
            return decorator
        return decorator(func)


form = _Form()
query = _Query()
command = _Command()
prerender = _Prerender()
